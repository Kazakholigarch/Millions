"""The arithmetic from STRATEGY.md §2, made live.

"Make $100,000" is not an instruction anyone can act on. "Send 61 evidence-backed
emails today, you are 14 behind" is. This module does that conversion and then
holds you to it.

The one refinement worth understanding is the **send deadline**. A deal takes
time to close, so a message sent on day 26 of a 30-day sprint cannot become
revenue inside the window — it is next month's pipeline. That means the sending
has to compress into the early part of the month, which raises the daily number
substantially. Most plans miss this and quietly fail in week four, on schedule,
having done the arithmetic wrong on day one.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone

# Order matters: index is used for "has reached at least this stage".
STAGES = ("scanned", "queued", "sent", "replied", "call_booked", "proposal", "won", "lost")
ACTIVE_STAGES = ("sent", "replied", "call_booked", "proposal")

# Probability a prospect at each stage eventually closes, used for weighting
# pipeline value. Derived from the base-case funnel rates below.
STAGE_CLOSE_PROBABILITY = {
    "scanned": 0.0,
    "queued": 0.0,
    "sent": 0.007,
    "replied": 0.0875,
    "call_booked": 0.25,
    "proposal": 0.45,
    "won": 1.0,
    "lost": 0.0,
}


@dataclass
class FunnelRates:
    """Conversion rates between stages.

    Defaults are the base case for *evidence-backed* outreach — a message citing
    a specific measured defect on the prospect's own site. Generic outreach runs
    roughly ten times worse; if you are sending that, none of this model applies
    and the honest fix is to send something better.
    """

    send_to_reply: float = 0.08
    reply_to_call: float = 0.35
    call_to_close: float = 0.25

    @property
    def send_to_close(self) -> float:
        return self.send_to_reply * self.reply_to_call * self.call_to_close

    def label(self) -> str:
        return (
            f"{self.send_to_reply:.0%} reply · {self.reply_to_call:.0%} call · "
            f"{self.call_to_close:.0%} close = {self.send_to_close:.2%} end to end"
        )


SCENARIOS = {
    "pessimistic": FunnelRates(send_to_reply=0.04, reply_to_call=0.25, call_to_close=0.15),
    "base": FunnelRates(send_to_reply=0.08, reply_to_call=0.35, call_to_close=0.25),
    "optimistic": FunnelRates(send_to_reply=0.12, reply_to_call=0.45, call_to_close=0.35),
}


@dataclass
class Requirements:
    """What the target demands, in units you can actually do today."""

    target_revenue: float
    avg_deal_value: float
    deals_needed: int
    calls_needed: int
    replies_needed: int
    sends_needed: int
    scans_needed: int
    send_days: int
    sends_per_day: int
    scans_per_day: int
    calls_per_week: float
    rates: str
    feasibility: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FunnelModel:
    """The plan: a target, a deadline, and the rates you believe."""

    target_revenue: float = 100_000.0
    days: int = 30
    avg_deal_value: float = 8_333.0
    rates: FunnelRates = field(default_factory=FunnelRates)
    # Days from first touch to signed. Sends after (days - sales_cycle_days)
    # land outside the window.
    sales_cycle_days: int = 10
    # Fraction of scanned sites worth contacting at all. Calibrate this from
    # your own data once you've scanned a few hundred; see `observed_yield`.
    scan_to_prospect_yield: float = 0.40
    # Realistic sustained sends per day for one person with this tooling.
    daily_send_capacity: int = 60

    def requirements(self) -> Requirements:
        warnings: list[str] = []

        deals = math.ceil(self.target_revenue / self.avg_deal_value)
        calls = math.ceil(deals / self.rates.call_to_close)
        replies = math.ceil(calls / self.rates.reply_to_call)
        sends = math.ceil(replies / self.rates.send_to_reply)
        scans = math.ceil(sends / max(self.scan_to_prospect_yield, 0.01))

        send_days = max(1, self.days - self.sales_cycle_days)
        if self.days <= self.sales_cycle_days:
            warnings.append(
                f"The {self.days}-day window is shorter than the {self.sales_cycle_days}-day "
                "sales cycle. Nothing sent can realistically close inside it."
            )

        sends_per_day = math.ceil(sends / send_days)
        scans_per_day = math.ceil(scans / send_days)
        calls_per_week = round(calls / max(self.days / 7, 0.1), 1)

        if sends_per_day > self.daily_send_capacity:
            warnings.append(
                f"{sends_per_day} sends/day exceeds a realistic capacity of "
                f"{self.daily_send_capacity}. Raise average deal value, extend the "
                "window, or accept a lower target — do not solve it by sending worse "
                "messages, which lowers the reply rate and makes the gap wider."
            )
        if calls_per_week > 25:
            warnings.append(
                f"{calls_per_week} calls/week is close to a full-time calendar with no "
                "delivery time left. Deals you win still have to be delivered."
            )

        ratio = sends_per_day / self.daily_send_capacity
        if ratio <= 0.5:
            feasibility = "comfortable"
        elif ratio <= 0.85:
            feasibility = "demanding but achievable"
        elif ratio <= 1.0:
            feasibility = "at the limit"
        else:
            feasibility = "not achievable at these rates"

        return Requirements(
            target_revenue=self.target_revenue,
            avg_deal_value=self.avg_deal_value,
            deals_needed=deals,
            calls_needed=calls,
            replies_needed=replies,
            sends_needed=sends,
            scans_needed=scans,
            send_days=send_days,
            sends_per_day=sends_per_day,
            scans_per_day=scans_per_day,
            calls_per_week=calls_per_week,
            rates=self.rates.label(),
            feasibility=feasibility,
            warnings=warnings,
        )

    def scenarios(self) -> dict[str, Requirements]:
        """The same target under pessimistic, base and optimistic rates."""
        out = {}
        for name, rates in SCENARIOS.items():
            model = FunnelModel(
                target_revenue=self.target_revenue,
                days=self.days,
                avg_deal_value=self.avg_deal_value,
                rates=rates,
                sales_cycle_days=self.sales_cycle_days,
                scan_to_prospect_yield=self.scan_to_prospect_yield,
                daily_send_capacity=self.daily_send_capacity,
            )
            out[name] = model.requirements()
        return out


@dataclass
class Prospect:
    """One company, and where it has got to."""

    domain: str
    url: str = ""
    company: str = ""
    contact_name: str = ""
    email: str = ""
    stage: str = "scanned"
    deal_value: float = 0.0
    package: str = ""
    health_score: int = 0
    deal_fit: int = 0
    created_at: str = ""
    updated_at: str = ""
    notes: str = ""
    history: list[dict] = field(default_factory=list)

    def advance(self, stage: str, note: str = "", value: float | None = None) -> None:
        if stage not in STAGES:
            raise ValueError(f"unknown stage {stage!r}; expected one of {', '.join(STAGES)}")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.history.append({"at": now, "from": self.stage, "to": stage, "note": note})
        self.stage = stage
        self.updated_at = now
        if value is not None:
            self.deal_value = value

    @property
    def weighted_value(self) -> float:
        return self.deal_value * STAGE_CLOSE_PROBABILITY.get(self.stage, 0.0)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Prospect:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class PipelineStatus:
    """Where you actually are, versus where the plan says you should be."""

    counts: dict[str, int]
    booked_revenue: float
    weighted_pipeline: float
    gap_to_target: float
    days_elapsed: int
    days_remaining: int
    sends_done: int
    sends_expected: int
    send_deficit: int
    on_pace: bool
    projected_revenue: float

    def to_dict(self) -> dict:
        return asdict(self)


def status(
    prospects: list[Prospect], model: FunnelModel, started_on: date | None = None
) -> PipelineStatus:
    """Compare reality to the plan."""
    counts = {stage: 0 for stage in STAGES}
    for prospect in prospects:
        if prospect.stage in counts:
            counts[prospect.stage] += 1

    booked = sum(p.deal_value for p in prospects if p.stage == "won")
    weighted = sum(p.weighted_value for p in prospects if p.stage in ACTIVE_STAGES)

    today = date.today()
    started = started_on or today
    days_elapsed = max(0, (today - started).days)
    days_remaining = max(0, model.days - days_elapsed)

    # Anything that has reached "sent" or beyond counts as sent — including the
    # ones that went on to reply, book, or close.
    sent_index = STAGES.index("sent")
    sends_done = sum(
        1
        for p in prospects
        if p.stage in STAGES and STAGES.index(p.stage) >= sent_index and p.stage != "lost"
    )
    sends_done += sum(
        1
        for p in prospects
        if p.stage == "lost" and any(h["to"] == "sent" for h in p.history)
    )

    requirements = model.requirements()
    send_days_elapsed = min(days_elapsed, requirements.send_days)
    sends_expected = requirements.sends_per_day * send_days_elapsed
    deficit = max(0, sends_expected - sends_done)

    return PipelineStatus(
        counts=counts,
        booked_revenue=booked,
        weighted_pipeline=round(weighted, 2),
        gap_to_target=round(max(0.0, model.target_revenue - booked - weighted), 2),
        days_elapsed=days_elapsed,
        days_remaining=days_remaining,
        sends_done=sends_done,
        sends_expected=sends_expected,
        send_deficit=deficit,
        on_pace=deficit == 0,
        projected_revenue=round(booked + weighted, 2),
    )


def daily_brief(
    prospects: list[Prospect], model: FunnelModel, started_on: date | None = None
) -> dict:
    """What to do today, and whether yesterday was enough."""
    state = status(prospects, model, started_on)
    requirements = model.requirements()

    # Catch-up is spread over the remaining send days rather than dumped on
    # today, because a 300-send day is how people burn a sending domain.
    send_days_left = max(1, requirements.send_days - state.days_elapsed)
    catch_up = math.ceil(state.send_deficit / send_days_left)
    sends_today = requirements.sends_per_day + catch_up

    actions: list[str] = []
    if sends_today > 0:
        actions.append(
            f"Send {sends_today} evidence-backed messages "
            f"({requirements.sends_per_day} on plan"
            + (f" + {catch_up} catch-up" if catch_up else "")
            + ")"
        )
        actions.append(
            f"Scan ~{math.ceil(sends_today / max(model.scan_to_prospect_yield, 0.01))} "
            "new sites to feed tomorrow's queue"
        )

    ready = [p for p in prospects if p.stage == "queued"]
    if ready:
        actions.append(f"{len(ready)} scanned prospect(s) are queued and unsent — send those first")

    waiting = [p for p in prospects if p.stage == "sent"]
    if waiting:
        actions.append(f"{len(waiting)} sent with no reply — schedule follow-ups")

    replied = [p for p in prospects if p.stage == "replied"]
    if replied:
        actions.append(f"{len(replied)} replied and not yet booked — book those calls today")

    proposals = [p for p in prospects if p.stage == "proposal"]
    if proposals:
        value = sum(p.deal_value for p in proposals)
        actions.append(f"{len(proposals)} open proposal(s) worth ${value:,.0f} — chase them")

    if state.days_remaining <= model.sales_cycle_days and state.days_remaining > 0:
        actions.append(
            f"Only {state.days_remaining} days left — inside the sales cycle. New sends now "
            "are next month's revenue; focus on closing what's already open."
        )

    return {
        "status": state,
        "requirements": requirements,
        "sends_today": sends_today,
        "catch_up": catch_up,
        "actions": actions,
    }


def observed_yield(prospects: list[Prospect], threshold: int = 45) -> float | None:
    """Your real scan→prospect yield, once you have enough data to say.

    Beats the default guess as soon as you've scanned a couple of hundred sites,
    because it reflects your actual list quality rather than an assumption.
    """
    scanned = [p for p in prospects if p.deal_fit or p.stage != "scanned"]
    if len(scanned) < 20:
        return None
    good = sum(1 for p in scanned if p.deal_fit >= threshold)
    return round(good / len(scanned), 3)
