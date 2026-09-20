"""Track record + adaptive indicator weighting.

This is the honest version of "learns from its mistakes": every signal the
agent makes gets logged with a timestamp. Once enough time has passed
(SCORE_HORIZON_DAYS), the next time that symbol is analyzed again, this
module checks what the price actually did and marks each indicator that
contributed to the old signal as having been "right" or "wrong" about the
direction. Each indicator's weight is then its historical win rate, so
indicators with a real track record of being right count for more, and
ones that have been unreliable count for less.

This is a simple, explainable, statistical adaptive system (a per-indicator
win-rate estimate) — not a neural network and not magic. It needs real
elapsed time and real outcomes to mean anything; on a brand new install
every indicator starts at a neutral 0.5 weight (a coin flip) until enough
signals have matured to say otherwise.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass

DB_PATH = os.environ.get(
    "AGENT_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "agent_history.db")
)

# How long to wait before checking whether a signal was right. Real trading
# systems would use several horizons; one is enough to keep this readable.
SCORE_HORIZON_DAYS = int(os.environ.get("AGENT_SCORE_HORIZON_DAYS", "7"))

# A move smaller than this is "flat" — not enough to call bullish or bearish.
FLAT_THRESHOLD_PCT = 1.0

DEFAULT_WEIGHT = 0.5
MIN_WEIGHT = 0.15  # floor so one bad stretch can't zero an indicator out
MAX_WEIGHT = 0.95  # ceiling so no indicator is ever treated as infallible


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                kind TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                price REAL NOT NULL,
                verdict TEXT NOT NULL,
                indicators TEXT NOT NULL,
                scored INTEGER NOT NULL DEFAULT 0,
                outcome TEXT,
                forward_return REAL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS indicator_weights (
                indicator TEXT PRIMARY KEY,
                correct INTEGER NOT NULL DEFAULT 0,
                incorrect INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        yield conn
        conn.commit()
    finally:
        conn.close()


@dataclass
class ScoredSignal:
    symbol: str
    timestamp: str
    old_verdict: str
    forward_return_pct: float
    outcome: str  # "correct" or "incorrect"


def get_weights(indicator_names: list[str]) -> dict[str, float]:
    """Return the current learned weight for each indicator, 0.5 if unknown."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT indicator, correct, incorrect FROM indicator_weights"
        ).fetchall()
    stats = {name: (correct, incorrect) for name, correct, incorrect in rows}

    weights = {}
    for name in indicator_names:
        correct, incorrect = stats.get(name, (0, 0))
        total = correct + incorrect
        if total == 0:
            weights[name] = DEFAULT_WEIGHT
        else:
            raw = correct / total
            weights[name] = max(MIN_WEIGHT, min(MAX_WEIGHT, raw))
    return weights


def log_signal(symbol: str, kind: str, price: float, verdict: str, indicator_directions: dict[str, str]) -> None:
    """Record a new signal so it can be scored later.

    indicator_directions maps indicator name -> "bullish" | "bearish" | "neutral".
    """
    with _connect() as conn:
        conn.execute(
            "INSERT INTO signals (symbol, kind, timestamp, price, verdict, indicators) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                symbol,
                kind,
                dt.datetime.now(dt.timezone.utc).isoformat(),
                price,
                verdict,
                json.dumps(indicator_directions),
            ),
        )


def score_due_signals(symbol: str, current_price: float) -> list[ScoredSignal]:
    """Score any of this symbol's past signals old enough to check, updating
    indicator weights as it goes. Returns what it scored, for display.
    """
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=SCORE_HORIZON_DAYS)

    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, timestamp, price, verdict, indicators FROM signals "
            "WHERE symbol = ? AND scored = 0",
            (symbol,),
        ).fetchall()

        scored: list[ScoredSignal] = []

        for row_id, timestamp, old_price, old_verdict, indicators_json in rows:
            signal_time = dt.datetime.fromisoformat(timestamp)
            if signal_time > cutoff:
                continue  # not old enough yet

            forward_return_pct = (current_price - old_price) / old_price * 100

            if old_verdict == "NEUTRAL":
                # A neutral call is "correct" if the price stayed roughly flat.
                actual_correct = abs(forward_return_pct) < FLAT_THRESHOLD_PCT
            elif old_verdict == "BULLISH":
                actual_correct = forward_return_pct > 0
            else:  # BEARISH
                actual_correct = forward_return_pct < 0

            outcome = "correct" if actual_correct else "incorrect"

            indicator_directions: dict[str, str] = json.loads(indicators_json)
            for name, direction in indicator_directions.items():
                if direction not in ("bullish", "bearish"):
                    continue
                direction_was_right = (
                    (direction == "bullish" and forward_return_pct > 0)
                    or (direction == "bearish" and forward_return_pct < 0)
                )
                conn.execute(
                    "INSERT INTO indicator_weights (indicator, correct, incorrect) "
                    "VALUES (?, ?, ?) "
                    "ON CONFLICT(indicator) DO UPDATE SET "
                    "correct = correct + excluded.correct, "
                    "incorrect = incorrect + excluded.incorrect",
                    (name, 1 if direction_was_right else 0, 0 if direction_was_right else 1),
                )

            conn.execute(
                "UPDATE signals SET scored = 1, outcome = ?, forward_return = ? WHERE id = ?",
                (outcome, forward_return_pct, row_id),
            )

            scored.append(
                ScoredSignal(
                    symbol=symbol,
                    timestamp=timestamp,
                    old_verdict=old_verdict,
                    forward_return_pct=forward_return_pct,
                    outcome=outcome,
                )
            )

    return scored


@dataclass
class TrackRecord:
    total_scored: int
    correct: int
    accuracy_pct: float | None
    indicator_accuracy: dict[str, float]  # indicator -> win rate (0-1)


def get_track_record(symbol: str | None = None) -> TrackRecord:
    """Aggregate accuracy stats, optionally filtered to one symbol."""
    with _connect() as conn:
        if symbol:
            rows = conn.execute(
                "SELECT outcome FROM signals WHERE scored = 1 AND symbol = ?", (symbol,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT outcome FROM signals WHERE scored = 1").fetchall()

        indicator_rows = conn.execute(
            "SELECT indicator, correct, incorrect FROM indicator_weights"
        ).fetchall()

    total = len(rows)
    correct = sum(1 for (outcome,) in rows if outcome == "correct")
    accuracy = (correct / total * 100) if total else None

    indicator_accuracy = {}
    for name, c, i in indicator_rows:
        t = c + i
        if t > 0:
            indicator_accuracy[name] = c / t

    return TrackRecord(
        total_scored=total, correct=correct, accuracy_pct=accuracy, indicator_accuracy=indicator_accuracy
    )
