"""
Pre-submission validation checklist for Access Accounting.

Runs every data/code/figure/test sanity check before paper submission.
Exits 0 if everything passes (warnings allowed), 1 if any FAIL is present.

Usage:
    python -m src.validate_submission --config data/ --outputs outputs/
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class Check:
    name: str
    status: str  # "PASS" | "WARN" | "FAIL"
    detail: str = ""

    def print(self) -> None:
        tag = f"[{self.status:<4}]"
        print(f"{tag} {self.name}: {self.detail}")


FRESHNESS_DAYS = 90
EXPECTED_FIGURES = [
    "compounding_gap_h100_sxm5.png",
    "compounding_gap_a100_sxm4.png",
    "budget_sweep.png",
    "continuous_vs_discrete.png",
    "sensitivity_heatmap.png",
    "provider_comparison.png",
]
EXPECTED_TABLES = [
    "aar_records.csv",
    "eca_results.csv",
    "sensitivity.csv",
]
DENSE_BF16_EXPECTED = {
    "H100_SXM5": 989.5,
    "A100_SXM4": 312.0,
}


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def check_data_freshness(config_dir: Path, reference_date: date) -> list[Check]:
    checks: list[Check] = []
    providers_path = config_dir / "providers.yaml"
    providers = yaml.safe_load(providers_path.read_text())
    stale = []
    for p in providers:
        d = _parse_date(p.get("pricing_retrieval_date"))
        if d is None:
            stale.append(f"{p['provider']}/{p['gpu_class']} (no date)")
        elif (reference_date - d).days > FRESHNESS_DAYS:
            stale.append(
                f"{p['provider']}/{p['gpu_class']} (retrieved {d}, "
                f"{(reference_date - d).days} days old)"
            )
    if not stale:
        checks.append(Check("Pricing freshness",
                            "PASS",
                            f"All providers within {FRESHNESS_DAYS} days"))
    else:
        checks.append(Check("Pricing freshness",
                            "WARN",
                            f"Stale: {', '.join(stale)}"))

    countries_path = config_dir / "countries.yaml"
    countries = yaml.safe_load(countries_path.read_text())
    stale_c = []
    for c in countries:
        d = _parse_date(c.get("data_verified_date"))
        if d is None:
            stale_c.append(f"{c['iso_alpha3']} (missing)")
        elif (reference_date - d).days > FRESHNESS_DAYS:
            stale_c.append(f"{c['iso_alpha3']} (verified {d})")
    if not stale_c:
        checks.append(Check("Country verification freshness",
                            "PASS",
                            f"All countries verified within {FRESHNESS_DAYS} days"))
    else:
        checks.append(Check("Country verification freshness",
                            "WARN",
                            f"Stale: {', '.join(stale_c)}"))
    return checks


def check_output_completeness(outputs_dir: Path) -> list[Check]:
    checks: list[Check] = []
    tables_dir = outputs_dir / "tables"
    figures_dir = outputs_dir / "figures"

    missing_tables = [t for t in EXPECTED_TABLES if not (tables_dir / t).exists()]
    if not missing_tables:
        checks.append(Check("Output tables", "PASS",
                            f"All {len(EXPECTED_TABLES)} expected tables exist"))
    else:
        checks.append(Check("Output tables", "FAIL",
                            f"Missing: {', '.join(missing_tables)}"))

    missing_figs = [f for f in EXPECTED_FIGURES if not (figures_dir / f).exists()]
    if not missing_figs:
        checks.append(Check("Output figures", "PASS",
                            f"All {len(EXPECTED_FIGURES)} expected figures exist"))
    else:
        checks.append(Check("Output figures", "FAIL",
                            f"Missing: {', '.join(missing_figs)}"))

    # Empty-file detection.
    empty = []
    for f in EXPECTED_FIGURES:
        p = figures_dir / f
        if p.exists() and p.stat().st_size < 1024:  # <1 KB means empty
            empty.append(f)
    if empty:
        checks.append(Check("Non-empty figures", "FAIL",
                            f"Empty/tiny: {', '.join(empty)}"))
    else:
        checks.append(Check("Non-empty figures", "PASS",
                            "All figures > 1KB"))
    return checks


def check_cross_consistency(config_dir: Path) -> list[Check]:
    providers = yaml.safe_load((config_dir / "providers.yaml").read_text())
    gpus = yaml.safe_load((config_dir / "gpus.yaml").read_text())
    gpu_names = {g["name"] for g in gpus}

    missing = [p["gpu_class"] for p in providers if p["gpu_class"] not in gpu_names]
    if not missing:
        return [Check("Provider↔GPU consistency", "PASS",
                      "All provider gpu_class values exist in gpus.yaml")]
    return [Check("Provider↔GPU consistency", "FAIL",
                  f"Unknown GPUs: {sorted(set(missing))}")]


def check_country_coverage(config_dir: Path) -> list[Check]:
    countries = yaml.safe_load((config_dir / "countries.yaml").read_text())
    tiers: dict[int, int] = {}
    for c in countries:
        tiers[c["bis_tier"]] = tiers.get(c["bis_tier"], 0) + 1
    detail = ", ".join(f"Tier {t}: {n}" for t, n in sorted(tiers.items()))
    below_min = [t for t, n in tiers.items() if n < 3]
    if below_min:
        return [Check("Country coverage", "WARN",
                      f"{detail} (tiers {below_min} have < 3 countries)")]
    return [Check("Country coverage", "PASS", detail)]


def check_flop_convention(config_dir: Path) -> list[Check]:
    gpus = yaml.safe_load((config_dir / "gpus.yaml").read_text())
    checks: list[Check] = []
    for g in gpus:
        name = g["name"]
        dense = g.get("peak_tflops_bf16_dense")
        sparse = g.get("peak_tflops_bf16_sparse")
        expected = DENSE_BF16_EXPECTED.get(name)
        if expected is None:
            continue
        if dense != expected:
            checks.append(Check(f"FLOP/s convention ({name})", "FAIL",
                                f"Expected dense={expected}, got {dense}"))
        elif sparse is not None and dense is not None and sparse < dense:
            checks.append(Check(f"FLOP/s convention ({name})", "FAIL",
                                f"Sparse ({sparse}) < dense ({dense}) — likely swapped"))
        else:
            checks.append(Check(f"FLOP/s convention ({name})", "PASS",
                                f"dense={dense}, sparse={sparse}"))
    return checks


def check_placeholder_language(config_dir: Path) -> list[Check]:
    triggers = ("illustrative", "verify later", "placeholder", "todo")
    flagged: list[str] = []
    for yml in ("countries.yaml", "providers.yaml", "gpus.yaml"):
        path = config_dir / yml
        if not path.exists():
            continue
        text = path.read_text().lower()
        for t in triggers:
            if t in text:
                flagged.append(f"{yml}: '{t}'")
    if not flagged:
        return [Check("Placeholder language", "PASS",
                      "No 'illustrative'/'placeholder' markers remaining")]
    return [Check("Placeholder language", "WARN",
                  "; ".join(flagged))]


def check_test_suite(repo_root: Path) -> list[Check]:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q"],
            cwd=repo_root, capture_output=True, text=True, timeout=120,
        )
    except Exception as exc:
        return [Check("Test suite", "FAIL", f"pytest failed to run: {exc}")]
    last_line = next(
        (ln for ln in reversed(proc.stdout.splitlines()) if ln.strip()), ""
    )
    if proc.returncode == 0:
        return [Check("Test suite", "PASS", last_line or "pytest reported success")]
    return [Check("Test suite", "FAIL", last_line or "pytest reported failures")]


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-submission validation")
    parser.add_argument("--config", type=Path, default=Path("data/"))
    parser.add_argument("--outputs", type=Path, default=Path("outputs/"))
    parser.add_argument("--skip-tests", action="store_true",
                        help="Skip the pytest run (useful in CI where tests run separately)")
    parser.add_argument("--reference-date", type=str, default=None,
                        help="YYYY-MM-DD — pretend this is 'today' for freshness checks")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    reference = _parse_date(args.reference_date) or date.today()

    print("=== PRE-SUBMISSION VALIDATION ===")
    print(f"Reference date: {reference.isoformat()}\n")

    checks: list[Check] = []
    checks.extend(check_data_freshness(args.config, reference))
    checks.extend(check_output_completeness(args.outputs))
    checks.extend(check_cross_consistency(args.config))
    checks.extend(check_country_coverage(args.config))
    checks.extend(check_flop_convention(args.config))
    checks.extend(check_placeholder_language(args.config))
    if not args.skip_tests:
        checks.extend(check_test_suite(repo_root))

    for c in checks:
        c.print()

    passed = sum(1 for c in checks if c.status == "PASS")
    warnings = sum(1 for c in checks if c.status == "WARN")
    failures = sum(1 for c in checks if c.status == "FAIL")
    print(f"\nRESULT: {passed} passed, {warnings} warning(s), {failures} failure(s)")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
