from __future__ import annotations

import logging

from app.extensions import scheduler

logger = logging.getLogger("fuehub.scheduler")


def register_jobs(app) -> None:
    interval_seconds = app.config.get("FOLLOWUP_TICK_SECONDS", 3600)

    def _followup_tick() -> None:
        with app.app_context():
            from app.services.followup_service import run_followup_tick

            try:
                sent = run_followup_tick()
                if sent:
                    logger.info("follow-up tick: sent %d nudge(s)", sent)
            except Exception:  # noqa: BLE001 - a scheduled job must never crash the process
                logger.exception("follow-up tick failed")

    scheduler.add_job(_followup_tick, "interval", seconds=interval_seconds, id="followup_tick", replace_existing=True)
