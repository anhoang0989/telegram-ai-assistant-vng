from src.ai.classifier import classify


def test_simple_greeting():
    assert classify("xin chào") == "simple"
    assert classify("ok") == "simple"


def test_medium_question():
    assert classify("tại sao DAU giảm trong Q1?") == "medium"
    assert classify("explain monetization strategy") == "medium"


def test_complex_tasks():
    assert classify("tổng hợp meeting này giúp tao") == "complex"
    assert classify("phân tích chiến lược retention") == "complex"
    assert classify("đưa ra khuyến nghị cho Q2") == "complex"


def test_long_message_is_medium_or_complex():
    long_text = "a" * 200
    assert classify(long_text) in {"medium", "complex"}
