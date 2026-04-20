"""
Unit tests for ECA computation.

Tests the core math to ensure dimensional consistency
and that the formulas match the paper's definitions.
"""

import math
import pytest
from src.eca import (
    compute_eca,
    compute_eca_budget_sweep,
    compute_normalization_value,
)


def make_record(
    country_iso="USA",
    country_name="United States",
    provider="aws",
    gpu_class="H100_SXM5",
    region_code="us-east-1",
    peak_tflops=989.5,
    price=3.933,
    ppp_factor=1.0,
    gdp_per_capita=80035,
    rd_spend=406000,
    avail_score=1.0,
    avail_class="GA",
    bis_tier=1,
    tpp_cap=None,
):
    return {
        "country_iso": country_iso,
        "country_name": country_name,
        "provider": provider,
        "gpu_class": gpu_class,
        "region_code": region_code,
        "gpu_full_name": "Test GPU",
        "peak_tflops_bf16_dense": peak_tflops,
        "on_demand_usd_per_gpu_hr": price,
        "reserved_usd_per_gpu_hr": None,
        "spot_usd_per_gpu_hr": None,
        "ppp_factor": ppp_factor,
        "gdp_per_capita_usd": gdp_per_capita,
        "rd_spend_per_researcher_usd": rd_spend,
        "availability_score": avail_score,
        "availability_class": avail_class,
        "bis_tier": bis_tier,
        "tpp_cap": tpp_cap,
        "pricing_url": "test",
        "pricing_retrieval_date": "2026-01-01",
        "data_source_type": "test",
        "verification_status": "test",
    }


class TestECAMath:
    """Test the core ECA formula matches the paper."""

    def test_usa_baseline(self):
        """USA with PPP=1.0 should get the most chips per budget."""
        records = [make_record()]
        results = compute_eca(records, budget_usd=10_000, reference_hours=720)
        assert len(results) == 1
        r = results[0]
        # Nominal cost = 3.933 * 720 = $2,831.76
        # PPP=1.0, so adjusted = same
        # Runs = 10000 / 2831.76 ≈ 3.53 → floor = 3
        expected_chips = math.floor(10_000 / (3.933 * 720 / 1.0))
        assert r.affordable_chips == expected_chips
        assert r.eca_scenario_a == expected_chips * 989.5

    def test_ppp_reduces_access(self):
        """Lower PPP factor = higher real cost = fewer chips."""
        usa = make_record()
        india = make_record(
            country_iso="IND", country_name="India",
            ppp_factor=0.26, gdp_per_capita=2485,
            bis_tier=2,
        )
        results = compute_eca([usa, india], budget_usd=10_000, reference_hours=720)
        usa_r = next(r for r in results if r.country_iso == "USA")
        ind_r = next(r for r in results if r.country_iso == "IND")
        assert usa_r.affordable_chips > ind_r.affordable_chips

    def test_tier3_gets_zero(self):
        """Tier 3 country should get ECA=0 under all scenarios."""
        usa = make_record()
        china = make_record(
            country_iso="CHN", country_name="China",
            ppp_factor=0.42, gdp_per_capita=12720,
            bis_tier=3, avail_class="Unavailable", avail_score=0.0,
        )
        results = compute_eca([usa, china], budget_usd=10_000, reference_hours=720)
        chn_r = next(r for r in results if r.country_iso == "CHN")
        assert chn_r.eca_scenario_a == 0.0
        assert chn_r.eca_scenario_b_mid == 0.0
        assert chn_r.eca_scenario_c == 0.0

    def test_tier2_scenario_c_is_zero(self):
        """Tier 2 under Scenario C (cap consumed) should get ECA=0."""
        usa = make_record()
        # Use A100 pricing ($1.475/hr) and higher budget so India can afford ≥1 run
        india = make_record(
            country_iso="IND", country_name="India",
            ppp_factor=0.26, gdp_per_capita=2485, bis_tier=2,
            price=1.475, peak_tflops=312.0,
        )
        usa_a100 = make_record(price=1.475, peak_tflops=312.0)
        results = compute_eca([usa_a100, india], budget_usd=10_000, reference_hours=720)
        ind_r = next(r for r in results if r.country_iso == "IND")
        assert ind_r.eca_scenario_c == 0.0
        assert ind_r.eca_scenario_a > 0.0  # Scenario A is positive with cheaper GPU

    def test_limited_availability_halves_eca(self):
        """Limited availability (0.5) should halve the ECA vs GA (1.0)."""
        usa = make_record()
        brazil_ga = make_record(
            country_iso="BRA", country_name="Brazil",
            ppp_factor=0.39, gdp_per_capita=8920,
            bis_tier=2, avail_class="GA", avail_score=1.0,
        )
        results_ga = compute_eca([usa, brazil_ga], budget_usd=10_000, reference_hours=720)
        bra_ga = next(r for r in results_ga if r.country_iso == "BRA")

        brazil_lim = make_record(
            country_iso="BRA", country_name="Brazil",
            ppp_factor=0.39, gdp_per_capita=8920,
            bis_tier=2, avail_class="Limited", avail_score=0.5,
        )
        results_lim = compute_eca([usa, brazil_lim], budget_usd=10_000, reference_hours=720)
        bra_lim = next(r for r in results_lim if r.country_iso == "BRA")

        assert bra_lim.eca_scenario_a == pytest.approx(bra_ga.eca_scenario_a * 0.5, rel=0.01)

    def test_dimensional_consistency(self):
        """ECA should be in TFLOP/s units."""
        records = [make_record()]
        results = compute_eca(records, budget_usd=10_000, reference_hours=720)
        r = results[0]
        # ECA = chips × TFLOP/s → units are TFLOP/s (throughput of the affordable cluster)
        assert r.eca_scenario_a == r.affordable_chips * 989.5


class TestContinuousECA:
    """Continuous ECA (no floor) should reveal gradient hidden by floor()."""

    def test_continuous_eca_shows_gradient(self):
        """Continuous ECA should differentiate countries that discrete ECA lumps together."""
        usa = make_record()
        germany = make_record(
            country_iso="DEU", country_name="Germany",
            ppp_factor=0.78, gdp_per_capita=52824, bis_tier=1,
        )
        japan = make_record(
            country_iso="JPN", country_name="Japan",
            ppp_factor=0.69, gdp_per_capita=33950, bis_tier=1,
        )
        results = compute_eca([usa, germany, japan], budget_usd=10_000, reference_hours=720)
        deu = next(r for r in results if r.country_iso == "DEU")
        jpn = next(r for r in results if r.country_iso == "JPN")
        # Discrete: both get floor(~2.x) = 2 chips → same ECA.
        assert deu.affordable_chips == jpn.affordable_chips
        # Continuous: Germany > Japan because PPP 0.78 > 0.69.
        assert deu.eca_continuous_scenario_a > jpn.eca_continuous_scenario_a

    def test_zero_discrete_nonzero_continuous(self):
        """Countries that can't afford 1 full run should still show nonzero continuous ECA."""
        usa = make_record()
        india = make_record(
            country_iso="IND", country_name="India",
            ppp_factor=0.24, gdp_per_capita=2695, bis_tier=2,
        )
        results = compute_eca([usa, india], budget_usd=10_000, reference_hours=720)
        ind = next(r for r in results if r.country_iso == "IND")
        assert ind.affordable_chips == 0
        assert ind.eca_continuous_scenario_a > 0

    def test_continuous_zero_when_alpha_zero(self):
        """Continuous ECA should respect availability multiplier (zero → zero)."""
        usa = make_record()
        china = make_record(
            country_iso="CHN", country_name="China",
            ppp_factor=0.49, gdp_per_capita=13303, bis_tier=3,
            avail_class="Unavailable", avail_score=0.0,
        )
        results = compute_eca([usa, china], budget_usd=10_000, reference_hours=720)
        chn = next(r for r in results if r.country_iso == "CHN")
        assert chn.eca_continuous_scenario_a == 0.0

    def test_nominal_tflops_ignores_ppp_and_alpha(self):
        """eca_nominal_tflops should be the same across countries sharing price/peak."""
        usa = make_record()
        india = make_record(
            country_iso="IND", country_name="India",
            ppp_factor=0.24, bis_tier=2, avail_class="Limited", avail_score=0.5,
        )
        results = compute_eca([usa, india], budget_usd=10_000, reference_hours=720)
        usa_r = next(r for r in results if r.country_iso == "USA")
        ind_r = next(r for r in results if r.country_iso == "IND")
        assert usa_r.eca_nominal_tflops == ind_r.eca_nominal_tflops


class TestBudgetSweep:
    """Multi-budget sweep should produce len(countries) × len(budgets) records."""

    def test_budget_sweep_produces_multiple_results(self):
        records = [make_record()]
        results = compute_eca_budget_sweep(records, budgets=[10_000, 25_000])
        assert len(results) == 2

    def test_budget_sweep_eca_monotonic(self):
        """Higher budget → more (or equal) discrete ECA for the same country."""
        records = [make_record()]
        results = compute_eca_budget_sweep(
            records,
            budgets=[5_000, 10_000, 25_000, 50_000, 100_000],
        )
        ecas = [r.eca_scenario_a for r in results]
        assert ecas == sorted(ecas)

    def test_budget_sweep_continuous_strictly_monotonic(self):
        """Continuous ECA should be strictly monotonic in budget (no floor plateaus)."""
        records = [make_record()]
        results = compute_eca_budget_sweep(records, budgets=[5_000, 10_000, 25_000])
        conts = [r.eca_continuous_scenario_a for r in results]
        assert conts[0] < conts[1] < conts[2]


class TestNormalization:
    def test_ppp_usa_is_one(self):
        """USA PPP normalization should be 1.0."""
        usa = make_record()
        val = compute_normalization_value(usa, "ppp", usa)
        assert val == 1.0

    def test_gdp_usa_is_one(self):
        """USA GDP normalization should be 1.0 (self-reference)."""
        usa = make_record()
        val = compute_normalization_value(usa, "gdp_per_capita", usa)
        assert val == 1.0

    def test_lower_ppp_higher_cost(self):
        """Country with lower PPP should have lower normalization value."""
        usa = make_record()
        india = make_record(ppp_factor=0.26)
        val = compute_normalization_value(india, "ppp", usa)
        assert val < 1.0  # India's PPP < USA's
        assert val == 0.26


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
