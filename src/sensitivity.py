"""
Sensitivity analysis: run ECA across multiple normalization methods
and compare ordinal rankings to test robustness.

The key empirical claim is that access gap RANKINGS are stable
regardless of which affordability normalization you use.
"""

import argparse
import csv
from pathlib import Path

from .eca import load_aar_csv, compute_eca, ECAResult


METHODS = ["ppp", "gdp_per_capita", "rd_per_researcher"]


def run_sensitivity(
    aar_path: Path,
    budget_usd: float = 10_000,
    reference_hours: int = 720,
) -> dict[str, list[ECAResult]]:
    """Run ECA with each normalization method. Returns {method: results}."""
    records = load_aar_csv(aar_path)
    return {
        method: compute_eca(records, budget_usd, reference_hours, method)
        for method in METHODS
    }


def compute_rank_correlation(
    results_by_method: dict[str, list[ECAResult]],
    gpu_class: str = "H100_SXM5",
    provider: str = "aws",
) -> None:
    """Compare ordinal rankings of countries across methods for a given GPU+provider."""

    print(f"\n{'=' * 80}")
    print(f"RANK STABILITY ANALYSIS — {gpu_class} / {provider}")
    print(f"{'=' * 80}")

    rankings = {}
    for method, results in results_by_method.items():
        filtered = [
            r for r in results
            if r.gpu_class == gpu_class and r.provider == provider
        ]
        # Sort by ECA Scenario A descending
        sorted_results = sorted(filtered, key=lambda x: -x.eca_scenario_a)
        rankings[method] = [r.country_iso for r in sorted_results]

    # Print side by side
    max_len = max(len(v) for v in rankings.values())
    header = f"{'Rank':<6}" + "".join(f"{m:<25}" for m in METHODS)
    print(header)
    print("-" * len(header))

    for i in range(max_len):
        row = f"{i+1:<6}"
        for method in METHODS:
            if i < len(rankings[method]):
                country = rankings[method][i]
                # Find the ECA value
                eca_val = next(
                    r.eca_scenario_a
                    for r in results_by_method[method]
                    if r.country_iso == country
                    and r.gpu_class == gpu_class
                    and r.provider == provider
                )
                row += f"{country} ({eca_val:,.0f}){'':<12}"
            else:
                row += f"{'—':<25}"
        print(row)

    # Compute Kendall's tau between PPP and each other method
    ppp_order = rankings["ppp"]
    print(f"\nRank agreement with PPP baseline:")
    for method in METHODS:
        if method == "ppp":
            continue
        other_order = rankings[method]
        # Simple: count how many positions match exactly
        common = set(ppp_order) & set(other_order)
        matches = sum(
            1 for c in common
            if ppp_order.index(c) == other_order.index(c)
        )
        total = len(common)
        # Concordant pairs (simplified Kendall's tau direction)
        concordant = 0
        discordant = 0
        common_list = [c for c in ppp_order if c in set(other_order)]
        for i in range(len(common_list)):
            for j in range(i + 1, len(common_list)):
                ci, cj = common_list[i], common_list[j]
                pos_other_i = other_order.index(ci)
                pos_other_j = other_order.index(cj)
                if pos_other_i < pos_other_j:
                    concordant += 1
                else:
                    discordant += 1
        n_pairs = concordant + discordant
        tau = (concordant - discordant) / n_pairs if n_pairs > 0 else 0
        print(f"  {method}: exact position matches = {matches}/{total}, "
              f"Kendall's τ = {tau:.3f}")


def sensitivity_table_csv(
    results_by_method: dict[str, list[ECAResult]],
    output_path: Path,
) -> None:
    """Write a combined sensitivity table."""
    rows = []
    for method, results in results_by_method.items():
        for r in results:
            rows.append({
                "normalization_method": method,
                "country_iso": r.country_iso,
                "country_name": r.country_name,
                "provider": r.provider,
                "gpu_class": r.gpu_class,
                "eca_scenario_a": r.eca_scenario_a,
                "eca_scenario_b_mid": r.eca_scenario_b_mid,
                "runs_per_budget": r.runs_per_budget,
                "ratio_to_usa": r.ratio_to_usa_scenario_a,
            })

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Sensitivity analysis across normalizations")
    parser.add_argument("--aar", type=Path, default=Path("outputs/tables/aar_records.csv"))
    parser.add_argument("--budget", type=float, default=10_000)
    parser.add_argument("--hours", type=int, default=720)
    parser.add_argument("--output", type=Path, default=Path("outputs/tables/sensitivity.csv"))
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    results_by_method = run_sensitivity(args.aar, args.budget, args.hours)

    sensitivity_table_csv(results_by_method, args.output)
    print(f"Sensitivity results written to {args.output}")

    # Print rank analysis for H100 AWS
    compute_rank_correlation(results_by_method, "H100_SXM5", "aws")
    # And A100
    compute_rank_correlation(results_by_method, "A100_SXM4", "aws")


if __name__ == "__main__":
    main()
