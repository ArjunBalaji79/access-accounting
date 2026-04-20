"""
Visualization module for Access Accounting.

Produces six publication-quality figures:

1. compounding_gap_h100_sxm5.png   — 4-bar decomposition: Nominal → +PPP → +α → +δ
2. compounding_gap_a100_sxm4.png   — same decomposition on cheaper GPU
3. budget_sweep.png                — ECA vs budget ($5K–$100K) per country
4. continuous_vs_discrete.png      — side-by-side panels revealing plateau problem
5. sensitivity_heatmap.png         — rank stability across normalization methods
6. provider_comparison.png         — cross-provider ECA bars
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

# ---------------------------------------------------------------------------
# Style conventions
# ---------------------------------------------------------------------------

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["savefig.dpi"] = 200
plt.rcParams["axes.titleweight"] = "bold"

TIER_COLORS = {1: "#4C78A8", 2: "#F58518", 3: "#E45756"}

# Compounding-gap bar palette (4 layers): light → dark.
COMPOUNDING_COLORS = ["#BBDEFB", "#64B5F6", "#1E88E5", "#0D47A1"]

SOURCE_ATTRIBUTION = (
    "Source: AWS/GCP public pricing, World Bank ICP 2024, BIS 90 FR 4544"
)


# ---------------------------------------------------------------------------
# CSV loaders
# ---------------------------------------------------------------------------


def _to_float(val) -> float | None:
    if val in (None, "", "None"):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def load_eca_csv(path: Path) -> list[dict]:
    with open(path) as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            for key in (
                "eca_scenario_a",
                "eca_scenario_b_low",
                "eca_scenario_b_mid",
                "eca_scenario_b_high",
                "eca_scenario_c",
                "eca_continuous_tflops",
                "eca_continuous_scenario_a",
                "eca_continuous_scenario_b_mid",
                "eca_nominal_tflops",
                "eca_economic_tflops",
                "runs_per_budget",
                "on_demand_usd_per_gpu_hr",
                "adjusted_run_cost_usd",
                "normalization_value",
                "alpha_availability",
                "budget_usd",
                "ppp_factor",
                "ratio_to_usa_scenario_a",
            ):
                if key in row:
                    v = _to_float(row[key])
                    if v is not None:
                        row[key] = v
            if "bis_tier" in row and row["bis_tier"]:
                row["bis_tier"] = int(row["bis_tier"])
            if "affordable_chips" in row and row["affordable_chips"]:
                row["affordable_chips"] = int(row["affordable_chips"])
            rows.append(row)
    return rows


def load_sensitivity_csv(path: Path) -> list[dict]:
    with open(path) as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            for key in ("eca_scenario_a", "eca_scenario_b_mid", "runs_per_budget"):
                if key in row and row[key]:
                    row[key] = _to_float(row[key])
            row["ratio_to_usa"] = _to_float(row.get("ratio_to_usa"))
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Figure 1 + 2: 4-bar compounding gap decomposition
# ---------------------------------------------------------------------------


def fig_compounding_gap(
    eca_data: list[dict],
    output_path: Path,
    gpu_class: str = "H100_SXM5",
    provider: str = "aws",
) -> None:
    """Four-bar per-country decomposition: Nominal → +PPP → +α → +δ.

    Bar 1 (Nominal):    ECA if budget were spent at nominal USD price, no
                        adjustments — a constant across countries for a given
                        provider+GPU (highlights that the story is all on the
                        adjustment side).
    Bar 2 (+ PPP):      eca_economic_tflops (budget × PPP → chips × peak).
    Bar 3 (+ α):        Scenario A = ECA_E × α (availability constraint).
    Bar 4 (+ δ mid):    Scenario B mid = ECA_E × α × 0.5 (Tier 2 legal gate).
    """
    filtered = [
        r for r in eca_data if r["gpu_class"] == gpu_class and r["provider"] == provider
    ]
    if not filtered:
        print(f"[compounding_gap] no data for {provider}/{gpu_class}")
        return
    filtered.sort(key=lambda x: -x.get("eca_nominal_tflops", 0.0))

    def _is_non_local(row: dict) -> bool:
        return str(row.get("is_local_region", "True")).strip().lower() in ("false", "0", "no")

    def _has_sovereignty_restriction(row: dict) -> bool:
        return row.get("data_sovereignty_class", "none") not in (None, "", "none")

    # Compose x-axis labels with compounding-constraint markers:
    #   *   = non-local cloud region (routed to nearest available)
    #   †   = non-local region + cross-border data transfer restrictions
    countries = []
    for r in filtered:
        name = r["country_name"]
        if _is_non_local(r) and _has_sovereignty_restriction(r):
            name += " †"
        countries.append(name)

    nominal = [r.get("eca_nominal_tflops", 0.0) for r in filtered]
    with_ppp = [r.get("eca_economic_tflops", 0.0) for r in filtered]
    with_alpha = [r.get("eca_scenario_a", 0.0) for r in filtered]
    with_legal = [r.get("eca_scenario_b_mid", 0.0) for r in filtered]

    x = np.arange(len(countries))
    width = 0.2

    fig, ax = plt.subplots(figsize=(15, 7))
    ax.bar(x - 1.5 * width, nominal, width, label="Nominal", color=COMPOUNDING_COLORS[0])
    ax.bar(x - 0.5 * width, with_ppp, width, label="+ PPP", color=COMPOUNDING_COLORS[1])
    ax.bar(x + 0.5 * width, with_alpha, width, label="+ Availability (α)", color=COMPOUNDING_COLORS[2])
    ax.bar(x + 1.5 * width, with_legal, width, label="+ Legal (δ, Scenario B mid)", color=COMPOUNDING_COLORS[3])

    ax.set_ylabel("Effective Compute Access (TFLOP/s)", fontsize=12)
    budget = filtered[0].get("budget_usd", 10_000)
    ax.set_title(
        f"Compounding Access Gaps — {gpu_class} / {provider.upper()}\n"
        f"Budget: ${budget:,.0f} | Reference run: {filtered[0].get('reference_hours', 720)} hours",
        fontsize=13,
    )
    ax.set_xticks(x)
    ax.set_xticklabels(countries, rotation=35, ha="right", fontsize=10)
    ax.legend(fontsize=10, loc="upper right")
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))

    # Annotate each group with tier and locality marker.
    usa_nominal = next((r["eca_nominal_tflops"] for r in filtered if r["country_iso"] == "USA"), None)
    for i, r in enumerate(filtered):
        ax.annotate(
            f"Tier {r['bis_tier']}",
            xy=(i, 0), xytext=(0, -24),
            textcoords="offset points", ha="center",
            fontsize=8, color="gray",
        )
        if usa_nominal and r.get("eca_scenario_a"):
            pct = 100.0 * r["eca_scenario_a"] / usa_nominal
            ax.annotate(
                f"{pct:.0f}% of US",
                xy=(i + 0.5 * width, r["eca_scenario_a"]),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center", fontsize=7, color="#222",
            )

    # Locality marker: asterisk below countries routed to a non-local region.
    for i, r in enumerate(filtered):
        if _is_non_local(r):
            ax.annotate(
                "*", xy=(i, 0), xytext=(0, -42),
                textcoords="offset points", ha="center",
                fontsize=14, color="#555",
            )

    ax.text(
        0.01, -0.18,
        "*  No local cloud region — routed to nearest available region.\n"
        "†  Non-local routing + cross-border data transfer restrictions apply "
        "(see data_sovereignty_class).\n"
        + SOURCE_ATTRIBUTION,
        transform=ax.transAxes, fontsize=8, color="gray", va="top",
    )

    plt.tight_layout()
    plt.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {output_path}")


# ---------------------------------------------------------------------------
# Figure 3: Budget sweep line chart
# ---------------------------------------------------------------------------


def fig_budget_sweep(
    sweep_data: list[dict],
    output_path: Path,
    gpu_class: str = "H100_SXM5",
    provider: str = "aws",
    countries: list[str] | None = None,
) -> None:
    """Line chart of ECA vs budget, one line per country."""
    filtered = [
        r for r in sweep_data if r["gpu_class"] == gpu_class and r["provider"] == provider
    ]
    if not filtered:
        print(f"[budget_sweep] no data for {provider}/{gpu_class}")
        return

    by_country: dict[str, list[dict]] = defaultdict(list)
    for r in filtered:
        by_country[r["country_name"]].append(r)
    for name, rows in by_country.items():
        rows.sort(key=lambda x: x["budget_usd"])

    if countries is None:
        countries = sorted(
            by_country.keys(),
            key=lambda c: -max(r["eca_scenario_a"] for r in by_country[c]),
        )

    fig, ax = plt.subplots(figsize=(13, 7))
    for country in countries:
        rows = by_country.get(country, [])
        if not rows:
            continue
        tier = rows[0]["bis_tier"]
        xs = [r["budget_usd"] for r in rows]
        ys = [r["eca_scenario_a"] for r in rows]
        ax.plot(
            xs, ys,
            marker="o", markersize=5, linewidth=2.0,
            color=TIER_COLORS.get(tier, "#666"),
            label=f"{country} (T{tier})",
        )

    ax.set_xlabel("Budget (USD)", fontsize=12)
    ax.set_ylabel("ECA (TFLOP/s) — Scenario A", fontsize=12)
    ax.set_xscale("log")
    ax.set_title(
        f"ECA vs Budget — {gpu_class} / {provider.upper()}\n"
        f"Reference run: {filtered[0].get('reference_hours', 720)} hours",
        fontsize=13,
    )
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"${v:,.0f}"))
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.grid(True, which="both", alpha=0.3)

    # Vertical reference lines.
    for ref_budget, label in [(10_000, "$10K (typical grant)"), (50_000, "$50K (major grant)")]:
        ax.axvline(ref_budget, linestyle="--", color="gray", alpha=0.6)
        ax.text(ref_budget, ax.get_ylim()[1] * 0.95, label, rotation=90,
                fontsize=8, color="gray", ha="right", va="top")

    ax.legend(fontsize=8, loc="upper left", ncol=2)
    ax.text(0.01, -0.12, SOURCE_ATTRIBUTION, transform=ax.transAxes,
            fontsize=8, color="gray")
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {output_path}")


# ---------------------------------------------------------------------------
# Figure 4: Discrete vs continuous side-by-side
# ---------------------------------------------------------------------------


def fig_continuous_vs_discrete(
    eca_data: list[dict],
    output_path: Path,
    gpu_class: str = "H100_SXM5",
    provider: str = "aws",
) -> None:
    filtered = [
        r for r in eca_data if r["gpu_class"] == gpu_class and r["provider"] == provider
    ]
    if not filtered:
        print(f"[continuous_vs_discrete] no data for {provider}/{gpu_class}")
        return
    filtered.sort(key=lambda x: -x.get("eca_continuous_scenario_a", 0.0))

    countries = [r["country_name"] for r in filtered]
    discrete = [r.get("eca_scenario_a", 0.0) for r in filtered]
    continuous = [r.get("eca_continuous_scenario_a", 0.0) for r in filtered]
    colors = [TIER_COLORS.get(r["bis_tier"], "#999") for r in filtered]

    fig, (ax_l, ax_r) = plt.subplots(1, 2, figsize=(16, 6), sharey=False)

    x = np.arange(len(countries))
    ax_l.bar(x, discrete, color=colors)
    ax_l.set_title("Discrete ECA (floor of runs) — Scenario A", fontsize=12)
    ax_l.set_ylabel("TFLOP/s", fontsize=11)
    ax_l.set_xticks(x)
    ax_l.set_xticklabels(countries, rotation=35, ha="right", fontsize=9)
    ax_l.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))

    ax_r.bar(x, continuous, color=colors)
    ax_r.set_title("Continuous ECA (no floor) — Scenario A", fontsize=12)
    ax_r.set_xticks(x)
    ax_r.set_xticklabels(countries, rotation=35, ha="right", fontsize=9)
    ax_r.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))

    # Highlight countries tied in discrete but different in continuous.
    # Group by discrete value; annotate groups with ≥2 countries.
    groups: dict[float, list[int]] = defaultdict(list)
    for i, v in enumerate(discrete):
        groups[v].append(i)
    for val, idxs in groups.items():
        if len(idxs) >= 2 and val > 0:
            for i in idxs:
                ax_l.annotate(
                    "(tied)", xy=(i, discrete[i]),
                    xytext=(0, 4), textcoords="offset points",
                    ha="center", fontsize=8, color="#555", fontweight="bold",
                )

    fig.suptitle(
        f"Discrete vs. Continuous ECA — {gpu_class} / {provider.upper()}\n"
        "Why both matter: discrete captures whole runs; continuous exposes the PPP gradient.",
        fontsize=13,
    )
    fig.text(0.01, 0.01, SOURCE_ATTRIBUTION, fontsize=8, color="gray")
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {output_path}")


# ---------------------------------------------------------------------------
# Figure 5: Sensitivity heatmap with rank-shift markers
# ---------------------------------------------------------------------------


def _kendall_tau(a: list[int], b: list[int]) -> float:
    """Return Kendall's τ for two equal-length rankings."""
    n = len(a)
    if n < 2:
        return 1.0
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            s = np.sign(a[i] - a[j]) * np.sign(b[i] - b[j])
            if s > 0:
                concordant += 1
            elif s < 0:
                discordant += 1
    total = concordant + discordant
    return (concordant - discordant) / total if total else 1.0


def fig_sensitivity_heatmap(
    sensitivity_data: list[dict],
    output_path: Path,
    gpu_class: str = "H100_SXM5",
    provider: str = "aws",
) -> None:
    methods = ["ppp", "gdp_per_capita", "rd_per_researcher"]
    method_labels = ["PPP Factor", "GDP per Capita", "R&D per Researcher"]

    rankings: dict[str, dict[str, int]] = {}
    eca_values: dict[str, dict[str, float]] = {}
    for method in methods:
        filtered = [
            r for r in sensitivity_data
            if r["normalization_method"] == method
            and r["gpu_class"] == gpu_class
            and r["provider"] == provider
        ]
        sorted_f = sorted(filtered, key=lambda x: -(x["eca_scenario_a"] or 0.0))
        rankings[method] = {r["country_name"]: i + 1 for i, r in enumerate(sorted_f)}
        eca_values[method] = {r["country_name"]: r["eca_scenario_a"] for r in sorted_f}

    countries = list(rankings.get("ppp", {}).keys())
    if not countries:
        print("[sensitivity_heatmap] no data")
        return

    matrix = np.array(
        [[rankings[m].get(c, len(countries)) for m in methods] for c in countries],
        dtype=float,
    )

    fig, ax = plt.subplots(figsize=(9, max(6, len(countries) * 0.5)))
    im = ax.imshow(matrix, cmap="RdYlGn_r", aspect="auto", vmin=1, vmax=len(countries))

    ax.set_xticks(range(len(methods)))
    ax.set_xticklabels(method_labels, fontsize=10)
    ax.set_yticks(range(len(countries)))
    ax.set_yticklabels(countries, fontsize=10)

    # Cell annotations: rank + ECA value; highlight rank shifts ≥ 2.
    for i, country in enumerate(countries):
        base_rank = rankings["ppp"][country]
        for j, method in enumerate(methods):
            rank = int(matrix[i, j])
            eca = eca_values[method].get(country, 0.0)
            txt = f"#{rank}\n{eca:,.0f}"
            ax.text(
                j, i, txt,
                ha="center", va="center", fontsize=8,
                color="white" if matrix[i, j] > len(countries) / 2 else "black",
                fontweight="bold",
            )
            if abs(rank - base_rank) >= 2 and method != "ppp":
                ax.add_patch(
                    plt.Rectangle(
                        (j - 0.45, i - 0.45), 0.9, 0.9,
                        fill=False, edgecolor="#222", linewidth=2.5,
                    )
                )

    # Kendall's τ for each method pair vs PPP.
    ppp_vec = [rankings["ppp"][c] for c in countries]
    tau_strs = []
    for method, label in zip(methods, method_labels):
        other = [rankings[method].get(c, len(countries)) for c in countries]
        tau = _kendall_tau(ppp_vec, other)
        tau_strs.append(f"τ(PPP, {label}) = {tau:+.2f}")

    ax.set_title(
        f"Rank Stability Across Normalization Methods\n"
        f"{gpu_class} / {provider.upper()} — $10K budget\n"
        + "  |  ".join(tau_strs[1:]),  # skip self-comparison
        fontsize=11,
    )
    plt.colorbar(im, ax=ax, label="Rank (1 = highest ECA)", shrink=0.8)
    ax.text(0.01, -0.12, SOURCE_ATTRIBUTION + "  |  Boxed cells: rank shifts ≥ 2 positions.",
            transform=ax.transAxes, fontsize=8, color="gray")
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {output_path}")


# ---------------------------------------------------------------------------
# Figure 6: Provider comparison
# ---------------------------------------------------------------------------


def fig_provider_comparison(
    eca_data: list[dict],
    output_path: Path,
    gpu_class: str = "H100_SXM5",
) -> None:
    filtered = [r for r in eca_data if r["gpu_class"] == gpu_class]
    providers = sorted({r["provider"] for r in filtered})

    country_providers: dict[str, set[str]] = defaultdict(set)
    for r in filtered:
        country_providers[r["country_name"]].add(r["provider"])
    common = [c for c, p in country_providers.items() if len(p) == len(providers)]
    common.sort(key=lambda c: -max(r["eca_scenario_a"] for r in filtered if r["country_name"] == c))

    if not common:
        print("No countries with all providers — skipping provider comparison")
        return

    x = np.arange(len(common))
    width = 0.8 / len(providers)
    palette = ["#4C78A8", "#F58518", "#54A24B", "#E45756"]

    fig, ax = plt.subplots(figsize=(14, 6))
    for j, prov in enumerate(providers):
        vals = []
        for country in common:
            match = [r for r in filtered if r["country_name"] == country and r["provider"] == prov]
            vals.append(match[0]["eca_scenario_a"] if match else 0)
        ax.bar(
            x + j * width - (len(providers) - 1) * width / 2,
            vals, width, label=prov.upper(), color=palette[j % len(palette)],
        )

    ax.set_ylabel("ECA (TFLOP/s) — Scenario A", fontsize=12)
    ax.set_title(f"Cross-Provider ECA Comparison — {gpu_class}", fontsize=13)
    ax.set_xticks(x)
    ax.set_xticklabels(common, rotation=35, ha="right", fontsize=10)
    ax.legend()
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.text(0.01, -0.18, SOURCE_ATTRIBUTION, transform=ax.transAxes,
            fontsize=8, color="gray")
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Access Accounting figures")
    parser.add_argument("--results", type=Path, default=Path("outputs/tables/"))
    parser.add_argument("--output", type=Path, default=Path("outputs/figures/"))
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    eca_path = args.results / "eca_results.csv"
    if eca_path.exists():
        eca_data = load_eca_csv(eca_path)
        for gpu in ("H100_SXM5", "A100_SXM4"):
            fig_compounding_gap(
                eca_data,
                args.output / f"compounding_gap_{gpu.lower()}.png",
                gpu_class=gpu,
            )
        fig_continuous_vs_discrete(
            eca_data, args.output / "continuous_vs_discrete.png"
        )
        fig_provider_comparison(eca_data, args.output / "provider_comparison.png")

    sweep_path = args.results / "eca_budget_sweep.csv"
    if sweep_path.exists():
        sweep_data = load_eca_csv(sweep_path)
        fig_budget_sweep(sweep_data, args.output / "budget_sweep.png")
    else:
        print(f"(no budget sweep CSV at {sweep_path}; skip budget_sweep.png)")

    sens_path = args.results / "sensitivity.csv"
    if sens_path.exists():
        sens_data = load_sensitivity_csv(sens_path)
        fig_sensitivity_heatmap(sens_data, args.output / "sensitivity_heatmap.png")


if __name__ == "__main__":
    main()
