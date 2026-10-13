"""Generation, judging, idea grouping and embeddings. Every stage is resumable and budget-guarded."""
import json
import math
import os
import random
import threading
import zlib
from concurrent.futures import ThreadPoolExecutor

from . import checks, items as itemlib, merge
from .store import Store, now_iso


def all_model_ids(cfg):
    return ([m["id"] for m in cfg["models"]] + [cfg["judges"]["primary"]["id"], cfg["judges"]["probe"]["id"]]
            + [cfg["embedding_model"]])


def load_meta(results_root, cfg, refresh=False):
    """Public /models listing for the configured ids (pricing, supported parameters, canonical slug)."""
    from .client import fetch_models, fetch_embedding_models
    path = os.path.join(results_root, "model_meta.json")
    if os.path.exists(path) and not refresh:
        with open(path) as fh:
            return json.load(fh)
    listing = {m["id"]: m for m in fetch_models()}
    for m in fetch_embedding_models():
        listing.setdefault(m["id"], m)
    meta = {"fetched_at": now_iso(), "models": {}}
    for mid in all_model_ids(cfg):
        m = listing.get(mid)
        if m is None:
            meta["models"][mid] = None
            continue
        meta["models"][mid] = {"canonical_slug": m.get("canonical_slug"), "name": m.get("name"),
                               "pricing": m.get("pricing"), "supported_parameters": m.get("supported_parameters") or [],
                               "context_length": m.get("context_length")}
    os.makedirs(results_root, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(meta, fh, indent=2)
    return meta


def price(meta, model_id):
    m = (meta["models"].get(model_id) or {}).get("pricing") or {}
    try:
        return float(m.get("prompt", 0)), float(m.get("completion", 0))
    except (TypeError, ValueError):
        return 0.0, 0.0


def call_cost(meta, model_id, resp):
    u = resp.get("usage") or {}
    if u.get("cost_usd") is not None:
        return float(u["cost_usd"])
    pin, pout = price(meta, model_id)
    return (u.get("prompt_tokens") or 0) * pin + (u.get("completion_tokens") or 0) * pout


def sampling_params(cfg_gen, meta_entry, seed_val):
    sup = set((meta_entry or {}).get("supported_parameters") or ["temperature", "top_p", "reasoning", "seed"])
    p = {"max_tokens": cfg_gen["max_tokens"]}
    if "temperature" in sup and cfg_gen.get("temperature") is not None:
        p["temperature"] = cfg_gen["temperature"]
    if "top_p" in sup and cfg_gen.get("top_p") is not None:
        p["top_p"] = cfg_gen["top_p"]
    if "reasoning" in sup and cfg_gen.get("reasoning"):
        p["reasoning"] = dict(cfg_gen["reasoning"])
    if "seed" in sup and cfg_gen.get("use_seed_if_supported", False):
        p["seed"] = seed_val
    return p


class Budget:
    def __init__(self, max_usd):
        self.max_usd, self.spent, self.lock, self.stopped = max_usd, 0.0, threading.Lock(), False

    def add(self, usd):
        with self.lock:
            self.spent += usd or 0.0
            if self.max_usd is not None and self.spent > self.max_usd:
                self.stopped = True


def _pool(tasks, worker, workers, label):
    done, total, lock = [0], len(tasks), threading.Lock()

    def wrapped(t):
        try:
            r = worker(t)
        except Exception as exc:   # one bad call must not abort the run; unstored work is redone on resume
            r = None
            print("  worker error, will be retried on resume: %r" % (exc,), flush=True)
        with lock:
            done[0] += 1
            if done[0] % 25 == 0 or done[0] == total:
                print("  %s %d/%d" % (label, done[0], total), flush=True)
        return r
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(wrapped, tasks))


# ------------------------------------------------------------------ estimate

def estimate(cfg, meta, items, n_runs, with_probe=True):
    gen_sys = itemlib.read("prompts/generator_system.txt")
    tasks = sum(len(itemlib.variants_for(i)) for i in items) * len(cfg["models"]) * n_runs
    rows = []
    total_lo = total_hi = 0.0
    sample = [itemlib.generator_messages(i, v) for i in items for v in itemlib.variants_for(i)]
    avg_in = sum(len(m[0]["content"]) + len(m[1]["content"]) for m in sample) / len(sample) / 4.0
    per_model_calls = sum(len(itemlib.variants_for(i)) for i in items) * n_runs
    for m in cfg["models"]:
        pin, pout = price(meta, m["id"])
        lo = per_model_calls * (avg_in * pin + 25 * pout)
        hi = per_model_calls * (avg_in * pin + 450 * pout)
        rows.append(("generate", m["id"], per_model_calls, lo, hi))
        total_lo, total_hi = total_lo + lo, total_hi + hi
    judge_in = 560.0
    for role in ("primary", "probe") if with_probe else ("primary",):
        jid = cfg["judges"][role]["id"]
        pin, pout = price(meta, jid)
        n_calls = tasks
        if role == "probe":   # held-out base outputs only
            n_calls = sum(1 for i in items if i["split"] == "heldout") * len(cfg["models"]) * n_runs
        lo = n_calls * 0.93 * (judge_in * pin + 70 * pout)   # ~7% of outputs are refusals / duplicates
        hi = n_calls * (judge_in * pin + 450 * pout)
        rows.append(("judge-" + role, jid, int(n_calls * 0.93), lo, hi))
        total_lo, total_hi = total_lo + lo, total_hi + hi
    pin, pout = price(meta, cfg["judges"]["primary"]["id"])
    ideas_calls = sum(len(itemlib.variants_for(i)) for i in items) * len(cfg["models"])
    lo, hi = ideas_calls * (170 * pin + 40 * pout), ideas_calls * (170 * pin + 400 * pout)
    rows.append(("ideas", cfg["judges"]["primary"]["id"], ideas_calls, lo, hi))
    total_lo, total_hi = total_lo + lo, total_hi + hi
    return rows, total_lo, total_hi, tasks


# ------------------------------------------------------------------ generation

def generate(cfg, client, meta, items, models, n_runs, store, budget, workers, retry_errors=False, phase="final"):
    done = store.load("generations.jsonl")
    tasks = []
    for it in items:
        for variant in itemlib.variants_for(it):
            for m in models:
                for run in range(1, n_runs + 1):
                    key = "|".join([phase, m["id"], it["id"], variant, str(run)])
                    old = done.get(key)
                    if old and (old.get("error") is None or not retry_errors):
                        continue
                    tasks.append((key, m, it, variant, run))
    random.Random(cfg["seed"]).shuffle(tasks)  # randomised order, interleaving models
    print("generation: %d calls to make (%d already stored)" % (len(tasks), len(done)), flush=True)

    def worker(t):
        if budget.stopped:
            return None
        key, m, it, variant, run = t
        seed_val = zlib.crc32(("%s|%s|%d" % (it["id"], variant, run)).encode()) & 0x7FFFFFFF
        params = sampling_params(cfg["generation"], meta["models"].get(m["id"]), seed_val)
        msgs = itemlib.generator_messages(it, variant)
        resp = client.chat(m["id"], msgs, params)
        budget.add(call_cost(meta, m["id"], resp))
        rec = {"kind": "gen", "key": key, "phase": phase, "model": m["id"], "item_id": it["id"], "variant": variant,
               "run": run, "ts": now_iso(), "raw": resp["text"], "finish_reason": resp["finish_reason"],
               "error": resp["error"], "latency_s": round(resp["latency_s"], 4), "attempts": resp["attempts"],
               "params_sent": resp["params_sent"], "params_dropped": resp["params_dropped"], "usage": resp["usage"],
               "provider": resp["provider"], "resolved_model": resp["resolved_model"], "request_id": resp["request_id"],
               "prompt_sha": merge.sha(json.dumps(msgs))}
        store.append("generations.jsonl", rec)
        return rec
    _pool(tasks, worker, workers, "gen")


# ------------------------------------------------------------------ judging

def _judge_params(cfg, meta_entry):
    j = cfg["judges"]
    sup = set((meta_entry or {}).get("supported_parameters") or ["temperature", "reasoning"])
    p = {"max_tokens": j["max_tokens"]}
    if "temperature" in sup:
        p["temperature"] = j["temperature"]
    if "reasoning" in sup and j.get("reasoning"):
        p["reasoning"] = dict(j["reasoning"])
    return p


def judge(cfg, client, meta, items, store, budget, workers, roles=("primary", "probe")):
    by_id = {i["id"]: i for i in items}
    gens = store.load("generations.jsonl")
    have = store.load("judgments.jsonl")
    tasks, seen = [], set()
    for rec in gens.values():
        item = by_id.get(rec["item_id"])
        if item is None:
            continue
        chk = checks.run_checks(item, rec.get("raw"), rec.get("error"))
        if not merge.needs_judging(chk):
            continue
        prompt = itemlib.judge_prompt(item, rec["variant"], chk["slogan"])
        for role in roles:
            if role == "probe" and not (item["split"] == "heldout" and rec["variant"] == "base"):
                continue  # probe is used only for the self-preference check on held-out base outputs
            jid = cfg["judges"][role]["id"]
            key = merge.judge_key(jid, prompt)
            if key in have or key in seen:
                continue
            seen.add(key)
            tasks.append((key, jid, role, item, rec["variant"], chk["slogan"], prompt))
    random.Random(cfg["seed"] + 1).shuffle(tasks)
    print("judging: %d judge calls to make (%d cached)" % (len(tasks), len(have)), flush=True)

    def worker(t):
        if budget.stopped:
            return None
        key, jid, role, item, variant, slogan, prompt = t
        params = _judge_params(cfg, meta["models"].get(jid))
        parsed, resp, cost = None, None, 0.0
        for attempt in (1, 2):  # one re-ask if the reply is not valid JSON
            resp = client.chat(jid, [{"role": "user", "content": prompt}], params)
            cost += call_cost(meta, jid, resp)
            if resp["error"]:
                break
            parsed = merge.normalize_judgment(itemlib.parse_json_object(resp["text"]))
            if parsed:
                break
        budget.add(cost)
        rec = {"kind": "judge", "key": key, "judge": jid, "role": role, "item_id": item["id"], "variant": variant,
               "slogan": slogan, "ts": now_iso(), "raw": resp["text"], "parsed": parsed, "error": resp["error"],
               "latency_s": round(resp["latency_s"], 4), "usage": resp["usage"], "cost_usd": round(cost, 6),
               "attempts_parse": attempt, "params_sent": resp["params_sent"], "params_dropped": resp["params_dropped"]}
        store.append("judgments.jsonl", rec)
        return rec
    _pool(tasks, worker, workers, "judge")


# ------------------------------------------------------------------ idea grouping (distinct ideas per item)

def ideas(cfg, client, meta, items, store, budget, workers):
    rows, have = merge.build_rows(store, items, cfg)
    jid = cfg["judges"]["primary"]["id"]
    groups = {}
    for r in rows:
        if r["valid"]:
            groups.setdefault(r["ideas_key"], []).append(r)
    tasks = []
    for k, rs in groups.items():
        uniq = []
        for r in sorted(rs, key=lambda r: r["run"]):
            if checks.normalize(r["chk"]["slogan"]) not in [checks.normalize(u) for u in uniq]:
                uniq.append(r["chk"]["slogan"])
        if len(uniq) >= 2 and k not in have:
            tasks.append((k, rs[0]["company"], uniq))
    print("idea grouping: %d calls to make" % len(tasks), flush=True)

    def worker(t):
        if budget.stopped:
            return None
        key, company, slogans = t
        params = _judge_params(cfg, meta["models"].get(jid))
        resp = client.chat(jid, [{"role": "user", "content": itemlib.ideas_prompt(company, slogans)}], params)
        budget.add(call_cost(meta, jid, resp))
        parsed = itemlib.parse_json_object(resp["text"]) or {}
        g = parsed.get("groups")
        ok = isinstance(g, list) and sorted(x for grp in g if isinstance(grp, list) for x in grp) == list(range(1, len(slogans) + 1))
        rec = {"kind": "ideas", "key": key, "slogans": slogans, "groups": g if ok else None, "error": resp["error"],
               "raw": resp["text"], "n_groups": len(g) if ok else None, "ts": now_iso(),
               "cost_usd": round(call_cost(meta, jid, resp), 6), "latency_s": round(resp["latency_s"], 4)}
        store.append("ideas.jsonl", rec)
        return rec
    _pool(tasks, worker, workers, "ideas")


# ------------------------------------------------------------------ embeddings (secondary diversity metric)

def embeddings(cfg, client, store, items):
    rows, _ = merge.build_rows(store, items, cfg)
    have = store.load("embeddings.jsonl", key="hash")
    texts = {}
    for r in rows:
        if r["valid"]:
            n = checks.normalize(r["chk"]["slogan"])
            h = merge.sha(n)
            if h not in have and h not in texts:
                texts[h] = r["chk"]["slogan"]
    hs = list(texts)
    print("embeddings: %d new texts" % len(hs), flush=True)
    for i in range(0, len(hs), 64):
        batch = hs[i:i + 64]
        res = client.embed(cfg["embedding_model"], [texts[h] for h in batch])
        if res["vectors"] is None:
            print("  embedding batch failed:", res["error"])
            continue
        per = (res["cost_usd"] or 0.0) / len(batch)
        for h, v in zip(batch, res["vectors"]):
            store.append("embeddings.jsonl", {"hash": h, "text": texts[h], "vector": v, "cost_usd": per})
