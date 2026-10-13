"""Command line entry point:  python3 bench.py <command> [options]   (see README.md)"""
import argparse
import csv
import hashlib
import json
import os
import random
import sys
import time
import zipfile

from . import checks, client, items as itemlib, merge, pipeline
from .store import Store, now_iso

ROOT = itemlib.ROOT


def load_cfg():
    with open(os.path.join(ROOT, "config.json")) as fh:
        return json.load(fh)


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


def freeze_payload(cfg):
    files = ["data/items.json", "bench/checks.py", "bench/merge.py"] + \
            ["prompts/" + f for f in sorted(os.listdir(os.path.join(ROOT, "prompts"))) if f.endswith(".txt")]
    frozen_cfg = {k: cfg[k] for k in ("n_runs", "models", "judges", "generation", "thresholds", "embedding_model",
                                      "bootstrap")}
    return {"files": {f: sha_file(os.path.join(ROOT, f)) for f in files},
            "config_sha": hashlib.sha256(json.dumps(frozen_cfg, sort_keys=True).encode()).hexdigest()}


def results_root(args):
    return os.path.join(ROOT, "results_mock" if args.mock else "results") if not args.results_root else args.results_root


def phase_dir(args):
    return os.path.join(results_root(args), args.phase)


def require_freeze(cfg, args):
    path = os.path.join(results_root(args), "freeze.json")
    if args.phase != "final" or args.mock:
        return None
    if not os.path.exists(path):
        sys.exit("Final run refused: nothing is frozen yet. Run `python3 bench.py freeze` first (after the pilot).")
    with open(path) as fh:
        frozen = json.load(fh)
    now = freeze_payload(cfg)
    bad = [f for f, h in now["files"].items() if frozen["files"].get(f) != h]
    if bad or frozen["config_sha"] != now["config_sha"]:
        sys.exit("Final run refused: frozen inputs changed since `freeze`: %s%s. Re-run the pilot and freeze again, "
                 "and record the change in DEVIATIONS.md." % (bad, " + config" if frozen["config_sha"] != now["config_sha"] else ""))
    return frozen


def get_client(args, cfg):
    if args.mock:
        return client.MockClient()
    key = client.load_key(ROOT)
    if not key:
        sys.exit("No API key: put OPENROUTER_API_KEY=... in %s/.env (see .env.example) or export it." % ROOT)
    return client.OpenRouter(key, timeout=cfg["timeout_s"], max_attempts=cfg["max_attempts"])


def get_meta(args, cfg, refresh=False):
    if args.mock:
        return {"fetched_at": "mock", "models": {mid: {"canonical_slug": mid + "-mock", "supported_parameters":
                                                       ["temperature", "top_p", "reasoning", "seed"],
                                                       "pricing": {"prompt": "0.000001", "completion": "0.000004"}}
                                                 for mid in pipeline.all_model_ids(cfg)}}
    return pipeline.load_meta(results_root(args), cfg, refresh)


# ------------------------------------------------------------------ commands

def cmd_check(args):
    cfg = load_cfg()
    items = itemlib.load_items()
    by_tier, by_split = {}, {}
    for it in items:
        by_tier[it["tier"]] = by_tier.get(it["tier"], 0) + 1
        by_split[it["split"]] = by_split.get(it["split"], 0) + 1
    print("items: %d  tiers: %s  splits: %s" % (len(items), by_tier, by_split))
    print("models:", ", ".join(m["id"] for m in cfg["models"]))
    print("judges: primary=%s probe=%s" % (cfg["judges"]["primary"]["id"], cfg["judges"]["probe"]["id"]))
    print("example prompt (%s):\n---\n%s\n---" % (items[0]["company"], itemlib.generator_messages(items[0])[1]["content"]))


def cmd_estimate(args):
    cfg = load_cfg()
    meta = get_meta(args, cfg, refresh=args.refresh)
    items = itemlib.load_items("dev" if args.phase == "pilot" else None)
    n = cfg["pilot_runs"] if args.phase == "pilot" else cfg["n_runs"]
    missing = [m for m, v in meta["models"].items() if v is None]
    if missing:
        print("WARNING: not in the live OpenRouter listing: %s" % missing)
    rows, lo, hi, tasks = pipeline.estimate(cfg, meta, items, n, with_probe=args.phase != "pilot")
    print("phase=%s  items=%d  runs=%d  generation calls=%d" % (args.phase, len(items), n, tasks))
    for stage, mid, calls, a, b in rows:
        print("  %-14s %-34s %5d calls   $%6.3f – $%6.3f" % (stage, mid, calls, a, b))
    print("  TOTAL (token-count estimate; the upper figure allows ~450 hidden reasoning tokens per call): $%.2f – $%.2f" % (lo, hi))
    print("\nparameters the models accept (from the live listing):")
    for m in cfg["models"]:
        sup = (meta["models"].get(m["id"]) or {}).get("supported_parameters") or []
        print("  %-34s temperature=%-5s top_p=%-5s seed=%-5s reasoning=%s" % (
            m["id"], "temperature" in sup, "top_p" in sup, "seed" in sup, "reasoning" in sup))


def cmd_freeze(args):
    cfg = load_cfg()
    payload = freeze_payload(cfg)
    payload["frozen_at"] = now_iso()
    os.makedirs(results_root(args), exist_ok=True)
    path = os.path.join(results_root(args), "freeze.json")
    with open(path, "w") as fh:
        json.dump(payload, fh, indent=2)
    print("frozen at %s\n%s" % (payload["frozen_at"], json.dumps(payload["files"], indent=2)))


def select_items(args, default_subset=None):
    items = itemlib.load_items(default_subset)
    if getattr(args, "items", None):
        wanted = [x.strip() for x in args.items.split(",") if x.strip()]
        unknown = [w for w in wanted if w not in {i["id"] for i in items}]
        if unknown:
            sys.exit("Unknown item ids: %s" % unknown)
        items = [i for i in items if i["id"] in wanted]
    return items


def cmd_run(args):
    cfg = load_cfg()
    frozen = require_freeze(cfg, args)
    meta = get_meta(args, cfg)
    items = select_items(args, "dev" if args.phase == "pilot" else None)
    n_runs = args.runs or (cfg["pilot_runs"] if args.phase == "pilot" else cfg["n_runs"])
    rows, lo, hi, tasks = pipeline.estimate(cfg, meta, items, n_runs, with_probe=args.phase != "pilot")
    print("phase=%s items=%d runs=%d -> estimated cost $%.2f–$%.2f" % (args.phase, len(items), n_runs, lo, hi))
    if not args.mock and not args.confirm:
        print("Dry run only. Re-run with --confirm to spend money (budget cap --max-usd, default %.0f)." % args.max_usd)
        return
    cl = get_client(args, cfg)
    store = Store(phase_dir(args))
    budget = pipeline.Budget(args.max_usd)
    workers = args.workers or cfg["concurrency"]
    t0 = time.time()
    pipeline.generate(cfg, cl, meta, items, cfg["models"], n_runs, store, budget, workers, args.retry_errors, args.phase)
    print("spent so far: $%.3f" % budget.spent)
    roles = ("primary",) if args.phase == "pilot" or args.no_probe else ("primary", "probe")
    if not budget.stopped:
        pipeline.judge(cfg, cl, meta, items, store, budget, workers, roles)
        print("spent so far: $%.3f" % budget.spent)
    if args.phase == "final" and not budget.stopped:
        pipeline.ideas(cfg, cl, meta, items, store, budget, workers)
        pipeline.embeddings(cfg, cl, store, items)
    if budget.stopped:
        print("BUDGET CAP HIT ($%.2f). Stopped; re-run to resume (stored work is kept)." % budget.max_usd)
    print("done in %.0f s, spent $%.3f" % (time.time() - t0, budget.spent))


def cmd_analyze(args):
    from . import analyze
    cfg = load_cfg()
    items = itemlib.load_items()
    meta = get_meta(args, cfg)
    store = Store(phase_dir(args))
    out = phase_dir(args)
    an = analyze.Analysis(cfg, items, store, out, meta, args.phase)
    if not an.rows:
        sys.exit("No generations found in %s" % store.raw)
    if args.phase == "pilot":
        items = [i for i in items if i["split"] == "dev"]
    frozen = None
    fp = os.path.join(results_root(args), "freeze.json")
    if os.path.exists(fp):
        with open(fp) as fh:
            frozen = json.load(fh)
    analyze.manifest(cfg, an.rows, meta, store, frozen, os.path.join(out, "run_manifest.json"))
    tabs = an.run_all()
    print(tabs["T1"], "\n")
    print(tabs["T4"], "\n")
    print("tables ->", an.tdir, "\nfigures ->", an.fdir)


def cmd_show(args):
    """Print outputs next to the checks and judge verdicts, grouped by item, so a human can read them."""
    cfg = load_cfg()
    items = {i["id"]: i for i in itemlib.load_items()}
    rows, _ = merge.build_rows(Store(phase_dir(args)), list(items.values()), cfg)
    names = {m["id"]: m["label"] for m in cfg["models"]}
    keep = set(args.items.split(",")) if args.items else None
    rows = [r for r in rows if r["model"] in names and (keep is None or r["item_id"] in keep)]
    rows.sort(key=lambda r: (r["item_id"], r["variant"], list(names).index(r["model"]), r["run"]))
    cur = None
    for r in rows:
        if (r["item_id"], r["variant"]) != cur:
            cur = (r["item_id"], r["variant"])
            it = items[r["item_id"]]
            print("\n[%s | %s/%s | %s | %s] %s -- max %d words, must include %s, must not include %s" % (
                r["item_id"], it["tier"], it["subtype"], it["split"], r["variant"], it["company"], it["max_words"],
                it["must_include"] or "-", it["must_not_include"] or "-"))
        c, j, j2 = r["chk"], r["j1"] or {}, r["j2"] or {}
        flag = "OK " if r["valid"] else ("?? " if r["valid"] is None else "BAD")
        why = []
        if c["api_error"]: why.append("API-ERROR")
        if c["refusal"]: why.append("REFUSAL")
        if c["format_flags"]: why.append("fmt:" + ",".join(c["format_flags"]))
        if not c["words_ok"]: why.append("%d words" % c["words"])
        if c["missing_required"]: why.append("missing:" + ",".join(c["missing_required"]))
        if c["used_banned"]: why.append("BANNED:" + ",".join(c["used_banned"]))
        if c["known_match"]: why.append("REAL-SLOGAN:" + c["known_match"])
        if j and not (j["coherent"] and j["relevant"] and j["complies"] and j["faithful"]):
            why.append("judge-no:" + ",".join(k for k in ("coherent", "relevant", "complies", "faithful") if not j[k]))
        probe = (" probe=%s" % j2["originality"]) if j2 else ""
        print("  %s %-20s r%d o=%s%s  %-62s %s" % (flag, names[r["model"]], r["run"], j.get("originality", "-"), probe,
                                                 repr((c["slogan"] or r["raw"])[:62]), " ".join(why)))


def cmd_audit(args):
    """Blinded sheet for human raters (rows shuffled, model identity withheld) + a separate key file."""
    cfg = load_cfg()
    items = {i["id"]: i for i in itemlib.load_items()}
    store = Store(phase_dir(args))
    rows, _ = merge.build_rows(store, list(items.values()), cfg)
    pool = [r for r in rows if r["split"] == "heldout" and r["variant"] == "base" and r["chk"]["slogan"]
            and not r["chk"]["api_error"]]
    rng = random.Random(cfg["seed"] + 7)
    per = max(1, args.n // len(cfg["models"]))
    pick = []
    for m in cfg["models"]:
        mine = [r for r in pool if r["model"] == m["id"]]
        pick += rng.sample(mine, min(per, len(mine)))
    rng.shuffle(pick)
    d = os.path.join(phase_dir(args), "audit")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "audit_sheet.csv"), "w", newline="") as fh, \
            open(os.path.join(d, "audit_key.csv"), "w", newline="") as kh:
        w, k = csv.writer(fh), csv.writer(kh)
        w.writerow(["audit_id", "company", "facts_given", "requirements", "slogan", "coherent_yes_no", "relevant_yes_no",
                    "complies_yes_no", "faithful_yes_no", "originality_1_to_5", "recognised_real_slogan_yes_no", "rater"])
        k.writerow(["audit_id", "model", "item_id", "run", "key"])
        for n, r in enumerate(pick, 1):
            it = items[r["item_id"]]
            aid = "A%03d" % n
            w.writerow([aid, it["company"], it["description"], itemlib.requirement_lines(it).replace("\n", " "),
                        r["chk"]["slogan"], "", "", "", "", "", "", ""])
            k.writerow([aid, r["model"], r["item_id"], r["run"], r["key"]])
    print("wrote %d-row audit sheet + key to %s" % (len(pick), d))


def cmd_package(args):
    import re
    out = os.path.join(os.path.dirname(ROOT), "slogan-benchmark-archive.zip")
    skip_dirs = {".git", "__pycache__", ".venv", "results_mock"}
    todo = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        todo += [os.path.join(base, f) for f in files if f not in (".env", ".DS_Store")]
    secret = re.compile(rb"sk-or-[A-Za-z0-9_-]{20,}")
    leaks = [os.path.relpath(p, ROOT) for p in todo if secret.search(open(p, "rb").read())]
    if leaks:
        sys.exit("Archive REFUSED: API-key-shaped text found in %s. Remove it and re-run." % leaks)
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in todo:
            z.write(p, os.path.join("slogan-benchmark", os.path.relpath(p, ROOT)))
            n += 1
    print("archived %d files -> %s (%.1f MB)" % (n, out, os.path.getsize(out) / 1e6))


def cmd_selftest(args):
    import unittest
    suite = unittest.defaultTestLoader.discover(os.path.join(ROOT, "tests"))
    res = unittest.TextTestRunner(verbosity=1).run(suite)
    sys.exit(0 if res.wasSuccessful() else 1)


def main(argv=None):
    p = argparse.ArgumentParser(prog="bench.py", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    from . import vs
    for name, fn in (("check", cmd_check), ("estimate", cmd_estimate), ("freeze", cmd_freeze), ("run", cmd_run),
                     ("show", cmd_show), ("analyze", cmd_analyze), ("audit", cmd_audit), ("package", cmd_package),
                     ("selftest", cmd_selftest), ("vs-freeze", vs.cmd_freeze), ("vs-run", vs.cmd_run),
                     ("vs-analyze", vs.cmd_analyze)):
        s = sub.add_parser(name)
        s.set_defaults(fn=fn)
        s.add_argument("--phase", choices=["pilot", "final"], default="final")
        s.add_argument("--mock", action="store_true", help="offline fake provider (self-test only; never real results)")
        s.add_argument("--results-root", default=None)
        s.add_argument("--confirm", action="store_true", help="actually spend money")
        s.add_argument("--max-usd", type=float, default=25.0)
        s.add_argument("--runs", type=int, default=None)
        s.add_argument("--workers", type=int, default=None)
        s.add_argument("--no-probe", action="store_true")
        s.add_argument("--retry-errors", action="store_true")
        s.add_argument("--refresh", action="store_true")
        s.add_argument("--n", type=int, default=60)
        s.add_argument("--condition", choices=["list", "vs"], default=None, help="vs-run: one condition only")
        s.add_argument("--items", default=None, help="comma-separated item ids (e.g. c02,c31) to restrict run/show")
    args = p.parse_args(argv)
    args.fn(args)
