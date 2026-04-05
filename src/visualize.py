"""
Visualization module for Access Accounting.

Generates publication-quality figures for the TAIGR paper:
1. Compounding gap bar chart (layer-by-layer decomposition)
2. Sensitivity heatmap (rank stability across methods)
3. Cross-provider comparison
"""

import argparse
import csv
from pathlib import Path
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np


def load_eca_csv(path: Path) -> list[dict]:
    with open(path) as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            for key in ["eca_scenario_a", "eca_scenario_b_mid", "eca_scenario_c",
                        "runs_per_budget", "on_demand_usd_per_gpu_hr",
                        "adjusted_run_cost_usd", "normalization_value",
                        "availability_score", "eca_economic_tflops"]:
                if key in row and row[key]:
                    row[key] = float(row[key])
            row["bis_tier"] = int(row["bis_tier"])
            row["budget_usd"] = float(row["budget_usd"])
            rows.append(row)
    return rows


def load_sensitivity_csv(path: Path) -> list[dict]:
    with open(path) as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            for key in ["eca_scenario_a", "eca_scenario_b_mid", "runs_per_budget"]:
                if key in row and row[key]:
                    row[key] = float(row[key])
            if row.get("ratio_to_usa") and row["ratio_to_usa"] != "None":
                row["ratio_to_usa"] = float(row["ratio_to_usa"])
            else:
                row["ratio_to_usa"] = None
            rows.append(row)
    return rows


def fig_compounding_gap(
    eca_data: list[dict],
    output_path: Path,
    gpu_class: str = "H100_SXM5",
    provider: str = "aws",
) -> None:
    """
    Bar chart showing how access gaps widen layer by layer.
    
    Three grouped bars per country:
    - Economic only (Scenario A): what budget buys
    - + Physical constraint: availability class applied
    - + Legal constraint (Scenario B mid): δ applied
    """
    filtered = [
        r for r in eca_data
        if r["gpu_class"] == gpu_class and r["provider"] == provider
    ]
    filtered.sort(key=lambda x: -x["eca_scenario_a"])

    countries = [r["country_name"] for r in filtered]
    econ_only = [r["eca_economic_tflops"] for r in filtered]
    with_phys = [r["eca_scenario_a"] for r in filtered]  # includes availability
    with_legal = [r["eca_scenario_b_mid"] for r in filtered]

    x = np.arange(len(countries))
    width = 0.25

    fig, ax = plt.subplots(figsize=(14, 6))
    bars1 = ax.bar(x - width, econ_only, width, label="Economic only", color="#4C78A8")
    bars2 = ax.bar(x, with_phys, width, label="+ Physical", color="#F58518")
    bars3 = ax.bar(x + width, with_legal, width, label="+ Legal (Scenario B)", color="#E45756")

    ax.set_ylabel("Effective Compute Access (TFLOP/s)", fontsize=12)
    ax.set_title(f"Compounding Access Gaps — {gpu_class} / {provider.upper()}\n"
                 f"Budget: $10,000 | Run: 720 hours", fontsize=13)
    ax.set_xticks(x)
    ax.set_xticklabels(countries, rotation=35, ha="right", fontsize=10)
    ax.legend(fontsize=10)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))

    # Add tier labels
    for i, r in enumerate(filtered):
        ax.annotate(f"Tier {r['bis_tier']}",
                    xy=(i, 0), xytext=(0, -22),
                    textcoords="offset points", ha="center",
                    fontsize=8, color="gray")

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved: {output_path}")


def fig_sensitivity_heatmap(
    sensitivity_data: list[dict],
    output_path: Path,
    gpu_class: str = "H100_SXM5",
    provider: str = "aws",
) -> None:
    """
    Heatmap: countries (rows) × normalization methods (cols).
    Cell value = rank (1 = highest ECA).
    Color intensity shows rank — makes stability visible.
    """
    methods = ["ppp", "gdp_per_capita", "rd_per_researcher"]
    method_labels = ["PPP Factor", "GDP per Capita", "R&D per Researcher"]

    # Compute ranks per method
    rankings = {}
    for method in methods:
        filtered = [
            r for r in sensitivity_data
            if r["normalization_method"] == method
            and r["gpu_class"] == gpu_class
            and r["provider"] == provider
        ]
        sorted_f = sorted(filtered, key=lambda x: -x["eca_scenario_a"])
        rankings[method] = {r["country_name"]: i + 1 for i, r in enumerate(sorted_f)}

    # Get country order from PPP method
    countries = list(rankings["ppp"].keys())

    # Build matrix
    matrix = np.zeros((len(countries), len(methods)))
    for j, method in enumerate(methods):
        for i, country in enumerate(countries):
            matrix[i, j] = rankings[method].get(country, len(countries))

    fig, ax = plt.subplots(figsize=(8, max(6, len(countries) * 0.5)))
    im = ax.imshow(matrix, cmap="RdYlGn_r", aspect="auto", vmin=1, vmax=len(countries))

    ax.set_xticks(range(len(methods)))
    ax.set_xticklabels(method_labels, fontsize=10)
    ax.set_yticks(range(len(countries)))
    ax.set_yticklabels(countries, fontsize=10)

    # Add rank numbers in cells
    for i in range(len(countries)):
        for j in range(len(methods)):
            ax.text(j, i, f"{int(matrix[i, j])}",
                    ha="center", va="center", fontsize=11, fontweight="bold",
                    color="white" if matrix[i, j] > len(countries) / 2 else "black")

    ax.set_title(f"Rank Stability Across Normalization Methods\n"
                 f"{gpu_class} / {provider.upper()} — $10K budget",
                 fontsize=13)
    plt.colorbar(im, ax=ax, label="Rank (1 = highest ECA)", shrink=0.8)
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved: {output_path}")


def fig_provider_comparison(
    eca_data: list[dict],
    output_path: Path,
    gpu_class: str = "H100_SXM5",
) -> None:
    """
    Grouped bar chart: ECA by country, grouped by provider.
    Shows whether provider choice matters for access gaps.
    """
    filtered = [r for r in eca_data if r["gpu_class"] == gpu_class]

    providers = sorted(set(r["provider"] for r in filtered))
    countries_set = set(r["country_name"] for r in filtered)

    # Only show countries present in ALL providers
    country_providers = defaultdict(set)
    for r in filtered:
        country_providers[r["country_name"]].add(r["provider"])
    common_countries = [c for c, p in country_providers.items() if len(p) == len(providers)]
    common_countries.sort(key=lambda c: -max(
        r["eca_scenario_a"] for r in filtered if r["country_name"] == c
    ))

    if not common_countries:
        print("No countries with all providers — skipping provider comparison")
        return

    x = np.arange(len(common_countries))
    width = 0.8 / len(providers)
    colors = ["#4C78A8", "#F58518", "#54A24B", "#E45756"]

    fig, ax = plt.subplots(figsize=(14, 6))
    for j, prov in enumerate(providers):
        vals = []
        for country in common_countries:
            match = [r for r in filtered
                     if r["country_name"] == country and r["provider"] == prov]
            vals.append(match[0]["eca_scenario_a"] if match else 0)
        ax.bar(x + j * width - (len(providers) - 1) * width / 2,
               vals, width, label=prov.upper(), color=colors[j % len(colors)])

    ax.set_ylabel("ECA (TFLOP/s) — Scenario A", fontsize=12)
    ax.set_title(f"Cross-Provider ECA Comparison — {gpu_class}", fontsize=13)
    ax.set_xticks(x)
    ax.set_xticklabels(common_countries, rotation=35, ha="right", fontsize=10)
    ax.legend()
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate Access Accounting figures")
    parser.add_argument("--results", type=Path, default=Path("outputs/tables/"))
    parser.add_argument("--output", type=Path, default=Path("outputs/figures/"))
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    # Load ECA results (PPP normalization)
    eca_path = args.results / "eca_results.csv"
    if eca_path.exists():
        eca_data = load_eca_csv(eca_path)
        fig_compounding_gap(eca_data, args.output / "compounding_gap.png")
        fig_provider_comparison(eca_data, args.output / "provider_comparison.png")

    # Load sensitivity results
    sens_path = args.results / "sensitivity.csv"
    if sens_path.exists():
        sens_data = load_sensitivity_csv(sens_path)
        fig_sensitivity_heatmap(sens_data, args.output / "sensitivity_heatmap.png")


if __name__ == "__main__":
    main()
