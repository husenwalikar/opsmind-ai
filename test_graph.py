"""
Pytest Test Suite for LangGraph Multi-Agent State Machine and Docker Sandbox.
Run with: python -m pytest test_graph.py -v
"""

import pytest
from services.agent.graph import (
    RemediationState,
    analyzer_node,
    tester_node as execute_tester_node,
    debugger_node,
    evaluate_test_output,
    remediation_graph,
)
from services.agent.parser import CrashLocation
from services.agent.llm_client import DiagnosticResult
from services.sandbox.docker_runner import (
    SandboxExecutionResult,
    is_docker_available,
    run_in_docker_sandbox,
)

TB_SAMPLE = """
Traceback (most recent call last):
  File "C:/Zephyrus/Husen/Projects/opsmind-ai/test_bed/app/services/billing.py", line 25, in calculate_order_summary
    effective_ratio = round(subtotal / net_payable_base, 2)
ZeroDivisionError: float division by zero
"""


def test_graph_compilation_and_nodes():
    """Verify that the LangGraph StateGraph compiles and contains all 5 architectural nodes."""
    nodes = remediation_graph.nodes
    assert "analyzer_node" in nodes
    assert "coder_node" in nodes
    assert "tester_node" in nodes
    assert "runner_node" in nodes
    assert "debugger_node" in nodes


def test_analyzer_node_execution():
    """Verify AnalyzerNode parses coordinates and populates RAG context."""
    initial_state: RemediationState = {
        "raw_traceback": TB_SAMPLE,
        "crash_location": None,
        "rag_context": None,
        "diagnostic": None,
        "patch_result": None,
        "sandbox_result": None,
        "retry_count": 0,
        "error_feedback": None,
        "status": "INIT",
        "logs": [],
    }

    result = analyzer_node(initial_state)
    assert result["status"] == "ANALYZED"
    assert result["crash_location"].error_type == "ZeroDivisionError"
    assert "billing.py" in result["crash_location"].file_path
    assert result["rag_context"] is not None


def test_tester_node_ast_preflight_rejection():
    """Verify TesterNode rejects invalid Python syntax before container launch."""
    broken_diagnostic = DiagnosticResult(
        root_cause_analysis="Test error",
        confidence_score=0.9,
        target_file="test_bed/app/services/billing.py",
        search_block="effective_ratio = round(subtotal / net_payable_base, 2)",
        replace_block="def broken_syntax(;",  # Syntax error
        explanation="Testing syntax guard",
    )

    state: RemediationState = {
        "raw_traceback": TB_SAMPLE,
        "crash_location": None,
        "rag_context": None,
        "diagnostic": broken_diagnostic,
        "patch_result": None,
        "sandbox_result": None,
        "retry_count": 0,
        "error_feedback": None,
        "status": "CODED",
        "logs": [],
    }

    result = execute_tester_node(state)
    assert result["patch_result"].success is False
    assert "AST Syntax Validation Failed" in result["patch_result"].error


def test_circuit_breaker_routing():
    """Verify conditional edge correctly routes between verified, retry, and manual review."""
    # Case 1: Sandbox passed -> verified
    pass_sandbox = SandboxExecutionResult(
        success=True, exit_code=0, stdout="", stderr="",
        duration_seconds=1.0, mode="docker", network_disabled=True
    )
    state_pass: RemediationState = {
        "sandbox_result": pass_sandbox,
        "retry_count": 0,
        "raw_traceback": "", "crash_location": None, "rag_context": None,
        "diagnostic": None, "patch_result": None, "error_feedback": None,
        "status": "", "logs": []
    }
    assert evaluate_test_output(state_pass) == "verified"

    # Case 2: Sandbox failed, retry_count = 1 (< 3) -> retry
    fail_sandbox = SandboxExecutionResult(
        success=False, exit_code=1, stdout="", stderr="Error",
        duration_seconds=1.0, mode="docker", network_disabled=True
    )
    state_retry: RemediationState = {
        "sandbox_result": fail_sandbox,
        "retry_count": 1,
        "raw_traceback": "", "crash_location": None, "rag_context": None,
        "diagnostic": None, "patch_result": None, "error_feedback": None,
        "status": "", "logs": []
    }
    assert evaluate_test_output(state_retry) == "retry"

    # Case 3: Sandbox failed, retry_count = 3 (limit reached) -> flag_manual_review
    state_exhausted: RemediationState = {
        "sandbox_result": fail_sandbox,
        "retry_count": 3,
        "raw_traceback": "", "crash_location": None, "rag_context": None,
        "diagnostic": None, "patch_result": None, "error_feedback": None,
        "status": "", "logs": []
    }
    assert evaluate_test_output(state_exhausted) == "flag_manual_review"


def test_debugger_node_increments_retry():
    """Verify DebuggerNode increments retry counter and extracts error feedback."""
    fail_sandbox = SandboxExecutionResult(
        success=False, exit_code=1, stdout="", stderr="AssertionError: 0.0 != 1.0",
        duration_seconds=1.0, mode="docker", network_disabled=True
    )
    state: RemediationState = {
        "sandbox_result": fail_sandbox,
        "patch_result": None,
        "retry_count": 1,
        "raw_traceback": "", "crash_location": None, "rag_context": None,
        "diagnostic": None, "error_feedback": None,
        "status": "", "logs": []
    }

    result = debugger_node(state)
    assert result["retry_count"] == 2
    assert "AssertionError" in result["error_feedback"]


def test_docker_sandbox_security_flags():
    """Verify Docker sandbox enforces network_disabled=True and isolation."""
    with open("test_bed/app/services/billing.py", "r", encoding="utf-8") as f:
        orig = f.read()

    # Patched version that passes pytest
    patched = orig.replace(
        "effective_ratio = round(subtotal / net_payable_base, 2)",
        "effective_ratio = 0.0 if net_payable_base == 0 else round(subtotal / net_payable_base, 2)"
    )

    res = run_in_docker_sandbox("test_bed/app/services/billing.py", patched)
    assert res.network_disabled is True
    assert res.exit_code == 0
    assert res.success is True


if __name__ == "__main__":
    pytest.main(["-v", __file__])
