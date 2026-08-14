"""Billing and financial settlement service for order checkouts."""

from test_bed.app.models.domain import OrderSummary
from test_bed.app.logger import log

TAX_RATE: float = 0.18


def calculate_order_summary(subtotal: float, discount_amount: float) -> OrderSummary:
    """Calculate subtotal, applicable taxes, and normalized discount ratios.

    Args:
        subtotal: Gross merchandise value before adjustments.
        discount_amount: Total promotional discount to deduct.

    Returns:
        OrderSummary containing line-item totals and computed payable sum.
    """
    log.info(f"Settling billing breakdown: subtotal={subtotal:.2f}, discount={discount_amount:.2f}")

    net_payable_base = round(subtotal - discount_amount, 2)
    tax_amount = round(net_payable_base * TAX_RATE, 2)
    final_total = round(net_payable_base + tax_amount, 2)

    effective_ratio = round(subtotal / net_payable_base, 2)

    return OrderSummary(
        subtotal=subtotal,
        tax=tax_amount,
        discount_amount=discount_amount,
        total_payable=final_total,
        effective_discount_ratio=effective_ratio,
    )