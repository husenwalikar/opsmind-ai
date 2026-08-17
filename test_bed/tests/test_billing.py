"""Unit tests for billing and financial settlement engine."""

import pytest
from test_bed.app.services.billing import calculate_order_summary


def test_standard_order_summary():
    """Verify standard discount calculation and tax allocation."""
    summary = calculate_order_summary(subtotal=1000.0, discount_amount=200.0)
    assert summary.subtotal == 1000.0
    assert summary.discount_amount == 200.0
    assert summary.tax == 144.0  # 18% of 800
    assert summary.total_payable == 944.0
    assert summary.effective_discount_ratio == 1.25


def test_full_discount_edge_case():
    """Verify invariant: 100% discount must yield 0.0 effective ratio without division errors."""
    summary = calculate_order_summary(subtotal=500.0, discount_amount=500.0)
    assert summary.subtotal == 500.0
    assert summary.discount_amount == 500.0
    assert summary.total_payable == 0.0
    assert summary.effective_discount_ratio == 0.0