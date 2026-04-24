import time
from collections import defaultdict
from dataclasses import dataclass, field

# Gemini free tier limits (conservative estimates)
# Actual limits: https://ai.google.dev/pricing
DEFAULT_LIMITS = {
    "gemini-2.5-flash-lite-preview-06-17": {"rpm": 30, "rpd": 1500},
    "gemini-2.5-flash":                    {"rpm": 15, "rpd": 1500},
    "gemini-2.5-pro":                      {"rpm": 5,  "rpd": 25},
    "llama-3.3-70b-versatile":             {"rpm": 30, "rpd": 14400},  # Groq free
}


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


class QuotaTracker:
    def __init__(self) -> None:
        self._quotas: dict[str, ModelQuota] = {
            name: ModelQuota(rpm=limits["rpm"], rpd=limits["rpd"])
            for name, limits in DEFAULT_LIMITS.items()
        }

    def available(self, model: str) -> bool:
        if model not in self._quotas:
            return True  # Unknown model — optimistically allow
        return self._quotas[model].available()

    def record(self, model: str) -> None:
        if model in self._quotas:
            self._quotas[model].record()

    def status(self) -> dict[str, dict]:
        result = {}
        for name, q in self._quotas.items():
            q._prune()
            result[name] = {
                "rpm_used": len(q._minute_calls),
                "rpm_limit": q.rpm,
                "rpd_used": len(q._day_calls),
                "rpd_limit": q.rpd,
            }
        return result


# Singleton — shared across the process
quota_tracker = QuotaTracker()
