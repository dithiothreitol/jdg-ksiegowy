"""Testy wyboru trybu skladek spolecznych ZUS."""

from datetime import date
from decimal import Decimal

from jdg_ksiegowy.tax.zus import (
    ZUSSocialMode,
    get_current_social_mode,
    get_social_contribution,
    get_total_monthly_zus,
)


class TestSocialModeAutoselect:
    BIZ_START = date(2021, 5, 1)

    def test_start_relief_first_6_months(self):
        assert (
            get_current_social_mode(
                today=date(2021, 6, 1),
                business_start=self.BIZ_START,
                employment_above_min=False,
            )
            == ZUSSocialMode.START_RELIEF
        )

    def test_small_zus_after_relief(self):
        assert (
            get_current_social_mode(
                today=date(2022, 6, 1),
                business_start=self.BIZ_START,
                employment_above_min=False,
            )
            == ZUSSocialMode.SMALL_ZUS
        )

    def test_full_after_30_months(self):
        assert (
            get_current_social_mode(
                today=date(2026, 4, 17),
                business_start=self.BIZ_START,
                employment_above_min=False,
            )
            == ZUSSocialMode.FULL
        )

    def test_employment_overrides_date_based(self):
        assert (
            get_current_social_mode(
                today=date(2021, 6, 1),
                business_start=self.BIZ_START,
                employment_above_min=True,
            )
            == ZUSSocialMode.EMPLOYMENT
        )

    def test_manual_override_wins(self):
        assert (
            get_current_social_mode(
                today=date(2026, 4, 17),
                business_start=self.BIZ_START,
                employment_above_min=True,
                override=ZUSSocialMode.FULL,
            )
            == ZUSSocialMode.FULL
        )

    def test_no_business_start_defaults_to_full(self):
        assert (
            get_current_social_mode(
                today=date(2026, 4, 17),
                business_start=None,
                employment_above_min=False,
            )
            == ZUSSocialMode.FULL
        )


class TestSocialContribution:
    def test_start_relief_zero(self):
        assert get_social_contribution(ZUSSocialMode.START_RELIEF) == Decimal("0.00")

    def test_employment_zero(self):
        assert get_social_contribution(ZUSSocialMode.EMPLOYMENT) == Decimal("0.00")

    def test_small_zus_without_sickness(self):
        assert get_social_contribution(ZUSSocialMode.SMALL_ZUS) == Decimal("420.86")

    def test_small_zus_with_sickness(self):
        assert get_social_contribution(ZUSSocialMode.SMALL_ZUS, voluntary_sickness=True) == Decimal(
            "456.18"
        )

    def test_full_without_sickness(self):
        assert get_social_contribution(ZUSSocialMode.FULL) == Decimal("1788.29")

    def test_full_with_sickness(self):
        assert get_social_contribution(ZUSSocialMode.FULL, voluntary_sickness=True) == Decimal(
            "1926.76"
        )


class TestTotalMonthlyZus:
    def test_employment_plus_tier2_health(self):
        # 200k przychodu -> tier II zdrowotnej 830.58 + employment 0 = 830.58
        total = get_total_monthly_zus(Decimal("200000"), ZUSSocialMode.EMPLOYMENT)
        assert total == Decimal("830.58")

    def test_full_plus_tier1_health(self):
        # 50k przychodu -> tier I 498.35 + full 1788.29 = 2286.64
        total = get_total_monthly_zus(Decimal("50000"), ZUSSocialMode.FULL)
        assert total == Decimal("2286.64")
