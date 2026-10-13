"""Append-only JSONL stores, so a long run can be interrupted and resumed without losing or repeating work."""
import json
import os
import threading
import time


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


class Store:
    def __init__(self, results_dir):
        self.dir = results_dir
        self.raw = os.path.join(results_dir, "raw")
        os.makedirs(self.raw, exist_ok=True)
        self._lock = threading.Lock()

    def path(self, name):
        return os.path.join(self.raw, name)

    def load(self, name, key="key"):
        out = {}
        p = self.path(name)
        if os.path.exists(p):
            with open(p) as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            rec = json.loads(line)
                        except ValueError:
                            continue  # a half-written last line after a crash
                        out[rec[key]] = rec
        return out

    def append(self, name, rec):
        line = json.dumps(rec, ensure_ascii=False)
        with self._lock:
            with open(self.path(name), "a") as fh:
                fh.write(line + "\n")
                fh.flush()
