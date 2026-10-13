"""Tables and figures from the raw records. Needs numpy + matplotlib (everything else is stdlib)."""
import csv
import json
import os
import random

import warnings

import numpy as np

warnings.filterwarnings("ignore", message="Mean of empty slice")

from . import checks, merge, stats

PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]   # validated: see README (dataviz palette slots 1-5)
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#dcdbd6", "#fcfcfb"
TIER_GREYS = {"standard": "#c9c8c2", "contextual": "#8f8e87", "stress": "#3d3d3a"}

# ---------------------------------------------------------------- metric definitions (num, den) per output


def _judged(r, f):
    j = r["j1"]
    if not merge.needs_judging(r["chk"]):
        return (0.0, 1.0)             # no output to judge = the requirement was not met
    if j is None:
        return (0.0, 0.0)             # judge reply missing: excluded, and counted in the coverage note
    return (float(j[f]), 1.0)


def m_valid(r, it):
    return (0.0, 0.0) if r["valid"] is None else (float(r["valid"]), 1.0)


def m_valid_j2(r, it):
    return (0.0, 0.0) if r["valid_j2"] is None else (float(r["valid_j2"]), 1.0)


def m_originality(r, it):
    return (float(r["j1"]["originality"]), 1.0) if r["valid"] and r["j1"] else (0.0, 0.0)


def m_originality_nomem(r, it):
    """Supplementary only: originality over valid outputs that do NOT reproduce a known real slogan."""
    if r["valid"] and r["j1"] and not r["chk"]["known_match"]:
        return (float(r["j1"]["originality"]), 1.0)
    return (0.0, 0.0)


def m_generic(r, it):
    return (float(r["j1"]["originality"] <= 2), 1.0) if r["valid"] and r["j1"] else (0.0, 0.0)


def m_compliance(r, it):
    c = merge.compliant(r)
    return (0.0, 0.0) if c is None else (float(c), 1.0)


def m_contam_prog(r, it):
    if not it["known_slogans"] or r["chk"]["empty"] or r["chk"]["api_error"]:
        return (0.0, 0.0)
    return (float(r["chk"]["known_match"] is not None), 1.0)


def m_contam_judge(r, it):
    return (float(r["j1"]["recognized"]), 1.0) if r["j1"] else (0.0, 0.0)


METRICS = {
    "valid": m_valid,
    "coherent": lambda r, it: _judged(r, "coherent"),
    "relevant": lambda r, it: _judged(r, "relevant"),
    "complies": lambda r, it: _judged(r, "complies"),
    "faithful": lambda r, it: _judged(r, "faithful"),
    "programmatic_ok": lambda r, it: (float(r["chk"]["programmatic_ok"]), 1.0),
    "refusal": lambda r, it: (float(r["chk"]["refusal"]), 1.0),
    "api_error": lambda r, it: (float(r["chk"]["api_error"]), 1.0),
    "format_violation": lambda r, it: (float(not r["chk"]["format_ok"] and not r["chk"]["empty"]
                                             and not r["chk"]["api_error"]), 1.0),
    "originality": m_originality,
    "originality_nomem": m_originality_nomem,
    "generic": m_generic,
    "compliance": m_compliance,
    "contam_prog": m_contam_prog,
    "contam_judge": m_contam_judge,
}

FAIL_ORDER = ["api_error", "refusal", "followed_injection", "format_violation", "word_limit", "missing_required",
              "used_banned", "incoherent_or_irrelevant", "noncompliant", "unfaithful"]
FAIL_CLASS = {"api_error": "infrastructure", "refusal": "model declined", "followed_injection": "model wrong",
              "format_violation": "model wrong", "word_limit": "model wrong", "missing_required": "model wrong",
              "used_banned": "model wrong", "incoherent_or_irrelevant": "model wrong",
              "noncompliant": "model wrong", "unfaithful": "see counterfactual (T8)"}


def failure_mode(r):
    c = r["chk"]
    if c["api_error"]:
        return "api_error"
    if c["refusal"] or c["empty"]:
        return "refusal"
    if c["followed_injection"]:
        return "followed_injection"
    if not c["format_ok"]:
        return "format_violation"
    if not c["words_ok"]:
        return "word_limit"
    if c["missing_required"]:
        return "missing_required"
    if c["used_banned"]:
        return "used_banned"
    j = r["j1"]
    if j is None:
        return None
    if not (j["coherent"] and j["relevant"]):
        return "incoherent_or_irrelevant"
    if not j["complies"]:
        return "noncompliant"
    if not j["faithful"]:
        return "unfaithful"
    return None


# ---------------------------------------------------------------- the analysis object

class Analysis:
    def __init__(self, cfg, items, store, out_dir, meta, label="final"):
        self.cfg, self.items, self.out, self.meta, self.label = cfg, items, out_dir, meta, label
        self.item = {i["id"]: i for i in items}
        self.rows, self.ideas = merge.build_rows(store, items, cfg)
        present = {r["item_id"] for r in self.rows}
        self.items = [i for i in items if i["id"] in present]     # a partial run is analysed on what exists
        self.item = {i["id"]: i for i in self.items}
        self.store = store
        self.models = [m["id"] for m in cfg["models"]]
        self.names = {m["id"]: m["label"] for m in cfg["models"]}
        self.color = {m["id"]: PALETTE[m["color_slot"] - 1] for m in cfg["models"]}
        self.runs = sorted({r["run"] for r in self.rows}) or [1]
        self.index = {(r["model"], r["item_id"], r["variant"], r["run"]): r for r in self.rows}
        self.tdir = os.path.join(out_dir, "tables")
        self.fdir = os.path.join(out_dir, "figures")
        os.makedirs(self.tdir, exist_ok=True)
        os.makedirs(self.fdir, exist_ok=True)
        B = cfg["bootstrap"]["B"]
        self.B, self.seed = B, cfg["bootstrap"]["seed"]
        self.emb = {k: np.array(v["vector"], float) for k, v in store.load("embeddings.jsonl", key="hash").items()}
        self._boot_cache = {}

    # -- selection
    def ids(self, split=None, tier=None, subtype=None):
        return sorted(i["id"] for i in self.items
                      if (split is None or i["split"] == split) and (tier is None or i["tier"] == tier)
                      and (subtype is None or i["subtype"] == subtype))

    def arrays(self, model, item_ids, fn, variant="base"):
        num = np.zeros((len(item_ids), len(self.runs)))
        den = np.zeros_like(num)
        for a, iid in enumerate(item_ids):
            for b, run in enumerate(self.runs):
                r = self.index.get((model, iid, variant, run))
                if r is not None:
                    num[a, b], den[a, b] = fn(r, self.item[iid])
        return num, den

    def metric(self, model, item_ids, name, variant="base"):
        num, den = self.arrays(model, item_ids, METRICS[name] if isinstance(name, str) else name, variant)
        s = stats.summarize(num, den)
        idx = self._idx(len(item_ids))
        boot = stats.boot_means(num, den, idx) if len(item_ids) else np.array([np.nan])
        s["ci"] = stats.ci(boot) if len(item_ids) else (np.nan, np.nan)
        s["boot"] = boot
        s["den"] = float(den.sum())
        return s

    def _idx(self, n):
        if n not in self._boot_cache:
            self._boot_cache[n] = stats.boot_indices(n, self.B, self.seed)
        return self._boot_cache[n]

    # -- output helpers
    def table(self, name, header, rows, note=""):
        with open(os.path.join(self.tdir, name + ".csv"), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)
        lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
        for r in rows:
            lines.append("| " + " | ".join(str(c) for c in r) + " |")
        with open(os.path.join(self.tdir, name + ".md"), "w") as fh:
            fh.write("\n".join(lines) + "\n" + ("\n" + note + "\n" if note else ""))
        return "\n".join(lines)

    @staticmethod
    def pm(s, scale=100.0, dec=1):
        if s["mean"] != s["mean"]:
            return "n/a"
        f = "%." + str(dec) + "f"
        return (f + " ± " + f + " [" + f + "–" + f + "]") % (s["mean"] * scale, s["sd"] * scale, s["min"] * scale, s["max"] * scale)

    @staticmethod
    def cis(s, scale=100.0, dec=1):
        f = "%." + str(dec) + "f"
        return (f + "–" + f) % (s["ci"][0] * scale, s["ci"][1] * scale)

    def L(self, m):
        return self.names[m]

    # -- tables
    def run_all(self):
        held = self.ids(split="heldout")
        every = self.ids()
        cov = self.coverage(held)
        out = {}
        out["T6"] = self.t6_pairwise(held)
        out["T1"] = self.t1_headline(held, cov)
        out["T2"] = self.t2_criteria(held)
        out["T3"] = self.t3_tiers(held)
        out["T3b"] = self.t3b_stress(every)
        out["T4"] = self.t4_cost_latency()
        out["T5"] = self.t5_diversity(held)
        out["T7"] = self.t7_failures(held)
        out["T8"] = self.t8_counterfactual()
        out["T9"] = self.t9_judges(held)
        out["T10"] = self.t10_all(every)
        self.disputes(held)
        self.sample_outputs()
        self.figures(held)
        return out

    def coverage(self, item_ids):
        exp = len(item_ids) * len(self.runs)
        res = {}
        for m in self.models:
            got = [self.index.get((m, i, "base", r)) for i in item_ids for r in self.runs]
            have = [g for g in got if g is not None]
            res[m] = {"expected": exp, "have": len(have),
                      "unjudged": sum(1 for g in have if g["valid"] is None)}
        return res

    def t1_headline(self, held, cov):
        th = self.cfg["thresholds"]
        ctx = self.ids(split="heldout", tier="contextual")
        rows = []
        for m in self.models:
            v = self.metric(m, held, "valid")
            o = self.metric(m, held, "originality")
            c = self.metric(m, ctx, "compliance")
            checks_ = [("valid", v["mean"] >= th["valid_rate"], v["mean"] - th["valid_rate"], 100, "pp"),
                       ("originality", o["mean"] >= th["originality_mean"], o["mean"] - th["originality_mean"], 1, "pts"),
                       ("compliance", c["mean"] >= th["contextual_compliance"], c["mean"] - th["contextual_compliance"], 100, "pp")]
            verdict = "; ".join("%s %s (%+.1f %s)" % (n, "PASS" if ok else "FAIL", d * sc, u) for n, ok, d, sc, u in checks_)
            clears = "YES" if all(ok for _, ok, *_ in checks_) else "no"
            lt = self.letters
            rank = " / ".join(lt[k][m] or "-" for k in ("valid", "originality", "compliance"))
            rows.append([self.L(m), self.pm(v), self.cis(v), self.pm(o, 1, 2), self.cis(o, 1, 2), self.pm(c),
                         self.cis(c), rank, clears, verdict])
        note = ("Held-out split (%d items x %d runs per model; contextual tier = %d items). Cells: mean ± SD across runs "
                "[min–max of the %d run means]; CI = 95%% bootstrap over items. Line (frozen before data): valid >= %.0f%%, "
                "mean originality >= %.1f, contextual compliance >= %.0f%%. Models sharing a rank letter are NOT separable "
                "(gap within run-to-run noise or item-bootstrap CI spans zero): do not rank them. Coverage (outputs present/expected): %s."
                % (len(held), len(self.runs), len(ctx), len(self.runs), th["valid_rate"] * 100, th["originality_mean"],
                   th["contextual_compliance"] * 100,
                   "; ".join("%s %d/%d (%d unjudged)" % (self.L(m), c["have"], c["expected"], c["unjudged"])
                             for m, c in cov.items())))
        return self.table("T1_headline", ["Model", "Valid outputs, %", "95% CI", "Originality (1–5)", "95% CI",
                                          "Contextual compliance, %", "95% CI", "Rank group (valid / orig. / compl.)",
                                          "Clears the line?", "Per-criterion vs line"], rows, note)

    def t2_criteria(self, held):
        names = [("coherent", "Coherent"), ("relevant", "Relevant"), ("complies", "Complies w/ brief"),
                 ("faithful", "No unsupported claim"), ("programmatic_ok", "Passes programmatic checks"),
                 ("format_violation", "Format violation"), ("refusal", "Refusal"), ("api_error", "API error")]
        rows = []
        for m in self.models:
            rows.append([self.L(m)] + [self.pm(self.metric(m, held, k), 100, 1).split(" [")[0] for k, _ in names])
        return self.table("T2_criteria", ["Model"] + [n for _, n in names], rows,
                          "Held-out split, %, mean ± SD across runs. Each criterion is a separate result; they are never "
                          "combined into one score. Missing outputs count against the criterion (failures are kept)." )

    def t3_tiers(self, held):
        rows = []
        for m in self.models:
            row = [self.L(m)]
            for tier in ("standard", "contextual", "stress"):
                ids = self.ids(split="heldout", tier=tier)
                v, o = self.metric(m, ids, "valid"), self.metric(m, ids, "originality")
                row += ["%.1f ± %.1f" % (v["mean"] * 100, v["sd"] * 100), "%.2f" % o["mean"]]
            rows.append(row)
        n = {t: len(self.ids(split="heldout", tier=t)) for t in ("standard", "contextual", "stress")}
        hdr = ["Model"]
        for t in ("standard", "contextual", "stress"):
            hdr += ["%s valid %% (n=%d items)" % (t, n[t]), "%s originality" % t]
        return self.table("T3_by_tier", hdr, rows,
                          "Held-out split. Edge cases (stress, and contextual for constraint-following) are reported "
                          "separately from standard briefs. Mean ± SD across runs; item counts are small, so see the CIs "
                          "in the per-tier bootstrap before reading a gap as real.")

    def t3b_stress(self, every):
        rows = []
        subs = ["sparse", "sensitive", "long_context", "injection"]
        for m in self.models:
            row = [self.L(m)]
            for s in subs:
                ids = self.ids(subtype=s)
                v = self.metric(m, ids, "valid")
                row.append("%.0f%%" % (v["mean"] * 100))
            rows.append(row)
        n = {s: len(self.ids(subtype=s)) for s in subs}
        return self.table("T3b_stress_subtypes", ["Model"] + ["%s (n=%d items)" % (s, n[s]) for s in subs], rows,
                          "All 50-item splits pooled (stress subtype sample sizes are 2-3 items each: treat as anecdotes, "
                          "not estimates).")

    def row_cost(self, r):
        u = r["usage"] or {}
        if u.get("cost_usd") is not None:
            return float(u["cost_usd"])
        m = (self.meta["models"].get(r["model"]) or {}).get("pricing") or {}
        return ((u.get("prompt_tokens") or 0) * float(m.get("prompt", 0) or 0)
                + (u.get("completion_tokens") or 0) * float(m.get("completion", 0) or 0))

    def t4_cost_latency(self):
        rows, self.cost_total, self.lat_median = [], {}, {}
        for m in self.models:
            rs = [r for r in self.rows if r["model"] == m]
            ok = [r for r in rs if not r["error"] and r["latency_s"] is not None]
            lat = np.array([r["latency_s"] for r in ok]) if ok else np.array([np.nan])
            per_run = [np.median([r["latency_s"] for r in ok if r["run"] == run]) for run in self.runs
                       if any(r["run"] == run for r in ok)]
            cost = sum(self.row_cost(r) for r in rs)
            outt = [r["usage"].get("completion_tokens") for r in rs if r["usage"].get("completion_tokens") is not None]
            rea = [r["usage"].get("reasoning_tokens") or 0 for r in rs if r["usage"]]
            self.cost_total[m], self.lat_median[m] = cost, float(np.median(lat))
            rows.append([self.L(m), "%.2f" % np.median(lat), "%.2f–%.2f" % (min(per_run), max(per_run)) if per_run else "n/a",
                         "%.2f" % np.nanpercentile(lat, 95), "$%.3f" % cost, "$%.3f" % (cost / max(len(rs), 1) * 1000),
                         "%.0f" % (np.mean(outt) if outt else 0), "%.0f" % (np.mean(rea) if rea else 0), len(rs),
                         sum(1 for r in rs if r["error"])])
        jc = self.judge_costs()
        note = ("Generation cost = billed USD for every generation call in the full run (all items incl. rich-brief "
                "variants, all runs), from the provider's reported usage.cost. Latency = wall-clock seconds per successful "
                "call, measured client-side with %d concurrent requests. Evaluation cost (reported separately, not part of a "
                "model's cost): %s." % (self.cfg["concurrency"], "; ".join("%s $%.3f" % (k, v) for k, v in jc.items())))
        return self.table("T4_latency_cost", ["Model", "Median latency / call, s", "Range of per-run medians, s",
                                              "p95 latency, s", "Total generation cost, USD", "USD per 1,000 outputs",
                                              "Mean output tokens", "Mean reasoning tokens", "Calls", "Errors"], rows, note)

    def judge_costs(self):
        out = {}
        for rec in self.store.load("judgments.jsonl").values():
            out[rec["judge"] + " (judging)"] = out.get(rec["judge"] + " (judging)", 0.0) + (rec.get("cost_usd") or 0.0)
        ideas = sum((r.get("cost_usd") or 0.0) for r in self.ideas.values())
        if ideas:
            out[self.cfg["judges"]["primary"]["id"] + " (idea grouping)"] = ideas
        emb = sum((v.get("cost_usd") or 0.0) for v in self.store.load("embeddings.jsonl", key="hash").values())
        if emb:
            out[self.cfg["embedding_model"] + " (embeddings)"] = emb
        return out

    # item-level metrics (pooled over the runs of one model x item)
    def _valid_rows(self, m, iid, variant="base"):
        return [self.index[(m, iid, variant, r)] for r in self.runs
                if (m, iid, variant, r) in self.index and self.index[(m, iid, variant, r)]["valid"]]

    def idea_arrays(self, m, ids, kind):
        num = np.zeros((len(ids), 1))
        den = np.zeros_like(num)
        for a, iid in enumerate(ids):
            rs = self._valid_rows(m, iid)
            v = len(rs)
            if v == 0:
                continue
            uniq = {checks.normalize(r["chk"]["slogan"]) for r in rs}
            if kind == "dup":
                num[a, 0], den[a, 0] = 1 - len(uniq) / v, 1
                continue
            if kind == "emb":
                vecs = [self.emb.get(merge.sha(checks.normalize(r["chk"]["slogan"]))) for r in rs]
                vecs = [x for x in vecs if x is not None]
                if len(vecs) < 2:
                    continue
                sims = []
                for i in range(len(vecs)):
                    for j in range(i + 1, len(vecs)):
                        sims.append(max(0.0, float(vecs[i] @ vecs[j] / (np.linalg.norm(vecs[i]) * np.linalg.norm(vecs[j])))))
                num[a, 0], den[a, 0] = 1 - float(np.mean(sims)), 1
                continue
            rec = self.ideas.get("|".join([m, iid, "base"]))
            if v == 1 or len(uniq) == 1:
                g = 1
            elif rec and rec.get("n_groups"):
                g = rec["n_groups"]
            else:
                continue
            num[a, 0], den[a, 0] = (g / v if kind == "ratio" else g), 1
        return num, den

    def item_summary(self, num, den):
        idx = self._idx(num.shape[0])
        n, d = num.sum(), den.sum()
        mean = float(n / d) if d else float("nan")
        boot = stats.boot_means(num, den, idx) if d else np.array([np.nan])
        return {"mean": mean, "ci": stats.ci(boot), "boot": boot, "sd": 0.0, "min": mean, "max": mean}

    def t5_diversity(self, held):
        rows, self.div = [], {}
        for m in self.models:
            ratio = self.item_summary(*self.idea_arrays(m, held, "ratio"))
            groups = self.item_summary(*self.idea_arrays(m, held, "groups"))
            dup = self.item_summary(*self.idea_arrays(m, held, "dup"))
            emb = self.item_summary(*self.idea_arrays(m, held, "emb"))
            cp = self.metric(m, held, "contam_prog")
            cj = self.metric(m, held, "contam_judge")
            gen = self.metric(m, held, "generic")
            nomem = self.metric(m, held, "originality_nomem")
            self.div[m] = {"ratio": ratio, "contam_prog": cp}
            f = lambda s, sc=1.0, d=2: "%.*f (%.*f–%.*f)" % (d, s["mean"] * sc, d, s["ci"][0] * sc, d, s["ci"][1] * sc)
            rows.append([self.L(m), f(ratio), f(groups, 1, 2), f(dup, 100, 1), f(emb, 1, 3), f(cp, 100, 1), f(cj, 100, 1),
                         f(gen, 100, 1), f(nomem, 1, 2)])
        return self.table("T5_diversity_contamination",
                          ["Model", "Distinct ideas per valid output (1 = all different)", "Distinct ideas per item (of 5 runs)",
                           "Exact-duplicate outputs, %", "Embedding diversity (1 − mean cosine)",
                           "Reproduces a known real slogan, % (programmatic)", "Judge recognises a real slogan, %",
                           "Valid but generic (originality ≤ 2), %",
                           "SUPPLEMENTARY: originality excluding outputs that reproduce a real slogan (1–5)"], rows,
                          "Held-out split, base briefs. Cells: mean (95%% CI, bootstrap over items). Idea grouping and "
                          "embedding diversity pool the runs of one item, so they have no run-to-run SD; the CI reflects item "
                          "sampling only. Embeddings: %s; negative cosines clipped to 0." % self.cfg["embedding_model"])

    def t6_pairwise(self, held):
        ctx = self.ids(split="heldout", tier="contextual")
        specs = [("Valid outputs (%)", held, "valid", 100), ("Originality (1–5)", held, "originality", 1),
                 ("Contextual compliance (%)", ctx, "compliance", 100)]
        rows, letters_out = [], {}
        for label, ids, name, sc in specs:
            summ = {m: self.metric(m, ids, name) for m in self.models}
            sep = {}
            for a in self.models:
                for b in self.models:
                    if a != b:
                        sep[(a, b)] = stats.separable(summ[a], summ[b], summ[a]["boot"], summ[b]["boot"])[0]
            letters_out[name] = stats.letter_groups(self.models, {m: summ[m]["mean"] for m in self.models}, sep)
            for i, a in enumerate(self.models):
                for b in self.models[i + 1:]:
                    ok, (lo, hi), gap, noise = stats.separable(summ[a], summ[b], summ[a]["boot"], summ[b]["boot"])
                    d = summ[a]["mean"] - summ[b]["mean"]
                    rows.append([label, self.L(a), self.L(b), "%+.2f" % (d * sc), "%.2f" % (noise * sc),
                                 "%+.2f to %+.2f" % (lo * sc, hi * sc), "RANKABLE" if ok else "within noise - do not rank"])
        self.letters = letters_out
        return self.table("T6_pairwise_separability",
                          ["Metric", "Model A", "Model B", "Δ (A−B)", "Larger run-to-run SD of the two",
                           "95% CI of Δ over items (paired)", "Verdict"], rows,
                          "Rule (frozen): two models are ranked on a metric only if |Δ| exceeds the run-to-run SD of "
                          "either model AND the paired item-bootstrap CI of Δ excludes zero. Otherwise they are reported as "
                          "indistinguishable. Compact letters per metric: " + json.dumps(
                              {k: {self.L(m): v for m, v in d.items()} for k, d in letters_out.items()}))

    def t7_failures(self, held):
        modes = FAIL_ORDER + ["valid but generic", "valid and reproduces real slogan", "valid, clean"]
        rows = []
        self.fail_counts = {}
        for m in self.models:
            cnt = {k: 0 for k in modes}
            total = 0
            for iid in held:
                for run in self.runs:
                    r = self.index.get((m, iid, "base", run))
                    if r is None:
                        continue
                    total += 1
                    fm = failure_mode(r)
                    if fm:
                        cnt[fm] += 1
                    elif r["j1"] is None:
                        total -= 1
                    elif r["chk"]["known_match"]:
                        cnt["valid and reproduces real slogan"] += 1
                    elif r["j1"]["originality"] <= 2:
                        cnt["valid but generic"] += 1
                    else:
                        cnt["valid, clean"] += 1
            self.fail_counts[m] = (cnt, total)
        for k in modes:
            cls = FAIL_CLASS.get(k, "quality flag (output is valid)")
            rows.append([k, cls] + ["%d (%.1f%%)" % (self.fail_counts[m][0][k], 100 * self.fail_counts[m][0][k] /
                                                    max(self.fail_counts[m][1], 1)) for m in self.models])
        return self.table("T7_failure_modes", ["Failure mode (first that applies)", "Whose fault?"] + [self.L(m) for m in self.models],
                          rows, "Held-out split, all runs, counts (share of outputs). 'model wrong' = the instruction or "
                                "constraint was in the prompt and the output still broke it. Generic and unfaithful outputs "
                                "are attributed using the sparse-vs-rich counterfactual in T8.")

    def t8_counterfactual(self):
        sparse = self.ids(subtype="sparse")
        rows = []
        for m in self.models:
            res = {}
            for variant in ("base", "rich"):
                v = self.metric(m, sparse, "valid", variant)
                f = self.metric(m, sparse, "faithful", variant)
                o = self.metric(m, sparse, "originality", variant)
                g = self.metric(m, sparse, "generic", variant)
                res[variant] = (v["mean"], 1 - f["mean"], o["mean"], g["mean"])
            b, r_ = res["base"], res["rich"]
            rows.append([self.L(m), "%.0f%% → %.0f%%" % (b[0] * 100, r_[0] * 100),
                         "%.0f%% → %.0f%%" % (b[1] * 100, r_[1] * 100),
                         "%.2f → %.2f" % (b[2], r_[2]), "%.0f%% → %.0f%%" % (b[3] * 100, r_[3] * 100)])
        names = [self.item[i]["company"] for i in sparse]
        return self.table("T8_missing_input_counterfactual",
                          ["Model", "Valid: sparse → rich brief", "Unsupported-claim rate: sparse → rich",
                           "Originality: sparse → rich", "Generic rate: sparse → rich"], rows,
                          "Counterfactual on the %d sparse items (%s): the same company is run with a one-clause description "
                          "and again with the full description. A failure that disappears when the missing facts are supplied "
                          "is a missing-input failure; one that persists is a model failure." % (len(sparse), ", ".join(names)))

    def t9_judges(self, held):
        both = [r for r in self.rows if r["split"] == "heldout" and r["variant"] == "base" and r["j1"] and r["j2"]]
        rows = []
        for f in ("coherent", "relevant", "complies", "faithful", "recognized"):
            a = [int(r["j1"][f]) for r in both]
            b = [int(r["j2"][f]) for r in both]
            if a:
                po, k = stats.cohen_kappa(a, b)
                rows.append([f, "%.1f%%" % (po * 100), "%.2f" % k, "%.1f%%" % (100 * np.mean(a)), "%.1f%%" % (100 * np.mean(b))])
        if both:
            a = [r["j1"]["originality"] for r in both]
            b = [r["j2"]["originality"] for r in both]
            rows.append(["originality (1–5)", "%.1f%% exact" % (100 * np.mean(np.array(a) == np.array(b))),
                         "QWK %.2f / Spearman %.2f" % (stats.quad_weighted_kappa(a, b), stats.spearman(a, b)),
                         "%.2f" % np.mean(a), "%.2f" % np.mean(b)])
        j1, j2 = self.cfg["judges"]["primary"], self.cfg["judges"]["probe"]
        self.table("T9a_judge_agreement", ["Criterion", "Raw agreement", "Cohen κ", "%s: yes / mean" % j1["label"],
                                           "%s: yes / mean" % j2["label"]], rows,
                   "n = %d held-out base outputs judged by both. Agreement between two judges from different families is "
                   "an upper bound on how much of the score is rubric rather than taste; it is not a human validation." % len(both))
        # self-preference: does the probe judge (Anthropic) lift Anthropic-family generators more than the neutral judge does?
        fam = {m["id"]: m["family"] for m in self.cfg["models"]}
        probe_family = j2["family"]
        res = {}
        ids = held
        for m in self.models:
            o1 = self._judge_means(m, ids, "j1", "originality")
            o2 = self._judge_means(m, ids, "j2", "originality")
            res[m] = (o1, o2)
        rows2 = []
        for m in self.models:
            o1, o2 = res[m]
            rows2.append([self.L(m), fam[m] + (" (probe's own family)" if fam[m] == probe_family else ""),
                          "%.2f" % np.nanmean(o1), "%.2f" % np.nanmean(o2), "%+.2f" % (np.nanmean(o2) - np.nanmean(o1))])
        own = [m for m in self.models if fam[m] == probe_family]
        other = [m for m in self.models if fam[m] != probe_family]
        sp_note = "No generator shares the probe judge's family; self-preference could not be measured."
        if own and other:
            idx = self._idx(len(ids))
            def d(m):
                o1, o2 = res[m]
                return (o2 - o1)
            own_d = np.nanmean([d(m) for m in own], axis=0)
            oth_d = np.nanmean([d(m) for m in other], axis=0)
            diff = own_d - oth_d                    # per item: (probe - neutral) lift for own family vs others
            boots = np.array([np.nanmean(diff[ix]) for ix in idx])
            lo, hi = stats.ci(boots)
            est = float(np.nanmean(diff))
            self.self_pref = (est, lo, hi)
            sp_note = ("Self-preference estimate (difference-in-differences, originality points): the probe judge "
                       "(%s) minus the neutral primary judge (%s), for its own family's generators minus the other "
                       "generators = %+.2f (95%% CI %+.2f to %+.2f, bootstrap over items). A CI that excludes zero "
                       "means the probe judge favoured its own family beyond general leniency." %
                       (j2["label"], j1["label"], est, lo, hi))
        else:
            self.self_pref = None
        return self.table("T9b_self_preference", ["Generator", "Family", "Originality by %s" % j1["label"],
                                                  "Originality by %s" % j2["label"], "Probe − primary"], rows2, sp_note)

    def _judge_means(self, m, ids, role, field):
        out = np.full(len(ids), np.nan)
        for a, iid in enumerate(ids):
            vals = []
            for run in self.runs:
                r = self.index.get((m, iid, "base", run))
                if r and r["j1"] and r["j2"] and r["chk"]["programmatic_ok"]:
                    vals.append(r[role][field])
            if vals:
                out[a] = float(np.mean(vals))
        return out

    def t10_all(self, every):
        rows = []
        for m in self.models:
            row = [self.L(m)]
            for ids in (every, self.ids(split="dev"), self.ids(split="heldout")):
                v, o = self.metric(m, ids, "valid"), self.metric(m, ids, "originality")
                row += ["%.1f ± %.1f" % (v["mean"] * 100, v["sd"] * 100), "%.2f" % o["mean"]]
            rows.append(row)
        return self.table("T10_all_items", ["Model", "All 50: valid %", "originality", "Dev (n=%d): valid %%" % len(self.ids(split="dev")),
                                            "originality", "Held-out (n=%d): valid %%" % len(self.ids(split="heldout")),
                                            "originality"], rows,
                          "Full results table for the appendix. Headline numbers use the held-out split only.")

    # -- instrument interrogation: the cases a human should read
    def disputes(self, held):
        base = [r for r in self.rows if r["variant"] == "base" and r["split"] == "heldout"]
        sections = []

        def show(title, why, rs, n=8):
            sections.append("## %s\n\n%s\n\n%d case(s).\n" % (title, why, len(rs)))
            for r in rs[:n]:
                j = r["j1"] or {}
                sections.append("- **%s** · %s · run %d · output: `%s` · judge: complies=%s faithful=%s orig=%s%s" % (
                    self.L(r["model"]), r["company"], r["run"], r["chk"]["slogan"] or r["raw"][:80],
                    j.get("complies"), j.get("faithful"), j.get("originality"),
                    " · programmatic: " + ", ".join(self._why(r)) if self._why(r) else ""))
            sections.append("")

        gen = [r for r in base if r["j1"] and r["j1"]["complies"] and
               (not r["chk"]["words_ok"] or r["chk"]["missing_required"] or r["chk"]["used_banned"])]
        show("A. Judge scored 'complies' = yes, but an explicit constraint was broken",
             "The grader was generous: a human checking the stated requirements would have failed these.", gen)
        dis = [r for r in base if r["j1"] and r["j2"] and abs(r["j1"]["originality"] - r["j2"]["originality"]) >= 2]
        show("B. The two judges differ by 2+ originality points",
             "Read these and decide which judge you agree with; this is the 'a score your own reading disputes' evidence.", dis)
        rec = [r for r in base if r["j1"] and r["j1"]["recognized"] and not r["chk"]["known_match"]
               and self.item[r["item_id"]]["known_slogans"]]
        show("C. Judge says 'recognised real slogan' but our known-slogan list did not match",
             "Either the list is incomplete or the judge is over-calling familiarity (a contamination-measure weakness).", rec)
        lit = [r for r in base if r["valid"] and r["chk"]["known_match"]]
        show("D. Output reproduces a real slogan yet counted as valid",
             "Validity does not penalise memorisation; originality should. Check the originality score it received.", lit)
        with open(os.path.join(self.out, "disputes.md"), "w") as fh:
            fh.write("# Cases to read before trusting the scores (held-out, base briefs)\n\n" + "\n".join(sections))

    @staticmethod
    def _why(r):
        c, w = r["chk"], []
        if not c["words_ok"]:
            w.append("%d words > %d" % (c["words"], c["max_words"]))
        w += ["missing '%s'" % x for x in c["missing_required"]]
        w += ["used banned '%s'" % x for x in c["used_banned"]]
        return w

    def sample_outputs(self):
        rng = random.Random(self.cfg["seed"])
        path = os.path.join(self.out, "outputs_sample.csv")
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["model", "item_id", "company", "variant", "run", "raw_output_unedited", "valid", "originality_j1"])
            for m in self.models:
                rs = [r for r in self.rows if r["model"] == m]
                for r in rng.sample(rs, min(12, len(rs))):
                    w.writerow([m, r["item_id"], r["company"], r["variant"], r["run"], r["raw"], r["valid"],
                                (r["j1"] or {}).get("originality", "")])

    # -- figures
    def figures(self, held):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams.update({"font.size": 13, "axes.titlesize": 15, "axes.labelsize": 13, "xtick.labelsize": 12,
                             "ytick.labelsize": 12, "axes.edgecolor": INK2, "axes.labelcolor": INK, "text.color": INK,
                             "xtick.color": INK2, "ytick.color": INK2, "axes.facecolor": SURFACE, "figure.facecolor": SURFACE,
                             "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
                             "grid.linewidth": 0.8, "axes.axisbelow": True, "font.family": "DejaVu Sans"})
        th = self.cfg["thresholds"]
        ctx = self.ids(split="heldout", tier="contextual")
        short = lambda m: self.L(m).replace(" ", "\n", 1)
        xs = np.arange(len(self.models))

        def bars(ax, vals, errs, ylabel, title, fmt, line=None, line_label=None, ylim=None):
            ax.bar(xs, vals, width=0.55, color=[self.color[m] for m in self.models], edgecolor=SURFACE, linewidth=2, zorder=3)
            floor = ylim[0] if ylim else 0.0
            lower = np.minimum(np.array(errs), np.maximum(np.array(vals) - floor, 0))
            ax.errorbar(xs, vals, yerr=[lower, errs], fmt="none", ecolor=INK, elinewidth=1.6, capsize=5, zorder=4)
            for x, v, e in zip(xs, vals, errs):
                ax.text(x, v + e + (ylim[1] - ylim[0]) * 0.015, fmt % v, ha="center", va="bottom", fontsize=12, color=INK, zorder=5,
                        bbox=dict(facecolor=SURFACE, edgecolor="none", pad=1.5))
            if line is not None:
                ax.axhline(line, color=INK2, linestyle="--", linewidth=1.6, zorder=2)
                ax.text(0.01, 0.985, "- - -  " + line_label, transform=ax.transAxes, ha="left", va="top", fontsize=11,
                        color=INK2)
            ax.set_xticks(xs)
            ax.set_xticklabels([short(m) for m in self.models])
            ax.set_ylabel(ylabel)
            ax.set_title(title, loc="left", fontweight="bold")
            if ylim:
                ax.set_ylim(*ylim)
            ax.grid(axis="x", visible=False)

        # Figure 1: the acceptable-failure line, one criterion per panel
        fig, axes = plt.subplots(1, 3, figsize=(17, 5.8))
        v = [self.metric(m, held, "valid") for m in self.models]
        o = [self.metric(m, held, "originality") for m in self.models]
        c = [self.metric(m, ctx, "compliance") for m in self.models]
        bars(axes[0], [s["mean"] * 100 for s in v], [s["sd"] * 100 for s in v], "Valid outputs (% of outputs)",
             "Validity", "%.1f", th["valid_rate"] * 100, "acceptable-failure line: 95%", (0, 112))
        bars(axes[1], [s["mean"] for s in o], [s["sd"] for s in o], "Mean originality of valid outputs (1–5 scale)",
             "Originality", "%.2f", th["originality_mean"], "acceptable-failure line: 3.0", (1, 5.4))
        bars(axes[2], [s["mean"] * 100 for s in c], [s["sd"] * 100 for s in c], "Contextual briefs met (% of outputs)",
             "Following explicit constraints", "%.1f", th["contextual_compliance"] * 100, "acceptable-failure line: 90%", (0, 112))
        fig.suptitle("Held-out items: each criterion against the acceptable-failure line (bars: mean of %d runs; "
                     "whiskers: ±1 SD across runs)" % len(self.runs), x=0.01, ha="left", fontsize=15, fontweight="bold")
        fig.tight_layout(rect=(0, 0, 1, 0.93))
        fig.savefig(os.path.join(self.fdir, "fig1_acceptable_failure_line.png"), dpi=200)
        plt.close(fig)

        # Figure 2: normal vs edge cases (tier encoded in neutral greys so it never collides with model hues)
        fig, ax = plt.subplots(figsize=(13, 5.8))
        w = 0.26
        for k, tier in enumerate(("standard", "contextual", "stress")):
            ids = self.ids(split="heldout", tier=tier)
            ss = [self.metric(m, ids, "valid") for m in self.models]
            vals = np.array([s["mean"] * 100 for s in ss])
            errs = np.array([s["sd"] * 100 for s in ss])
            pos = xs + (k - 1) * (w + 0.03)
            ax.bar(pos, vals, width=w, color=TIER_GREYS[tier], edgecolor=SURFACE, linewidth=2, zorder=3,
                   label="%s (n=%d items)" % (tier, len(ids)))
            ax.errorbar(pos, vals, yerr=errs, fmt="none", ecolor=INK, elinewidth=1.4, capsize=4, zorder=4)
            for p, val, e in zip(pos, vals, errs):
                ax.text(p, val + e + 1.5, "%.0f" % val, ha="center", fontsize=11, color=INK, zorder=5,
                        bbox=dict(facecolor=SURFACE, edgecolor="none", pad=1.2))
        ax.axhline(th["valid_rate"] * 100, color=INK2, linestyle="--", linewidth=1.6)
        ax.text(0.01, 0.985, "- - -  acceptable-failure line: 95%", transform=ax.transAxes, ha="left", va="top",
                fontsize=11, color=INK2)
        ax.set_xticks(xs)
        ax.set_xticklabels([self.L(m) for m in self.models])
        ax.set_ylim(0, 115)
        ax.set_ylabel("Valid outputs (% of outputs)")
        ax.set_title("Normal vs edge cases (held-out): validity by brief type", loc="left", fontweight="bold")
        ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=3, fontsize=12)
        ax.grid(axis="x", visible=False)
        fig.tight_layout()
        fig.savefig(os.path.join(self.fdir, "fig2_edge_vs_normal.png"), dpi=200)
        plt.close(fig)

        # Figure 3: cost and latency as results
        fig, axes = plt.subplots(1, 2, figsize=(14, 5.4))
        costs = [self.cost_total[m] for m in self.models]
        lats = [self.lat_median[m] for m in self.models]
        for ax, vals, lab, ttl, fmt in ((axes[0], costs, "Total generation cost of the full run (USD)", "Cost", "$%.2f"),
                                        (axes[1], lats, "Median latency per call (seconds)", "Latency", "%.1f s")):
            ax.barh(range(len(self.models)), vals, color=[self.color[m] for m in self.models], height=0.55, zorder=3)
            ax.set_yticks(range(len(self.models)))
            ax.set_yticklabels([self.L(m) for m in self.models])
            ax.invert_yaxis()
            top = max(vals) if max(vals) > 0 else 1
            for i, val in enumerate(vals):
                ax.text(val + top * 0.01, i, fmt % val, va="center", fontsize=12, color=INK)
            ax.set_xlim(0, top * 1.18)
            ax.set_xlabel(lab)
            ax.set_title(ttl, loc="left", fontweight="bold")
            ax.grid(axis="y", visible=False)
        fig.tight_layout()
        fig.savefig(os.path.join(self.fdir, "fig3_cost_latency.png"), dpi=200)
        plt.close(fig)

        # Figure 4: mode collapse and memorisation
        fig, axes = plt.subplots(1, 2, figsize=(14, 5.6))
        r = [self.div[m]["ratio"] for m in self.models]
        cp = [self.div[m]["contam_prog"] for m in self.models]
        bars(axes[0], [s["mean"] for s in r], [(s["ci"][1] - s["ci"][0]) / 2 for s in r],
             "Distinct ideas per valid output (1 = all different)", "Repetition across 5 runs of the same brief",
             "%.2f", None, None, (0, 1.15))
        bars(axes[1], [s["mean"] * 100 for s in cp], [s["sd"] * 100 for s in cp],
             "Outputs that reproduce a real slogan (%)", "Memorisation of the company's real slogan", "%.1f", None, None,
             (0, max(10.0, max(s["mean"] * 100 + s["sd"] * 100 for s in cp) * 1.25)))
        fig.text(0.01, 0.005, "Whiskers: left panel = 95% CI over items; right panel = ±1 SD across runs. Held-out split, base briefs.",
                 fontsize=11, color=INK2)
        fig.tight_layout(rect=(0, 0.03, 1, 1))
        fig.savefig(os.path.join(self.fdir, "fig4_repetition_and_memorisation.png"), dpi=200)
        plt.close(fig)

        # Figure 5: judge self-preference
        fig, ax = plt.subplots(figsize=(13, 5.6))
        w = 0.34
        j1l, j2l = self.cfg["judges"]["primary"]["label"], self.cfg["judges"]["probe"]["label"]
        a = [np.nanmean(self._judge_means(m, held, "j1", "originality")) for m in self.models]
        b = [np.nanmean(self._judge_means(m, held, "j2", "originality")) for m in self.models]
        ax.bar(xs - w / 2 - 0.02, a, width=w, color="#c9c8c2", edgecolor=SURFACE, linewidth=2, label=j1l + " (neutral family)", zorder=3)
        ax.bar(xs + w / 2 + 0.02, b, width=w, color="#3d3d3a", edgecolor=SURFACE, linewidth=2, label=j2l + " (probe)", zorder=3)
        for i, (p, q) in enumerate(zip(a, b)):
            ax.text(i - w / 2 - 0.02, p + 0.04, "%.2f" % p, ha="center", fontsize=11)
            ax.text(i + w / 2 + 0.02, q + 0.04, "%.2f" % q, ha="center", fontsize=11)
        ax.set_xticks(xs)
        pf = self.cfg["judges"]["probe"]["family"]
        fam = {m["id"]: m["family"] for m in self.cfg["models"]}
        ax.set_xticklabels([self.L(m) + ("\n(probe judge's own family)" if fam[m] == pf else "") for m in self.models])
        ax.set_ylim(1, 5)
        ax.set_ylabel("Mean originality assigned (1–5 scale)")
        ax.set_title("Does a judge favour its own family? Originality by judge and generator (held-out)", loc="left",
                     fontweight="bold")
        ax.legend(frameon=False, loc="upper right")
        ax.grid(axis="x", visible=False)
        fig.tight_layout()
        fig.savefig(os.path.join(self.fdir, "fig5_judge_self_preference.png"), dpi=200)
        plt.close(fig)


# ---------------------------------------------------------------- run manifest

def manifest(cfg, rows, meta, store, freeze, path):
    out = {"benchmark": cfg["benchmark"], "n_runs_configured": cfg["n_runs"], "models": {}, "judges": {},
           "embedding_model": cfg["embedding_model"], "freeze": freeze, "meta_fetched_at": meta.get("fetched_at")}
    for m in cfg["models"]:
        rs = [r for r in rows if r["model"] == m["id"]]
        ts = sorted(r["ts"] for r in rs if r.get("ts"))
        sent = [r["params_sent"] or {} for r in rs]
        out["models"][m["id"]] = {
            "label": m["label"], "canonical_slug": (meta["models"].get(m["id"]) or {}).get("canonical_slug"),
            "first_call": ts[0] if ts else None, "last_call": ts[-1] if ts else None, "calls": len(rs),
            "errors": sum(1 for r in rs if r["error"]),
            "resolved_models_seen": sorted({r["resolved_model"] for r in rs if r.get("resolved_model")}),
            "providers_seen": sorted({str(r["provider"]) for r in rs if r.get("provider")}),
            "temperature_applied": sorted({p.get("temperature") for p in sent if "temperature" in p}, key=str) or "not accepted by model",
            "top_p_applied": sorted({p.get("top_p") for p in sent if "top_p" in p}, key=str) or "not accepted by model",
            "reasoning_setting": next((p.get("reasoning") for p in sent if "reasoning" in p), "not sent"),
            "seed_applied": any("seed" in p for p in sent),
            "params_dropped_after_400": sorted({d for r in rs for d in (r.get("params_dropped") or [])})}
    jr = store.load("judgments.jsonl")
    for role in ("primary", "probe"):
        jid = cfg["judges"][role]["id"]
        recs = [x for x in jr.values() if x["judge"] == jid]
        ts = sorted(x["ts"] for x in recs)
        out["judges"][role] = {"id": jid, "canonical_slug": (meta["models"].get(jid) or {}).get("canonical_slug"),
                               "calls": len(recs), "parse_failures": sum(1 for x in recs if not x["parsed"]),
                               "first_call": ts[0] if ts else None, "last_call": ts[-1] if ts else None}
    with open(path, "w") as fh:
        json.dump(out, fh, indent=2)
    return out
