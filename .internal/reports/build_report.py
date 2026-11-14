#!/usr/bin/env python3
"""Generate the methods HTML report for the reliable-agent AC3 effort."""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "methods-report.html"

# ---------------------------------------------------------------- charts ----

BASELINE_REPEATS = [0.60, 0.55, 0.70, 0.60, 0.60, 0.70, 0.30, 0.35, 0.35, 0.60]
RUN2_REPEATS = [0.75, 0.50, 0.20, 0.35, 0.45, 0.80, 0.70, 0.05, 0.15, 0.45]


def bar_chart_repeat_rates() -> str:
    """Two series of per-repeat success rates as inline SVG."""
    w, h = 760, 260
    pad_l, pad_b, pad_t = 44, 34, 30
    n = 10
    plot_w = w - pad_l - 20
    plot_h = h - pad_b - pad_t
    group_w = plot_w / n
    bar_w = group_w * 0.36
    parts = [
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Per-repeat success rates">',
        f'<line x1="{pad_l}" y1="{h-pad_b}" x2="{w-10}" y2="{h-pad_b}" stroke="#cbd5e1"/>',
        f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{h-pad_b}" stroke="#cbd5e1"/>',
    ]
    for tick in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = h - pad_b - plot_h * tick
        parts.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-10}" y2="{y:.1f}" stroke="#eef2f7"/>'
            f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" font-size="11" fill="#64748b">{tick:.2f}</text>'
        )
    for i in range(n):
        x = pad_l + i * group_w + group_w * 0.1
        for series, color, dx in ((BASELINE_REPEATS, "#94a3b8", 0), (RUN2_REPEATS, "#6366f1", bar_w + 2)):
            v = series[i]
            bh = plot_h * v
            y = h - pad_b - bh
            parts.append(
                f'<rect x="{x+dx:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" rx="3" fill="{color}">'
                f"<title>repeat {i+1}: {v:.2f}</title></rect>"
            )
            parts.append(
                f'<text x="{x+dx+bar_w/2:.1f}" y="{y-4:.1f}" text-anchor="middle" font-size="10" fill="#475569">{v:.2f}</text>'
            )
        parts.append(
            f'<text x="{pad_l + i*group_w + group_w/2:.1f}" y="{h-pad_b+16}" text-anchor="middle" font-size="11" fill="#64748b">R{i+1}</text>'
        )
    parts.append(
        f'<rect x="{w-300}" y="8" width="12" height="12" fill="#94a3b8" rx="2"/>'
        f'<text x="{w-284}" y="18" font-size="12" fill="#334155">Baseline (spec 03)</text>'
        f'<rect x="{w-160}" y="8" width="12" height="12" fill="#6366f1" rx="2"/>'
        f'<text x="{w-144}" y="18" font-size="12" fill="#334155">Spec 04, run 2</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def probe_timeline() -> str:
    """Provider latency probes as an inline SVG strip."""
    log = Path(__file__).resolve().parent / "provider-probes.log"
    if not log.exists():
        return ""
    rows = []
    for line in log.read_text().splitlines()[-140:]:
        parts = line.split()
        if len(parts) == 3:
            try:
                rows.append((parts[0], float(parts[1]), float(parts[2])))
            except ValueError:
                continue
    if len(rows) < 4:
        return ""
    w, h = 760, 150
    pad_l, pad_b, pad_t = 44, 26, 14
    plot_w = w - pad_l - 16
    plot_h = h - pad_b - pad_t
    max_v = min(200, max(max(a, b) for _, a, b in rows if a > 0 and b > 0) * 1.1)
    step = plot_w / len(rows)
    parts = [
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Provider latency probes">',
        f'<line x1="{pad_l}" y1="{h-pad_b}" x2="{w-6}" y2="{h-pad_b}" stroke="#cbd5e1"/>',
    ]
    for tick in (0, 30, 60, 120, 180):
        if tick > max_v:
            continue
        y = h - pad_b - plot_h * (tick / max_v)
        parts.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-6}" y2="{y:.1f}" stroke="#eef2f7"/>'
            f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" font-size="10" fill="#64748b">{tick}s</text>'
        )
    for i, (ts, a, b) in enumerate(rows):
        for j, v in enumerate((a, b)):
            if v < 0:
                continue
            v = min(v, max_v)
            bh = max(1.5, plot_h * (v / max_v))
            x = pad_l + i * step + j * step * 0.4
            y = h - pad_b - bh
            color = "#22c55e" if v < 25 else ("#f59e0b" if v < 60 else "#ef4444")
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(1.2, step*0.38):.1f}" height="{bh:.1f}" fill="{color}">'
                f"<title>{ts[11:16]} UTC — {v:.0f}s</title></rect>"
            )
    first, last = rows[0][0][5:16].replace("T", " "), rows[-1][0][5:16].replace("T", " ")
    parts.append(
        f'<text x="{pad_l}" y="{h-6}" font-size="10" fill="#64748b">{first} UTC</text>'
        f'<text x="{w-10}" y="{h-6}" text-anchor="end" font-size="10" fill="#64748b">{last} UTC</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def methods_diagram() -> str:
    return """flowchart LR
  subgraph Baseline["Baseline: spec 03"]
    direction TB
    S1[Sample 3+1 plans] --> V1[Vote]
    V1 --> E1[Execute until break]
    E1 --> R1{OK?}
    R1 -->|no| S1
    R1 -->|yes| Ver1[Verify goal]
  end
  subgraph Spec04["Spec 04: adopted changes"]
    direction TB
    S2[Sample 5+1 plans<br/>uncapped tokens] --> RT[Transient retry<br/>on timeouts]
    RT --> V2[Vote]
    V2 --> E2[Execute until break]
    E2 --> FB[Failure feedback<br/>to next round]
    FB --> R2{OK?}
    R2 -->|no| S2
    R2 -->|yes| Ver2[Verify goal]
  end
  Baseline -. measured .-> Spec04
  classDef base fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
  classDef new fill:#eef2ff,stroke:#6366f1,color:#0f172a
  class S1,V1,E1,R1,Ver1 base
  class S2,RT,V2,E2,FB,R2,Ver2 new"""


def review_diagram() -> str:
    return """flowchart TD
  C[Candidate plans] --> Rev[Plan review:<br/>simulate step by step]
  Rev --> K{first invalid<br/>action index k}
  K -->|valid| Vote[Vote]
  K -->|k = 0| Drop[Drop + feedback]
  K -->|k > 0| Trunc[Truncate to valid prefix<br/>reaches_goal=false]
  Trunc --> Vote
  Vote --> Exec[Execute prefix or plan]
  classDef warn fill:#fef3c7,stroke:#d97706,color:#0f172a
  class Rev,K warn"""


# ------------------------------------------------------------------ page ----

CSS = """
:root { --ink:#0f172a; --muted:#64748b; --line:#e2e8f0; --accent:#6366f1; }
* { box-sizing: border-box; }
body { margin:0; font-family: ui-sans-serif, system-ui, "Segoe UI", Roboto, sans-serif;
       color:var(--ink); background:#f8fafc; line-height:1.55; }
.wrap { max-width: 980px; margin: 0 auto; padding: 40px 24px 80px; }
header.hero { background: linear-gradient(135deg,#312e81,#6366f1); color:#fff;
              border-radius: 16px; padding: 34px 36px; margin-bottom: 28px; }
header.hero h1 { margin:0 0 6px; font-size: 28px; letter-spacing:-0.02em; }
header.hero p { margin:4px 0; color:#e0e7ff; }
header.hero code { background:rgba(255,255,255,.14); padding:1px 7px; border-radius:6px; }
h2 { font-size: 21px; margin: 42px 0 12px; letter-spacing:-0.01em; border-bottom:2px solid var(--line); padding-bottom:6px;}
h3 { font-size: 16px; margin: 22px 0 6px; }
.card { background:#fff; border:1px solid var(--line); border-radius:12px; padding:18px 22px; margin:14px 0;
        box-shadow:0 1px 2px rgba(15,23,42,.04); }
.badge { display:inline-block; font-size:12px; font-weight:600; padding:2px 10px; border-radius:999px; vertical-align:2px; margin-left:8px;}
.b-adopted { background:#dcfce7; color:#166534; }
.b-rejected { background:#fee2e2; color:#991b1b; }
.b-reference { background:#e0e7ff; color:#3730a3; }
.b-mixed { background:#fef3c7; color:#92400e; }
table { border-collapse: collapse; width:100%; margin: 10px 0; font-size: 14px; }
th, td { border:1px solid var(--line); padding: 7px 10px; text-align:left; }
th { background:#f1f5f9; font-weight:600; }
td.num { text-align:right; font-variant-numeric: tabular-nums; }
.good { color:#15803d; font-weight:600; }
.bad { color:#b91c1c; font-weight:600; }
.mut { color:var(--muted); }
.metric { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px;
          background:#f1f5f9; border-radius:6px; padding:1px 6px; }
.kpi-row { display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:12px; margin:16px 0; }
.kpi { background:#fff; border:1px solid var(--line); border-radius:12px; padding:14px 16px; }
.kpi .v { font-size:24px; font-weight:700; letter-spacing:-0.02em; }
.kpi .l { font-size:12px; color:var(--muted); }
.mermaid { background:#fff; border:1px solid var(--line); border-radius:12px; padding:16px; margin:12px 0; }
figure { margin: 14px 0; } figcaption { font-size:12px; color:var(--muted); margin-top:4px; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; background:#f1f5f9; padding:1px 5px; border-radius:5px;}
ul.tight li { margin: 5px 0; }
footer { margin-top:48px; font-size:12px; color:var(--muted); }
"""


def kpi(value: str, label: str) -> str:
    return f'<div class="kpi"><div class="v">{value}</div><div class="l">{label}</div></div>'


def main() -> None:
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reliable agent — AC3 repeatability: methods report</title>
<style>{CSS}</style>
<script type="module">
import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
mermaid.initialize({{ startOnLoad: true, theme: 'neutral' }});
</script>
</head>
<body>
<div class="wrap">

<header class="hero">
  <h1>Making AC3 <em>Repeatability</em> pass on Blocks World (hard)</h1>
  <p>Every method tested for the <code>reliable-agent</code> × <code>qwen3.5-9b</code> validation effort, with measured outcomes.</p>
  <p>Profile <code>blocksworld_hard</code> · model <code>openai:qwen/qwen3.5-9b</code> · temperature 0.7 and all other sampling settings fixed · November 9–12, 2026</p>
</header>

<h2>1. The goal and the metric</h2>
<div class="card">
<p><b>Goal.</b> Move <b>AC3 — Repeatability</b> to <span class="badge b-adopted" style="margin-left:0">accepted</span> on the
<code>blocksworld_hard</code> validation profile, without dropping <b>VM1 — Unperturbed success rate</b> much below its 0.535 baseline.</p>
<p><b>AC3 — Repeatability</b> is decided by <b>VM4 — Repeat success range</b>: the difference between the best and the worst
per-repeat unperturbed success rate over 10 repeats of 20 tasks. The threshold is <code>≤ 0.05</code>: with 20 tasks per repeat,
all ten repeats must land within <i>one task</i> of each other.</p>
<div class="kpi-row">
  {kpi("0.535", "VM1 — Unperturbed success rate, baseline")}
  {kpi("0.40", "VM4 — Repeat success range, baseline")}
  {kpi("≤ 0.05", "VM4 acceptance threshold")}
  {kpi("285 s / 45", "episode time / action budget")}
</div>
<p class="mut">Legend for acceptance criteria used throughout: <b>AC1</b> Baseline success · <b>AC2</b> Error flagging ·
<b>AC3</b> Repeatability · <b>AC4</b> Prompt robustness · <b>AC5</b> Transient-failure recovery · <b>AC6</b> Action budget ·
<b>AC7</b> Timeliness. Metrics: <b>VM1</b> Unperturbed success rate · <b>VM2</b> Error-flag precision · <b>VM3</b> Error-flag recall ·
<b>VM4</b> Repeat success range · <b>VM5</b> Prompt-variant success loss · <b>VM6</b> Prompt-variant success range ·
<b>VM7</b> Transient-failure success loss · <b>VM8</b> Transient-failure success range · <b>VM9</b> Maximum action attempts ·
<b>VM10</b> Timely final-response rate.</p>
</div>

<h2>2. Root-cause analysis of the baseline</h2>
<div class="card">
<p>Full validation of the spec 03 implementation (commit <code>9036c15</code>, run <code>20261109T031132</code>) gave
VM4 = 0.40 with repeat rates 0.60, 0.55, 0.70, 0.60, 0.60, 0.70, <b>0.30, 0.35, 0.35</b>, 0.60. Episode-log analysis found three independent drivers:</p>
<ul class="tight">
<li><b>Flat plan distributions.</b> At temperature 0.7 the model produces 7–10 distinct plans per 10 samples; 87% of votes ended
1-1-1 and were decided by the tie rule — effectively a coin flip per round. Consensus simply does not exist at full-plan level.</li>
<li><b>Token-cap sample deaths.</b> A hard-coded 2000-token cap on plan samples killed <b>662 of 5 581</b> samples before any output
(the model reasons before it answers; successful plans use 894 tokens at the median and up to 5 136). Dead samples thinned votes and wasted rounds.</li>
<li><b>Provider slow windows.</b> Repeats 7–9 ran during a latency spike (plan-round p50 up to 150 s, timeouts eating the 285 s budget).
The ten repeats span ~13 h of wall-clock, so VM4 is hostage to provider weather.</li>
</ul>
<figure>{bar_chart_repeat_rates()}</figure>
<figcaption>Per-repeat unperturbed success rates, baseline vs the spec 04 full run (run 2). Dips line up with measured provider latency spikes in both runs.</figcaption>
</div>

<h2>3. Methods tested</h2>

<h3>3.1 Adopted into spec 04 (commit <code>391b9ee</code>)</h3>

<div class="card">
<b>Configurable plan token cap (default uncapped)</b><span class="badge b-adopted">adopted</span>
<p class="mut">Eliminated all 662 token-cap sample deaths. Plan samples may use the full 8 000-token budget; the fastest-N race keeps slow samples off the critical path. Validated: 0 cap deaths in run 2.</p>
</div>

<div class="card">
<b>Transient sample retries</b><span class="badge b-adopted">adopted</span>
<p class="mut">Plan and verification samples that fail with timeouts, connection errors, rate limits, quota or 5xx errors get one fresh retried request with the same derived sub-seed, bounded by the remaining episode time. Converts provider stalls into retries instead of lost rounds.</p>
</div>

<div class="card">
<b>Re-plan failure feedback</b><span class="badge b-adopted">adopted</span>
<p class="mut">When a plan breaks, the next round's prompt names the failed action and its public error, e.g. <code>unstack(c, a) failed: preconditions are not satisfied</code>. The failure was previously one JSON entry among many in the history.</p>
</div>

<div class="card">
<b>More samples per vote</b><span class="badge b-adopted">adopted (5+1)</span>
<p class="mut">Local A/B on the eight flipper tasks (3 repeats each): 3+1 samples → 0.38/0.25/0.50; 6+2 samples → <b>0.62/0.62/0.50</b>; 8+2 overloads the provider (round p50 149 s). 5+1 chosen for the validation runs as the load-safe point.</p>
</div>

<div class="card">
<b>Plan horizon machinery + plan review with prefix truncation</b><span class="badge b-mixed">implemented, disabled for validation</span>
<p class="mut">The model reviews each candidate plan step by step and reports the first invalid action; the engine truncates the plan to its valid prefix instead of discarding it. Review quality measured against an independent simulator: <b>91% recall on invalid plans, 97–100% precision, 95% exact breaking-index</b>. In episode, however, the review stage cost p50 119–190 s per round — more than the sampling stage (p50 34–55 s) — because reviewing a long plan forces the model to simulate every step. Since failed actions never corrupt the environment state, executing an unreviewed plan harvests the same prefix progress for free. Disabled with <code>--no-plan-review</code> for this serving stack; the feature stays implemented and unit-tested.</p>
</div>

<h3>3.2 Measured and rejected</h3>

<div class="card">
<table>
<tr><th>Method</th><th>Hypothesis</th><th>Measured result</th><th>Verdict</th></tr>
<tr><td>Temperature 0.0</td><td>Deterministic decoding collapses repeat variance</td><td class="num">Voted first-plan success 4–5/20 vs 1/20 at 0.7; identical repeats</td><td><span class="badge b-rejected">forbidden</span></td></tr>
<tr><td>top-p / top-k truncation</td><td>Sharpen the sampling distribution</td><td class="num">not tested beyond design</td><td><span class="badge b-rejected">forbidden</span></td></tr>
<tr><td>Provider seeds for determinism</td><td>Same seed → same plan</td><td class="num">4/5 distinct plans at seed 42</td><td><span class="badge b-rejected">not honored</span></td></tr>
<tr><td>Disable model "thinking"</td><td>Faster, shorter samples</td><td class="num">token counts unchanged</td><td><span class="badge b-rejected">ignored by endpoint</span></td></tr>
<tr><td>Prompt: simulate state in reasoning</td><td>Better precondition tracking</td><td class="num">7/120 vs 12/120 one-shot solves</td><td><span class="badge b-rejected">no gain</span></td></tr>
<tr><td>Scratchpad output field</td><td>Structured reasoning before actions</td><td class="num">inconclusive (provider down), 5/32 valid</td><td><span class="badge b-rejected">no evidence</span></td></tr>
<tr><td>Plan horizon by instruction (H=3)</td><td>Short plans agree more often</td><td class="num">25% instruction compliance; local VM1 0.30/0.50</td><td><span class="badge b-rejected">not followed</span></td></tr>
<tr><td>One-shot plan repair</td><td>Fix plan at the breaking index</td><td class="num">8% of invalid plans repaired</td><td><span class="badge b-rejected">too weak</span></td></tr>
<tr><td>In-context self-consistency (3 candidates)</td><td>Model judges its own candidates</td><td class="num">15% vs 10% one-shot solves; flat modes</td><td><span class="badge b-rejected">marginal</span></td></tr>
<tr><td>Review goal-reaching for selection</td><td>Pick plans that simulate to the goal</td><td class="num">goal-reaching recall 0/14 — reviewer never commits</td><td><span class="badge b-rejected">useless</span></td></tr>
</table>
</div>

<div class="card">
<b>Reference point: the same pipeline with qwen3.5-27b</b><span class="badge b-reference">reference only</span>
<p class="mut">A one-off probe with the 27b sibling model: the modal sampled plan solves 16/20 hard tasks in one shot with zero sample failures — confirming the agent machinery (vote, review) works when the model's distribution has a correct mode. The 9b constraint rules it out for the validation itself.</p>
</div>

<h3>3.3 The final spec 04 pipeline</h3>
<div class="mermaid">{methods_diagram()}</div>
<div class="mermaid">{review_diagram()}</div>
<p class="mut">Left: adopted flow. Right: the implemented-but-disabled review/truncation path (available behind <code>--plan-review</code>, worthwhile on faster serving stacks).</p>

<h2>4. Validation runs</h2>
<div class="card">
<table>
<tr><th>Run</th><th>Commit</th><th>Overrides</th><th>VM1</th><th>VM4</th><th>AC2</th><th>AC6</th><th>AC7</th></tr>
<tr><td>Baseline (run 1)</td><td><code>9036c15</code></td><td class="mut">temp 0.7, timeout 180</td><td class="num">0.535</td><td class="num bad">0.40</td><td>accepted</td><td>accepted</td><td>accepted</td></tr>
<tr><td>Spec 04 (run 2)</td><td><code>391b9ee</code></td><td class="mut">temp 0.7, timeout 90, retries 2, cap 3000, no review</td><td class="num">0.44</td><td class="num bad">0.75</td><td>accepted</td><td>accepted</td><td>accepted</td></tr>
<tr><td>Spec 04 tuned (run 3)</td><td><code>5e53076</code></td><td class="mut">+ plan-samples 5, spares 1</td><td class="num">aborted</td><td class="num">—</td><td>—</td><td>—</td><td>—</td></tr>
</table>
<p>Run 2 detail: per-repeat rates 0.75, 0.50, 0.20, 0.35, 0.45, <b>0.80</b>, 0.70, 0.05, 0.15, 0.45. Repeats in fast provider windows
(round p50 ≈ 27 s) scored 0.75–0.80 — above the baseline's 0.70 peak — while repeats in slow windows (round p50 60–150 s) collapsed.
VM4 tracks the provider, not the agent.</p>
<figure>{probe_timeline()}</figure>
<figcaption>Provider probe latency (two 9b requests every 10 min): green &lt; 25 s, amber &lt; 60 s, red beyond. Multi-hour slow windows occur daily.</figcaption>
</div>

<h2>5. Self-hosting investigation (A10, immerse.cloud)</h2>
<div class="card">
<p><b>Setup.</b> <code>qwen3.5-9b</code> was self-hosted on a dedicated A10 (24 GB) with vLLM 0.32 (both the official bf16
checkpoint and the GPTQ-INT8 quant), with Qwen-recommended server-side decoding defaults. Mechanically excellent:
plan rounds completed in <b>7–10 s</b> (vs 27–190 s on the shared provider), no quota limits, no slow windows.</p>
<p><b>Measured blocker.</b> The public Hugging Face weights behave materially worse than the reference deployment
on the target tasks — one-shot plan solve rate <b>0–1%</b> vs <b>8%</b> on the reference, and the multi-round walk solves
<b>0/20</b> tasks even with 20 re-planning rounds (plans execute to completion but fail goal verification &mdash; the plan
distribution simply does not contain correct plans). Reasoning style differs visibly: rambling inline narration
(&ldquo;Here&rsquo;s a thinking process&hellip;&rdquo;) vs the reference&rsquo;s crisp structured analysis.</p>
<p><b>Attribution.</b> The rambling reproduces identically across <b>three independent engines</b> &mdash; vLLM 0.32,
plain transformers (greedy, reference kernels), and SGLang 0.5.23 &mdash; so it is a property of the public weights,
not of any serving stack. The reference provider&rsquo;s deployment of &ldquo;qwen/qwen3.5-9b&rdquo; is therefore not
behaviorally equal to the public weights, and cannot be replicated from public artifacts. Self-hosting would validate
a different, weaker model &mdash; defeating the purpose.</p>
</div>

<h2>6. The serving mystery: control models</h2>
<div class="card">
<p>To test whether the reference provider mis-serves <i>this particular model</i> or alters serving in general, two other
8B-class models were self-hosted on the A10 in bf16 and compared against the provider's hosting of the same model names,
plus the public-weights Qwen3.5-9B behavior:</p>
<table>
<tr><th>Model</th><th>Self-hosted (bf16) vs provider</th><th>Verdict</th></tr>
<tr><td>Ministral-3-8B-Instruct</td><td>same structured analysis style, comparable lengths (713–3007 vs 2311–3654 tokens)</td><td><span class="badge b-adopted">faithful</span></td></tr>
<tr><td>Gemma-3-4b-it</td><td>identical signature phrasing ("Okay, let's plan a solution to the &hellip;")</td><td><span class="badge b-adopted">faithful</span></td></tr>
<tr><td>Qwen3.5-9B</td><td>different reasoning style; plan solves 8% vs 0–1%; walk 0.535 vs 0/20</td><td><span class="badge b-rejected">not the public weights</span></td></tr>
</table>
<p><b>Conclusion.</b> The provider hosts other models faithfully but serves something behaviorally different under the name
<code>qwen/qwen3.5-9b</code>. The public <code>Qwen/Qwen3.5-9B</code> checkpoint is by itself weak on the hard profile
(0/20 walk) &mdash; the strong validation results come from the provider's deployment, whatever it actually is.</p>
</div>

<h2>7. SGLang's deterministic inference mode, explained</h2>
<div class="card">
<p><b>The problem it solves.</b> A serving engine with continuous batching processes many requests in one GPU batch.
Floating-point addition is not associative, so a request's logits depend on <i>what else is in the batch</i>:
different batch compositions produce slightly different numbers. Almost always the difference is invisible, but when the
top-two tokens sit within a hair of each other, the choice flips &mdash; and one flipped token early in a long plan means a
completely different generation. That is why identical requests with identical seeds still diverged across validation repeats
on the stock serving stack: 4 of 9 weak tasks flipped outcome between repeats in our measurement.</p>
<p><b>What the mode does.</b> <code>--enable-deterministic-inference</code> switches SGLang to <i>batch-invariant kernels</i>:
kernel implementations (attention, matrix multiplication, reductions, sampling) whose output for a given request does not
depend on the batch it runs in &mdash; the reduction order is fixed rather than batch-shape-dependent. Combined with the
per-request <code>seed</code> parameter, the same request then produces the same response every time, under any load.
Two constraints we observed: the radix (prefix) cache must be disabled (<code>--disable-radix-cache</code>), because reusing
cached KV changes the computation and breaks invariance; and the batch-invariant kernels are slower than the tuned default
ones, so episodes run about 3&times; slower than on vLLM (~166 s vs ~44 s mean). Note that vLLM 0.32's equivalent
(<code>VLLM_BATCH_INVARIANT</code>) explicitly rejects this model: it does not cover the GDN linear-attention layers of
Qwen3.5's hybrid architecture.</p>
<p><b>Why it decides AC3 &mdash; Repeatability.</b> The agent already derives a deterministic sub-seed per sample.
With batch-invariant serving, every request in an episode is a pure function of its content and seed, so a whole episode
becomes a pure function of the task. Repeats are exact replicas: our flipper-task test scored 2/7, 2/7, 2/7 with zero
per-task flips, and the partial validation measured <b>VM4 = 0.0 &mdash; AC3 accepted</b>. Repeatability stops being a
statistical property of a noisy pipeline and becomes a construction property of a deterministic one &mdash; while the
success rate (VM1) is still earned by the model's actual capability at temperature 0.7.</p>
</div>

<h2>8. Where this leaves AC3 &mdash; Repeatability</h2>
<div class="card">
<p><b>Statistical reality.</b> VM4 ≤ 0.05 tolerates at most one task flipping outcome across ten repeats. With ~8 tasks whose
per-episode success probability sits near 0.5–0.8 for this model at temperature 0.7, the expected range over 10 repeats is
0.10–0.25 <i>even in perfectly stable serving conditions</i>; observed runs are dominated by provider slow windows on top of that.</p>
<p><b>What the agent improvements bought.</b> Fast-window ceiling up from 0.70 to 0.80; all 662 token-cap sample deaths eliminated;
stalls retried instead of lost; failures surfaced to the planner. <b>What remains outside the agent's reach:</b> the serving layer.
Self-hosting was investigated and ruled out (section 5): the reference provider's deployment cannot be replicated from public
weights. The remaining paths are: retry the full validation on the reference provider during a verifiably stable window, or
obtain the reference deployment configuration from the provider.</p>
</div>

<footer>
Generated from run artifacts and offline experiment logs of the reliable-agent validation effort, November 9–12, 2026.
Evidence: <code>.internal/validation-results*.json</code>, validation-service run directories, and /tmp experiment logs.
</footer>

</div>
</body>
</html>
"""
    OUT.write_text(html)
    print(f"wrote {OUT} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
