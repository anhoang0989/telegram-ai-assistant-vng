from src.ai.quota_tracker import QuotaTracker, ModelQuota


def test_fresh_tracker_has_quota():
    tracker = QuotaTracker()
    for model in ["gemini-2.5-flash-lite-preview-06-17", "gemini-2.5-pro"]:
        assert tracker.available(model)


def test_record_consumes_quota():
    q = ModelQuota(rpm=2, rpd=10)
    assert q.available()
    q.record()
    q.record()
    assert not q.available()  # hit RPM cap


def test_unknown_model_optimistic():
    tracker = QuotaTracker()
    assert tracker.available("unknown-model-xyz")


def test_status_reports_usage():
    tracker = QuotaTracker()
    model = "gemini-2.5-flash"
    tracker.record(model)
    tracker.record(model)
    status = tracker.status()
    assert status[model]["rpm_used"] == 2
