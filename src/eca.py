"""
Effective Compute Access (ECA) computation.

Takes AAR-Core records and computes ECA under all three legal scenarios,
using configurable budget and reference run duration.

ECA formula:
    ECA(c, b) = min(ECA_Phys(c), ECA_E(c, b)) × δ(legal_scenario)

Where:
    ECA_Phys = availability_score (GA=1.0, Limited=0.5, etc.)
    ECA_E = floor(budget / (price × H × PPP)) × peak_TFLOP/s
    δ = legal scenario multiplier
"""

import argparse
import csv
import math
from dataclasses import dataclass, asdict, fields
from pathlib import Path
from typing import Optional


@dataclass
class ECAResult:
    """ECA computation result for one AAR record under all scenarios."""

    # From AAR
    country_name: str
    country_iso: str
    provider: str
    region_code: str
    gpu_class: str

    # Input parameters
    budget_usd: float
    reference_hours: int
    normalization_method: str  # "ppp", "gdp_per_capita", "rd_per_researcher"

    # Physical layer
    availability_class: str
    availability_score: float

    # Economic layer — detailed breakdown
    on_demand_usd_per_gpu_hr: float
    nominal_run_cost_usd: float  # price × H (cost of 1 GPU for H hours)
    ppp_factor: float
    normalization_value: float  # The actual normalization denominator used
    adjusted_run_cost_usd: float  # nominal × normalization adjustment
    runs_per_budget: float  # How many H-hour runs the budget buys
    affordable_chips: int  # floor of runs_per_budget
    eca_economic_tflops: float  # affordable_chips × peak_TFLOP/s

    # Legal layer
    bis_tier: int

    # Composite ECA under each scenario
    eca_scenario_a: float  # Unconstrained (δ=1.0)
    eca_scenario_b_low: float  # Partially constrained (δ=0.3)
    eca_scenario_b_mid: float  # Partially constrained (δ=0.5)
    eca_scenario_b_high: float  # Partially constrained (δ=0.7)
    eca_scenario_c: float  # Prohibited (δ=0.0)

    # Ratios (relative to USA baseline for same provider+GPU)
    ratio_to_usa_scenario_a: Optional[float] = None


def load_aar_csv(path: Path) -> list[dict]:
    """Load AAR records from CSV."""
    with open(path) as f:
        reader = csv.DictReader(f)
        records = []
        for row in reader:
            # Type conversions
            row["peak_tflops_bf16_dense"] = float(row["peak_tflops_bf16_dense"])
            row["on_demand_usd_per_gpu_hr"] = float(row["on_demand_usd_per_gpu_hr"])
            row["ppp_factor"] = float(row["ppp_factor"])
            row["gdp_per_capita_usd"] = float(row["gdp_per_capita_usd"])
            row["availability_score"] = float(row["availability_score"])
            row["bis_tier"] = int(row["bis_tier"])
            rd = row.get("rd_spend_per_researcher_usd")
            row["rd_spend_per_researcher_usd"] = float(rd) if rd and rd != "None" else None
            records.append(row)
    return records


def compute_normalization_value(
    record: dict,
    method: str,
    usa_reference: dict,
) -> float:
    """Compute the normalization adjustment factor.
    
    Returns a multiplier applied to nominal cost to get adjusted cost.
    Higher = less purchasing power = more expensive in real terms.
    
    Methods:
        ppp: Uses PPP conversion factor ratio (USA/country)
        gdp_per_capita: Uses GDP per capita ratio (USA/country)
        rd_per_researcher: Uses R&D spend per researcher ratio (USA/country)
    """
    if method == "ppp":
        # PPP factor < 1 means cheaper local prices → budget goes further
        # But cloud is priced in USD, so local-currency budget buys less
        # Adjustment: divide by PPP factor (smaller PPP = higher real cost)
        return record["ppp_factor"]
    
    elif method == "gdp_per_capita":
        # Normalize by GDP per capita ratio
        # A country with 1/10th the GDP/cap faces 10x the real cost
        usa_gdp = usa_reference["gdp_per_capita_usd"]
        country_gdp = record["gdp_per_capita_usd"]
        return country_gdp / usa_gdp
    
    elif method == "rd_per_researcher":
        rd = record.get("rd_spend_per_researcher_usd")
        usa_rd = usa_reference.get("rd_spend_per_researcher_usd")
        if rd and usa_rd and float(usa_rd) > 0:
            return float(rd) / float(usa_rd)
        else:
            # Fallback to PPP if R&D data missing
            return record["ppp_factor"]
    
    else:
        raise ValueError(f"Unknown normalization method: {method}")


def compute_eca(
    records: list[dict],
    budget_usd: float = 10_000,
    reference_hours: int = 720,
    normalization_method: str = "ppp",
) -> list[ECAResult]:
    """Compute ECA for all AAR records."""

    # Find USA records as baseline
    usa_records = {
        (r["provider"], r["gpu_class"]): r
        for r in records
        if r["country_iso"] == "USA"
    }

    results = []

    for rec in records:
        price = rec["on_demand_usd_per_gpu_hr"]
        peak_tflops = rec["peak_tflops_bf16_dense"]
        avail_score = rec["availability_score"]
        bis_tier = rec["bis_tier"]

        # Get USA baseline for this provider+GPU
        usa_ref = usa_records.get((rec["provider"], rec["gpu_class"]))
        if usa_ref is None:
            # Skip if no USA baseline exists for this combo
            continue

        # Nominal run cost (1 GPU × H hours)
        nominal_run_cost = price * reference_hours

        # Normalization
        norm_value = compute_normalization_value(rec, normalization_method, usa_ref)
        
        # Adjusted run cost: how expensive this run is in real terms
        # Lower norm_value = less purchasing power = higher real cost
        adjusted_run_cost = nominal_run_cost / norm_value

        # Runs affordable
        runs = budget_usd / adjusted_run_cost
        affordable_chips = math.floor(runs)

        # ECA-Economic (TFLOP/s accessible)
        eca_e = affordable_chips * peak_tflops

        # ECA-Physical (bounded by availability)
        eca_phys = avail_score  # Normalized 0-1

        # Composite: min of physical and economic, scaled
        # When physical = 0 (Unavailable), ECA = 0 regardless of budget
        eca_base = eca_e * eca_phys

        # Legal scenarios
        if bis_tier == 1:
            delta_a, delta_b_low, delta_b_mid, delta_b_high, delta_c = 1.0, 1.0, 1.0, 1.0, 1.0
        elif bis_tier == 2:
            delta_a = 1.0
            delta_b_low, delta_b_mid, delta_b_high = 0.3, 0.5, 0.7
            delta_c = 0.0
        else:  # Tier 3
            delta_a, delta_b_low, delta_b_mid, delta_b_high, delta_c = 0.0, 0.0, 0.0, 0.0, 0.0

        eca_a = eca_base * delta_a
        eca_b_low = eca_base * delta_b_low
        eca_b_mid = eca_base * delta_b_mid
        eca_b_high = eca_base * delta_b_high
        eca_c = eca_base * delta_c

        # Ratio to USA
        usa_eca_e = None
        if usa_ref:
            usa_norm = compute_normalization_value(usa_ref, normalization_method, usa_ref)
            usa_adj = (usa_ref["on_demand_usd_per_gpu_hr"] * reference_hours) / usa_norm
            usa_chips = math.floor(budget_usd / usa_adj)
            usa_eca = usa_chips * peak_tflops * 1.0  # USA is always Tier 1, GA
            ratio = eca_a / usa_eca if usa_eca > 0 else None
        else:
            ratio = None

        result = ECAResult(
            country_name=rec["country_name"],
            country_iso=rec["country_iso"],
            provider=rec["provider"],
            region_code=rec["region_code"],
            gpu_class=rec["gpu_class"],
            budget_usd=budget_usd,
            reference_hours=reference_hours,
            normalization_method=normalization_method,
            availability_class=rec["availability_class"],
            availability_score=avail_score,
            on_demand_usd_per_gpu_hr=price,
            nominal_run_cost_usd=round(nominal_run_cost, 2),
            ppp_factor=rec["ppp_factor"],
            normalization_value=round(norm_value, 4),
            adjusted_run_cost_usd=round(adjusted_run_cost, 2),
            runs_per_budget=round(runs, 2),
            affordable_chips=affordable_chips,
            eca_economic_tflops=round(eca_e, 1),
            bis_tier=bis_tier,
            eca_scenario_a=round(eca_a, 1),
            eca_scenario_b_low=round(eca_b_low, 1),
            eca_scenario_b_mid=round(eca_b_mid, 1),
            eca_scenario_b_high=round(eca_b_high, 1),
            eca_scenario_c=round(eca_c, 1),
            ratio_to_usa_scenario_a=round(ratio, 3) if ratio is not None else None,
        )
        results.append(result)

    return results


def results_to_csv(results: list[ECAResult], output_path: Path) -> None:
    """Write ECA results to CSV."""
    if not results:
        return
    fieldnames = [f.name for f in fields(ECAResult)]
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(asdict(r))


def print_summary(results: list[ECAResult]) -> None:
    """Print a human-readable summary table."""
    # Group by country and GPU, show AWS only for clarity
    print("\n" + "=" * 90)
    print("ECA SUMMARY — Scenario A (Unconstrained)")
    print("=" * 90)
    print(f"{'Country':<20} {'GPU':<12} {'Provider':<6} {'Runs/$10K':<10} "
          f"{'ECA (TFLOP/s)':<15} {'vs USA':<8}")
    print("-" * 90)

    for r in sorted(results, key=lambda x: (x.gpu_class, -x.eca_scenario_a)):
        ratio_str = f"{r.ratio_to_usa_scenario_a:.2f}x" if r.ratio_to_usa_scenario_a else "N/A"
        print(f"{r.country_name:<20} {r.gpu_class:<12} {r.provider:<6} "
              f"{r.runs_per_budget:<10.1f} {r.eca_scenario_a:<15.1f} {ratio_str:<8}")

    print("\n" + "=" * 90)
    print("COMPOUNDING ANALYSIS — How legal scenarios affect Tier 2 countries")
    print("=" * 90)
    tier2 = [r for r in results if r.bis_tier == 2]
    for r in sorted(tier2, key=lambda x: (x.gpu_class, x.country_name)):
        print(f"{r.country_name:<20} {r.gpu_class:<12} "
              f"A={r.eca_scenario_a:<10.1f} B(mid)={r.eca_scenario_b_mid:<10.1f} "
              f"C={r.eca_scenario_c:<10.1f}")


def main():
    parser = argparse.ArgumentParser(description="Compute Effective Compute Access")
    parser.add_argument("--aar", type=Path, default=Path("outputs/tables/aar_records.csv"))
    parser.add_argument("--budget", type=float, default=10_000)
    parser.add_argument("--hours", type=int, default=720)
    parser.add_argument("--normalization", default="ppp",
                        choices=["ppp", "gdp_per_capita", "rd_per_researcher"])
    parser.add_argument("--output", type=Path, default=Path("outputs/tables/eca_results.csv"))
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    records = load_aar_csv(args.aar)
    print(f"Loaded {len(records)} AAR records")

    results = compute_eca(
        records,
        budget_usd=args.budget,
        reference_hours=args.hours,
        normalization_method=args.normalization,
    )

    results_to_csv(results, args.output)
    print(f"Written {len(results)} ECA results to {args.output}")

    print_summary(results)


if __name__ == "__main__":
    main()
