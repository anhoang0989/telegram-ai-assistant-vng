import re

# Keywords that signal a complex task needing deeper reasoning
_COMPLEX_PATTERNS = re.compile(
    r"(meeting|minutes|tổng hợp|phân tích|chiến lược|strategy|kế hoạch|"
    r"đánh giá|báo cáo|report|recommend|khuyến nghị|phản biện|"
    r"so sánh|benchmark|roadmap|pitch|proposal)",
    re.IGNORECASE,
)

_MEDIUM_PATTERNS = re.compile(
    r"(tại sao|why|how|như thế nào|giải thích|explain|"
    r"tìm|search|lịch sử|trend|xu hướng|market|thị trường)",
    re.IGNORECASE,
)


def classify(text: str) -> str:
    """
    Returns 'simple', 'medium', or 'complex'.
    Used to pick the starting LLM tier before applying quota fallback.
    """
    if _COMPLEX_PATTERNS.search(text):
        return "complex"
    if len(text) > 120 or _MEDIUM_PATTERNS.search(text):
        return "medium"
    return "simple"


# Maps complexity → starting tier index (0-based into TIER list).
# - simple → tier 0 (gemini-3-flash-lite, 500 RPD, default workhorse)
# - medium → tier 2 (gemini-3-flash, reasoning Gen3) — fallback xuống flash-lite nếu hết quota
# - complex → tier 2 (gemini-3-flash) — Pro chỉ reach được qua fallback nếu key trả phí
# Không dùng start=Pro vì free tier = 0, sẽ luôn fail call đầu tiên.
COMPLEXITY_START = {"simple": 0, "medium": 2, "complex": 2}
