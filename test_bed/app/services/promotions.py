"""Promotional campaign engine and markdown calculation service."""

from test_bed.app.logger import log

ACTIVE_PROMOTIONS = {
    "SAVE10": 10.0,
    "SAVE20": 20.0,
    "FREE100": 100.0,
    "MALFORMED_MINUS50": -50.0,
}


def evaluate_coupon_discount(coupon_code: str, base_amount: float) -> float:
    """Compute monetary discount deduction from active campaign vouchers.

    Args:
        coupon_code: Alphanumeric marketing promotional code.
        base_amount: Line-item total eligible for promotional deduction.

    Returns:
        Calculated monetary deduction to apply.

    Raises:
        ValueError: If campaign rate metadata contains negative percentages.
    """
    log.info(f"Evaluating promotional voucher: {coupon_code}")

    rate = ACTIVE_PROMOTIONS.get(coupon_code, 0.0)

    if rate < 0:
        raise ValueError(f"Invalid promotional rate configured for campaign: {rate}%")

    discount_value = round(base_amount * (rate / 100.0), 2)
    return discount_value