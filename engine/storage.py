"""Plain JSON persistence under `.engine/`.

No database. The entire state of a campaign is a handful of readable JSON files
you can grep, diff, back up with `cp -r`, and hand to a spreadsheet when a
client asks for a report. For a thing one person runs for thirty days, that is
the correct amount of infrastructure.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from .outreach import Sender
from .pipeline import FunnelModel, FunnelRates, Prospect
from .scan import AuditResult

DEFAULT_ROOT = Path(".engine")


class Store:
    """Everything a campaign knows, on disk."""

    def __init__(self, root: Path | str = DEFAULT_ROOT):
        self.root = Path(root)
        self.scans_dir = self.root / "scans"
        self.drafts_dir = self.root / "drafts"
        self.reports_dir = self.root / "reports"
        self.prospects_path = self.root / "prospects.json"
        self.config_path = self.root / "config.json"

    def ensure(self) -> None:
        for directory in (self.root, self.scans_dir, self.drafts_dir, self.reports_dir):
            directory.mkdir(parents=True, exist_ok=True)

    # -- scans -------------------------------------------------------------

    def save_scan(self, result: AuditResult) -> Path:
        self.ensure()
        path = self.scans_dir / f"{_slug(result.domain)}.json"
        _write_json(path, result.to_dict())
        return path

    def load_scan(self, domain: str) -> AuditResult | None:
        path = self.scans_dir / f"{_slug(domain)}.json"
        data = _read_json(path)
        return AuditResult.from_dict(data) if data else None

    def all_scans(self) -> list[AuditResult]:
        if not self.scans_dir.exists():
            return []
        results = []
        for path in sorted(self.scans_dir.glob("*.json")):
            data = _read_json(path)
            if data:
                try:
                    results.append(AuditResult.from_dict(data))
                except (TypeError, KeyError):
                    continue  # a corrupt file shouldn't break the whole campaign
        return results

    # -- prospects ---------------------------------------------------------

    def load_prospects(self) -> list[Prospect]:
        data = _read_json(self.prospects_path) or []
        return [Prospect.from_dict(item) for item in data]

    def save_prospects(self, prospects: list[Prospect]) -> None:
        self.ensure()
        _write_json(self.prospects_path, [p.to_dict() for p in prospects])

    def get_prospect(self, domain: str) -> Prospect | None:
        target = _slug(domain)
        return next((p for p in self.load_prospects() if _slug(p.domain) == target), None)

    def upsert_prospect(self, prospect: Prospect) -> Prospect:
        """Insert, or merge into an existing record without losing its history."""
        prospects = self.load_prospects()
        target = _slug(prospect.domain)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        for index, existing in enumerate(prospects):
            if _slug(existing.domain) == target:
                # Re-scanning must not silently reset a prospect's stage or wipe
                # the trail of what you've already sent them.
                merged = asdict(existing)
                for key, value in prospect.to_dict().items():
                    if key in ("stage", "history", "created_at"):
                        continue
                    if value not in (None, "", 0, 0.0, []):
                        merged[key] = value
                merged["updated_at"] = now
                prospects[index] = Prospect.from_dict(merged)
                self.save_prospects(prospects)
                return prospects[index]

        prospect.created_at = prospect.created_at or now
        prospect.updated_at = now
        prospects.append(prospect)
        self.save_prospects(prospects)
        return prospect

    # -- drafts & reports --------------------------------------------------

    def save_draft(self, domain: str, variant: str, text: str) -> Path:
        self.ensure()
        path = self.drafts_dir / f"{_slug(domain)}.{variant}.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def save_report(self, domain: str, suffix: str, text: str) -> Path:
        self.ensure()
        path = self.reports_dir / f"{_slug(domain)}-audit.{suffix}"
        path.write_text(text, encoding="utf-8")
        return path

    # -- config ------------------------------------------------------------

    def load_config(self) -> dict:
        return _read_json(self.config_path) or {}

    def save_config(self, config: dict) -> None:
        self.ensure()
        _write_json(self.config_path, config)

    def sender(self) -> Sender:
        data = self.load_config().get("sender", {})
        known = {f.name for f in Sender.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return Sender(**{k: v for k, v in data.items() if k in known})

    def model(self) -> FunnelModel:
        data = self.load_config().get("model", {})
        rates = FunnelRates(**data.pop("rates", {})) if isinstance(data.get("rates"), dict) else FunnelRates()
        known = {f.name for f in FunnelModel.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        kwargs = {k: v for k, v in data.items() if k in known and k != "rates"}
        return FunnelModel(rates=rates, **kwargs)

    def started_on(self) -> date | None:
        raw = self.load_config().get("started_on")
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None

    def set_started_on(self, when: date) -> None:
        config = self.load_config()
        config["started_on"] = when.isoformat()
        self.save_config(config)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9.-]+", "-", text.lower()).strip("-") or "unknown"


def _read_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_json(path: Path, data) -> None:
    # Write-then-rename: an interrupted write must not corrupt the campaign.
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    temp.replace(path)
