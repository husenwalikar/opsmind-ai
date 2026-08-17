"""Unit tests for marketing campaign promotional markdown rules."""

import pytest
from test_bed.app.services.promotions import evaluate_coupon_discount


def test_standard_promotion_discount():
    """Verify standard percentage deduction on active vouchers."""
    discount = evaluate_coupon_discount(coupon_code="SAVE20", base_amount=1000.0)
    assert discount == 200.0


def test_invalid_negative_promotion_boundary():
    """Verify invariant: malformed campaign rates resolve to 0.0 deduction safely."""
    discount = evaluate_coupon_discount(coupon_code="MALFORMED_MINUS50", base_amount=1000.0)
    assert discount == 0.0