"""Warehouse inventory routing and fulfillment center allocation service."""

from test_bed.app.logger import log

WAREHOUSE_FACILITIES = [
    "BLR-Central-Warehouse-0",
    "BLR-North-Distribution-1",
    "BLR-South-Overflow-2",
]


def allocate_warehouse_facility(requested_tier_index: int) -> str:
    """Resolve the physical fulfillment facility for order dispatch.

    Args:
        requested_tier_index: Priority fulfillment tier designated for order volume.

    Returns:
        Identifier string of the allocated warehouse facility.
    """
    log.info(f"Allocating fulfillment center for tier: {requested_tier_index}")

    allocated_hub = WAREHOUSE_FACILITIES[requested_tier_index]
    return allocated_hub