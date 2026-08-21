"""
Pytest Test Suite for services/agent/parser.py
Run with: pytest test_parser.py
"""

import os
import pytest
from services.agent.parser import (
    normalize_traceback_text,
    extract_exception_details,
    extract_failing_frame,
    extract_source_window,
    parse_crash_traceback,
    CrashLocation,
)

TB_STANDARD = """
Traceback (most recent call last):
  File "C:\\Zephyrus\\Husen\\Projects\\opsmind-ai\\test_bed\\app\\services\\billing.py", line 19, in calculate_order_summary
    effective_discount_ratio = subtotal / net_payable_base
                               ~~~~~~~~~^~~~~~~~~~~~~~~~~~
ZeroDivisionError: float division by zero
"""

TB_POLLUTED = """
Traceback (most recent call last):
  File "C:/Python314/Lib/site-packages/uvicorn/protocols/http/httptools_impl.py", line 426, in run_asgi
    result = await app(self.scope, self.receive, self.send)
  File "C:/Python314/Lib/site-packages/starlette/routing.py", line 680, in app
    await route.handle(scope, receive, send)
  File "C:/Zephyrus/Husen/Projects/opsmind-ai/test_bed/app/services/checkout.py", line 23, in process_order_checkout
    destination = customer_payload["shipping_address"]
KeyError: 'shipping_address'
"""

TB_SYNTAX = """
  File "C:/Zephyrus/Husen/Projects/opsmind-ai/test_bed/app/services/auth.py", line 14
    def verify_permissions(
                          ^
SyntaxError: invalid syntax
"""

TB_CHAINED = """
Traceback (most recent call last):
  File "C:\\Zephyrus\\Husen\\Projects\\opsmind-ai\\test_bed\\app\\services\\billing.py", line 19, in calculate_order_summary
    effective_discount_ratio = subtotal / net_payable_base
ZeroDivisionError: float division by zero

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "C:\\Zephyrus\\Husen\\Projects\\opsmind-ai\\test_bed\\app\\main.py", line 45, in checkout_endpoint
    raise RuntimeError("Payment pipeline failed") from e
RuntimeError: Payment pipeline failed
"""


def test_normalize_traceback():
    lines = normalize_traceback_text(TB_STANDARD)
    assert len(lines) >= 3


def test_extract_exception_details():
    lines = normalize_traceback_text(TB_STANDARD)
    err_type, err_msg = extract_exception_details(lines)
    assert err_type == "ZeroDivisionError"
    assert "division by zero" in err_msg


def test_extract_failing_frame_pollution():
    lines = normalize_traceback_text(TB_POLLUTED)
    frame = extract_failing_frame(lines)
    assert frame is not None
    assert "checkout.py" in frame["file_path"]
    assert frame["line_number"] == 23


def test_extract_failing_frame_syntax_error():
    lines = normalize_traceback_text(TB_SYNTAX)
    frame = extract_failing_frame(lines)
    assert frame is not None
    assert "auth.py" in frame["file_path"]


def test_path_traversal_guard():
    # Attempting to access an arbitrary file outside allowed_root
    output = extract_source_window(
        file_path="C:/Windows/System32/drivers/etc/hosts",
        line_number=1,
        allowed_root="C:/Zephyrus/Husen/Projects/opsmind-ai/test_bed",
    )
    assert "Security Guard" in output
    assert "Access denied" in output or "traverses across" in output


def test_chained_exception_targeting_root_cause():
    # Chained exception must target the root cause (ZeroDivisionError in billing.py), not outer RuntimeError
    location = parse_crash_traceback(TB_CHAINED)
    assert location.error_type == "ZeroDivisionError"
    assert "billing.py" in location.file_path
    assert location.line_number == 19


def test_parse_crash_traceback_full():
    location = parse_crash_traceback(TB_STANDARD)
    assert isinstance(location, CrashLocation)
    assert location.error_type == "ZeroDivisionError"
    assert ">>" in location.source_context


if __name__ == "__main__":
    pytest.main(["-v", __file__])
