from src.ai.tools import TOOLS


REQUIRED_TOOLS = {
    "save_note", "search_notes", "list_notes",
    "create_schedule", "list_schedules", "delete_schedule",
    "save_meeting_summary", "list_meetings",
}


def test_all_required_tools_defined():
    defined = {t["name"] for t in TOOLS}
    assert REQUIRED_TOOLS == defined


def test_create_schedule_has_iso_datetime_description():
    tool = next(t for t in TOOLS if t["name"] == "create_schedule")
    assert "ISO 8601" in tool["input_schema"]["properties"]["scheduled_at"]["description"]


def test_save_meeting_has_action_items_schema():
    tool = next(t for t in TOOLS if t["name"] == "save_meeting_summary")
    props = tool["input_schema"]["properties"]
    assert "summary" in props
    assert "action_items" in props
    assert "counterarguments" in props


def test_all_tools_have_required_fields():
    for t in TOOLS:
        assert "name" in t
        assert "description" in t
        assert "input_schema" in t
        assert t["input_schema"].get("type") == "object"
