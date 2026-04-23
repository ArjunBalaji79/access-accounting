"""
Publication figures for Access Accounting (TAIGR @ ICML 2026).

Generates the 4 paper-ready figures specified in README_07:

    fig1_compounding_gap.png    — horizontal waterfall, 5 countries on A100
    fig2_budget_threshold.png   — step function, discrete runs vs budget on H100
    fig3_rank_stability.png     — rank-stability heatmap with Kendall's τ
    fig4_gpu_class_effect.png   — dumbbell, H100@$25K vs A100@$10K

Design principles (from README_07):
  * One figure, one claim.
  * BIS tier drives the color encoding (Tier 1 blue, Tier 2 orange-red,
    Tier 3 dark gray), consistent across every figure.
  * Grayscale fallback via hatch patterns.
  * Clean layout: top/right spines removed, minimal grid, source line.

These figures are written to a dedicated ``paper/`` subfolder so they
sit alongside (and do not replace) the exploratory charts produced by
``src/visualize.py``.

Usage::

    python -m src.visualize_paper \
        --results outputs/tables/ \
        --output outputs/figures/paper/

"""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

from .visualize import _kendall_tau, _to_float, load_eca_csv, load_sensitivity_csv

# ---------------------------------------------------------------------------
# Style system — consistent across every figure in this module
# ---------------------------------------------------------------------------

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica Neue", "Arial", "DejaVu Sans"],
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "axes.labelsize": 11,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.dpi": 200,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
})

TIER_COLORS = {1: "#2166AC", 2: "#D6604D", 3: "#4D4D4D"}
TIER_FILLS = {1: "#92C5DE", 2: "#F4A582", 3: "#BABABA"}
TIER_HATCHES = {1: "", 2: "///", 3: "xxx"}

BASELINE_GRAY = "#E8E8E8"
BASELINE_EDGE = "#BFBFBF"

SOURCE_ATTRIBUTION = (
    "Source: AWS Capacity Blocks & On-Demand pricing (Apr 2026), "
    "World Bank ICP 2024, BIS 90 FR 4544."
)


def _clean_axes(ax) -> None:
    """Drop top/right spines and tighten grid — paper style."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.grid(True, alpha=0.3, linestyle=":")
    ax.set_axisbelow(True)


def _add_source_line(fig, y: float = -0.02) -> None:
    fig.text(
        0.5, y, SOURCE_ATTRIBUTION,
        ha="center", fontsize=7, color="#888888", style="italic",
    )


# ---------------------------------------------------------------------------
# Figure 1 — "The Compounding Gap" (horizontal waterfall)
# ---------------------------------------------------------------------------


DEFAULT_FIG1_COUNTRIES = ["USA", "DEU", "IND", "NGA", "CHN"]


def fig1_compounding_gap(
    eca_data: list[dict],
    output_path: Path,
    countries: list[str] | None = None,
    gpu_class: str = "A100_SXM4",
    provider: str = "aws",
) -> None:
    """Horizontal bars showing how much of the US baseline remains after
    PPP and legal-scenario adjustments.

    Each country gets 1 row if Tier 1 (only PPP reduces their ECA) or 2
    rows if Tier 2 (PPP row, then PPP + Scenario B mid row). Tier 3 gets
    one row at zero width. The bar is a tier-colored, tier-hatched fill
    drawn on top of a light-gray "USA-baseline" reference bar so the
    reader immediately sees the fraction lost to each layer.
    """
    countries = countries or DEFAULT_FIG1_COUNTRIES
    rows = [
        r for r in eca_data
        if r["gpu_class"] == gpu_class and r["provider"] == provider
        and r["country_iso"] in countries
    ]
    if not rows:
        print(f"[fig1] no data for {provider}/{gpu_class}")
        return
    by_iso = {r["country_iso"]: r for r in rows}
    usa = by_iso.get("USA")
    if usa is None:
        print("[fig1] USA baseline missing — cannot normalise")
        return
    baseline = usa.get("eca_nominal_tflops") or usa.get("eca_scenario_a") or 1.0

    # Compose bar rows in the desired display order (top → bottom), with
    # Tier 2 countries expanded into two rows.
    entries: list[dict] = []
    for iso in countries:
        r = by_iso.get(iso)
        if r is None:
            continue
        tier = int(r.get("bis_tier", 1))
        econ = r.get("eca_economic_tflops", 0.0) or 0.0
        leg = r.get("eca_scenario_b_mid", 0.0) or 0.0
        is_nonlocal = str(r.get("is_local_region", "True")).strip().lower() in ("false", "0", "no")
        dagger = " †" if is_nonlocal else ""

        if tier == 1:
            entries.append(dict(label=r["country_name"] + dagger,
                                value=econ, tier=tier, layer="After PPP"))
        elif tier == 2:
            entries.append(dict(label=r["country_name"] + dagger,
                                value=econ, tier=tier, layer="After PPP"))
            entries.append(dict(label="  + Legal (Scen. B mid)",
                                value=leg, tier=tier, layer="+ Legal"))
        else:  # Tier 3 — blocked
            entries.append(dict(label=r["country_name"] + " (Tier 3 — blocked)",
                                value=0.0, tier=tier, layer="Blocked"))

    n = len(entries)
    fig, ax = plt.subplots(figsize=(10, 0.55 * n + 1.2))
    y = np.arange(n)[::-1]  # top of chart = first entry

    # 1) USA-baseline reference bar (light gray background) — only for
    #    non-Tier-3 rows; Tier 3 gets a zero-width notation instead.
    for i, e in enumerate(entries):
        if e["tier"] == 3:
            continue
        ax.barh(
            y[i], baseline, height=0.65,
            color=BASELINE_GRAY, edgecolor=BASELINE_EDGE, linewidth=0.8, zorder=1,
        )

    # 2) Tier-colored accessible portion.
    for i, e in enumerate(entries):
        if e["value"] <= 0:
            continue
        ax.barh(
            y[i], e["value"], height=0.65,
            color=TIER_FILLS[e["tier"]],
            edgecolor=TIER_COLORS[e["tier"]],
            hatch=TIER_HATCHES[e["tier"]],
            linewidth=1.0, zorder=2,
        )

    # 3) Right-aligned annotations: "% of US" + absolute TFLOP/s.
    for i, e in enumerate(entries):
        pct = (e["value"] / baseline * 100.0) if baseline else 0.0
        label = (
            "0% — Tier 3 blocked" if e["tier"] == 3
            else f"{pct:.0f}% of US  ({e['value']:,.0f} TFLOP/s)"
        )
        ax.text(
            baseline * 1.02, y[i], label,
            va="center", ha="left", fontsize=9,
            color=TIER_COLORS[e["tier"]], fontweight="bold",
        )

    ax.set_yticks(y)
    ax.set_yticklabels([e["label"] for e in entries], fontsize=10)
    ax.set_xlabel(f"Effective Compute Access (TFLOP/s, BF16 dense)", fontsize=11)
    ax.set_xlim(0, baseline * 1.35)
    ax.set_title(
        f"Effective Compute Access at $10,000 budget — {gpu_class} / {provider.upper()}",
        fontsize=12, loc="left", pad=34,
    )
    ax.text(
        0.0, 1.02,
        "Each bar shows the share of US-baseline access remaining after PPP "
        "and legal adjustments.\n"
        "Scenario B assumes partial TPP-cap consumption for Tier 2 countries. "
        "† marks non-local cloud routing.",
        transform=ax.transAxes, fontsize=8.5, color="#444",
        va="bottom",
    )

    _clean_axes(ax)
    ax.spines["left"].set_visible(False)
    ax.tick_params(left=False)
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    _add_source_line(fig, y=-0.05)
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close(fig)
    print(f"Saved: {output_path}")


# ---------------------------------------------------------------------------
# Figure 2 — "The Budget Threshold" (step function, H100)
# ---------------------------------------------------------------------------


DEFAULT_FIG2_COUNTRIES = ["USA", "DEU", "IND", "NGA", "CHN"]


def _affordable_chips(budget: float, price: float, hours: int, ppp: float,
                      alpha: float, delta: float) -> int:
    """Re-derive affordable whole runs given the economic model.

    For the step-function chart we need a dense budget grid that the
    5-point sweep CSV doesn't provide, so we recompute directly from
    each country's cached per-GPU-hour price and PPP factor.
    """
    if ppp <= 0 or alpha <= 0 or delta <= 0:
        return 0
    adjusted = price * hours / ppp
    runs = budget / adjusted
    return int(math.floor(runs))


def fig2_budget_threshold(
    eca_data: list[dict],
    output_path: Path,
    countries: list[str] | None = None,
    gpu_class: str = "H100_SXM5",
    provider: str = "aws",
    hours: int = 720,
    budget_min: float = 2_000,
    budget_max: float = 50_000,
    budget_step: float = 250,
) -> None:
    """Step function: discrete affordable H100 runs as budget grows.

    For each country, compute ``floor(budget / adjusted_run_cost)`` over
    a dense budget grid, then draw it as ``plt.step()`` so the integer
    jumps are visible (the whole point of the chart).
    """
    countries = countries or DEFAULT_FIG2_COUNTRIES
    rows = [
        r for r in eca_data
        if r["gpu_class"] == gpu_class and r["provider"] == provider
        and r["country_iso"] in countries
    ]
    if not rows:
        print(f"[fig2] no data for {provider}/{gpu_class}")
        return
    by_iso = {r["country_iso"]: r for r in rows}

    xs = np.arange(budget_min, budget_max + budget_step, budget_step)

    fig, ax = plt.subplots(figsize=(10, 5))

    linestyles = ["-", "--", "-.", ":", (0, (5, 1))]

    for idx, iso in enumerate(countries):
        r = by_iso.get(iso)
        if r is None:
            continue
        tier = int(r.get("bis_tier", 1))
        price = float(r.get("on_demand_usd_per_gpu_hr", 0.0))
        ppp = float(r.get("ppp_factor", 1.0))
        alpha = float(r.get("alpha_availability", 1.0))
        # Scenario A / Tier-1 baseline (δ = 1 for Tier 1, 1 for Tier 2
        # under Scenario A, 0 for Tier 3 — matches fig-1's "economic +
        # availability" layer before legal scenarios are applied).
        delta = 0.0 if tier == 3 else 1.0
        ys = np.array([
            _affordable_chips(b, price, hours, ppp, alpha, delta) for b in xs
        ])

        ax.step(
            xs, ys, where="post",
            color=TIER_COLORS[tier],
            linestyle=linestyles[idx % len(linestyles)],
            linewidth=2.2,
            label=f"{r['country_name']} (Tier {tier})",
        )

        # Threshold annotation: first budget where chips ≥ 1.
        first_on = np.where(ys >= 1)[0]
        if first_on.size:
            b0 = xs[first_on[0]]
            ax.axvline(b0, color=TIER_COLORS[tier], alpha=0.25,
                       linewidth=1.0, linestyle=":")
            # Stagger vertical offset per country so nearby thresholds
            # (e.g. USA vs Germany) don't overlap.
            ax.annotate(
                f"${b0/1000:.1f}K",
                xy=(b0, 1), xytext=(4, 10 + 12 * idx),
                textcoords="offset points",
                color=TIER_COLORS[tier], fontsize=8, fontweight="bold",
            )

    ax.set_xlabel("Training budget (USD)", fontsize=11)
    ax.set_ylabel("Affordable complete training runs\n"
                  f"({hours}-hour, 1×{gpu_class})", fontsize=11)
    ax.set_title(
        f"Budget thresholds for frontier compute access — {gpu_class} / {provider.upper()}",
        fontsize=12, loc="left", pad=28,
    )
    ax.text(
        0.0, 1.02,
        "Step function shows discrete training runs affordable at each budget level.  "
        "Dotted vertical ticks mark the minimum budget for ≥ 1 run.",
        transform=ax.transAxes, fontsize=8.5, color="#444", va="bottom",
    )
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"${v/1000:.0f}K"))
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.set_ylim(bottom=-0.3)
    ax.legend(loc="upper left", frameon=False, ncol=1)
    _clean_axes(ax)
    _add_source_line(fig, y=-0.08)
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close(fig)
    print(f"Saved: {output_path}")


# ---------------------------------------------------------------------------
# Figure 3 — Rank-stability heatmap
# ---------------------------------------------------------------------------


def fig3_rank_stability(
    sensitivity_data: list[dict],
    output_path: Path,
    gpu_class: str = "A100_SXM4",
    provider: str = "aws",
    countries: list[str] | None = None,
) -> None:
    """Rank-stability heatmap with discrete 3-level stability coloring
    (stable / minor shift / noteworthy shift) + a companion ECA-value
    panel so the reader can see whether a rank change corresponds to a
    meaningful numeric gap.

    Kendall's τ for each normalization method vs. the PPP baseline is
    shown in the subtitle — TAIGR reviewers care about a formal
    correlation measure.
    """
    methods = ["ppp", "gdp_per_capita", "rd_per_researcher"]
    method_labels = ["PPP", "GDP/capita", "R&D/researcher"]

    rankings: dict[str, dict[str, int]] = {}
    eca_vals: dict[str, dict[str, float]] = {}
    all_names: list[str] = []
    for m in methods:
        rows = [
            r for r in sensitivity_data
            if r["normalization_method"] == m
            and r["gpu_class"] == gpu_class
            and r["provider"] == provider
        ]
        # Rank by ECA Scenario A descending.
        rows.sort(key=lambda x: -(x.get("eca_scenario_a") or 0.0))
        rankings[m] = {r["country_name"]: i + 1 for i, r in enumerate(rows)}
        eca_vals[m] = {r["country_name"]: r.get("eca_scenario_a") or 0.0 for r in rows}
        if not all_names:
            all_names = [r["country_name"] for r in rows]

    # Drop only the degenerate case (China is Tier 3, always ECA = 0
    # everywhere, so it contributes no rank information). USA is kept
    # because under GDP/capita normalization Singapore overtakes it —
    # i.e. USA is NOT trivially rank #1 across all methods. We reverse
    # so worst-off countries appear at the TOP of the chart — that matches
    # imshow's default orientation (row 0 at top) and avoids the need for
    # invert_yaxis(), which previously caused tick labels and bar data to
    # come unstuck when the two panels share a y-axis.
    if countries is None:
        countries = [c for c in reversed(all_names) if c != "China"]

    if not countries:
        print("[fig3] no middle countries to plot")
        return

    base = np.array([rankings["ppp"][c] for c in countries])
    matrix = np.array(
        [[rankings[m].get(c, len(countries) + 1) for m in methods] for c in countries],
        dtype=int,
    )
    eca_matrix = np.array(
        [[eca_vals[m].get(c, 0.0) for m in methods] for c in countries],
        dtype=float,
    )

    fig, (ax_rank, ax_val) = plt.subplots(
        1, 2, figsize=(13, max(5.0, 0.55 * len(countries) + 2)),
        gridspec_kw={"width_ratios": [1.1, 1.0], "wspace": 0.35},
    )

    # Slope / bump chart.  Each country is ONE line drawn across three
    # x positions (PPP, GDP/cap, R&D) at y = its rank under that method.
    # Rank #1 sits at the top (inverted y-axis), so a line that climbs
    # visually means the country *gained* rank; a line that slopes down
    # means the country *lost* rank.  No color legend, no arrows — the
    # slope of each line is the shift, which is the entire point.
    x_positions = np.arange(len(methods))

    # Anything moving 2+ positions is a "significant shift" worth
    # highlighting.  Everyone else is drawn in neutral gray so the eye
    # gets drawn to the handful of lines that actually cross.
    SHIFT_THRESHOLD = 2
    NEUTRAL = "#B8B8B8"
    movers = {}  # country -> line color
    for c in countries:
        ranks = [rankings[m][c] for m in methods]
        max_abs_shift = max(abs(ranks[0] - r) for r in ranks[1:])
        if max_abs_shift >= SHIFT_THRESHOLD:
            # Color by direction of the dominant shift so "gainers" and
            # "losers" are separable at a glance. This is NOT a traffic-
            # light (green/red); it is a simple distinguishable pair.
            direction = (ranks[0] - ranks[-1])  # positive → gained
            movers[c] = "#1F6FB0" if direction > 0 else "#C0504D"

    for c in countries:
        ranks = [rankings[m][c] for m in methods]
        color = movers.get(c, NEUTRAL)
        lw = 2.2 if c in movers else 1.1
        alpha = 1.0 if c in movers else 0.55
        z = 3 if c in movers else 2
        ax_rank.plot(
            x_positions, ranks,
            color=color, linewidth=lw, alpha=alpha,
            marker="o", markersize=7, markerfacecolor="white",
            markeredgewidth=1.6, zorder=z,
        )

    # Country labels on left and right sides, right next to each line's
    # endpoint so the reader can identify them without a legend.
    n = len(countries)
    for c in countries:
        left_rank = rankings["ppp"][c]
        right_rank = rankings[methods[-1]][c]
        color = movers.get(c, "#555")
        weight = "bold" if c in movers else "normal"
        ax_rank.text(
            -0.12, left_rank, c,
            va="center", ha="right",
            fontsize=9.5, color=color, fontweight=weight,
        )
        ax_rank.text(
            len(methods) - 1 + 0.12, right_rank, c,
            va="center", ha="left",
            fontsize=9.5, color=color, fontweight=weight,
        )

    ax_rank.set_xticks(x_positions)
    ax_rank.set_xticklabels(method_labels, fontsize=10, fontweight="bold")
    ax_rank.set_yticks(range(1, n + 1))
    ax_rank.set_yticklabels([f"#{i}" for i in range(1, n + 1)])
    ax_rank.set_ylim(n + 0.5, 0.5)  # rank #1 at top
    ax_rank.set_xlim(-0.9, len(methods) - 1 + 0.9)
    ax_rank.set_ylabel("Rank  (#1 = best access, #9 = worst)", fontsize=10)
    ax_rank.set_title(
        "How each country's access rank changes when you swap economic yardsticks",
        fontsize=11, loc="left",
    )
    ax_rank.grid(axis="y", alpha=0.2, linestyle=":")
    for s in ("top", "right"):
        ax_rank.spines[s].set_visible(False)
    ax_rank.tick_params(length=0)

    # Companion value panel: horizontal bars per method. Bars for
    # countries[i] must live at y=i so they line up with the tick labels
    # drawn by the rank panel (which share this y-axis via sharey=True).
    method_colors = ["#2166AC", "#5AAE61", "#9970AB"]
    bar_h = 0.26
    y_positions = np.arange(len(countries))
    for j, m in enumerate(methods):
        offset = (j - 1) * bar_h
        ax_val.barh(
            y_positions + offset, eca_matrix[:, j], height=bar_h,
            color=method_colors[j], alpha=0.85, label=method_labels[j],
            edgecolor="white", linewidth=0.5,
        )
        # Annotate zero-valued cells with an explicit "0" marker so readers
        # don't mistake an unaffordable country for a data gap. The floor-
        # division ECA formula sends countries to 0 when their adjusted
        # budget can't buy a single full run.
        for i in range(len(countries)):
            if eca_matrix[i, j] == 0.0:
                ax_val.text(
                    0, y_positions[i] + offset,
                    "  0 (unaffordable)",
                    va="center", ha="left",
                    fontsize=7.5, color=method_colors[j], fontstyle="italic",
                )

    ax_val.set_yticks(y_positions)
    ax_val.set_yticklabels(countries)
    # countries is ordered worst → best (Nigeria, ..., USA).  With
    # y_positions = np.arange(N) and a non-inverted axis, y=0 lands at the
    # bottom and y=N-1 at the top, which puts USA at the top — matching
    # the slope chart on the left (rank #1 at top).
    ax_val.set_xlabel("ECA Scenario A (TFLOP/s)", fontsize=11)
    ax_val.set_title("ECA value under each normalization", fontsize=11, loc="left")
    ax_val.xaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax_val.legend(loc="lower right", frameon=False, ncol=1)
    _clean_axes(ax_val)

    # Kendall's τ vs PPP baseline — computed on the FULL country list,
    # not just the middle subset shown in the heatmap, so the reported
    # statistic reflects overall rank robustness.
    taus = []
    full_ppp_vec = [rankings["ppp"][c] for c in all_names]
    for m, lbl in zip(methods, method_labels):
        other = [rankings[m].get(c, len(all_names) + 1) for c in all_names]
        taus.append((lbl, _kendall_tau(full_ppp_vec, other)))

    tau_str = "  |  ".join(
        f"τ(PPP, {lbl}) = {val:+.2f}" for lbl, val in taus if lbl != "PPP"
    )

    fig.suptitle(
        f"Rank stability of ECA across normalization methods — {gpu_class} / {provider.upper()}",
        fontsize=12, fontweight="bold", x=0.02, ha="left", y=1.01,
    )
    fig.text(
        0.02, 0.965,
        "Each line is one country. Follow it left-to-right to see how its "
        "access rank changes when we measure affordability with PPP vs. GDP/capita "
        "vs. R&D-per-researcher. Flat line = rank unchanged; steep line = rank shift. "
        f"Most countries stay flat ({tau_str}).",
        fontsize=8.5, color="#444",
    )
    _add_source_line(fig, y=-0.04)
    plt.savefig(output_path)
    plt.close(fig)
    print(f"Saved: {output_path}")


# ---------------------------------------------------------------------------
# Figure 4 — Dumbbell: H100 @ $25K vs A100 @ $10K
# ---------------------------------------------------------------------------


DEFAULT_FIG4_COUNTRIES = ["USA", "DEU", "SGP", "BRA", "IND", "NGA"]


def fig4_gpu_class_effect(
    eca_10k: list[dict],
    sweep_data: list[dict],
    output_path: Path,
    countries: list[str] | None = None,
    provider: str = "aws",
) -> None:
    """Dumbbell plot: for each country, compare the ECA their budget
    buys on H100 ($25K) vs. on A100 ($10K). The connecting line makes
    the GPU-class effect immediately visible; the ordinal position
    persists while absolute values shift.
    """
    countries = countries or DEFAULT_FIG4_COUNTRIES

    h100 = {
        r["country_iso"]: r for r in sweep_data
        if r["provider"] == provider
        and r["gpu_class"] == "H100_SXM5"
        and float(r.get("budget_usd", 0)) == 25_000.0
    }
    a100 = {
        r["country_iso"]: r for r in eca_10k
        if r["provider"] == provider and r["gpu_class"] == "A100_SXM4"
    }

    rows = []
    for iso in countries:
        h = h100.get(iso)
        a = a100.get(iso)
        if h is None or a is None:
            continue
        rows.append({
            "name": a["country_name"],
            "iso": iso,
            "tier": int(a.get("bis_tier", 1)),
            "h100": float(h.get("eca_scenario_a", 0.0) or 0.0),
            "a100": float(a.get("eca_scenario_a", 0.0) or 0.0),
        })
    if not rows:
        print("[fig4] no matching rows")
        return
    rows.sort(key=lambda x: x["a100"])

    fig, ax = plt.subplots(figsize=(10, 0.55 * len(rows) + 2))
    y = np.arange(len(rows))

    for i, r in enumerate(rows):
        tc = TIER_COLORS[r["tier"]]
        ax.hlines(y[i], min(r["h100"], r["a100"]), max(r["h100"], r["a100"]),
                  color="#888", linewidth=1.2, zorder=1)
        ax.scatter(r["h100"], y[i], color=tc, marker="s", s=110, zorder=3,
                   edgecolor="white", linewidth=1.2,
                   label="H100 SXM5 @ $25K" if i == 0 else "")
        ax.scatter(r["a100"], y[i], color=tc, marker="o", s=130, zorder=3,
                   edgecolor="white", linewidth=1.2,
                   label="A100 SXM4 @ $10K" if i == 0 else "")

        # Value annotations (small, to the right of each marker).
        ax.text(r["h100"], y[i] + 0.22, f"{r['h100']:,.0f}",
                ha="center", fontsize=8, color=tc)
        ax.text(r["a100"], y[i] - 0.28, f"{r['a100']:,.0f}",
                ha="center", fontsize=8, color=tc)

    ax.set_yticks(y)
    ax.set_yticklabels([r["name"] for r in rows])
    ax.set_xlabel("Effective Compute Access — Scenario A (TFLOP/s, BF16 dense)", fontsize=11)
    ax.set_title(
        "GPU class effect — cheaper hardware narrows but does not close the access gap",
        fontsize=12, loc="left", pad=28,
    )
    ax.text(
        0.0, 1.02,
        r"Each country shows two dots: H100 SXM5 at \$25K budget vs. A100 SXM4 at \$10K budget.  "
        "The A100 shifts each country rightward but preserves ranking and compounding structure.",
        transform=ax.transAxes, fontsize=8.5, color="#444", va="bottom",
    )
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.legend(loc="lower right", frameon=False)
    _clean_axes(ax)
    ax.spines["left"].set_visible(False)
    ax.tick_params(left=False)
    _add_source_line(fig, y=-0.05)
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close(fig)
    print(f"Saved: {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate paper-ready figures (README_07)"
    )
    parser.add_argument("--results", type=Path, default=Path("outputs/tables/"))
    parser.add_argument("--output", type=Path, default=Path("outputs/figures/paper/"))
    parser.add_argument("--format", default="png",
                        choices=["png", "pdf", "svg"],
                        help="File format for saved figures (pdf recommended for LaTeX)")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    ext = args.format

    eca_path = args.results / "eca_results.csv"
    sweep_path = args.results / "eca_budget_sweep.csv"
    sens_path = args.results / "sensitivity.csv"

    if eca_path.exists():
        eca_data = load_eca_csv(eca_path)
        fig1_compounding_gap(eca_data, args.output / f"fig1_compounding_gap.{ext}")

        if sweep_path.exists():
            sweep_data = load_eca_csv(sweep_path)
            fig2_budget_threshold(eca_data, args.output / f"fig2_budget_threshold.{ext}")
            fig4_gpu_class_effect(
                eca_data, sweep_data,
                args.output / f"fig4_gpu_class_effect.{ext}",
            )
        else:
            print(f"(missing {sweep_path}; skipping fig2 + fig4)")

    if sens_path.exists():
        sens_data = load_sensitivity_csv(sens_path)
        fig3_rank_stability(sens_data, args.output / f"fig3_rank_stability.{ext}")
    else:
        print(f"(missing {sens_path}; skipping fig3)")


if __name__ == "__main__":
    main()
