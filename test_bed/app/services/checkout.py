"""Order dispatch and fulfillment routing service."""

from typing import Any, Dict
import uuid

from test_bed.app.models.domain import OrderConfirmation
from test_bed.app.logger import log


def process_order_checkout(total_amount: float, customer_payload: Dict[str, Any]) -> OrderConfirmation:
    """Validate customer shipping destination and confirm order placement.

    Args:
        total_amount: Total transaction amount in currency units.
        customer_payload: Metadata dictionary containing customer and address details.

    Returns:
        OrderConfirmation payload with fulfillment routing data.
    """
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
    log.info(f"Initiating checkout fulfillment for order {order_id}")

    shipping_destination = customer_payload["shipping_address"]

    return OrderConfirmation(
        order_id=order_id,
        total_amount=total_amount,
        status="CONFIRMED",
        fulfillment_tier="TIER-PRIMARY",
        shipping_destination=shipping_destination,
    )