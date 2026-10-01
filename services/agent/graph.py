"""
LangGraph Multi-Agent Remediation State Machine.
Orchestrates autonomous diagnosis, coding, testing, and debugging with a 3-retry circuit breaker.
Conforms strictly to the OpsMind SRE architecture:
  Analyzer Node -> Coder Node -> Tester Node -> Runner Node (Docker Sandbox) -> Evaluator -> Debugger Node / END
"""

import time
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from data.seed_chroma import query_incident_context
from services.agent.llm_client import (
    DiagnosticResult,
    diagnose_and_generate_patch,
)
from services.agent.parser import CrashLocation, parse_crash_traceback
from services.agent.patcher import PatchResult, synthesize_patch
from services.sandbox.docker_runner import (
    SandboxExecutionResult,
    run_in_docker_sandbox,
)


class RemediationState(TypedDict):
    """Shared state dictionary passed across all agent nodes."""
    raw_traceback: str
    crash_location: Optional[CrashLocation]
    rag_context: Optional[Dict[str, Any]]
    diagnostic: Optional[DiagnosticResult]
    patch_result: Optional[PatchResult]
    sandbox_result: Optional[SandboxExecutionResult]
    retry_count: int
    error_feedback: Optional[str]
    status: str
    logs: List[str]


# ── NODE 1: ANALYZER NODE ────────────────────────────────────────────────────

def analyzer_node(state: RemediationState) -> Dict[str, Any]:
    """
    Ingests raw traceback telemetry, isolates failing application coordinates,
    and queries ChromaDB for historical incident runbooks and invariants.
    """
    raw_tb = state["raw_traceback"]
    log_entry = f"[AnalyzerNode] Ingesting traceback and parsing failure coordinates..."
    
    # 1. Parse crash coordinates
    crash_loc = parse_crash_traceback(raw_tb)
    
    # 2. Query ChromaDB vector knowledge base
    rag_ctx = query_incident_context(
        error_type=crash_loc.error_type,
        error_message=crash_loc.error_message,
        source_context=crash_loc.source_context,
        persist_dir="data/chroma_db",
    )
    
    inc_id = rag_ctx.get("incident", {}).get("id", "none")
    rb_id = rag_ctx.get("runbook", {}).get("id", "none")
    log_detail = (
        f"[AnalyzerNode] Target: {crash_loc.file_path}:{crash_loc.line_number} ({crash_loc.error_type}). "
        f"RAG Matches: incident={inc_id}, runbook={rb_id}"
    )

    return {
        "crash_location": crash_loc,
        "rag_context": rag_ctx,
        "status": "ANALYZED",
        "logs": state.get("logs", []) + [log_entry, log_detail],
    }


# ── NODE 2: CODER NODE ───────────────────────────────────────────────────────

def coder_node(state: RemediationState) -> Dict[str, Any]:
    """
    Invokes Groq LPU reasoning agent with coordinates, RAG invariants,
    and prior feedback to synthesize a surgical SEARCH/REPLACE patch.
    """
    crash_loc = state["crash_location"]
    rag_ctx = state["rag_context"]
    error_fb = state.get("error_feedback")
    attempt_num = state.get("retry_count", 0) + 1

    log_entry = f"[CoderNode] Synthesizing patch proposal (Attempt {attempt_num}/3)..."

    diagnostic = diagnose_and_generate_patch(
        crash_location=crash_loc,
        rag_context=rag_ctx,
        previous_error=error_fb,
    )

    log_detail = (
        f"[CoderNode] Generated SEARCH/REPLACE patch for {diagnostic.target_file} "
        f"(Confidence: {diagnostic.confidence_score * 100:.1f}%)"
    )

    return {
        "diagnostic": diagnostic,
        "status": "PATCH_GENERATED",
        "logs": state.get("logs", []) + [log_entry, log_detail],
    }


# ── NODE 3: TESTER NODE ──────────────────────────────────────────────────────

def tester_node(state: RemediationState) -> Dict[str, Any]:
    """
    Enforces in-memory AST syntax compilation checks and generates standard
    git-compatible unified diffs without modifying host source files.
    """
    diagnostic = state["diagnostic"]
    log_entry = f"[TesterNode] Validating AST syntax and synthesizing unified diff..."

    patch_res = synthesize_patch(
        target_file=diagnostic.target_file,
        search_block=diagnostic.search_block,
        replace_block=diagnostic.replace_block,
    )

    if patch_res.success:
        log_detail = "[TesterNode] AST Pre-flight PASSED (Zero syntax regressions)."
    else:
        log_detail = f"[TesterNode] AST Pre-flight FAILED: {patch_res.error}"

    return {
        "patch_result": patch_res,
        "status": "AST_TESTED",
        "logs": state.get("logs", []) + [log_entry, log_detail],
    }


# ── NODE 4: RUNNER NODE (DOCKER SANDBOX) ─────────────────────────────────────

def runner_node(state: RemediationState) -> Dict[str, Any]:
    """
    Executes the patch inside an ephemeral sandbox container with network_disabled=True.
    Evaluates whether the reproduction pytest passes with Exit Code == 0.
    """
    patch_res = state["patch_result"]

    # If AST already failed, skip container run
    if not patch_res.success:
        failed_sandbox = SandboxExecutionResult(
            success=False,
            exit_code=1,
            stdout="",
            stderr=patch_res.error or "AST Syntax Error",
            duration_seconds=0.0,
            mode="ast_rejection",
            network_disabled=True,
            error_message=patch_res.error,
        )
        return {
            "sandbox_result": failed_sandbox,
            "status": "SANDBOX_EVALUATED",
            "logs": state.get("logs", []) + ["[RunnerNode] Skipped sandbox: AST validation failed."],
        }

    log_entry = "[RunnerNode] Provisioning ephemeral sandbox container (network_disabled=True)..."

    sandbox_res = run_in_docker_sandbox(
        target_rel_path=patch_res.target_file,
        patched_content=patch_res.patched_content,
    )

    status_tag = "PASS" if sandbox_res.success else "FAIL"
    log_detail = (
        f"[RunnerNode] Sandbox pytest result: {status_tag} (Exit Code: {sandbox_res.exit_code}, "
        f"Mode: {sandbox_res.mode}, Duration: {sandbox_res.duration_seconds}s)"
    )

    return {
        "sandbox_result": sandbox_res,
        "status": "SANDBOX_EVALUATED",
        "logs": state.get("logs", []) + [log_entry, log_detail],
    }


# ── NODE 5: DEBUGGER NODE ────────────────────────────────────────────────────

def debugger_node(state: RemediationState) -> Dict[str, Any]:
    """
    Captures sandbox test failures or compiler errors, increments the circuit breaker,
    and updates error feedback to prompt the Coder Node with corrective instructions.
    """
    sandbox_res = state.get("sandbox_result")
    patch_res = state.get("patch_result")
    current_retries = state.get("retry_count", 0) + 1

    # Extract relevant error message from sandbox stderr or AST failure
    error_msg = ""
    if patch_res and not patch_res.success:
        error_msg = f"AST Syntax Validation Error: {patch_res.error}"
    elif sandbox_res and sandbox_res.stderr:
        error_msg = f"Pytest Execution Failure:\n{sandbox_res.stderr.strip()}"
    else:
        error_msg = "Unknown regression caught during sandbox verification."

    log_entry = (
        f"[DebuggerNode] Iterating implementation plan. Caught failure. "
        f"Retry counter incremented to {current_retries}/3."
    )

    return {
        "retry_count": current_retries,
        "error_feedback": error_msg,
        "status": "DEBUGGING",
        "logs": state.get("logs", []) + [log_entry],
    }


# ── ROUTING / CIRCUIT BREAKER ────────────────────────────────────────────────

def evaluate_test_output(state: RemediationState) -> str:
    """
    Evaluates sandbox execution output.
    Routes to END on pass, or loops through DebuggerNode if retries < 3.
    """
    sandbox_res = state.get("sandbox_result")
    retry_count = state.get("retry_count", 0)

    # 1. Successful verification -> Verified & Ready for PR
    if sandbox_res and sandbox_res.success:
        return "verified"

    # 2. Failure with retry budget remaining -> Circuit breaker loop
    if retry_count < 3:
        return "retry"

    # 3. Exhausted 3 retries -> Trip circuit breaker, escalate to human
    return "flag_manual_review"


# ── GRAPH CONSTRUCTION ───────────────────────────────────────────────────────

def build_remediation_graph() -> StateGraph:
    """
    Constructs and compiles the full LangGraph state machine.
    """
    builder = StateGraph(RemediationState)

    # Add 5 core agent nodes matching the architecture
    builder.add_node("analyzer_node", analyzer_node)
    builder.add_node("coder_node", coder_node)
    builder.add_node("tester_node", tester_node)
    builder.add_node("runner_node", runner_node)
    builder.add_node("debugger_node", debugger_node)

    # Define linear execution flow
    builder.add_edge(START, "analyzer_node")
    builder.add_edge("analyzer_node", "coder_node")
    builder.add_edge("coder_node", "tester_node")
    builder.add_edge("tester_node", "runner_node")

    # Define conditional evaluation edge (Circuit Breaker)
    builder.add_conditional_edges(
        "runner_node",
        evaluate_test_output,
        {
            "verified": END,
            "retry": "debugger_node",
            "flag_manual_review": END,
        },
    )

    # Loop back from Debugger to Coder
    builder.add_edge("debugger_node", "coder_node")

    return builder.compile()


# Singleton compiled graph instance
remediation_graph = build_remediation_graph()


# ── CLI & RUNNER HELPER ──────────────────────────────────────────────────────

def run_remediation_graph(raw_traceback: str) -> RemediationState:
    """
    Helper function to run the compiled LangGraph state machine against a crash traceback.
    """
    initial_state: RemediationState = {
        "raw_traceback": raw_traceback,
        "crash_location": None,
        "rag_context": None,
        "diagnostic": None,
        "patch_result": None,
        "sandbox_result": None,
        "retry_count": 0,
        "error_feedback": None,
        "status": "INITIALIZED",
        "logs": [],
    }

    final_state = remediation_graph.invoke(initial_state)
    return final_state


if __name__ == "__main__":
    from demo import SCENARIOS
    import sys

    choice = sys.argv[1] if len(sys.argv) > 1 else "billing"
    tb = SCENARIOS.get(choice, SCENARIOS["billing"])["traceback"]

    print("\n" + "=" * 75)
    print(f"  OPSMIND AI — LANGGRAPH AUTONOMOUS REMEDIATION STATE MACHINE")
    print(f"  Executing StateGraph for scenario: {choice}")
    print("=" * 75 + "\n")

    result = run_remediation_graph(tb)

    for log in result.get("logs", []):
        print(f"  --> {log}")

    print("\n" + "-" * 75)
    print("  FINAL STATE MACHINE STATUS:", result.get("status"))
    if result.get("sandbox_result") and result["sandbox_result"].success:
        print("  SANDBOX VERIFICATION:     PASSED (Exit Code == 0)")
        print("  GENERATED UNIFIED DIFF:")
        print(result["patch_result"].diff)
    else:
        print("  SANDBOX VERIFICATION:     FAILED / MANUAL REVIEW REQUIRED")
    print("=" * 75 + "\n")
