# ShopFlow SRE Service Runbook & Invariants

This document defines the official business logic contracts, boundary requirements, and remediation rules for the ShopFlow microservice.

---

## 1. Billing Service (`app/services/billing.py`)
* **Contract:** Calculates the discount factor and net payable ratio.
* **Domain Rule:** Discount amounts can be up to 100% of the total amount.
* **Invariant:** When `discount_amount == total_amount`, net payable is $0.00. The function MUST NOT divide by zero. It must return a ratio of `0.0` safely.

---

## 2. Checkout Service (`app/services/checkout.py`)
* **Contract:** Processes customer checkout payloads.
* **Domain Rule:** Guest users are permitted to initiate orders without an existing profile.
* **Invariant:** When processing guest orders, the payload may lack the `shipping_address` key. Code must use defensive dictionary access (`.get()`) with a fallback default string (`"STANDARD_DELIVERY"`), never direct key indexing.

---

## 3. Inventory Service (`app/services/inventory.py`)
* **Contract:** Fetches product batches from warehouse tiers.
* **Domain Rule:** Warehouses are divided into 3 stock tiers (Indices 0, 1, 2).
* **Invariant:** When a customer requests an arbitrary tier index, code must clamp the index to the maximum available tier (`min(requested_tier_index, len(WAREHOUSE_FACILITIES) - 1)`) to prevent `IndexError`.

---

## 4. Authentication Service (`app/services/auth.py`)
* **Contract:** Validates bearer tokens and user sessions.
* **Domain Rule:** Session tokens can expire or be revoked.
* **Invariant:** A revoked or expired token returns `None`. Code must verify `if session is None: return "GUEST"`, and only access `session["role"]` when session exists, preventing `TypeError`.

---

## 5. Promotions Service (`app/services/promotions.py`)
* **Contract:** Validates promo discount percentages.
* **Domain Rule:** Legitimate promotional codes provide discounts between 1% and 99%.
* **Invariant:** Negative discount values are malformed configuration entries. Code must verify that if `rate < 0`, return a safe discount deduction of `0.0` instead of raising an unhandled `ValueError`.

---

## 6. Payment Gateway (`app/services/gateway.py`)
* **Contract:** Dispatches transaction charges to external mock banking APIs.
* **Domain Rule:** Network calls to external payment providers can experience transient latency.
* **Invariant:** When `simulate_network_hang` is triggered or external calls time out, code must catch `TimeoutError` and return `{"status": "GATEWAY_TIMEOUT", "order_id": order_id}` safely rather than crashing with an unhandled exception.
