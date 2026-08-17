"""Unit tests for upstream payment network settlement client."""

import pytest
from test_bed.app.services.gateway import dispatch_card_charge


def test_standard_payment_capture():
    """Verify successful transaction dispatch under normal network conditions."""
    result = dispatch_card_charge(order_id="ORD-1001", amount=1200.0, simulate_network_hang=False)
    assert result["status"] == "CHARGED"
    assert "transaction_id" in result


def test_gateway_latency_timeout_resilience():
    """Verify invariant: upstream gateway latency returns degraded failure payload instead of crashing."""
    result = dispatch_card_charge(order_id="ORD-1002", amount=1200.0, simulate_network_hang=True)
    assert result["status"] == "GATEWAY_TIMEOUT"