"""
Pytest Test Suite for data/seed_chroma.py
Run with: pytest test_chroma.py
"""

import os
import shutil
import pytest
from data.seed_chroma import (
    parse_runbook_markdown,
    seed_vector_db,
    query_incident_context,
)

RUNBOOK_PATH = "test_bed/docs/SERVICE_RUNBOOK.md"
INCIDENTS_PATH = "data/historical_incidents.json"
TEST_DB_DIR = "data/test_chroma_db"


@pytest.fixture(scope="module", autouse=True)
def setup_teardown():
    if os.path.exists(TEST_DB_DIR):
        shutil.rmtree(TEST_DB_DIR, ignore_errors=True)
    yield
    if os.path.exists(TEST_DB_DIR):
        shutil.rmtree(TEST_DB_DIR, ignore_errors=True)


def test_parse_runbook_markdown():
    runbook_items = parse_runbook_markdown(RUNBOOK_PATH)
    assert len(runbook_items) == 6
    service_names = [item["service_name"] for item in runbook_items]
    assert "Billing Service" in service_names
    assert "Checkout Service" in service_names
    # Check aligned path
    billing_item = next(item for item in runbook_items if item["service_name"] == "Billing Service")
    assert billing_item["file_target"] == "app/services/billing.py"


def test_seed_vector_db_idempotency():
    counts_1 = seed_vector_db(INCIDENTS_PATH, RUNBOOK_PATH, persist_dir=TEST_DB_DIR)
    assert counts_1["incidents"] == 6
    assert counts_1["runbooks"] == 6

    # Re-seeding must not duplicate or fail
    counts_2 = seed_vector_db(INCIDENTS_PATH, RUNBOOK_PATH, persist_dir=TEST_DB_DIR)
    assert counts_2["incidents"] == 6
    assert counts_2["runbooks"] == 6


def test_query_incident_context_high_confidence_zerodiv():
    res = query_incident_context(
        error_type="ZeroDivisionError",
        error_message="float division by zero",
        source_context="effective_discount_ratio = subtotal / net_payable_base",
        persist_dir=TEST_DB_DIR,
    )
    assert res["incident"]["is_confident"] is True
    assert res["incident"]["id"] == "inc-INC-2024-041"
    assert res["runbook"]["is_confident"] is True
    assert "Billing" in res["runbook"]["metadata"]["service_name"]


def test_query_incident_context_high_confidence_keyerror():
    res = query_incident_context(
        error_type="KeyError",
        error_message="'shipping_address'",
        source_context="destination = customer_payload['shipping_address']",
        persist_dir=TEST_DB_DIR,
    )
    assert res["incident"]["is_confident"] is True
    assert res["incident"]["id"] == "inc-INC-2024-088"
    assert res["runbook"]["is_confident"] is True
    assert "Checkout" in res["runbook"]["metadata"]["service_name"]


def test_query_incident_context_distance_threshold_guard():
    # An entirely unrelated error must be rejected by the distance threshold
    res = query_incident_context(
        error_type="UnrelatedKernelPanicError",
        error_message="corrupted hardware interrupt memory segment",
        source_context="asm volatile('cli')",
        persist_dir=TEST_DB_DIR,
    )
    # Both must be marked as not confident so the LLM prompt does not hallucinate
    assert res["incident"]["is_confident"] is False
    assert res["runbook"]["is_confident"] is False
    assert "No domain runbook invariant defined" in res["rag_prompt_snippet"]


if __name__ == "__main__":
    pytest.main(["-v", __file__])
