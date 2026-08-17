"""Unit tests for warehouse tier allocation and routing engine."""

import pytest
from test_bed.app.services.inventory import allocate_warehouse_facility


def test_primary_tier_allocation():
    """Verify routing to primary warehouse facility tier."""
    facility = allocate_warehouse_facility(requested_tier_index=0)
    assert facility == "BLR-Central-Warehouse-0"


def test_overflow_boundary_tier_allocation():
    """Verify invariant: tier indices exceeding facility count clamp to maximum tier."""
    facility = allocate_warehouse_facility(requested_tier_index=5)
    assert facility == "BLR-South-Overflow-2"