import pytest
from tests.conftest import db_session
from src.services.note_service import save_note, list_notes, search_notes


@pytest.mark.asyncio
async def test_save_and_list_note(db_session):
    note = await save_note(db_session, title="Test Note", content="Nội dung test", tags=["test"])
    assert note.id is not None
    assert note.title == "Test Note"

    listing = await list_notes(db_session)
    assert "Test Note" in listing


@pytest.mark.asyncio
async def test_search_notes_by_keyword(db_session):
    await save_note(db_session, title="KPI tháng 4", content="KPI đạt 85% target")
    await save_note(db_session, title="Meeting recap", content="Thảo luận về roadmap Q2")

    result = await search_notes(db_session, "KPI")
    assert "KPI" in result

    result2 = await search_notes(db_session, "xyz_not_exist")
    assert "Không tìm thấy" in result2


@pytest.mark.asyncio
async def test_save_note_with_tags(db_session):
    note = await save_note(db_session, title="Tagged", content="Content", tags=["game", "vn"])
    assert "game" in note.tags
    assert "vn" in note.tags
