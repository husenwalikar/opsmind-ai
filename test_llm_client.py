"""
Pytest Test Suite for services/agent/llm_client.py
Run with: pytest test_llm_client.py
"""

import os
import pytest
from dotenv import load_dotenv

load_dotenv()

from services.agent.parser import CrashLocation, parse_crash_traceback
from data.seed_chroma import query_incident_context
from services.agent.llm_client import (
    DiagnosticResult,
    diagnose_and_generate_patch,
    format_diagnostic_prompt,
    clean_json_response,
)

TB_BILLING = """
Traceback (most recent call last):
  File "C:\\Zephyrus\\Husen\\Projects\\opsmind-ai\\test_bed\\app\\services\\billing.py", line 19, in calculate_order_summary
    effective_discount_ratio = subtotal / net_payable_base
                               ~~~~~~~~~^~~~~~~~~~~~~~~~~~
ZeroDivisionError: float division by zero
"""


def test_format_diagnostic_prompt_deterministic():
    crash = parse_crash_traceback(TB_BILLING)
    mock_rag = {
        "rag_prompt_snippet": "### Service Runbook Invariant\nWhen discount_amount == total_amount, return 0.0."
    }
    prompt = format_diagnostic_prompt(crash, mock_rag)
    assert "ZeroDivisionError" in prompt
    assert "billing.py" in prompt
    assert "return 0.0" in prompt


def test_clean_json_response_markdown_stripping():
    raw_with_fences = """```json
{
  "root_cause_analysis": "Division by zero",
  "confidence_score": 0.95,
  "target_file": "billing.py",
  "search_block": "a / b",
  "replace_block": "0.0 if b == 0 else a / b",
  "explanation": "Safe guard"
}
```"""
    parsed = clean_json_response(raw_with_fences)
    assert parsed["confidence_score"] == 0.95
    assert parsed["search_block"] == "a / b"


def test_clean_json_response_plain():
    raw_plain = '{"root_cause_analysis": "test", "confidence_score": 1.0, "target_file": "f.py", "search_block": "x", "replace_block": "y", "explanation": "z"}'
    parsed = clean_json_response(raw_plain)
    assert parsed["root_cause_analysis"] == "test"


def test_diagnose_and_generate_patch_live():
    # Live end-to-end integration test against Groq LPU
    crash = parse_crash_traceback(TB_BILLING)
    rag = query_incident_context(
        crash.error_type,
        crash.error_message,
        crash.source_context,
        persist_dir="data/chroma_db",
    )
    result = diagnose_and_generate_patch(crash, rag)
    assert isinstance(result, DiagnosticResult)
    assert "billing.py" in result.target_file
    assert "subtotal / net_payable_base" in result.search_block
    assert len(result.replace_block.strip()) > 0
    assert result.confidence_score >= 0.5


if __name__ == "__main__":
    pytest.main(["-v", __file__])
