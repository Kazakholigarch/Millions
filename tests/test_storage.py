"""Persistence. The property that matters: a re-scan must not destroy history."""
from __future__ import annotations

import pytest

from engine.checks import Finding
from engine.pipeline import Prospect
from engine.scan import AuditResult
from engine.storage import Store


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(tmp_path / ".engine")


def make_scan(domain="acme.com") -> AuditResult:
    result = AuditResult(url=f"https://{domain}/", domain=domain, scanned_at="2026-01-01T00:00:00+00:00", ok=True)
    result.findings = [
        Finding(code="A", title="t", category="seo", severity="high", evidence="e",
                impact="i", fix="f", effort_hours=2.0, metrics={"x": 1})
    ]
    return result


def test_scan_survives_a_roundtrip(store):
    store.save_scan(make_scan())
    loaded = store.load_scan("acme.com")
    assert loaded.findings[0].code == "A"
    assert loaded.findings[0].metrics == {"x": 1}


def test_domain_lookup_is_case_insensitive(store):
    store.save_scan(make_scan())
    assert store.load_scan("ACME.com") is not None


def test_missing_scan_returns_none(store):
    assert store.load_scan("nope.com") is None


def test_corrupt_scan_file_does_not_break_the_campaign(store):
    store.save_scan(make_scan())
    store.ensure()
    (store.scans_dir / "broken.json").write_text("{not json", encoding="utf-8")
    assert len(store.all_scans()) == 1  # the good one still loads


def test_rescanning_preserves_stage_and_history(store):
    """The bug this prevents: a re-scan silently resetting a won deal to 'scanned'."""
    store.upsert_prospect(Prospect(domain="acme.com", company="Acme", deal_fit=40))
    prospect = store.get_prospect("acme.com")
    prospect.advance("sent", "opener")
    prospect.advance("replied")
    store.save_prospects([prospect])

    store.upsert_prospect(Prospect(domain="acme.com", company="Acme Ltd", deal_fit=85, deal_value=20000))

    after = store.get_prospect("acme.com")
    assert after.stage == "replied"  # preserved
    assert len(after.history) == 2  # preserved
    assert after.company == "Acme Ltd"  # updated
    assert after.deal_fit == 85  # updated


def test_config_ignores_unknown_keys(store):
    store.save_config({"sender": {"name": "Dan", "email": "d@e.com", "nonsense": "x"}})
    assert store.sender().name == "Dan"


def test_model_reads_nested_rates(store):
    store.save_config({"model": {"target_revenue": 50000, "rates": {"send_to_reply": 0.2}}})
    model = store.model()
    assert model.target_revenue == 50000
    assert model.rates.send_to_reply == 0.2


def test_defaults_apply_with_no_config(store):
    assert store.model().target_revenue == 100_000
    assert store.started_on() is None


def test_invalid_start_date_is_ignored_rather_than_raising(store):
    store.save_config({"started_on": "not-a-date"})
    assert store.started_on() is None


def test_writes_are_atomic_leaving_no_temp_files(store):
    store.save_prospects([Prospect(domain="a.com")])
    assert list(store.root.glob("*.tmp")) == []
