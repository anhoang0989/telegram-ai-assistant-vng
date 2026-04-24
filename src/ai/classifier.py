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


# Maps complexity → starting tier index (0-based into TIER list)
COMPLEXITY_START = {"simple": 0, "medium": 1, "complex": 2}
