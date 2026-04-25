"""
Per-user quota tracker. Each user's free-tier limit is tracked independently
since they use their own API keys (BYOK).
"""
import time
from collections import defaultdict
from dataclasses import dataclass, field

# Free tier limits per user per model (verified từ Google AI Studio rate-limit dashboard 2026-04)
# Pro models: free=0, chỉ work nếu key trả phí — vẫn track để tránh waste call
DEFAULT_LIMITS = {
    "gemini-3-flash-lite-preview":  {"rpm": 15, "rpd": 500},
    "gemini-2.5-flash-lite":        {"rpm": 10, "rpd": 20},
    "gemini-3-flash-preview":       {"rpm": 5,  "rpd": 20},
    "gemini-2.5-flash":             {"rpm": 5,  "rpd": 20},
    "llama-3.3-70b-versatile":      {"rpm": 30, "rpd": 1000},
    "gemini-3-pro-preview":         {"rpm": 999, "rpd": 999},  # paid only
    "gemini-2.5-pro":               {"rpm": 999, "rpd": 999},  # paid only
}


def get_limits(model: str) -> dict:
    """Tra limits cho 1 model — nếu unknown trả limits mặc định an toàn."""
    return DEFAULT_LIMITS.get(model, {"rpm": 5, "rpd": 20})


@dataclass
class ModelQuota:
    rpm: int
    rpd: int
    _minute_calls: list[float] = field(default_factory=list)
    _day_calls: list[float] = field(default_factory=list)

    def _prune(self) -> None:
        now = time.time()
        self._minute_calls = [t for t in self._minute_calls if now - t < 60]
        self._day_calls = [t for t in self._day_calls if now - t < 86400]

    def available(self) -> bool:
        self._prune()
        return len(self._minute_calls) < self.rpm and len(self._day_calls) < self.rpd

    def record(self) -> None:
        now = time.time()
        self._minute_calls.append(now)
        self._day_calls.append(now)

    def mark_exhausted(self) -> None:
        """Đánh dấu hết quota cho cả ngày — dùng khi API trả 429."""
        now = time.time()
        self._day_calls = [now] * self.rpd
        self._minute_calls = [now] * self.rpm


class QuotaTracker:
    """Nested dict: user_id → model_name → ModelQuota."""

    def __init__(self) -> None:
        self._user_quotas: dict[int, dict[str, ModelQuota]] = defaultdict(self._build_user_quotas)

    @staticmethod
    def _build_user_quotas() -> dict[str, ModelQuota]:
        return {
            name: ModelQuota(rpm=limits["rpm"], rpd=limits["rpd"])
            for name, limits in DEFAULT_LIMITS.items()
        }

    def available(self, user_id: int, model: str) -> bool:
        quotas = self._user_quotas[user_id]
        if model not in quotas:
            return True
        return quotas[model].available()

    def record(self, user_id: int, model: str) -> None:
        quotas = self._user_quotas[user_id]
        if model in quotas:
            quotas[model].record()

    def mark_exhausted(self, user_id: int, model: str) -> None:
        quotas = self._user_quotas[user_id]
        if model in quotas:
            quotas[model].mark_exhausted()

    def status(self, user_id: int) -> dict[str, dict]:
        quotas = self._user_quotas[user_id]
        result = {}
        for name, q in quotas.items():
            q._prune()
            result[name] = {
                "rpm_used": len(q._minute_calls),
                "rpm_limit": q.rpm,
                "rpd_used": len(q._day_calls),
                "rpd_limit": q.rpd,
            }
        return result


quota_tracker = QuotaTracker()
