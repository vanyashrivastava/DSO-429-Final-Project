"""Joins raw generations with programmatic checks and judge verdicts into one row per output.

The validity definition lives here and nowhere else (it is frozen in PREREGISTRATION.md):
    valid = programmatic_ok AND coherent AND relevant AND complies AND faithful   (primary judge)
"""
import hashlib
import json

from . import checks, items as itemlib

YESNO = ("coherent", "relevant", "complies", "faithful", "recognized")


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]


def judge_key(judge_id, prompt):
    return sha(judge_id + "\n" + prompt)


def normalize_judgment(obj):
    """Validate a judge reply; return a clean dict or None."""
    if not isinstance(obj, dict):
        return None
    out = {}
    for f in YESNO:
        v = obj.get(f)
        if isinstance(v, bool):
            out[f] = v
        elif isinstance(v, str) and v.strip().lower() in ("yes", "no"):
            out[f] = v.strip().lower() == "yes"
        elif f == "recognized" and v is None:
            out[f] = False
        else:
            return None
    try:
        o = int(round(float(obj.get("originality"))))
    except (TypeError, ValueError):
        return None
    if not 1 <= o <= 5:
        return None
    out["originality"] = o
    out["recognized_as"] = str(obj.get("recognized_as") or "")[:80]
    out["note"] = str(obj.get("note") or "")[:160]
    return out


def needs_judging(chk):
    return not (chk["api_error"] or chk["empty"] or chk["refusal"])


def build_rows(store, items, cfg):
    by_id = {i["id"]: i for i in items}
    gens = store.load("generations.jsonl")
    judgments = store.load("judgments.jsonl")
    ideas = store.load("ideas.jsonl")
    roles = {"j1": cfg["judges"]["primary"]["id"], "j2": cfg["judges"]["probe"]["id"]}
    rows = []
    for rec in gens.values():
        item = by_id.get(rec["item_id"])
        if item is None:
            continue
        chk = checks.run_checks(item, rec.get("raw"), rec.get("error"))
        row = {"key": rec["key"], "model": rec["model"], "item_id": item["id"], "company": item["company"],
               "variant": rec["variant"], "run": rec["run"], "tier": item["tier"], "subtype": item["subtype"],
               "split": item["split"], "raw": rec.get("raw") or "", "latency_s": rec.get("latency_s"),
               "usage": rec.get("usage") or {}, "error": rec.get("error"), "chk": chk,
               "params_sent": rec.get("params_sent"), "params_dropped": rec.get("params_dropped"),
               "provider": rec.get("provider"), "resolved_model": rec.get("resolved_model"), "ts": rec.get("ts")}
        for role, jid in roles.items():
            j = None
            if needs_judging(chk):
                prompt = itemlib.judge_prompt(item, rec["variant"], chk["slogan"])
                jr = judgments.get(judge_key(jid, prompt))
                if jr and jr.get("parsed"):
                    j = jr["parsed"]
            row[role] = j
        row["valid"] = _valid(chk, row["j1"])
        row["valid_j2"] = _valid(chk, row["j2"])
        row["ideas_key"] = "|".join([rec["model"], item["id"], rec["variant"]])
        rows.append(row)
    return rows, ideas


def _valid(chk, j):
    if not chk["programmatic_ok"]:
        return False  # failures are kept as failures
    if j is None:
        return None  # not (yet) judged: excluded from judged metrics and counted separately
    return bool(j["coherent"] and j["relevant"] and j["complies"] and j["faithful"])


def compliant(row, role="j1"):
    """Contextual-brief compliance: all explicit constraints met AND the judge agrees on audience/tone."""
    if not row["chk"]["programmatic_ok"]:
        return False
    j = row[role]
    return None if j is None else bool(j["complies"])
