"""
Live Demonstration Script for OpsMind AI (Steps 1 through 4).
Runs the end-to-end autonomous diagnosis and patch generation pipeline:
  Crash Traceback -> Step 1: Parser -> Step 2: Vector RAG -> Step 3: Groq LLM -> Step 4: AST Patcher.
"""

import sys
import time
from services.agent.parser import parse_crash_traceback
from data.seed_chroma import query_incident_context
from services.agent.llm_client import diagnose_and_generate_patch
from services.agent.patcher import synthesize_patch

SCENARIOS = {
    "billing": {
        "name": "Billing Service — ZeroDivisionError (FREE100 promo code)",
        "traceback": """Traceback (most recent call last):
  File "C:/Zephyrus/Husen/Projects/opsmind-ai/test_bed/app/services/billing.py", line 25, in calculate_order_summary
    effective_ratio = round(subtotal / net_payable_base, 2)
ZeroDivisionError: float division by zero""",
    },
    "checkout": {
        "name": "Checkout Service — KeyError (Guest checkout missing shipping_address)",
        "traceback": """Traceback (most recent call last):
  File "C:/Zephyrus/Husen/Projects/opsmind-ai/test_bed/app/services/checkout.py", line 23, in process_order_checkout
    shipping_destination = customer_payload["shipping_address"]
KeyError: 'shipping_address'""",
    },
}


def run_demo(scenario_key: str = "billing"):
    scenario = SCENARIOS.get(scenario_key, SCENARIOS["billing"])
    raw_tb = scenario["traceback"]

    print("\n" + "=" * 70)
    print(f"  OPSMIND AI AUTONOMOUS REMEDIATION DEMO")
    print(f"  Target Scenario: {scenario['name']}")
    print("=" * 70)

    # ── Step 1: Parser ────────────────────────────────────────────────────────
    print("\n[STEP 1] Ingesting Crash Telemetry & Isolating Coordinates...")
    time.sleep(0.3)
    crash_loc = parse_crash_traceback(raw_tb)
    print(f"  --> Failure Target:    {crash_loc.file_path}:{crash_loc.line_number}")
    print(f"  --> Exception Type:    {crash_loc.error_type}")
    print(f"  --> Exception Message: {crash_loc.error_message}")
    print(f"  --> Source Window:\n{crash_loc.source_context}")

    # ── Step 2: Vector RAG ────────────────────────────────────────────────────
    print("\n[STEP 2] Querying ChromaDB Vector Knowledge Base (Cosine Distance)...")
    time.sleep(0.3)
    rag_context = query_incident_context(
        crash_loc.error_type,
        crash_loc.error_message,
        crash_loc.source_context,
        persist_dir="data/chroma_db",
    )
    inc = rag_context.get("incident", {})
    rb = rag_context.get("runbook", {})
    print(f"  --> Incident Match:    {inc.get('id', 'N/A')} (Distance: {inc.get('distance', 1.0):.4f}, Confident: {inc.get('is_confident', False)})")
    print(f"  --> Runbook Invariant: {rb.get('id', 'N/A')} (Distance: {rb.get('distance', 1.0):.4f}, Confident: {rb.get('is_confident', False)})")

    # ── Step 3: Groq LLM Diagnostic Agent ─────────────────────────────────────
    print("\n[STEP 3] Synthesizing Surgical Patch via Groq LPU...")
    t0 = time.time()
    diagnostic = diagnose_and_generate_patch(crash_loc, rag_context)
    latency = time.time() - t0
    print(f"  --> Generation Time:   {latency:.2f}s")
    print(f"  --> Confidence Score:  {diagnostic.confidence_score * 100:.1f}%")
    print(f"  --> Root Cause:        {diagnostic.root_cause_analysis}")
    print(f"  --> Search Block:\n      {diagnostic.search_block.strip()}")
    print(f"  --> Replace Block:\n      {diagnostic.replace_block.strip()}")

    # ── Step 4: AST Guard & Patcher ───────────────────────────────────────────
    print("\n[STEP 4] Enforcing AST Compilation Guard & Synthesizing Unified Diff...")
    time.sleep(0.2)
    patch_result = synthesize_patch(
        target_file=diagnostic.target_file,
        search_block=diagnostic.search_block,
        replace_block=diagnostic.replace_block,
    )

    if patch_result.success:
        print("  --> AST Validation:    PASSED (Syntax valid, zero compilation errors)")
        print("  --> Host File Status:  UNTOUCHED (Patch applied strictly in-memory)")
        print("\n" + "-" * 70)
        print("  GENERATED MATHEMATICAL UNIFIED DIFF:")
        print("-" * 70)
        print(patch_result.diff)
        print("-" * 70)
        print("[SUCCESS] Remediation proposal synthesized and verified in memory!")
    else:
        print(f"  --> AST Validation FAILED: {patch_result.error}")

    print("=" * 70 + "\n")


if __name__ == "__main__":
    choice = sys.argv[1] if len(sys.argv) > 1 else "billing"
    run_demo(choice)
