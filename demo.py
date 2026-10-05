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
        "service": "billing.py",
        "error_type": "ZeroDivisionError",
        "description": "100% discount voucher makes net_payable zero, causing division by zero when calculating ratio.",
        "traceback": """Traceback (most recent call last):
  File "C:/Zephyrus/Husen/Projects/opsmind-ai/test_bed/app/services/billing.py", line 25, in calculate_order_summary
    effective_ratio = round(subtotal / net_payable_base, 2)
ZeroDivisionError: float division by zero""",
    },
    "checkout": {
        "name": "Checkout Service — KeyError (Guest checkout missing shipping_address)",
        "service": "checkout.py",
        "error_type": "KeyError",
        "description": "Guest checkout payload omits 'shipping_address', causing unhandled KeyError on direct dictionary lookup.",
        "traceback": """Traceback (most recent call last):
  File "C:/Zephyrus/Husen/Projects/opsmind-ai/test_bed/app/services/checkout.py", line 23, in process_order_checkout
    shipping_destination = customer_payload["shipping_address"]
KeyError: 'shipping_address'""",
    },
    "inventory": {
        "name": "Inventory Service — IndexError (Out-of-bounds warehouse tier index)",
        "service": "inventory.py",
        "error_type": "IndexError",
        "description": "Fulfillment tier index 5 or 99 exceeds the 3 available warehouse tiers, raising IndexError.",
        "traceback": """Traceback (most recent call last):
  File "C:/Zephyrus/Husen/Projects/opsmind-ai/test_bed/app/services/inventory.py", line 23, in allocate_warehouse_facility
    allocated_hub = WAREHOUSE_FACILITIES[requested_tier_index]
IndexError: list index out of range""",
    },
    "auth": {
        "name": "Authentication Service — TypeError (NoneType session subscript)",
        "service": "auth.py",
        "error_type": "TypeError",
        "description": "Expired or missing bearer token resolves to None, causing TypeError on session['role'] access.",
        "traceback": """Traceback (most recent call last):
  File "C:/Zephyrus/Husen/Projects/opsmind-ai/test_bed/app/services/auth.py", line 34, in verify_user_permissions
    user_role = session["role"]
TypeError: 'NoneType' object is not subscriptable""",
    },
    "promotions": {
        "name": "Promotions Service — ValueError (Malformed negative percentage campaign)",
        "service": "promotions.py",
        "error_type": "ValueError",
        "description": "Corrupted promotional rate with negative percentage raises unhandled ValueError instead of safe deduction.",
        "traceback": """Traceback (most recent call last):
  File "C:/Zephyrus/Husen/Projects/opsmind-ai/test_bed/app/services/promotions.py", line 31, in evaluate_coupon_discount
    raise ValueError(f"Invalid promotional rate configured for campaign: {rate}%")
ValueError: Invalid promotional rate configured for campaign: -50.0%""",
    },
    "gateway": {
        "name": "Payment Gateway — TimeoutError (Upstream merchant bank network hang)",
        "service": "gateway.py",
        "error_type": "TimeoutError",
        "description": "Upstream bank latency raises unhandled TimeoutError, failing transaction without fallback payload.",
        "traceback": """Traceback (most recent call last):
  File "C:/Zephyrus/Husen/Projects/opsmind-ai/test_bed/app/services/gateway.py", line 25, in dispatch_card_charge
    raise TimeoutError("Upstream payment network gateway timed out after 3000ms")
TimeoutError: Upstream payment network gateway timed out after 3000ms""",
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
