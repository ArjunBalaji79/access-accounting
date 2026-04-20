"""
Data verification agent for Access Accounting.

Verifies every public-data field in the project's YAML configs against live
sources:
  - World Bank v2 API for PPP conversion factors and GDP per capita.
  - AWS Capacity Blocks pricing page (scraped) for p5 (H100) / p4d (A100) rates.
  - GCP GPU pricing page (best-effort scrape; often dynamic — flagged otherwise).
  - Hard-coded NVIDIA datasheet values for GPU specs.

Writes a JSON verification report to outputs/verification_report.json and
prints per-field recommendations to stdout.

Usage:
    python -m src.verify_data --config data/ --output outputs/verification_report.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore


# ---------------------------------------------------------------------------
# Reference data (used when live sources are unavailable or for comparison)
# ---------------------------------------------------------------------------

COUNTRY_ISO3_TO_ISO2: dict[str, str] = {
    "USA": "US",
    "DEU": "DE",
    "JPN": "JP",
    "GBR": "GB",
    "IND": "IN",
    "BRA": "BR",
    "ARE": "AE",
    "SGP": "SG",
    "NGA": "NG",
    "CHN": "CN",
}

VERIFIED_GPU_SPECS: dict[str, dict[str, Any]] = {
    "H100_SXM5": {
        "peak_tflops_bf16_dense": 989.5,
        "peak_tflops_bf16_sparse": 1979.0,
        "source": "NVIDIA H100 datasheet — dense BF16 Tensor Core (non-sparse)",
        "note": (
            "NVIDIA datasheet footnote: 'Shown with sparsity. Specifications "
            "1/2 lower without sparsity.' Paper convention = dense (non-sparse)."
        ),
    },
    "A100_SXM4": {
        "peak_tflops_bf16_dense": 312.0,
        "peak_tflops_bf16_sparse": 624.0,
        "source": "NVIDIA A100 datasheet",
        "note": "312 TFLOP/s dense BF16 is well established across editions.",
    },
}

# Manual findings from operator verification (2026-04-20).
MANUAL_AWS_PRICING: dict[str, dict[str, float]] = {
    "H100_SXM5": {
        "us-east-1": 3.933,
        "us-east-2": 3.933,
        "us-west-2": 3.933,
        "us-west-1": 4.916,  # Exception noted on Capacity Blocks page.
        "ap-northeast-1": 3.933,
        "ap-southeast-1": 3.933,
        "ap-southeast-2": 3.933,
        "ap-southeast-3": 3.933,
        "ap-south-1": 3.933,
        "eu-west-2": 3.933,
        "eu-north-1": 3.933,
        "sa-east-1": 3.933,
    },
    "A100_SXM4": {
        # A100 (p4d) is typically on the On-Demand page, not Capacity Blocks.
        "us-east-1": 1.475,
        "eu-west-1": 1.475,
        "eu-central-1": 1.475,
        "ap-south-1": 1.475,
        "ap-northeast-1": 1.475,
        "eu-west-2": 1.475,
        "sa-east-1": 1.475,
        "me-south-1": 1.475,
        "ap-southeast-1": 1.475,
    },
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class VerificationResult:
    """One row in the verification report."""

    category: str  # "country" | "provider" | "gpu"
    subject: str  # e.g. "IND" or "aws/H100_SXM5/us-east-1"
    field: str  # e.g. "ppp_factor"
    yaml_value: Any
    live_value: Any
    live_source: str
    live_year: Optional[int] = None
    pct_diff: Optional[float] = None
    status: str = "OK"  # OK | WARN | FAIL | UNVERIFIED | DATA_UNAVAILABLE
    message: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pct_diff(yaml_val: Optional[float], live_val: Optional[float]) -> Optional[float]:
    if yaml_val in (None, 0) or live_val is None:
        return None
    try:
        return abs(float(live_val) - float(yaml_val)) / abs(float(yaml_val)) * 100.0
    except (TypeError, ValueError):
        return None


def _classify(pct: Optional[float], warn_threshold: float = 5.0, fail_threshold: float = 10.0) -> str:
    if pct is None:
        return "UNVERIFIED"
    if pct < warn_threshold:
        return "OK"
    if pct < fail_threshold:
        return "WARN"
    return "FAIL"


def load_yaml(path: Path) -> Any:
    with open(path) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# World Bank API verification
# ---------------------------------------------------------------------------


def _fetch_worldbank_latest(iso2: str, indicator: str, session: Any) -> tuple[Optional[float], Optional[int]]:
    """Fetch the most recent non-null value for an indicator between 2020 and 2024."""
    if session is None:
        return None, None

    url = (
        f"https://api.worldbank.org/v2/country/{iso2}/indicator/{indicator}"
        f"?date=2020:2024&format=json&per_page=50"
    )
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:  # pragma: no cover
        print(f"  [worldbank] {iso2}/{indicator}: fetch failed ({exc})", file=sys.stderr)
        return None, None

    if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
        return None, None

    records = payload[1]
    # Records are newest-first by date; find the latest non-null.
    for rec in records:
        val = rec.get("value")
        if val is None:
            continue
        try:
            year = int(rec.get("date"))
        except (TypeError, ValueError):
            year = None
        return float(val), year
    return None, None


def _compute_price_level_ratio(
    iso2: str, session: Any
) -> tuple[Optional[float], Optional[int]]:
    """
    Reconstruct the (archived) price-level ratio PA.NUS.PPPC.RF using live
    indicators:

        price_level_ratio(country) = PA.NUS.PPP(country) / PA.NUS.FCRF(country)

    This yields a USA-baseline ratio because PA.NUS.PPP(USA) = PA.NUS.FCRF(USA)
    = 1.0 by construction. Returns (ratio, most_recent_year).
    """
    ppp_val, ppp_year = _fetch_worldbank_latest(iso2, "PA.NUS.PPP", session)
    if session is not None:
        time.sleep(0.3)
    fx_val, fx_year = _fetch_worldbank_latest(iso2, "PA.NUS.FCRF", session)
    if session is not None:
        time.sleep(0.3)

    if ppp_val is None or fx_val in (None, 0):
        return None, ppp_year or fx_year

    year = min(y for y in (ppp_year, fx_year) if y is not None) if ppp_year and fx_year else (ppp_year or fx_year)
    return ppp_val / fx_val, year


def verify_countries(
    countries: list[dict], session: Any, results: list[VerificationResult]
) -> dict[str, dict[str, Any]]:
    """Verify PPP and GDP for each country. Returns dict[iso3] of live values."""
    live_per_country: dict[str, dict[str, Any]] = {}

    for country in countries:
        iso3 = country["iso_alpha3"]
        iso2 = COUNTRY_ISO3_TO_ISO2.get(iso3)
        if iso2 is None:
            continue
        live_per_country[iso3] = {}

        # Price level ratio (archived indicator — we rebuild from PA.NUS.PPP / PA.NUS.FCRF).
        live_ppp, ppp_year = _compute_price_level_ratio(iso2, session)
        yaml_ppp = country.get("ppp_factor")
        pct_p = _pct_diff(yaml_ppp, live_ppp)
        status_p = _classify(pct_p) if live_ppp is not None else "DATA_UNAVAILABLE"
        results.append(
            VerificationResult(
                category="country",
                subject=iso3,
                field="ppp_factor",
                yaml_value=yaml_ppp,
                live_value=round(live_ppp, 4) if live_ppp is not None else None,
                live_source="World Bank PA.NUS.PPP / PA.NUS.FCRF (reconstructed price-level ratio)",
                live_year=ppp_year,
                pct_diff=round(pct_p, 2) if pct_p is not None else None,
                status=status_p,
                message=(
                    ""
                    if status_p == "OK"
                    else _recommendation(iso3, "ppp_factor", yaml_ppp, round(live_ppp, 4) if live_ppp is not None else None, ppp_year)
                ),
            )
        )
        live_per_country[iso3]["ppp_factor"] = {"value": live_ppp, "year": ppp_year}

        # GDP per capita: NY.GDP.PCAP.CD (current USD).
        live_gdp, gdp_year = _fetch_worldbank_latest(iso2, "NY.GDP.PCAP.CD", session)
        if session is not None:
            time.sleep(0.3)
        yaml_gdp = country.get("gdp_per_capita_usd")
        pct_g = _pct_diff(yaml_gdp, live_gdp)
        status_g = _classify(pct_g) if live_gdp is not None else "DATA_UNAVAILABLE"
        results.append(
            VerificationResult(
                category="country",
                subject=iso3,
                field="gdp_per_capita_usd",
                yaml_value=yaml_gdp,
                live_value=round(live_gdp, 2) if live_gdp is not None else None,
                live_source="World Bank NY.GDP.PCAP.CD",
                live_year=gdp_year,
                pct_diff=round(pct_g, 2) if pct_g is not None else None,
                status=status_g,
                message="" if status_g == "OK" else _recommendation(
                    iso3, "gdp_per_capita_usd", yaml_gdp, round(live_gdp, 2) if live_gdp is not None else None, gdp_year
                ),
            )
        )
        live_per_country[iso3]["gdp_per_capita_usd"] = {"value": live_gdp, "year": gdp_year}

    return live_per_country


def _recommendation(iso3: str, field: str, yaml_val: Any, live_val: Any, year: Optional[int]) -> str:
    if live_val is None:
        return f"No live data returned for {iso3} {field} — manual check required."
    return (
        f"RECOMMENDATION: Update data/countries.yaml {iso3} {field} "
        f"from {yaml_val} to {live_val} (World Bank {year})"
    )


# ---------------------------------------------------------------------------
# AWS pricing verification (scraping is best-effort; falls back to manual)
# ---------------------------------------------------------------------------


def _scrape_aws_capacity_blocks(session: Any) -> dict[str, dict[str, float]]:
    """Try to scrape the Capacity Blocks page. Returns {gpu_class: {region: price}}."""
    if session is None or BeautifulSoup is None:
        return {}

    url = "https://aws.amazon.com/ec2/capacityblocks/pricing/"
    try:
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
    except Exception as exc:  # pragma: no cover
        print(f"  [aws] scrape failed: {exc}", file=sys.stderr)
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    # The AWS page is JS-heavy. A useful heuristic is to regex-pull any
    # "$X.XXX" values that appear near instance type tokens. If we find none
    # we return empty, which signals "scrape not usable".
    prices: dict[str, dict[str, float]] = {}
    # Look for p5.48xlarge rows with a dollar amount.
    p5_hits = re.findall(r"p5\.48xlarge[\s\S]{0,200}?\$([0-9]+\.[0-9]+)", text)
    if p5_hits:
        prices.setdefault("H100_SXM5", {})["__scraped_any__"] = float(p5_hits[0])
    p4_hits = re.findall(r"p4d\.24xlarge[\s\S]{0,200}?\$([0-9]+\.[0-9]+)", text)
    if p4_hits:
        prices.setdefault("A100_SXM4", {})["__scraped_any__"] = float(p4_hits[0])
    return prices


def verify_providers(
    providers: list[dict], session: Any, results: list[VerificationResult]
) -> None:
    """Verify AWS and GCP pricing entries in providers.yaml."""
    scraped = _scrape_aws_capacity_blocks(session) if session is not None else {}

    for entry in providers:
        prov = entry["provider"]
        gpu = entry["gpu_class"]
        for region in entry.get("regions", []):
            code = region["region_code"]
            yaml_price = region.get("on_demand_usd_per_gpu_hr")
            subject = f"{prov}/{gpu}/{code}"

            if prov == "aws":
                manual_price = MANUAL_AWS_PRICING.get(gpu, {}).get(code)
                if manual_price is None:
                    results.append(
                        VerificationResult(
                            category="provider",
                            subject=subject,
                            field="on_demand_usd_per_gpu_hr",
                            yaml_value=yaml_price,
                            live_value=None,
                            live_source="AWS public pricing (manual)",
                            status="UNVERIFIED",
                            message=(
                                "Region not in manual-verified AWS price list. "
                                "Check https://aws.amazon.com/ec2/capacityblocks/pricing/ "
                                "or https://aws.amazon.com/ec2/pricing/on-demand/."
                            ),
                        )
                    )
                else:
                    pct = _pct_diff(yaml_price, manual_price)
                    status = _classify(pct) if pct is not None else "UNVERIFIED"
                    results.append(
                        VerificationResult(
                            category="provider",
                            subject=subject,
                            field="on_demand_usd_per_gpu_hr",
                            yaml_value=yaml_price,
                            live_value=manual_price,
                            live_source="AWS pricing (operator verified 2026-04-20)",
                            pct_diff=round(pct, 2) if pct is not None else None,
                            status=status,
                        )
                    )

                # Bonus: if we scraped anything, report it as an informational note.
                if gpu in scraped:
                    scraped_val = next(iter(scraped[gpu].values()))
                    results.append(
                        VerificationResult(
                            category="provider",
                            subject=subject,
                            field="on_demand_usd_per_gpu_hr_scraped_sample",
                            yaml_value=yaml_price,
                            live_value=scraped_val,
                            live_source="AWS capacity blocks page (scraped)",
                            status="OK" if abs(scraped_val - (yaml_price or 0)) < 0.5 else "WARN",
                            message="Scrape is heuristic — treat as sanity check only.",
                        )
                    )

            elif prov == "gcp":
                results.append(
                    VerificationResult(
                        category="provider",
                        subject=subject,
                        field="on_demand_usd_per_gpu_hr",
                        yaml_value=yaml_price,
                        live_value=None,
                        live_source="GCP pricing (dynamic page)",
                        status="UNVERIFIED",
                        message=(
                            "GCP pricing page is rendered client-side. "
                            "Verify manually at https://cloud.google.com/compute/gpus-pricing."
                        ),
                    )
                )

            else:
                results.append(
                    VerificationResult(
                        category="provider",
                        subject=subject,
                        field="on_demand_usd_per_gpu_hr",
                        yaml_value=yaml_price,
                        live_value=None,
                        live_source=f"{prov} pricing",
                        status="UNVERIFIED",
                        message=f"No automated verifier implemented for provider '{prov}'.",
                    )
                )


# ---------------------------------------------------------------------------
# GPU spec verification
# ---------------------------------------------------------------------------


def verify_gpus(gpus: list[dict], results: list[VerificationResult]) -> None:
    for gpu in gpus:
        name = gpu["name"]
        ref = VERIFIED_GPU_SPECS.get(name)
        if ref is None:
            results.append(
                VerificationResult(
                    category="gpu",
                    subject=name,
                    field="(all)",
                    yaml_value=None,
                    live_value=None,
                    live_source="NVIDIA datasheets",
                    status="UNVERIFIED",
                    message=f"No reference entry for GPU {name}.",
                )
            )
            continue

        for spec in ("peak_tflops_bf16_dense", "peak_tflops_bf16_sparse"):
            yaml_val = gpu.get(spec)
            live_val = ref[spec]
            pct = _pct_diff(yaml_val, live_val)
            status = _classify(pct, warn_threshold=0.5, fail_threshold=2.0) if pct is not None else "UNVERIFIED"
            results.append(
                VerificationResult(
                    category="gpu",
                    subject=name,
                    field=spec,
                    yaml_value=yaml_val,
                    live_value=live_val,
                    live_source=ref["source"],
                    pct_diff=round(pct, 2) if pct is not None else None,
                    status=status,
                    message=ref["note"] if status != "OK" else "",
                )
            )


# ---------------------------------------------------------------------------
# Report writing
# ---------------------------------------------------------------------------


def summarise(results: list[VerificationResult]) -> dict[str, int]:
    summary = {"total_checks": len(results), "passed": 0, "warnings": 0, "failures": 0, "unverified": 0}
    for r in results:
        if r.status == "OK":
            summary["passed"] += 1
        elif r.status == "WARN":
            summary["warnings"] += 1
        elif r.status == "FAIL":
            summary["failures"] += 1
        else:
            summary["unverified"] += 1
    return summary


def write_report(results: list[VerificationResult], output_path: Path) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "verification_date": datetime.now(timezone.utc).isoformat(),
        "results": [asdict(r) for r in results],
        "summary": summarise(results),
    }
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    return report


def print_report(report: dict[str, Any]) -> None:
    print("\n=== DATA VERIFICATION REPORT ===")
    print(f"Generated: {report['verification_date']}")
    s = report["summary"]
    print(
        f"Checks: {s['total_checks']} | passed {s['passed']} | "
        f"warnings {s['warnings']} | failures {s['failures']} | "
        f"unverified {s['unverified']}"
    )
    print()
    printed_recs = 0
    for r in report["results"]:
        if r["status"] in ("WARN", "FAIL") and r.get("message"):
            print(f"  [{r['status']}] {r['subject']} {r['field']}: {r['message']}")
            printed_recs += 1
    if printed_recs == 0:
        print("  (no actionable recommendations)")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify project data against live sources")
    parser.add_argument("--config", type=Path, default=Path("data/"))
    parser.add_argument(
        "--output", type=Path, default=Path("outputs/verification_report.json")
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip all network calls (uses manual-verified data only).",
    )
    args = parser.parse_args()

    session = None
    if not args.offline and requests is not None:
        session = requests.Session()
        session.headers.update(
            {"User-Agent": "access-accounting-verifier/1.0 (research; contact TAIGR SIPA)"}
        )

    countries = load_yaml(args.config / "countries.yaml")
    providers = load_yaml(args.config / "providers.yaml")
    gpus = load_yaml(args.config / "gpus.yaml")

    results: list[VerificationResult] = []
    print("Verifying countries (World Bank API)...")
    verify_countries(countries, session, results)
    print("Verifying providers (AWS manual + GCP flag)...")
    verify_providers(providers, session, results)
    print("Verifying GPU specs (NVIDIA datasheet reference)...")
    verify_gpus(gpus, results)

    report = write_report(results, args.output)
    print_report(report)
    print(f"Full report written to {args.output}")


if __name__ == "__main__":
    main()
