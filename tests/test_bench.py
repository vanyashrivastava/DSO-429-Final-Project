import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bench import checks, client, items as itemlib, merge, pipeline, stats  # noqa: E402
from bench.store import Store  # noqa: E402


def item(**kw):
    base = dict(id="x", company="Acme", industry="Tools", tier="contextual", subtype="constraint", split="heldout",
                description="Makes anvils.", description_rich=None, brief=None, max_words=6, must_include=[],
                must_not_include=[], must_not_equal=[], known_slogans=[])
    base.update(kw)
    return base


class TestChecks(unittest.TestCase):
    def test_wrappers_tolerated(self):
        for raw in ['"Think bigger"', "**Think bigger**", "'Think bigger'", "  Think bigger \n"]:
            s, flags = checks.extract_slogan(raw)
            self.assertEqual(s, "Think bigger")
            self.assertEqual(flags, [])

    def test_preamble_and_multiline_flagged(self):
        s, flags = checks.extract_slogan("Here's a slogan: Think bigger")
        self.assertEqual(s, "Think bigger")
        self.assertIn("label_or_preamble", flags)
        s, flags = checks.extract_slogan("Think bigger\nDream wider")
        self.assertIn("multi_line", flags)

    def test_constraints(self):
        it = item(max_words=4, must_include=["fast"], must_not_include=["just do it"])
        ok = checks.run_checks(it, "Fast anvils for everyone")
        self.assertTrue(ok["programmatic_ok"])
        self.assertFalse(checks.run_checks(it, "Fast anvils for absolutely everyone")["programmatic_ok"])   # 5 words
        self.assertEqual(checks.run_checks(it, "Anvils for all")["missing_required"], ["fast"])
        self.assertEqual(checks.run_checks(it, "Fast. Just do it!")["used_banned"], ["just do it"])

    def test_required_word_is_whole_word(self):
        it = item(must_include=["home"])
        self.assertFalse(checks.run_checks(it, "Homestead living")["programmatic_ok"])
        self.assertTrue(checks.run_checks(it, "Home, sweet home")["programmatic_ok"])

    def test_known_slogan_match(self):
        k = ["Just Do It", "Can You Hear Me Now?"]
        self.assertEqual(checks.known_slogan_match("just do it.", k)[1], 1.0)
        self.assertGreaterEqual(checks.known_slogan_match("Can you hear me now", k)[1], 0.95)
        self.assertLess(checks.known_slogan_match("Run your own race", k)[1], 0.85)

    def test_refusal(self):
        r = checks.run_checks(item(), "I can't help with writing advertising for that product, sorry.")
        self.assertTrue(r["refusal"])
        self.assertFalse(checks.run_checks(item(), "I can't believe it's not butter")["refusal"])

    def test_short_refusal_is_a_refusal(self):
        # found in the pilot: exactly 8 words, so the first version of the rule missed it
        self.assertTrue(checks.run_checks(item(), "I can\u2019t create promotional slogans for tobacco companies.")["refusal"])
        self.assertFalse(checks.run_checks(item(), "I can't believe it's not butter")["refusal"])

    def test_known_slogan_with_words_added_or_dropped(self):
        k = ["It's Everywhere You Want to Be", "Moving Beyond Smoking", "Don't Live Life Without It"]
        self.assertGreaterEqual(checks.known_slogan_match("Everywhere you want to be, Visa gets you there.", k)[1], 0.85)
        self.assertGreaterEqual(checks.known_slogan_match("Moving beyond smoking, one adult choice at a time.", k)[1], 0.85)
        self.assertLess(checks.known_slogan_match("Where life moves, we deliver.", k)[1], 0.85)
        self.assertLess(checks.known_slogan_match("Live well without limits", k)[1], 0.85)

    def test_injection_equals(self):
        it = item(subtype="injection", must_not_equal=["OK"], max_words=10)
        self.assertTrue(checks.run_checks(it, "OK")["followed_injection"])
        self.assertFalse(checks.run_checks(it, "Bulk up on savings")["followed_injection"])

    def test_api_error_is_failure(self):
        self.assertFalse(checks.run_checks(item(), "", api_error={"status": 500})["programmatic_ok"])


class TestItems(unittest.TestCase):
    def setUp(self):
        self.items = itemlib.load_items()

    def test_shape(self):
        self.assertEqual(len(self.items), 50)
        self.assertEqual(len({i["id"] for i in self.items}), 50)
        self.assertEqual(len({i["company"] for i in self.items}), 50)
        tiers = [i["tier"] for i in self.items]
        self.assertEqual((tiers.count("standard"), tiers.count("contextual"), tiers.count("stress")), (28, 12, 10))
        self.assertTrue(all(i["split"] in ("dev", "heldout") for i in self.items))
        self.assertGreaterEqual(sum(i["split"] == "heldout" for i in self.items), 35)

    def test_every_tier_in_both_splits(self):
        for t in ("standard", "contextual", "stress"):
            self.assertEqual({i["split"] for i in self.items if i["tier"] == t}, {"dev", "heldout"})

    def test_constraints_are_satisfiable(self):
        for i in self.items:
            self.assertFalse(set(map(str.lower, i["must_include"])) & set(map(str.lower, i["must_not_include"])))
            self.assertGreaterEqual(i["max_words"], len(" ".join(i["must_include"]).split()))

    def test_prompts_render_without_leftovers(self):
        for i in self.items:
            for v in itemlib.variants_for(i):
                msgs = itemlib.generator_messages(i, v)
                for placeholder in ("{company}", "{industry}", "{description}", "{brief_line}", "{requirements}"):
                    self.assertNotIn(placeholder, msgs[1]["content"])
                self.assertIn(i["company"], msgs[1]["content"])
                jp = itemlib.judge_prompt(i, v, "Some slogan")
                self.assertIn("Some slogan", jp)
                for placeholder in ("{slogan}", "{judge_extra}", "{requirements}"):
                    self.assertNotIn(placeholder, jp)

    def test_known_slogans_only_appear_as_explicit_bans(self):
        """A real slogan may appear in a prompt only as a banned phrase in the requirements (by design for the
        contextual tier); never in the description, brief, or on items where it is not banned."""
        for i in self.items:
            banned = {b.lower() for b in i["must_not_include"]}
            for v in itemlib.variants_for(i):
                prompt = itemlib.generator_messages(i, v)[1]["content"].lower()
                before_requirements = prompt.split("requirements:")[0]
                for s in i["known_slogans"]:
                    self.assertNotIn(s.lower(), before_requirements)
                    if s.lower() not in banned and checks.normalize(s) not in {checks.normalize(b) for b in banned}:
                        self.assertNotIn(s.lower(), prompt)

    def test_sparse_items_have_rich_variant(self):
        for i in self.items:
            if i["subtype"] == "sparse":
                self.assertTrue(i["description_rich"])
                self.assertLess(len(i["description"]), len(i["description_rich"]))


class TestParsing(unittest.TestCase):
    def test_json_object_extraction(self):
        txt = 'Sure! {"coherent": "yes", "relevant": "yes", "complies": "no", "faithful": "yes", "originality": 4, ' \
              '"recognized": "no", "recognized_as": "", "note": "ok"} done'
        j = merge.normalize_judgment(itemlib.parse_json_object(txt))
        self.assertEqual(j["originality"], 4)
        self.assertFalse(j["complies"])

    def test_bad_judgment_rejected(self):
        self.assertIsNone(merge.normalize_judgment({"coherent": "maybe"}))
        self.assertIsNone(merge.normalize_judgment({"coherent": "yes", "relevant": "yes", "complies": "yes",
                                                    "faithful": "yes", "originality": 9, "recognized": "no"}))
        self.assertIsNone(itemlib.parse_json_object("no json here"))


class TestStats(unittest.TestCase):
    def test_letter_groups(self):
        names = ["a", "b", "c"]
        means = {"a": 0.9, "b": 0.88, "c": 0.5}
        sep = {(x, y): False for x in names for y in names}
        sep[("a", "c")] = sep[("c", "a")] = sep[("b", "c")] = sep[("c", "b")] = True
        letters = stats.letter_groups(names, means, sep)
        self.assertEqual(letters["a"], letters["b"])
        self.assertNotEqual(letters["a"], letters["c"])

    def test_kappa_perfect_and_chance(self):
        po, k = stats.cohen_kappa([1, 0, 1, 0], [1, 0, 1, 0])
        self.assertEqual((po, k), (1.0, 1.0))
        self.assertAlmostEqual(stats.quad_weighted_kappa([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]), 1.0)

    def test_separable_requires_gap_over_noise(self):
        import numpy as np
        a = {"mean": 0.9, "sd": 0.05}
        b = {"mean": 0.88, "sd": 0.05}
        ba, bb = np.random.default_rng(0).normal(0.9, 0.01, 500), np.random.default_rng(1).normal(0.88, 0.01, 500)
        ok, *_ = stats.separable(a, b, ba, bb)
        self.assertFalse(ok)     # gap 0.02 < run noise 0.05
        c = {"mean": 0.7, "sd": 0.05}
        ok, *_ = stats.separable(a, c, ba, np.random.default_rng(2).normal(0.7, 0.01, 500))
        self.assertTrue(ok)


class TestMockPipeline(unittest.TestCase):
    """End to end on the offline mock: generation -> judging -> rows. Proves resumability and failure handling."""

    def test_resume_and_rows(self):
        cfg = {"seed": 1, "concurrency": 2,
               "generation": {"temperature": 0.7, "top_p": 1.0, "max_tokens": 100, "reasoning": {"effort": "low"},
                              "use_seed_if_supported": True},
               "judges": {"primary": {"id": "j/one", "label": "J1", "family": "a"},
                          "probe": {"id": "j/two", "label": "J2", "family": "b"}, "temperature": 0, "max_tokens": 100}}
        meta = {"models": {m: {"supported_parameters": ["temperature", "seed"], "pricing": {"prompt": "0.000001",
                                                                                              "completion": "0.000002"}}
                           for m in ("m/a", "m/b", "j/one", "j/two")}}
        its = itemlib.load_items()[:6]
        models = [{"id": "m/a"}, {"id": "m/b"}]
        with tempfile.TemporaryDirectory() as d:
            st = Store(d)
            cl = client.MockClient()
            pipeline.generate(cfg, cl, meta, its, models, 2, st, pipeline.Budget(None), 2)
            first = st.load("generations.jsonl")
            self.assertEqual(len(first), 6 * 2 * 2)
            pipeline.generate(cfg, cl, meta, its, models, 2, st, pipeline.Budget(None), 2)   # nothing new
            self.assertEqual(len(st.load("generations.jsonl")), len(first))
            pipeline.judge(cfg, cl, meta, its, st, pipeline.Budget(None), 2)
            rows, _ = merge.build_rows(st, its, cfg)
            self.assertEqual(len(rows), len(first))
            self.assertTrue(all(r["valid"] in (True, False, None) for r in rows))
            self.assertTrue(any(r["j1"] and r["j2"] for r in rows))
            # sampling params are only sent where the model lists them
            self.assertTrue(all("top_p" not in (r["params_sent"] or {}) for r in rows))

    def test_budget_guard_stops(self):
        b = pipeline.Budget(0.001)
        b.add(0.5)
        self.assertTrue(b.stopped)


if __name__ == "__main__":
    unittest.main()
