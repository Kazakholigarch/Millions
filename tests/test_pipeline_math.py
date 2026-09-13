"""The arithmetic that decides whether the month works.

The send-deadline correction is the one most plans get wrong, so it gets the
most tests: dividing the required sends by the full 30 days instead of the
20 usable send-days understates the daily number by a third, and the plan
fails in week four having been wrong on day one.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from engine.pipeline import (
    SCENARIOS,
    FunnelModel,
    FunnelRates,
    Prospect,
    daily_brief,
    observed_yield,
    status,
)


# -- funnel arithmetic -------------------------------------------------------


def test_end_to_end_rate_is_the_product_of_the_stages():
    rates = FunnelRates(send_to_reply=0.08, reply_to_call=0.35, call_to_close=0.25)
    assert rates.send_to_close == pytest.approx(0.007)


def test_requirements_chain_back_from_the_target():
    model = FunnelModel(target_revenue=100_000, avg_deal_value=10_000)
    req = model.requirements()
    assert req.deals_needed == 10
    assert req.calls_needed == 40  # 10 / 0.25
    assert req.replies_needed == 115  # ceil(40 / 0.35)
    assert req.sends_needed == 1438  # ceil(115 / 0.08)


def test_send_window_excludes_the_sales_cycle():
    """A send inside the last 10 days cannot close before the deadline."""
    model = FunnelModel(days=30, sales_cycle_days=10)
    assert model.requirements().send_days == 20


def test_daily_sends_divide_by_send_days_not_total_days():
    model = FunnelModel(target_revenue=100_000, avg_deal_value=10_000, days=30, sales_cycle_days=10)
    req = model.requirements()
    naive = req.sends_needed / model.days  # the mistake
    assert req.sends_per_day > naive
    assert req.sends_per_day == -(-req.sends_needed // req.send_days)


def test_window_shorter_than_the_sales_cycle_is_flagged():
    req = FunnelModel(days=7, sales_cycle_days=10).requirements()
    assert any("sales cycle" in w for w in req.warnings)


def test_infeasible_plans_are_labelled_infeasible():
    """$100k of $2,500 deals in 30 days is not a plan. Say so."""
    req = FunnelModel(target_revenue=100_000, avg_deal_value=2_500).requirements()
    assert req.feasibility == "not achievable at these rates"
    assert any("exceeds a realistic capacity" in w for w in req.warnings)


def test_raising_deal_value_is_the_dominant_lever():
    """The finding that reshaped the strategy: deal size beats every other lever."""
    base = FunnelModel(target_revenue=100_000, avg_deal_value=8_333)
    bigger_deals = FunnelModel(target_revenue=100_000, avg_deal_value=15_000)
    better_reply = FunnelModel(
        target_revenue=100_000, avg_deal_value=8_333, rates=FunnelRates(0.12, 0.35, 0.25)
    )
    shorter_cycle = FunnelModel(target_revenue=100_000, avg_deal_value=8_333, sales_cycle_days=7)

    per_day = lambda m: m.requirements().sends_per_day  # noqa: E731
    assert per_day(bigger_deals) < per_day(better_reply) < per_day(base)
    assert per_day(bigger_deals) < per_day(shorter_cycle)
    # And only the deal-value lever gets over the line on its own.
    assert "not achievable" in base.requirements().feasibility
    assert "not achievable" not in bigger_deals.requirements().feasibility


def test_scenarios_are_ordered_by_difficulty():
    model = FunnelModel(target_revenue=100_000, avg_deal_value=15_000)
    scenarios = model.scenarios()
    assert (
        scenarios["pessimistic"].sends_per_day
        > scenarios["base"].sends_per_day
        > scenarios["optimistic"].sends_per_day
    )


def test_every_scenario_is_a_valid_rate_set():
    for name, rates in SCENARIOS.items():
        assert 0 < rates.send_to_close < 1, name


# -- pipeline state ----------------------------------------------------------


def make_prospects(count: int, stage: str = "sent", value: float = 6500.0) -> list[Prospect]:
    prospects = []
    for index in range(count):
        prospect = Prospect(domain=f"p{index}.com", deal_value=value, deal_fit=60)
        prospect.advance(stage)
        prospects.append(prospect)
    return prospects


def test_advancing_records_history():
    prospect = Prospect(domain="a.com")
    prospect.advance("sent", note="opener")
    prospect.advance("replied")
    assert prospect.stage == "replied"
    assert [h["to"] for h in prospect.history] == ["sent", "replied"]
    assert prospect.history[0]["note"] == "opener"


def test_advancing_to_an_unknown_stage_is_rejected():
    with pytest.raises(ValueError, match="unknown stage"):
        Prospect(domain="a.com").advance("negotiating")


def test_weighted_value_rises_along_the_pipeline():
    stages = ["sent", "replied", "call_booked", "proposal", "won"]
    values = []
    for stage in stages:
        prospect = Prospect(domain="a.com", deal_value=10_000)
        prospect.advance(stage)
        values.append(prospect.weighted_value)
    assert values == sorted(values)
    assert values[-1] == 10_000  # a won deal is worth its full value


def test_lost_deals_are_worth_nothing():
    prospect = Prospect(domain="a.com", deal_value=10_000)
    prospect.advance("lost")
    assert prospect.weighted_value == 0


def test_sends_done_counts_everything_past_the_send_stage():
    """Someone who replied was also sent to — otherwise pace reads as behind."""
    prospects = make_prospects(5, "sent") + make_prospects(3, "replied") + make_prospects(2, "won")
    state = status(prospects, FunnelModel(), started_on=date.today())
    assert state.sends_done == 10


def test_lost_prospects_still_count_as_sent_if_they_were_sent():
    prospect = Prospect(domain="a.com")
    prospect.advance("sent")
    prospect.advance("lost")
    assert status([prospect], FunnelModel(), started_on=date.today()).sends_done == 1


def test_unsent_prospects_do_not_count():
    prospects = [Prospect(domain="a.com", stage="queued"), Prospect(domain="b.com", stage="scanned")]
    assert status(prospects, FunnelModel(), started_on=date.today()).sends_done == 0


def test_booked_revenue_counts_only_won_deals():
    prospects = make_prospects(3, "proposal", 10_000) + make_prospects(2, "won", 20_000)
    state = status(prospects, FunnelModel(), started_on=date.today())
    assert state.booked_revenue == 40_000
    assert state.weighted_pipeline == pytest.approx(3 * 10_000 * 0.45)


def test_being_behind_is_detected():
    model = FunnelModel(target_revenue=100_000, avg_deal_value=10_000)
    state = status(make_prospects(5), model, started_on=date.today() - timedelta(days=5))
    assert not state.on_pace
    assert state.send_deficit > 0


def test_being_on_pace_is_detected():
    model = FunnelModel(target_revenue=100_000, avg_deal_value=10_000)
    req = model.requirements()
    prospects = make_prospects(req.sends_per_day * 3)
    state = status(prospects, model, started_on=date.today() - timedelta(days=3))
    assert state.on_pace
    assert state.send_deficit == 0


# -- the daily brief ---------------------------------------------------------


def test_catch_up_is_spread_not_dumped_on_today():
    """A 300-send day is how you burn a sending domain. Spread the deficit."""
    model = FunnelModel(target_revenue=100_000, avg_deal_value=10_000)
    brief = daily_brief(make_prospects(0), model, started_on=date.today() - timedelta(days=5))
    req = model.requirements()
    assert brief["catch_up"] > 0
    assert brief["sends_today"] < req.sends_per_day + brief["status"].send_deficit


def test_brief_surfaces_queued_and_waiting_work():
    prospects = (
        [Prospect(domain=f"q{i}.com", stage="queued") for i in range(3)]
        + make_prospects(2, "replied")
        + make_prospects(1, "proposal", 20_000)
    )
    actions = " ".join(daily_brief(prospects, FunnelModel(), started_on=date.today())["actions"])
    assert "queued and unsent" in actions
    assert "book those calls" in actions
    assert "$20,000" in actions


def test_brief_warns_when_inside_the_closing_window():
    model = FunnelModel(days=30, sales_cycle_days=10)
    brief = daily_brief(make_prospects(5), model, started_on=date.today() - timedelta(days=25))
    assert any("next month's revenue" in a for a in brief["actions"])


# -- calibration -------------------------------------------------------------


def test_observed_yield_needs_enough_data_to_be_meaningful():
    assert observed_yield([Prospect(domain=f"p{i}.com", deal_fit=80) for i in range(10)]) is None


def test_observed_yield_measures_real_list_quality():
    prospects = [Prospect(domain=f"g{i}.com", deal_fit=70) for i in range(15)]
    prospects += [Prospect(domain=f"b{i}.com", deal_fit=20) for i in range(15)]
    assert observed_yield(prospects) == 0.5
