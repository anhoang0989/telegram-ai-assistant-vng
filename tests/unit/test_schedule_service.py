import pytest
from datetime import datetime, timezone
from tests.conftest import db_session
from src.services.schedule_service import create_schedule, list_schedules, parse_iso


def test_parse_iso_with_timezone():
    dt = parse_iso("2026-05-01T09:00:00+07:00")
    assert dt.hour == 9
    assert dt.tzinfo is not None


def test_parse_iso_naive_gets_localized():
    dt = parse_iso("2026-05-01T09:00:00")
    assert dt.tzinfo is not None


@pytest.mark.asyncio
async def test_create_and_list_schedule(db_session):
    s = await create_schedule(
        db_session,
        title="Họp product review",
        scheduled_at_str="2099-12-31T15:00:00+07:00",
    )
    assert s.id is not None
    assert s.title == "Họp product review"

    listing = await list_schedules(db_session, days_ahead=999999)
    assert "Họp product review" in listing


@pytest.mark.asyncio
async def test_list_schedules_empty(db_session):
    result = await list_schedules(db_session, days_ahead=7)
    assert "Không có lịch" in result
