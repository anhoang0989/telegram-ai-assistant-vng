import pytest
from datetime import datetime, timezone
from tests.conftest import db_session
from src.db.repositories import notes as notes_repo, schedules as sched_repo, conversation as conv_repo


@pytest.mark.asyncio
async def test_conversation_save_and_retrieve(db_session):
    await conv_repo.save(db_session, user_id=111, role="user", content="Xin chào")
    await conv_repo.save(db_session, user_id=111, role="assistant", content="Chào mày!")

    history = await conv_repo.get_recent(db_session, user_id=111)
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[1].role == "assistant"


@pytest.mark.asyncio
async def test_note_search_full_text(db_session):
    await notes_repo.create(db_session, title="Revenue report", content="Doanh thu tháng 4 tăng 20%")
    await notes_repo.create(db_session, title="Bug report", content="Crash on Android 13")

    results = await notes_repo.search(db_session, "tháng 4")
    assert len(results) == 1
    assert "Revenue" in results[0].title


@pytest.mark.asyncio
async def test_schedule_mark_notified(db_session):
    s = await sched_repo.create(
        db_session,
        title="Test reminder",
        scheduled_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    assert not s.notified

    pending = await sched_repo.get_pending_unnotified(db_session)
    assert any(p.id == s.id for p in pending)

    await sched_repo.mark_notified(db_session, s.id)
    pending_after = await sched_repo.get_pending_unnotified(db_session)
    assert not any(p.id == s.id for p in pending_after)


@pytest.mark.asyncio
async def test_auth_blocks_unknown_user():
    from src.bot.middleware import is_allowed
    # Known allowed user from env would pass, unknown should fail
    assert not is_allowed(0)
