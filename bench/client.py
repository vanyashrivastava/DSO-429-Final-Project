"""OpenRouter client (stdlib only) and a deterministic offline mock used by the self-test."""
import hashlib
import http.client
import json
import os
import random
import re
import threading
import time
import urllib.error
import urllib.request

API = "https://openrouter.ai/api/v1"
OPTIONAL_PARAMS = ("reasoning", "seed", "top_p", "temperature")


def load_key(project_dir):
    """API key from the environment or a local .env file. Never printed or stored."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key.strip()
    path = os.path.join(project_dir, ".env")
    if os.path.exists(path):
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("OPENROUTER_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def fetch_models():
    """Public listing (no key needed): ids, pricing, supported parameters."""
    req = urllib.request.Request(API + "/models", headers={"User-Agent": "dso429-slogan-bench"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))["data"]


def fetch_embedding_models():
    req = urllib.request.Request(API + "/embeddings/models", headers={"User-Agent": "dso429-slogan-bench"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))["data"]


def _parse(raw):
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return {"error": {"message": raw[:300].decode("utf-8", "replace")}}


def _err_message(data):
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        return str(err.get("message") or err)[:500]
    return str(err)[:500] if err else "unknown error"


class OpenRouter:
    def __init__(self, key, timeout=180, max_attempts=4):
        self.key = key
        self.timeout = timeout
        self.max_attempts = max_attempts

    def _post(self, path, body):
        """Hard wall-clock limit: a response that trickles keep-alive bytes never trips urllib's socket timeout."""
        box = {}

        def go():
            try:
                box["r"] = self._post_once(path, body)
            except Exception as exc:   # never let a worker thread die silently
                box["r"] = (None, {"error": {"message": "network: %r" % (exc,)}})
        t = threading.Thread(target=go, daemon=True)
        t.start()
        t.join(self.timeout + 30)
        return box.get("r") or (None, {"error": {"message": "network: wall-clock timeout after %ds" % (self.timeout + 30)}})

    def _post_once(self, path, body):
        req = urllib.request.Request(
            API + path, data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json",
                     "X-Title": "DSO 429 slogan benchmark", "User-Agent": "dso429-slogan-bench"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, _parse(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, _parse(exc.read())
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            return None, {"error": {"message": "network: %r" % exc}}   # incl. IncompleteRead: retried by chat()

    def chat(self, model, messages, params):
        body = {"model": model, "messages": messages, "usage": {"include": True}}
        body.update(params)
        dropped, attempts, status, data, latency = [], 0, None, {}, 0.0
        while attempts < self.max_attempts:
            attempts += 1
            t0 = time.perf_counter()
            status, data = self._post("/chat/completions", body)
            latency = time.perf_counter() - t0
            choices = data.get("choices") if isinstance(data, dict) else None
            if status == 200 and choices:
                return self._ok(data, body, latency, attempts, dropped)
            message = _err_message(data).lower()
            if status == 400:  # an optional parameter this model rejects: drop it, retry, and say so
                bad = [p for p in OPTIONAL_PARAMS if p in body and p in message]
                if bad:
                    for p in bad:
                        body.pop(p)
                        dropped.append(p)
                    attempts -= 1
                    if len(dropped) > len(OPTIONAL_PARAMS):
                        break
                    continue
            if status in (None, 408, 429, 500, 502, 503, 504) or (status == 200 and not choices):
                time.sleep(min(30, 2 ** attempts) + random.random())
                continue
            break
        return {"text": "", "finish_reason": None, "error": {"status": status, "message": _err_message(data)},
                "latency_s": latency, "attempts": attempts, "params_sent": _public(body), "params_dropped": dropped,
                "usage": {}, "provider": None, "resolved_model": None, "request_id": None}

    def _ok(self, data, body, latency, attempts, dropped):
        choice = data["choices"][0]
        msg = choice.get("message") or {}
        content = msg.get("content") or ""
        if isinstance(content, list):
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        usage = data.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        return {"text": content, "finish_reason": choice.get("finish_reason"), "error": None,
                "latency_s": latency, "attempts": attempts, "params_sent": _public(body), "params_dropped": dropped,
                "usage": {"prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
                          "reasoning_tokens": details.get("reasoning_tokens"), "cost_usd": usage.get("cost")},
                "provider": data.get("provider"), "resolved_model": data.get("model"), "request_id": data.get("id")}

    def embed(self, model, texts):
        t0 = time.perf_counter()
        status, data = self._post("/embeddings", {"model": model, "input": texts})
        if status != 200 or "data" not in data:
            return {"vectors": None, "error": _err_message(data), "cost_usd": None, "latency_s": time.perf_counter() - t0}
        vecs = [d["embedding"] for d in sorted(data["data"], key=lambda d: d.get("index", 0))]
        return {"vectors": vecs, "error": None, "cost_usd": (data.get("usage") or {}).get("cost"),
                "latency_s": time.perf_counter() - t0}


def _public(body):
    return {k: v for k, v in body.items() if k not in ("messages", "usage")}


# ----------------------------------------------------------------------------- mock

FAMOUS = {"Nike": "Just Do It", "Apple": "Think Different", "McDonald's": "I'm Lovin' It",
          "Adidas": "Impossible Is Nothing", "FedEx": "The World On Time"}
TEMPLATES = ["Where {w} meets tomorrow", "Made for the {w} in you", "{c}: {w}, simplified", "Rethink {w}",
             "The smarter way to {w}", "Your {w}, your way", "Every day, a little more {w}", "{w} without limits",
             "Because {w} matters", "Start your {w} story", "Bring {w} home", "Powered by {w}",
             "Real {w}, right now", "Beyond ordinary {w}", "{c} makes {w} yours"]
WORDS = ["moments", "journey", "progress", "comfort", "speed", "trust", "craft", "energy", "freedom", "value"]


def _rng(*parts):
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return random.Random(int(h[:12], 16))


class MockClient:
    """Deterministic fake provider. Only for exercising the pipeline offline; never used for results."""

    def chat(self, model, messages, params):
        user = messages[-1]["content"]
        rng = _rng(model, user, params.get("seed"))
        latency = 0.4 + rng.random() * (3.0 if "flash" in model else 6.0)
        usage = {"prompt_tokens": len(user) // 4 + 60, "completion_tokens": 18 + rng.randint(0, 20),
                 "reasoning_tokens": rng.randint(0, 60), "cost_usd": round(rng.random() * 0.002, 6)}
        base = {"finish_reason": "stop", "error": None, "latency_s": latency, "attempts": 1,
                "params_sent": {k: v for k, v in params.items()}, "params_dropped": [], "usage": usage,
                "provider": "MockProvider", "resolved_model": model + "-mock", "request_id": "mock-%08x" % rng.getrandbits(32)}
        if user.startswith("You are helping measure"):
            return dict(base, text=self._ideas(user))
        if user.startswith("You are an impartial evaluator"):
            return dict(base, text=self._judge(model, user, rng))
        return dict(base, text=self._generate(model, user, rng))

    def _generate(self, model, user, rng):
        company = re.search(r"Company: (.*)", user).group(1)
        industry = re.search(r"Industry: (.*)", user).group(1)
        maxw = int(re.search(r"Maximum (\d+) words", user).group(1))
        inc = re.findall(r'Must include the (?:word|phrase) "(.*?)"', user)
        qual = _rng("q", model).random()
        if industry in ("Tobacco", "Alcoholic beverages") and qual < 0.5 and rng.random() < 0.7:
            return "I can't help with writing advertising for this product."
        if "OK." in user and rng.random() < qual * 0.8:
            return "OK"
        if company in FAMOUS and rng.random() < 0.25 * (1 - qual):
            return FAMOUS[company]
        pool = TEMPLATES[: 4 + int(qual * 10)]
        s = rng.choice(pool).format(c=company, w=rng.choice(WORDS[: 3 + int(qual * 7)]))
        if inc and rng.random() > 0.35 + qual * 0.5:
            pass
        else:
            for w in inc:
                if w.lower() not in s.lower():
                    s = s + " " + w
        if rng.random() < 0.06:
            s = "Here's a slogan: " + s
        words = s.split()
        if len(words) > maxw and rng.random() < 0.8:
            s = " ".join(words[:maxw])
        return s

    def _judge(self, model, user, rng):
        slogan = user.split("CANDIDATE SLOGAN\n", 1)[1].split("\n\nRUBRIC", 1)[0].strip()
        yes = lambda p: "yes" if rng.random() < p else "no"
        out = {"coherent": yes(0.97), "relevant": yes(0.95), "complies": yes(0.9), "faithful": yes(0.88),
               "originality": min(5, max(1, int(round(rng.gauss(2.7, 0.9))))),
               "recognized": "yes" if slogan.lower() in {v.lower() for v in FAMOUS.values()} else "no",
               "recognized_as": "", "note": "mock judgement"}
        return json.dumps(out)

    def _ideas(self, user):
        lines = re.findall(r"^(\d+)\. (.*)$", user, re.M)
        groups = {}
        for num, text in lines:
            key = max(text.lower().split(), key=len)
            groups.setdefault(key, []).append(int(num))
        return json.dumps({"groups": list(groups.values())})

    def embed(self, model, texts):
        vecs = []
        for t in texts:
            rng = _rng("emb", t.lower())
            vecs.append([rng.gauss(0, 1) for _ in range(32)])
        return {"vectors": vecs, "error": None, "cost_usd": 0.00001 * len(texts), "latency_s": 0.1}
