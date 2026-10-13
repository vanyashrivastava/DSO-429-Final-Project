"""Small statistics helpers (numpy only). Definitions match PREREGISTRATION.md.

A metric is held as two arrays, num[item, run] and den[item, run]. A run's value is sum(num)/sum(den) over the
items in the subset. Two sources of uncertainty are reported separately:
  * run-to-run spread   - SD / min / max of the run values (same items, fresh samples)
  * item sampling       - bootstrap that resamples whole items, keeping each item's runs together
"""
import numpy as np


def run_values(num, den):
    n, d = num.sum(axis=0), den.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(d > 0, n / d, np.nan)


def summarize(num, den):
    rv = run_values(num, den)
    ok = rv[~np.isnan(rv)]
    if len(ok) == 0:
        return {"mean": np.nan, "sd": np.nan, "min": np.nan, "max": np.nan, "runs": rv}
    return {"mean": float(ok.mean()), "sd": float(ok.std(ddof=1)) if len(ok) > 1 else 0.0,
            "min": float(ok.min()), "max": float(ok.max()), "runs": rv}


def boot_indices(n_items, B, seed):
    return np.random.default_rng(seed).integers(0, n_items, size=(B, n_items))


def boot_means(num, den, idx):
    """Mean-over-runs of the run ratio, for every bootstrap resample of items. Shape (B,)."""
    n = num[idx].sum(axis=1)          # (B, runs)
    d = den[idx].sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(d > 0, n / d, np.nan)
    return np.nanmean(r, axis=1)


def ci(arr, level=0.95):
    a = (1 - level) / 2
    return float(np.nanquantile(arr, a)), float(np.nanquantile(arr, 1 - a))


def separable(sum_a, sum_b, boot_a, boot_b):
    """Rank two models only if the gap beats run-to-run noise of EITHER model AND the paired item bootstrap
    interval for the difference excludes zero."""
    gap = abs(sum_a["mean"] - sum_b["mean"])
    noise = max(sum_a["sd"], sum_b["sd"])
    lo, hi = ci(boot_a - boot_b)
    return bool(gap > noise and (lo > 0 or hi < 0)), (lo, hi), gap, noise


def letter_groups(names, means, sep):
    """Compact letter display. Models sharing a letter are NOT separable. sep[(a,b)] -> bool."""
    order = sorted(names, key=lambda n: -means[n])
    groups = []
    for i in range(len(order)):
        j = i
        while j + 1 < len(order) and all(not sep[(order[a], order[j + 1])] and not sep[(order[j + 1], order[a])]
                                         for a in range(i, j + 1) if a != j + 1):
            j += 1
        grp = tuple(order[i:j + 1])
        if not any(set(grp) <= set(g) for g in groups):
            groups.append(grp)
    letters = {n: "" for n in names}
    for k, g in enumerate(groups):
        for n in g:
            letters[n] += "abcdefghij"[k]
    return letters


def cohen_kappa(a, b):
    a, b = np.asarray(a), np.asarray(b)
    po = float((a == b).mean())
    pe = sum(float((a == c).mean()) * float((b == c).mean()) for c in np.unique(np.concatenate([a, b])))
    return po, (po - pe) / (1 - pe) if pe < 1 else float("nan")


def quad_weighted_kappa(a, b, levels=(1, 2, 3, 4, 5)):
    a, b = np.asarray(a), np.asarray(b)
    k = len(levels)
    obs = np.zeros((k, k))
    for x, y in zip(a, b):
        obs[levels.index(int(x)), levels.index(int(y))] += 1
    n = obs.sum()
    exp = np.outer(obs.sum(1), obs.sum(0)) / n
    w = np.array([[(i - j) ** 2 / (k - 1) ** 2 for j in range(k)] for i in range(k)])
    den = (w * exp).sum()
    return float(1 - (w * obs).sum() / den) if den else float("nan")


def spearman(a, b):
    def rank(x):
        x = np.asarray(x, float)
        order = x.argsort()
        r = np.empty(len(x))
        r[order] = np.arange(len(x))
        for v in np.unique(x):
            m = x == v
            r[m] = r[m].mean()
        return r
    ra, rb = rank(a), rank(b)
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])
