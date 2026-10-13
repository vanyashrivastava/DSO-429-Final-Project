"""Verbalized-sampling follow-up (Zhang et al. 2026): List vs VS-Standard at the same budget of 5 candidates per
(model, item). The Direct baseline is the 5 independent runs already collected in results/final.

    python3 bench.py vs-freeze                         # choose the item subset + hash prompts, before any output
    python3 bench.py vs-run --confirm --max-usd 5.5    # generate (1 call per model x item x condition), judge, group
    python3 bench.py vs-analyze                        # tables, rule verdicts, figure
"""
import hashlib
import json
import os
import random
import re
import zlib
from concurrent.futures import ThreadPoolExecutor

from . import items as itemlib, pipeline
from .store import Store, now_iso

K = 5
CONDITIONS = {"list": "prompts/list_user.txt", "vs": "prompts/vs_user.txt"}
PROMPTS = ["prompts/vs_system.txt", "prompts/list_user.txt", "prompts/vs_user.txt"]
N_ITEMS = {"standard": 6, "contextual": 3, "stress": 3}
RULE = {"min_extra_ideas": 0.5, "max_originality_drop": 0.25, "max_cost_ratio": 1.25}


def sha_file(rel):
    with open(os.path.join(itemlib.ROOT, rel), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def messages(item, condition):
    return [{"role": "system", "content": itemlib.read("prompts/vs_system.txt").strip()},
            {"role": "user", "content": itemlib.read(CONDITIONS[condition]).format(**itemlib._fields(item, "base")).strip()}]


def parse_candidates(text):
    obj = itemlib.parse_json_object(text or "")
    out, probs = [], []
    if isinstance(obj, dict) and isinstance(obj.get("responses"), list):
        for r in obj["responses"]:
            if isinstance(r, dict) and isinstance(r.get("text"), str):
                out.append(r["text"].strip())
                probs.append(r.get("probability"))
            elif isinstance(r, str):
                out.append(r.strip())
                probs.append(None)
    if not out:
        for m in re.findall(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"', text or ""):
            try:
                out.append(json.loads('"%s"' % m))
            except ValueError:
                out.append(m)
            probs.append(None)
    return out[:K], probs[:K]


# ------------------------------------------------------------------ commands

def _root(args):
    from . import cli
    return cli.results_root(args)


def cmd_freeze(args):
    from . import cli
    root = _root(args)
    path = os.path.join(root, "vs_prereg.json")
    if os.path.exists(path):
        raise SystemExit("vs_prereg.json already exists; delete it only if no VS output has been collected.")
    items = [i for i in itemlib.load_items("heldout")]
    rng = random.Random(cli.load_cfg()["seed"] + 11)
    subset = []
    for tier, n in N_ITEMS.items():
        subset += sorted(i["id"] for i in rng.sample([i for i in items if i["tier"] == tier], n))
    payload = {"frozen_at": now_iso(), "subset": subset, "k": K, "rule": RULE,
               "prompts": {p: sha_file(p) for p in PROMPTS},
               "note": "Written before any List/VS output was collected. Direct baseline = results/final runs 1-5."}
    os.makedirs(root, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(payload, fh, indent=2)
    print("subset (%d items): %s" % (len(subset), ", ".join(subset)))


def _prereg(args):
    path = os.path.join(_root(args), "vs_prereg.json")
    if not os.path.exists(path):
        raise SystemExit("Run `bench.py vs-freeze` first.")
    with open(path) as fh:
        pre = json.load(fh)
    bad = [p for p, h in pre["prompts"].items() if sha_file(p) != h]
    if bad:
        raise SystemExit("VS prompts changed since vs-freeze: %s" % bad)
    return pre


def generate(cfg, client, meta, items, models, condition, store, budget, workers):
    phase = condition
    done = store.load("calls.jsonl")
    import random as _r
    tasks = [(f"{phase}|{m['id']}|{it['id']}", m, it) for it in items for m in models
             if f"{phase}|{m['id']}|{it['id']}" not in done]
    _r.Random(cfg["seed"] + 5).shuffle(tasks)
    print("%s: %d calls to make (%d stored)" % (condition, len(tasks), len(done)), flush=True)

    def worker(t):
        if budget.stopped:
            return None
        key, m, it = t
        seed_val = zlib.crc32(("%s|%s" % (it["id"], condition)).encode()) & 0x7FFFFFFF
        params = pipeline.sampling_params(cfg["generation"], meta["models"].get(m["id"]), seed_val)
        resp = client.chat(m["id"], messages(it, condition), params)
        cost = pipeline.call_cost(meta, m["id"], resp)
        budget.add(cost)
        cands, probs = ([], []) if resp["error"] else parse_candidates(resp["text"])
        u = resp["usage"] or {}
        store.append("calls.jsonl", {"key": key, "condition": condition, "model": m["id"], "item_id": it["id"],
                                    "ts": now_iso(), "raw": resp["text"], "error": resp["error"],
                                    "latency_s": round(resp["latency_s"], 4), "cost_usd": round(cost, 6),
                                    "n_parsed": len(cands), "probabilities": probs, "usage": u,
                                    "params_sent": resp["params_sent"], "params_dropped": resp["params_dropped"],
                                    "provider": resp["provider"], "resolved_model": resp["resolved_model"]})
        for k in range(1, K + 1):
            err = resp["error"] or (None if k <= len(cands) else {"status": None, "message": "candidate missing"})
            store.append("generations.jsonl", {
                "kind": "gen", "key": "%s|%s|%s|base|%d" % (phase, m["id"], it["id"], k), "phase": phase,
                "model": m["id"], "item_id": it["id"], "variant": "base", "run": k, "ts": now_iso(),
                "raw": cands[k - 1] if k <= len(cands) else "", "finish_reason": resp["finish_reason"], "error": err,
                "latency_s": round(resp["latency_s"], 4), "attempts": resp["attempts"],
                "params_sent": resp["params_sent"], "params_dropped": resp["params_dropped"],
                "usage": {"prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"),
                          "reasoning_tokens": u.get("reasoning_tokens"), "cost_usd": cost / K},
                "provider": resp["provider"], "resolved_model": resp["resolved_model"], "request_id": resp["request_id"]})
        return key
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(worker, tasks))


def cmd_run(args):
    from . import cli
    cfg = cli.load_cfg()
    pre = _prereg(args)
    meta = cli.get_meta(args, cfg)
    by_id = {i["id"]: i for i in itemlib.load_items()}
    wanted = [x for x in (args.items.split(",") if args.items else pre["subset"]) if x in pre["subset"]]
    items = [by_id[i] for i in wanted]
    conds = [args.condition] if getattr(args, "condition", None) in CONDITIONS else list(CONDITIONS)
    est = len(items) * len(cfg["models"]) * len(conds)
    print("VS test: %d items x %d models x %d conditions = %d calls (+ ~%d judge calls)" % (
        len(items), len(cfg["models"]), len(conds), est, est * K))
    if not args.confirm:
        print("Dry run. Re-run with --confirm (cap --max-usd, default %.1f)." % args.max_usd)
        return
    cl = cli.get_client(args, cfg)
    budget = pipeline.Budget(args.max_usd)
    workers = args.workers or cfg["concurrency"]
    for c in conds:
        store = Store(os.path.join(_root(args), c))
        generate(cfg, cl, meta, items, cfg["models"], c, store, budget, workers)
        print("  spent $%.3f" % budget.spent, flush=True)
    for c in conds:
        if budget.stopped:
            break
        store = Store(os.path.join(_root(args), c))
        pipeline.judge(cfg, cl, meta, items, store, budget, workers, roles=("primary",))
        pipeline.ideas(cfg, cl, meta, items, store, budget, workers)
        pipeline.embeddings(cfg, cl, store, items)
        print("  spent $%.3f" % budget.spent, flush=True)
    print("BUDGET CAP HIT" if budget.stopped else "done", "- total $%.3f" % budget.spent)


def cmd_analyze(args):
    import numpy as np
    from . import analyze, cli, stats
    cfg = cli.load_cfg()
    pre = _prereg(args)
    ids = sorted(pre["subset"])
    items = itemlib.load_items()
    meta = cli.get_meta(args, cfg)
    root = _root(args)
    A = {}
    for c, d in (("direct", "final"), ("list", "list"), ("vs", "vs")):
        A[c] = analyze.Analysis(cfg, items, Store(os.path.join(root, d)), os.path.join(root, d), meta)
    idx = stats.boot_indices(len(ids), cfg["bootstrap"]["B"], cfg["bootstrap"]["seed"])
    models = [m["id"] for m in cfg["models"]]
    nm = {m["id"]: m["label"] for m in cfg["models"]}

    def item_means(an, m, kind):
        n, d = an.idea_arrays(m, ids, kind)
        return n, d

    def run_metric(an, m, name):
        return an.arrays(m, ids, analyze.METRICS[name])

    summary, rows_v1, rows_v2 = {}, [], []
    for m in models:
        s = {}
        for c, an in A.items():
            gn, gd = item_means(an, m, "groups")
            rn, rd = item_means(an, m, "ratio")
            en, ed = item_means(an, m, "emb")
            vn, vd = run_metric(an, m, "valid")
            on, od = run_metric(an, m, "originality")
            kn, kd = run_metric(an, m, "contam_prog")
            rows = [r for r in an.rows if r["model"] == m and r["item_id"] in ids]
            cost = sum(an.row_cost(r) for r in rows)
            lat = [r["latency_s"] for r in rows if not r["error"] and r["latency_s"] is not None]
            tot = lambda n, d: float(n.sum() / d.sum()) if d.sum() else float("nan")
            s[c] = {"ideas": tot(gn, gd), "ratio": tot(rn, rd), "emb": tot(en, ed), "valid": tot(vn, vd),
                    "orig": tot(on, od), "known": tot(kn, kd), "cost_item": cost / len(ids),
                    "lat": float(np.median(lat)) if lat else float("nan"),
                    "cost_per_idea": cost / gn.sum() if gn.sum() else float("nan"),
                    "_g": (gn, gd), "_o": (on, od), "_r": (rn, rd)}
        # paired item bootstrap: VS - List and VS - Direct
        def diff(a, b, key):
            na, da = s[a][key]
            nb, db = s[b][key]
            ba = stats.boot_means(na.sum(1, keepdims=True) if na.shape[1] > 1 else na, da.sum(1, keepdims=True) if da.shape[1] > 1 else da, idx)
            bb = stats.boot_means(nb.sum(1, keepdims=True) if nb.shape[1] > 1 else nb, db.sum(1, keepdims=True) if db.shape[1] > 1 else db, idx)
            return float(np.nanmean(ba - bb)), stats.ci(ba - bb)
        dl_i, dl_ci = diff("vs", "list", "_g")
        dd_i, dd_ci = diff("vs", "direct", "_g")
        dl_o, dl_oci = diff("vs", "list", "_o")
        ratio = s["vs"]["cost_per_idea"] / s["list"]["cost_per_idea"] if s["list"]["cost_per_idea"] else float("nan")
        beneficial = (dl_i >= RULE["min_extra_ideas"] and dl_ci[0] > 0 and dl_o >= -RULE["max_originality_drop"]
                      and ratio <= RULE["max_cost_ratio"])
        summary[nm[m]] = {c: {k: v for k, v in s[c].items() if not k.startswith("_")} for c in s}
        summary[nm[m]]["vs_minus_list_ideas"] = [dl_i, dl_ci[0], dl_ci[1]]
        summary[nm[m]]["vs_minus_direct_ideas"] = [dd_i, dd_ci[0], dd_ci[1]]
        summary[nm[m]]["vs_minus_list_orig"] = [dl_o, dl_oci[0], dl_oci[1]]
        summary[nm[m]]["cost_per_idea_ratio"] = ratio
        summary[nm[m]]["beneficial"] = bool(beneficial)
        f3 = lambda k, fmt="%.2f", sc=1: " / ".join(fmt % (s[c][k] * sc) for c in ("direct", "list", "vs"))
        rows_v1.append([nm[m], f3("ideas"), f3("valid", "%.0f", 100), f3("orig"), f3("emb", "%.2f"), f3("known", "%.0f", 100),
                        "$%.3f / $%.3f / $%.3f" % tuple(s[c]["cost_item"] for c in ("direct", "list", "vs")),
                        " / ".join("%.1f" % s[c]["lat"] for c in ("direct", "list", "vs"))])
        rows_v2.append([nm[m], "%+.2f (%+.2f to %+.2f)" % (dl_i, dl_ci[0], dl_ci[1]),
                        "%+.2f (%+.2f to %+.2f)" % (dd_i, dd_ci[0], dd_ci[1]),
                        "%+.2f (%+.2f to %+.2f)" % (dl_o, dl_oci[0], dl_oci[1]), "%.2f×" % ratio,
                        "YES" if beneficial else "no"])
    an = A["vs"]
    an.table("V1_direct_list_vs", ["Model", "Distinct ideas per 5 (Direct / List / VS)", "Valid, %", "Originality (1–5)",
                                   "Embedding diversity", "Real slogan reproduced, %", "Cost per item (5 candidates)",
                                   "Median call latency, s"], rows_v1,
             "%d held-out items, 5 candidates per (model, item). Direct = 5 independent calls (results/final); List and VS = "
             "one call returning 5. Judge: primary only." % len(ids))
    an.table("V2_vs_rule", ["Model", "Δ distinct ideas, VS − List (95% CI)", "Δ distinct ideas, VS − Direct (95% CI)",
                            "Δ originality, VS − List (95% CI)", "Cost per distinct idea, VS ÷ List", "VS beneficial?"],
             rows_v2, "Pre-registered rule (scaled from the proposal's 2-in-20 to 0.5-in-5): beneficial iff Δ ideas ≥ %.1f with "
             "CI above zero, originality drop ≤ %.2f, cost per distinct idea ≤ %.2f× List." % (
                 RULE["min_extra_ideas"], RULE["max_originality_drop"], RULE["max_cost_ratio"]))
    with open(os.path.join(root, "vs", "summary.json"), "w") as fh:
        json.dump({"subset": ids, "n_items": len(ids), "rule": RULE, "models": summary}, fh, indent=2)
    _figure(summary, os.path.join(root, "vs", "figures"), models and [nm[m] for m in models])
    print("\n".join("| " + " | ".join(r) + " |" for r in rows_v1), "\n")
    print("\n".join("| " + " | ".join(r) + " |" for r in rows_v2))


def _figure(summary, fdir, names):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    os.makedirs(fdir, exist_ok=True)
    cols = {"direct": "#c9c8c2", "list": "#8f8e87", "vs": "#C8452C"}
    lab = {"direct": "Direct (5 calls)", "list": "List (1 call)", "vs": "Verbalized sampling (1 call)"}
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.6))
    fig.patch.set_facecolor("#fcfcfb")
    for ax, key, ttl, yl, top in ((axes[0], "ideas", "Distinct ideas among the 5 candidates", "Distinct ideas per item (max 5)", 5.4),
                                  (axes[1], "orig", "Originality of valid candidates", "Mean originality (1–5 scale)", 5.0)):
        xs = np.arange(len(names))
        for k, c in enumerate(("direct", "list", "vs")):
            v = [summary[n][c][key] for n in names]
            pos = xs + (k - 1) * 0.27
            ax.bar(pos, v, width=0.25, color=cols[c], label=lab[c], zorder=3)
            for p, val in zip(pos, v):
                ax.text(p, val + 0.05, "%.1f" % val if key == "ideas" else "%.2f" % val, ha="center", fontsize=10)
        ax.set_xticks(xs)
        ax.set_xticklabels([n.replace(" ", "\n", 1) for n in names], fontsize=11)
        ax.set_ylabel(yl, fontsize=12)
        ax.set_title(ttl, loc="left", fontweight="bold", fontsize=14)
        ax.set_ylim(1 if key == "orig" else 0, top)
        ax.grid(axis="y", color="#dcdbd6", zorder=0)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[0].legend(frameon=False, loc="upper center", bbox_to_anchor=(1.05, -0.12), ncol=3, fontsize=11)
    fig.tight_layout()
    fig.savefig(os.path.join(fdir, "figV_direct_list_vs.png"), dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)
