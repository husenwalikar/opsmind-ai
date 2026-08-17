"""Unit tests for checkout and fulfillment dispatch workflow."""

import pytest
from test_bed.app.services.checkout import process_order_checkout


def test_registered_customer_checkout():
    """Verify checkout processing when full shipping metadata is provided."""
    payload = {
        "customer_name": "Alice Smith",
        "shipping_address": "42 Residency Road, Bangalore",
    }
    confirmation = process_order_checkout(total_amount=1500.0, customer_payload=payload)
    assert confirmation.status == "CONFIRMED"
    assert confirmation.shipping_destination == "42 Residency Road, Bangalore"


def test_guest_checkout_missing_address():
    """Verify invariant: guest payloads lacking shipping_address fallback safely."""
    payload = {
        "customer_name": "Guest Customer",
        "is_guest": True,
    }
    confirmation = process_order_checkout(total_amount=800.0, customer_payload=payload)
    assert confirmation.status == "CONFIRMED"
    assert confirmation.shipping_destination == "STANDARD_DELIVERY"