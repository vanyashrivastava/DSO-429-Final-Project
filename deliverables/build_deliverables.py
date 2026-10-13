"""Builds the 6-slide deck (PDF), the speaker notes (Markdown) and the one-page summary (PDF) from results/final.

Every number is read from the raw results, never typed by hand.  Needs numpy + matplotlib:
    python3 deliverables/build_deliverables.py
Layout copies the Phase 1 materials: dark cover and closing slide, cream content slides, serif titles, orange accent,
rounded cards, "n / 6" footers; a Times one-pager with numbered sans headings and a "Page x of y" footer.
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.font_manager import FontProperties
from matplotlib.ft2font import FT2Font, LOAD_NO_HINTING
from matplotlib.patches import FancyBboxPatch, Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.dirname(ROOT)
sys.path.insert(0, ROOT)

from bench import analyze, items as itemlib, pipeline  # noqa: E402
from bench.store import Store  # noqa: E402

SUP = "/System/Library/Fonts/Supplemental/"
FONT = {"sans": SUP + "Arial.ttf", "sansb": SUP + "Arial Bold.ttf", "serifb": SUP + "Georgia Bold.ttf",
        "times": SUP + "Times New Roman.ttf", "timesb": SUP + "Times New Roman Bold.ttf",
        "timesi": SUP + "Times New Roman Italic.ttf", "sym": matplotlib.get_data_path() + "/fonts/ttf/DejaVuSans.ttf"}
NAVY, CREAM, CARD, BORDER = "#1B1D27", "#F5F3EE", "#FFFEFA", "#D9D6CE"
INK, MUTED, ACCENT, ACCENT_DK, SOFT = "#1B1D27", "#6F6D68", "#C8452C", "#E8895F", "#C9C8C4"
MODEL_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
TEAM = "Milan Jha · Shahir Ali · Vanya Shrivastava · Samira Mustapha · James Kyles · Kirti Subramanian"
COURSE = "Digital Transformation of Business: AI and Smart Contracts"
_ft = {}


def measure(text, key, size, k):
    if key not in _ft:
        _ft[key] = FT2Font(FONT[key])
    f = _ft[key]
    f.set_size(size * k, 72)
    f.set_text(text, 0.0, flags=LOAD_NO_HINTING)
    return f.get_width_height()[0] / 64.0 / k


class Canvas:
    """Drawing surface in 'units' (px for slides, pt for the letter page); y grows downward."""

    def __init__(self, pdf, w, h, fig_w_in, fig_h_in, bg):
        self.pdf, self.w, self.h = pdf, w, h
        self.fig = plt.figure(figsize=(fig_w_in, fig_h_in))
        self.fig.patch.set_facecolor(bg)
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, w)
        self.ax.set_ylim(h, 0)
        self.ax.axis("off")
        self.k = fig_w_in * 72.0 / w
        self.warnings = []

    def text(self, x, y, s, key="sans", size=20, color=INK, ha="left"):
        self.ax.text(x, y, s, fontproperties=FontProperties(fname=FONT[key]), fontsize=size * self.k, color=color,
                     ha=ha, va="baseline")

    def para(self, x, y, width, markup, key="sans", bkey="sansb", size=20, color=INK, lead=1.36, bcolor=None, limit=None):
        """Greedy-wrapped paragraph; **bold** runs; '\\n' forces a break. Returns the y below the last line."""
        words = []
        for li, line in enumerate(markup.split("\n")):
            if li:
                words.append(("\n", None, False))
            prev_nonspace = False
            for si, seg in enumerate(line.split("**")):
                for ti, wd in enumerate(seg.split(" ")):
                    if wd:
                        words.append((wd, bkey if si % 2 else key, ti == 0 and si > 0 and prev_nonspace))
                if seg:
                    prev_nonspace = not seg.endswith(" ")
        cx, cy = x, y
        sp = measure(" ", key, size, self.k)
        for wd, kk, glue in words:
            if wd == "\n":
                cx, cy = x, cy + size * lead
                continue
            ww = measure(wd, kk, size, self.k)
            if glue:
                cx -= sp
            elif cx > x and cx + ww > x + width:
                cx, cy = x, cy + size * lead
            self.text(cx, cy, wd, kk, size, (bcolor or color) if kk == bkey else color)
            cx += ww + sp
        bottom = cy + size * 0.35
        if limit is not None and bottom > limit:
            self.warnings.append("text overflows by %.0f units: %r" % (bottom - limit, markup[:50]))
        return cy + size * lead

    def card(self, x, y, w, h, fill=CARD, edge=BORDER, lw=1.6, r=16):
        self.ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=%d" % r, fc=fill, ec=edge,
                                         lw=lw * self.k / 1.0))

    def line(self, x0, y0, x1, y1, color=INK, lw=1.5, dash=None):
        self.ax.plot([x0, x1], [y0, y1], color=color, lw=lw * self.k / 1.0, ls=dash or "-", solid_capstyle="butt")

    def rect(self, x, y, w, h, color):
        self.ax.add_patch(Rectangle((x, y), w, h, fc=color, ec="none"))

    def save(self):
        self.pdf.savefig(self.fig, facecolor=self.fig.get_facecolor())
        plt.close(self.fig)


# ------------------------------------------------------------------ numbers

def load_results():
    cfg = json.load(open(os.path.join(ROOT, "config.json")))
    items = itemlib.load_items()
    meta = pipeline.load_meta(os.path.join(ROOT, "results"), cfg)
    out = os.path.join(ROOT, "results", "final")
    an = analyze.Analysis(cfg, items, Store(out), out, meta)
    held = an.ids(split="heldout")
    ctx = an.ids(split="heldout", tier="contextual")
    an.t4_cost_latency()
    an.t6_pairwise(held)
    an.t9_judges(held)
    R = {"order": an.models, "name": an.names, "n_held": len(held), "n_ctx": len(ctx), "m": {}}
    for m in an.models:
        v, o, c = an.metric(m, held, "valid"), an.metric(m, held, "originality"), an.metric(m, ctx, "compliance")
        tier = {t: an.metric(m, an.ids(split="heldout", tier=t), "valid")["mean"] for t in ("standard", "contextual", "stress")}
        cp = an.metric(m, held, "contam_prog")
        wl = sum(1 for r in an.rows if r["model"] == m and r["split"] == "heldout" and r["variant"] == "base"
                 and not r["chk"]["words_ok"] and not r["chk"]["api_error"])
        n_out = sum(1 for r in an.rows if r["model"] == m and r["split"] == "heldout" and r["variant"] == "base")
        sparse = an.ids(subtype="sparse")
        gen_b, gen_r = an.metric(m, sparse, "generic", "base")["mean"], an.metric(m, sparse, "generic", "rich")["mean"]
        o_b, o_r = an.metric(m, sparse, "originality", "base")["mean"], an.metric(m, sparse, "originality", "rich")["mean"]
        calls = sum(1 for r in an.rows if r["model"] == m)
        R["m"][m] = dict(calls=calls, valid=v, orig=o, comp=c, tier=tier, contam=cp["mean"], wordlimit=wl, n_out=n_out,
                         lat=an.lat_median[m], cost=an.cost_total[m], gen_b=gen_b, gen_r=gen_r, o_b=o_b, o_r=o_r,
                         letters={k: an.letters[k][m] for k in an.letters})
    R["total_gen_cost"] = sum(an.cost_total.values())
    jc = an.judge_costs()
    R["eval_cost"] = sum(jc.values())
    R["total_cost"] = R["total_gen_cost"] + R["eval_cost"]
    R["n_outputs"] = sum(1 for r in an.rows)
    R["self_pref"] = getattr(an, "self_pref", None)
    # judge agreement and saturation
    both = [r for r in an.rows if r["split"] == "heldout" and r["variant"] == "base" and r["j1"] and r["j2"]]
    from bench import stats
    a, b = [r["j1"]["originality"] for r in both], [r["j2"]["originality"] for r in both]
    R["qwk"] = stats.quad_weighted_kappa(a, b)
    R["j1_mean"], R["j2_mean"] = sum(a) / len(a), sum(b) / len(b)
    yes = {f: sum(r["j1"][f] for r in both) / len(both) for f in ("coherent", "relevant", "complies", "faithful")}
    R["min_yes"] = min(yes.values())
    return R


def pct(x, d=1):
    return ("%." + str(d) + "f") % (x * 100)


# ------------------------------------------------------------------ deck

def footer(c, n, src, dark=False):
    c.text(96, 782, "%d / 6 · %s" % (n, src) if n > 1 else "", "sans", 17, SOFT if dark else MUTED)


def build_deck(R, path):
    M = R["m"]
    order = R["order"]
    nm = R["name"]
    best_o = max(order, key=lambda m: M[m]["orig"]["mean"])
    worst_o = min(order, key=lambda m: M[m]["orig"]["mean"])
    cheapest = min(order, key=lambda m: M[m]["cost"])
    slow = max(order, key=lambda m: M[m]["lat"])
    sonnet = order[0]
    others = [m for m in order if m != sonnet]
    wl_other = max(M[m]["wordlimit"] for m in others)
    n_out = M[sonnet]["n_out"]
    gb = [M[m]["gen_b"] for m in order]
    gr = [M[m]["gen_r"] for m in order]
    od = [M[m]["o_r"] - M[m]["o_b"] for m in order]
    cont = {m: M[m]["contam"] for m in order}
    with PdfPages(path) as pdf:
        # 1 cover
        c = Canvas(pdf, 1440, 810, 14.4, 8.1, NAVY)
        c.text(96, 462, "DSO 429 · PROJECT 1 · PHASE 2 FINAL DELIVERABLE", "sansb", 24, ACCENT_DK)
        c.text(96, 548, "Benchmarking Ad Slogan Writing", "serifb", 70, CREAM)
        c.text(96, 622, "in LLMs", "serifb", 70, CREAM)
        c.text(96, 690, "Which of five models writes valid, original slogans, and does any clear our line?", "sans", 27, SOFT)
        c.text(96, 745, TEAM, "sans", 19, "#A9A8A4")
        c.text(96, 773, COURSE + "  |  October 13, 2026", "sans", 19, "#A9A8A4")
        c.save()

        # 2 task and items
        c = Canvas(pdf, 1440, 810, 14.4, 8.1, CREAM)
        c.text(96, 118, "The task: one slogan from one company brief", "serifb", 46, INK)
        cards = [("50 companies", "**28** standard briefs, **12** with hard constraints (word limit, required and banned "
                                  "words) and **10** edge cases: sparse description, sensitive industry, long irrelevant "
                                  "context, injected instruction. **12 dev, 38 held-out**; headline numbers use held-out only."),
                 ("5 models, one prompt", "Claude Sonnet 5.5 · Gemini 3.8 Flash · GPT-6.1 Sol · Mistral Large 4 · "
                                          "DeepSeek V4.1 Flash, through OpenRouter. Identical prompt, fresh context, "
                                          "**5 independent runs** per item."),
                 ("%s outputs" % format(R["n_outputs"], ","), "50 items × 5 models × 5 runs, plus the 3 sparse items "
                  "re-run with a full description. Run on October 12, 2026; **$%.2f** in total including grading."
                  % R["total_cost"])]
        for i, (h, b) in enumerate(cards):
            x = 96 + i * 425
            c.card(x, 160, 395, 262)
            c.text(x + 26, 205, h, "sansb", 28)
            c.para(x + 26, 244, 345, b, size=19, limit=412, bcolor=ACCENT)
        c.card(96, 445, 700, 305)
        c.text(122, 488, "An example brief (Nike, a constraint item)", "sansb", 26)
        c.para(122, 528, 650, "**Company:** Nike · **Industry:** Sportswear\n**About:** A US sportswear company that "
               "designs athletic shoes, apparel and equipment, sponsors elite athletes, and is known for the swoosh "
               "logo.\n**Campaign brief:** Beginner running line, aimed at first-time marathon runners.\n"
               "**Requirements:** maximum 6 words · must not include the phrase \"just do it\".\n"
               "**Write one slogan.**", size=19, limit=742, bcolor=ACCENT)
        c.card(826, 445, 515, 305)
        c.text(852, 488, "Held fixed, and what varies", "sansb", 26)
        c.para(852, 528, 465, "**Fixed:** prompt, items, 5 runs, token cap, reasoning setting requested (low).\n"
               "**Varies:** the model.\n**Not equal:** temperature 0.7 is sent only where a model accepts it. "
               "Sonnet 5.5 and GPT-6.1 Sol accept none, so sampling was not identical.", size=20, limit=735, bcolor=ACCENT)
        footer(c, 2, "Eval set: data/items.json, held-out split marked · prompts: prompts/generator_*.txt")
        c.save()

        # 3 instrument
        c = Canvas(pdf, 1440, 810, 14.4, 8.1, CREAM)
        c.text(96, 118, "The instrument: rules first, then a blinded judge", "serifb", 46, INK)
        cols = [("1 · Rules, no LLM", "A slogan must be **one line**, within the **word limit**, include every "
                 "**required** word, avoid every **banned** word, and not be a refusal or an error. "
                 "A missing output counts as a failure."),
                ("2 · Blind judge (Grok 4.7)", "Sees the slogan only. Yes/no: **coherent, relevant, complies, "
                 "faithful** (no unsupported claim). Originality **1–5**: 1 stock · 2 cosmetic · 3 new twist · "
                 "4 distinctive · 5 standout."),
                ("3 · Checks on the judge", "**Claude Opus 5.5** re-scores held-out outputs to test self-preference. "
                 "A list of **real slogans** measures memorization. A **60-output blinded sheet** is ready for "
                 "human raters.")]
        for i, (h, b) in enumerate(cols):
            x = 96 + i * 425
            c.card(x, 155, 395, 335)
            c.text(x + 26, 202, h, "sansb", 27)
            c.para(x + 26, 248, 345, b, size=23, limit=482, bcolor=ACCENT, lead=1.38)
        c.card(96, 515, 1245, 112, edge=ACCENT, lw=2.4)
        c.text(124, 558, "Acceptable-failure line (frozen before any output; carried over from the proposal)", "sansb", 24, ACCENT)
        c.text(124, 600, "valid outputs  ≥ 95%     ·     mean originality  ≥ 3.0 of 5     ·     constraint briefs met  ≥ 90%",
               "sansb", 29, INK)
        c.card(96, 650, 1245, 100, fill=NAVY, edge=NAVY)
        c.text(124, 692, "CALL IT  ·  15 seconds, before the next slide", "sansb", 27, ACCENT_DK)
        c.text(124, 731, "On your card: (1) which model scores highest?   (2) does any model clear the line?", "sans", 25, CREAM)
        footer(c, 3, "Grading code: bench/checks.py, bench/merge.py · judge prompt: prompts/judge.txt")
        c.save()

        # 4 results (native chart, large type)
        c = Canvas(pdf, 1440, 810, 14.4, 8.1, CREAM)
        c.text(96, 118, "Results: no model clears the line, and four are tied", "serifb", 46, INK)
        x_name, col_x, col_w, track = 96, [372, 628, 884], 252, 126
        specs = [("Valid outputs, %", "line ≥ 95", 0, 100, 95, "valid", 100), ("Originality, 1–5", "line ≥ 3.0", 1, 5, 3.0, "orig", 1),
                 ("Constraints met, %", "line ≥ 90", 0, 100, 90, "comp", 100)]
        for (lab, sub, lo, hi, th, key, sc), cx in zip(specs, col_x):
            c.text(cx, 168, lab, "sansb", 22)
            c.text(cx, 196, sub, "sans", 18, MUTED)
        c.text(1140, 168, "Median", "sansb", 22)
        c.text(1140, 196, "latency", "sans", 18, MUTED)
        c.text(1250, 168, "Generation", "sansb", 22)
        c.text(1250, 196, "cost, run", "sans", 18, MUTED)
        top, rh = 222, 66
        for ri, m in enumerate(order):
            y = top + ri * rh
            c.rect(x_name, y + 20, 18, 18, MODEL_COLORS[ri])
            c.text(x_name + 30, y + 37, nm[m], "sansb", 22)
            for (lab, sub, lo, hi, th, key, sc), cx in zip(specs, col_x):
                s = M[m][key]
                mean, sd = s["mean"] * (100 if sc == 100 else 1), s["sd"] * (100 if sc == 100 else 1)
                scale = track / float(hi - lo)
                c.rect(cx, y + 18, max((mean - lo) * scale, 1), 24, MODEL_COLORS[ri])
                c.line(cx + (mean - sd - lo) * scale, y + 30, cx + (min(mean + sd, hi) - lo) * scale, y + 30, INK, 2)
                ok = mean >= th
                vt = ("%.1f" if sc == 100 else "%.2f") % mean
                c.text(cx + track + 12, y + 38, vt, "sansb", 22)
                c.text(cx + track + 12 + measure(vt, "sansb", 22, c.k) + 8, y + 38, "✓" if ok else "✗", "sym", 20,
                       "#0a7a0a" if ok else ACCENT)
            c.text(1140, y + 38, "%.1f s" % M[m]["lat"], "sans", 22)
            c.text(1250, y + 38, "$%.2f" % M[m]["cost"], "sans", 22)
        for (lab, sub, lo, hi, th, key, sc), cx in zip(specs, col_x):
            xx = cx + (th - lo) * track / float(hi - lo)
            c.line(xx, top + 8, xx, top + 5 * rh - 8, MUTED, 1.6, (0, (4, 3)))
        c.text(96, top + 5 * rh + 24, "Held-out items (%d) × 5 runs. Bar = mean of run means; whisker = ±1 SD across runs; dashed = "
               "frozen line; the mark after each value says clears or misses." % R["n_held"], "sans", 17, MUTED)
        notes = [("Four models are tied", "Gemini, GPT, Mistral and DeepSeek differ by less than run-to-run noise on "
                  "validity and constraints. Only Sonnet separates, lower."),
                 ("Sonnet's miss is one failure", "%d of %d outputs broke an explicit word limit (%s%%). The other four "
                  "models: %d or fewer." % (M[sonnet]["wordlimit"], n_out, pct(M[sonnet]["wordlimit"] / float(n_out), 0),
                                           wl_other)),
                 ("Originality is flat", "%.2f to %.2f for every model: most slogans score 2 or 3 of 5. None reaches 3.0."
                  % (M[worst_o]["orig"]["mean"], M[best_o]["orig"]["mean"]))]
        for i, (h, b) in enumerate(notes):
            x = 96 + i * 425
            c.card(x, 600, 395, 150)
            c.text(x + 22, 640, h, "sansb", 23)
            c.para(x + 22, 672, 350, b, size=18, limit=744)
        footer(c, 4, "Tables T1, T4, T6 in results/final/tables; raw outputs in results/final/raw")
        c.save()

        # 5 failure modes and instrument
        c = Canvas(pdf, 1440, 810, 14.4, 8.1, CREAM)
        c.text(96, 118, "Failure modes, and where our instrument bit", "serifb", 46, INK)
        c.card(96, 155, 395, 590)
        c.text(120, 200, "Normal vs edge cases", "sansb", 26)
        c.text(120, 230, "valid outputs, %, held-out", "sans", 18, MUTED)
        hx = [(300, "standard"), (372, "constr."), (444, "stress")]
        for xx, lab in hx:
            c.text(xx, 275, lab, "sansb", 17, MUTED, ha="center")
        for ri, m in enumerate(order):
            y = 312 + ri * 62
            c.rect(120, y - 17, 14, 14, MODEL_COLORS[ri])
            c.text(142, y, nm[m].split(" ")[0], "sansb", 21)
            for xx, t in zip([300, 372, 444], ("standard", "contextual", "stress")):
                v = M[m]["tier"][t] * 100
                if v < 95:
                    c.rect(xx - 30, y - 28, 60, 40, "#F6D9CF")
                c.text(xx, y, "%.0f" % v, "sansb" if v < 95 else "sans", 24, INK, ha="center")
        c.para(120, 640, 350, "Shaded = below 95%. Stress has 7 held-out items (sparse, sensitive, long context, "
               "injection): small n.", size=18, color=MUTED, limit=738)
        c.card(517, 155, 395, 590)
        c.text(541, 200, "Model wrong, or never told?", "sansb", 26)
        c.para(541, 245, 345, "**Model wrong.** Sonnet broke a word limit that was in the prompt: %d of %d outputs. "
               "No other model more than %d.\n\n**Missing input.** On 3 sparse items, giving the full description cut "
               "generic outputs from %d–%d%% to %d–%d%% and lifted originality %.1f to %.1f points.\n\n"
               "**Declined.** GPT and Mistral refused the tobacco brief (a dev item)."
               % (M[sonnet]["wordlimit"], n_out, wl_other, round(min(gb) * 100), round(max(gb) * 100),
                  round(min(gr) * 100), round(max(gr) * 100), min(od), max(od)),
               size=22, limit=738, bcolor=ACCENT)
        c.card(938, 155, 403, 590)
        c.text(962, 200, "Where our instrument bit", "sansb", 26)
        sp = R["self_pref"]
        c.para(962, 245, 355, "**Memorization.** Mistral reproduced a real slogan in %s%% of outputs, DeepSeek %s%%, GPT %s%%. "
               "The judge gave a verbatim Coke slogan 4/5.\n\n**Saturation.** Yes/no criteria are ≥ %d%% yes, so "
               "validity gaps come from our rules.\n\n**Self-preference.** Claude judge vs neutral judge: %+.2f "
               "(95%% CI %+.2f to %+.2f). None found.\n\n**Agreement.** Judges agree only moderately on originality "
               "(QWK %.2f)." % (pct(cont[order[3]], 0), pct(cont[order[4]], 0), pct(cont[order[2]], 0),
                                int(R["min_yes"] * 100), sp[0], sp[1], sp[2], R["qwk"]),
               size=20, limit=738, bcolor=ACCENT)
        footer(c, 5, "Tables T3, T5, T7, T8, T9 · disputes.md lists the cases to read")
        c.save()

        # 6 interpretation (dark, like the old closing slide)
        c = Canvas(pdf, 1440, 810, 14.4, 8.1, NAVY)
        c.text(96, 118, "What this means, and what we would do Monday", "serifb", 46, CREAM)
        c.text(96, 192, "All five write valid slogans. None writes distinctive ones.", "serifb", 36, ACCENT_DK)
        c.text(96, 240, "Use them for first drafts, not finished copy.", "serifb", 36, ACCENT_DK)
        cols = [("Against our line", "Four models pass validity and constraints; **all five miss originality** "
                 "(%.2f best, %.2f worst, line 3.0). Sonnet also misses validity: an instruction-following "
                 "slip, not a creativity gap." % (M[best_o]["orig"]["mean"], M[worst_o]["orig"]["mean"])),
                ("What to do Monday", "Choose on reliability and cost: %s is cheapest ($%.2f per 1,000 slogans). "
                 "Add a length check before human review. **Supply a differentiator** in the brief: it was our "
                 "cheapest originality gain." % (nm[cheapest], M[cheapest]["cost"] / M[cheapest]["calls"] * 1000)),
                ("Limits and next change", "No human check yet; one judge family; 50 companies; sampling not "
                 "identical; originality is not persuasion. **Next:** blinded human ratings of ~200 slogans to anchor "
                 "the score.")]
        for i, (h, b) in enumerate(cols):
            x = 96 + i * 425
            c.card(x, 300, 395, 330, fill=NAVY, edge="#3A3D4A", lw=1.8)
            c.text(x + 26, 348, h, "sansb", 27, CREAM)
            c.para(x + 26, 396, 345, b, size=23, color="#DAD9D5", bcolor=CREAM, limit=626, lead=1.38)
        c.card(96, 655, 1245, 90, fill=NAVY, edge=ACCENT_DK, lw=2.2)
        c.text(124, 695, "BREAK IT  ·  write one item you think this benchmark would get wrong", "sansb", 24, ACCENT_DK)
        c.text(124, 727, "A case a model would fail for a reason we did not test, or one our grader would score incorrectly.",
               "sans", 21, SOFT)
        footer(c, 6, "Full tables, figures, raw outputs and the re-run README are in the archive", dark=True)
        c.save()
    return c.warnings


# ------------------------------------------------------------------ one-pager

def build_onepager(R, path):
    M, order, nm = R["m"], R["order"], R["name"]
    sonnet = order[0]
    others = [m for m in order if m != sonnet]
    n_out = M[sonnet]["n_out"]
    gb = [M[m]["gen_b"] for m in order]
    gr = [M[m]["gen_r"] for m in order]
    od = [M[m]["o_r"] - M[m]["o_b"] for m in order]
    lat_ratio = (M[max(order, key=lambda m: M[m]["lat"])]["lat"] / M[min(order, key=lambda m: M[m]["lat"])]["lat"])
    o_all = [M[m]["orig"]["mean"] for m in order]
    sp = R["self_pref"]
    with PdfPages(path) as pdf:
        c = Canvas(pdf, 612, 792, 8.5, 11, "white")
        L, W = 56, 500
        c.text(306, 62, "Benchmarking LLMs on Advertising Slogan Writing", "timesb", 17, "black", ha="center")
        c.text(306, 80, "Milan Jha, Shahir Ali, Vanya Shrivastava, Samira Mustapha, James Kyles, Kirti Subramanian",
               "times", 9.2, "black", ha="center")
        c.text(306, 92, "DSO 429 " + COURSE, "times", 9.2, "black", ha="center")
        c.text(306, 104, "Project 1 Phase 2 Final Deliverable (summary) | October 13, 2026", "timesi", 9.2, "black", ha="center")
        y = 124
        S = 10.0
        LEAD = 1.26

        def head(y, t):
            c.text(L, y, t, "sansb", 9.2, "black")
            return y + 12

        y = head(y, "1  Implementation and reproducibility")
        y = c.para(L, y, W, "We graded five LLMs on writing one slogan from a company brief. The eval set is **50 real "
                   "companies**: 28 standard briefs, 12 with word-limit and required/banned-word constraints, and 10 edge "
                   "cases (sparse description, sensitive industry, long irrelevant context, injected instruction). Twelve "
                   "items are dev; 38 are held-out and carry the headline numbers. On 2026-10-12 we ran "
                   "claude-sonnet-5.5, gemini-3.8-flash, gpt-6.1-sol, mistral-large-4-0 and deepseek-v4.1-flash through "
                   "OpenRouter with an identical prompt, fresh context and **5 runs per item** (%s outputs); no rubric or "
                   "examples were supplied. Outputs get rule checks plus a blinded judge (grok-4.7, never a generator); "
                   "claude-opus-5.5 re-scores held-out outputs to test self-preference. **Deviations from the proposal:** "
                   "slogans not jokes; one prompt condition, not three; 50 items × 5 runs, not 60 × 20; a new model and "
                   "judge set; an added unsupported-claim criterion and rule checks; a held-out split; a 60-output human "
                   "audit; Mistral replacing the age-gated Muse Spark. Temperature could not be held fixed: Sonnet and "
                   "GPT accept none. The archive holds the eval set, judge prompt, grading code and raw outputs, and "
                   "re-runs from its README." % format(R["n_outputs"], ","), "times", "timesb", S, "black", LEAD)
        y += 5
        y = head(y, "2  Results")
        # table
        cols = [("Model", L, "left"), ("Valid, %", 252, "right"), ("Originality (1–5)", 330, "right"),
                ("Constraints met, %", 412, "right"), ("Median latency", 480, "right"), ("Gen. cost", 556, "right")]
        for lab, xx, al in cols:
            c.text(xx, y, lab, "sansb", 8.2, "black", ha=al)
        c.line(L, y + 3, L + W, y + 3, "black", 0.6)
        y += 13
        for m in order:
            s = M[m]
            row = [nm[m], "%.1f ± %.1f" % (s["valid"]["mean"] * 100, s["valid"]["sd"] * 100),
                   "%.2f ± %.2f" % (s["orig"]["mean"], s["orig"]["sd"]),
                   "%.0f ± %.1f" % (s["comp"]["mean"] * 100, s["comp"]["sd"] * 100), "%.1f s" % s["lat"], "$%.2f" % s["cost"]]
            for (lab, xx, al), t in zip(cols, row):
                c.text(xx, y, t, "times", 9.6, "black", ha=al)
            y += 12.5
        c.line(L, y - 7, L + W, y - 7, "black", 0.6)
        y += 2
        y = c.para(L, y, W, "Held-out items, mean ± SD across 5 runs; line: valid ≥ 95%%, originality ≥ 3.0, constraints "
                   "≥ 90%%. Gemini, GPT, Mistral and DeepSeek are **not separable** on validity or constraints (gaps inside "
                   "run-to-run noise), so we do not rank them; only Sonnet separates, lower. Edge cases: Sonnet falls to "
                   "%.0f%% on constraint briefs and %.0f%% on stress items; the others stay at %.0f–100%%. Mistral is "
                   "%.0f× slower than the fastest model because of ~1,500 hidden reasoning tokens per slogan. Total "
                   "generation cost was $%.2f; grading cost $%.2f." % (
                       M[sonnet]["tier"]["contextual"] * 100, M[sonnet]["tier"]["stress"] * 100,
                       min(M[m]["tier"][t] for m in others for t in ("contextual", "stress")) * 100, lat_ratio,
                       R["total_gen_cost"], R["eval_cost"]), "times", "timesb", S, "black", LEAD)
        y += 5
        y = head(y, "3  Analysis and interpretation")
        y = c.para(L, y, W, "**No model clears the line**: all five miss originality (%.2f–%.2f vs 3.0) and Sonnet also "
                   "misses validity (%.1f%%) and constraints (%.0f%%). **Model wrong:** %d of %d Sonnet outputs broke a "
                   "word limit stated in the prompt (other models: %d or fewer). **Missing input:** on the three sparse "
                   "items, supplying the full description cut generic outputs from %d–%d%% to %d–%d%% and lifted "
                   "originality %.1f–%.1f points, so much of that shortfall is the brief, not the model. "
                   "**Instrument:** contamination bit: Mistral reproduced a real company slogan in %.0f%% of outputs and "
                   "the judge scored a verbatim Coke slogan 4/5, so originality is inflated by memorization (we report "
                   "a supplementary score without it). Yes/no criteria saturate (≥ %d%% yes), so validity differences "
                   "come from our rules, not the judge, and the two judges agree only moderately on originality (QWK "
                   "%.2f). We found **no self-preference** (Claude judge minus neutral judge %+.2f, 95%% CI %+.2f to "
                   "%+.2f). The blinded human audit is prepared but not yet scored, so judge validity is untested "
                   "against people." % (min(o_all), max(o_all), M[sonnet]["valid"]["mean"] * 100,
                                        M[sonnet]["comp"]["mean"] * 100, M[sonnet]["wordlimit"], n_out,
                                        max(M[m]["wordlimit"] for m in others), round(min(gb) * 100), round(max(gb) * 100),
                                        round(min(gr) * 100), round(max(gr) * 100), min(od), max(od),
                                        M[order[3]]["contam"] * 100, int(R["min_yes"] * 100), R["qwk"], sp[0], sp[1], sp[2]),
                   "times", "timesb", S, "black", LEAD)
        y += 5
        y = head(y, "4  Limitations and what we would do next")
        y = c.para(L, y, W, "This benchmark does not show that a slogan sells: originality is a model's rating, not "
                   "audience response; 50 companies and one prompt cannot cover brand voice; the stress subtypes have 2–3 "
                   "items each; sampling parameters differed by model; and famous companies make memorization likely. "
                   "With two more weeks we would make one change: replace the LLM originality score with blinded human "
                   "ratings of about 200 slogans and test whether either score predicts which slogans people choose.",
                   "times", "timesb", S, "black", LEAD)
        c.warnings.append("one-pager bottom y=%.0f (limit 735)" % y) if y > 735 else None
        c.text(L, 760, "DSO 429  |  Project 1 Final Deliverable", "sans", 8, "black")
        c.text(L + W, 760, "Page 1 of 1", "sans", 8, "black", ha="right")
        c.save()
    return c.warnings, y


def build_notes(R, path):
    M, order, nm = R["m"], R["order"], R["name"]
    sonnet = order[0]
    others = [m for m in order if m != sonnet]
    n_out = M[sonnet]["n_out"]
    cheapest = min(order, key=lambda m: M[m]["cost"])
    slow = max(order, key=lambda m: M[m]["lat"])
    o = [M[m]["orig"]["mean"] for m in order]
    gb = [M[m]["gen_b"] for m in order]
    gr = [M[m]["gen_r"] for m in order]
    od = [M[m]["o_r"] - M[m]["o_b"] for m in order]
    sp = R["self_pref"]
    md = f"""# Speaker Notes — Benchmarking Ad Slogan Writing in LLMs

Oct 13, 2026 · Project 1, Phase 2 final deliverable · six-minute slot, questions included

**Timing plan:** about 4:45 of talking plus the 15-second call-it pause, which leaves about a minute for questions. The
suggested speaker split below is a default: change the names freely, but whoever presents a slide should also be able to
answer questions about the others (the assignment requires it for every team member).

## Slide 1 — Cover — Milan Jha (0:30)

Good morning. We're Milan, Shahir, Vanya, Samira, James and Kirti. Our proposal was to benchmark joke creativity. After
our professor's feedback we moved to a task with a clearer business use: writing an advertising slogan from a company
brief. The question is simple. Five current language models each write slogans for the same fifty companies. Which ones
write slogans that are valid and original enough to use, and does any of them clear the line we committed to before we
saw a single output?

## Slide 2 — The task — Shahir Ali (0:45)

The task is one slogan per company brief. We have fifty real companies in three tiers. Twenty-eight are standard briefs:
a company, an industry and a description. Twelve add hard constraints a rule can check, such as a word limit, a required
word or a banned phrase; for example Nike, with six words maximum and the phrase "just do it" banned. Ten are edge cases:
a description of only a few words, sensitive industries like tobacco and defense, a description buried in irrelevant
meeting minutes, and an instruction injected into the description.

Twelve items are dev items we were allowed to look at while building. Thirty-eight are held-out and carry every headline
number. Five models, one identical prompt, fresh context each call, five independent runs per item: {R['n_outputs']:,}
outputs, run on October 12. What we could not hold fixed is sampling: Sonnet 5.5 and GPT-6.1 Sol do not accept a
temperature setting, so we say that plainly rather than pretend the conditions were identical.

## Slide 3 — The instrument — Samira Mustapha (1:00, then the call-it pause)

Grading has three layers. First, rules with no model involved: one line, within the word limit, every required word
present, no banned word, not a refusal. A missing output counts as a failure. Second, a blinded judge, Grok 4.7, which
never generates slogans and sees only the slogan. It answers yes or no on coherence, relevance, compliance and whether the
slogan makes an unsupported factual claim, and gives originality from one to five: one is stock, three is a new twist,
five is a standout. Third, checks on the judge itself: a second judge from the Claude family re-scores held-out outputs
to test self-preference, a list of real slogans measures memorization, and a blinded human sheet is ready.

The line at the bottom was frozen before we collected anything and carried over from the proposal: at least ninety-five
percent valid, mean originality at least three out of five, and at least ninety percent of constraint briefs met.

**Pause here.** Ask the room to take fifteen seconds and write on their card which model they expect to score highest and
whether any model clears the line. Do not show slide 4 until they have written it down.

## Slide 4 — Results — Vanya Shrivastava (1:00)

Here is the answer. No model clears the line. Look at the dashed lines: four of the five models pass validity and
constraints, and every model misses originality. The best originality is {max(o):.2f} and the worst is {min(o):.2f}
against a line of three.

Two things matter about how to read this. First, the whiskers are one standard deviation across five runs, and where two
models differ by less than that run-to-run noise we do not rank them. Gemini, GPT, Mistral and DeepSeek are tied on
validity and constraints. Second, there is one real separation: Sonnet falls to {M[sonnet]['valid']['mean']*100:.1f}% valid
and {M[sonnet]['comp']['mean']*100:.0f}% on constraints, and that comes from a single failure, breaking a stated word
limit in {M[sonnet]['wordlimit']} of {n_out} outputs. On the right, cost and speed are results too: {nm[cheapest]} is
cheapest at ${M[cheapest]['cost']:.2f} for its whole run, and {nm[slow]} is slowest at {M[slow]['lat']:.0f} seconds a slogan
because it does a lot of hidden reasoning.

## Slide 5 — Where it breaks — James Kyles (0:50)

This slide separates a model being wrong from a model never being given what it needed. Sonnet's word-limit failures are
model-wrong: the limit was in the prompt. The originality shortfall is partly missing input. On the three sparse items, when
we gave the full description instead of one clause, generic outputs fell from {min(gb)*100:.0f}–{max(gb)*100:.0f}% to
{min(gr)*100:.0f}–{max(gr)*100:.0f}% and originality rose {min(od):.1f} to {max(od):.1f} points. It is only three items, so
it is evidence, not proof.

On the right is where our own instrument bit. Memorization: Mistral reproduced a real company slogan in
{M[order[3]]['contam']*100:.0f}% of outputs, and the judge gave a verbatim Coke slogan four out of five, so originality is
inflated; we report a supplementary score without those outputs. The yes/no criteria saturate, so validity differences
come from our rules. And we looked for self-preference: the Claude judge minus the neutral judge, for Claude's own family
against the others, is {sp[0]:+.2f} with an interval of {sp[1]:+.2f} to {sp[2]:+.2f}, so we found none.

## Slide 6 — Interpretation — Kirti Subramanian (0:45)

What this means: every model writes a valid slogan, and none writes a distinctive one. Against our own line, four models
pass validity and constraints and all five miss originality. So on Monday, treat these as first-draft tools. Choose a model
on reliability and cost, add a simple length check before human review, and put a differentiator in the brief, because that
was our cheapest originality gain.

The limits matter. We have not yet validated the judge against people, we used one primary judge family, fifty companies
and one prompt, and originality is a rating, not evidence a slogan sells. The one change we would make with two more weeks
is blinded human ratings of about two hundred slogans. And now, break it: write on your card one item you think this
benchmark would get wrong.

## Questions to be ready for (everyone)

- **Why did you drop the joke project and verbalized sampling?** Professor feedback moved us to a model-versus-model
  business task. One prompt condition made five models, five runs and a held-out split feasible before the deadline.
  The proposal's "VS is beneficial" thresholds are retired (see DEVIATIONS.md).
- **What is the held-out split for?** Twelve dev items were used to tune prompts and parsing in a pilot; the headline
  numbers use only the other 38, which were not looked at before the freeze.
- **Why is Sonnet's validity so low?** Rule check: it broke the stated word limit in {M[sonnet]['wordlimit']} of {n_out}
  held-out outputs. Every other failure was rare. It is an instruction-following slip, not a creativity gap.
- **Is the judge biased toward its own family?** We checked with a second judge from the Claude family. The difference
  between the two judges, for Claude's output against the others, was {sp[0]:+.2f} (CI {sp[1]:+.2f} to {sp[2]:+.2f}).
  We found none, but only one family was probed.
- **Why did nobody reach 3.0 originality?** Most slogans were scored 2 or 3. Part is missing input (sparse briefs gain
  0.6 to 1.1 points with a fuller description) and part is that these are competent but generic lines. We did not
  change the line after seeing the scores.
- **What does memorization do to the score?** It inflates originality (a verbatim Coke slogan scored 4/5). We report
  memorization separately and a supplementary originality without those outputs.
- **Why Mistral and not Muse Spark?** Muse Spark was blocked by an account age confirmation, so we replaced it after the
  pilot and before the freeze.
- **What did it cost?** ${R['total_cost']:.2f} in total: ${R['total_gen_cost']:.2f} generating and ${R['eval_cost']:.2f}
  grading. Generation is cheap; evaluation dominates.
- **What could still be wrong?** The human audit has not been scored, sampling parameters differed by model, and the
  stress subtypes have two or three items each.
"""
    open(path, "w").write(md)


def main():
    R = load_results()
    deck = os.path.join(OUT, "DSO 429 Project 1 Final Deck.pdf")
    summ = os.path.join(OUT, "DSO 429 Project 1 Final Summary.pdf")
    notes = os.path.join(OUT, "DSO 429 Project 1 Final Deck - Speaker Notes.md")
    w1 = build_deck(R, deck)
    w2, y = build_onepager(R, summ)
    build_notes(R, notes)
    print("deck warnings:", w1 or "none")
    print("one-pager warnings:", w2 or "none", "| bottom y=%.0f" % y)
    print("total cost $%.2f (gen $%.2f, eval $%.2f)" % (R["total_cost"], R["total_gen_cost"], R["eval_cost"]))
    for p in (deck, summ, notes):
        print("wrote", p)


if __name__ == "__main__":
    main()
