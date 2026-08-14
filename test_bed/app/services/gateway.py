"""Payment gateway settlement client for external processing networks."""

from typing import Dict

from test_bed.app.logger import log


def dispatch_card_charge(order_id: str, amount: float, simulate_network_hang: bool = False) -> Dict[str, str]:
    """Dispatch settlement request to upstream merchant payment processor.

    Args:
        order_id: Unique order reference identifier.
        amount: Transaction total to capture.
        simulate_network_hang: Testing hook to emulate upstream gateway latency.

    Returns:
        Processor transaction record on successful settlement.

    Raises:
        TimeoutError: If upstream processing network exceeds timeout thresholds.
    """
    log.info(f"Dispatching settlement request for order {order_id} (amount={amount:.2f})")

    if simulate_network_hang:
        raise TimeoutError("Upstream payment network gateway timed out after 3000ms")

    return {
        "status": "CHARGED",
        "order_id": order_id,
        "transaction_id": "TXN_7741892",
    }