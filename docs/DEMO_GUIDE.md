# OpsMind AI — Presenter Demo Guide & Walkthrough

This document provides a comprehensive presentation walkthrough for demonstrating the OpsMind AI autonomous incident remediation engine alongside the ShopFlow microservice.

---

## 1. Environment Setup (Pre-Demo)

### 1. Start the ShopFlow Server
Run in your project root:
```bash
python -m uvicorn test_bed.app.main:app --host 0.0.0.0 --port 8000
```
Verify the startup log shows:
```text
INFO:     Products seeded: 6
INFO:     ShopFlow application initialized successfully
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 2. Browser Preparation
Open Chrome or Edge and navigate to **[http://localhost:8000](http://localhost:8000)**.
Keep your browser on the left half of your display and your terminal on the right half.

---

## 2. The 3-Act Demonstration Script

### Act 1: The Healthy Microservice (45 Seconds)
* **Goal:** Establish that ShopFlow is an authentic, production-grade microservice with a database, session auth, and business logic.
* **Actions:**
  1. Show the product catalog (6 hardware products).
  2. Click **"Add to Cart"** on the *Asus Zephyrus G14 Gaming Laptop* (₹1,20,000).
  3. Click the shopping cart icon (🛒) in the top-right to reveal the checkout drawer.
  4. Enter a normal delivery address (e.g. `Brigade Road, Bangalore`).
  5. Click **"Confirm & Place Order"**.
  6. Point to the green confirmation modal (`Order Confirmed!`) and the bottom-right **Network Events** stream (`POST /api/checkout -> 200 OK`).
* **Presenter Script:**
  > *"This is ShopFlow, an authentic microservice handling inventory, billing, promotional pricing, and checkout settlement. Right now the system is healthy and transactions are settling with 200 OK."*

---

### Act 2: The Production Incident (60 Seconds)
* **Goal:** Demonstrate an authentic edge-case crash and show the raw log telemetry emitted to the system.
* **Actions:**
  1. Click the subtle **`DevOps ⚙`** button in the header (next to the cart icon).
  2. The dark slate **Traffic & Failure Scenarios** control bar expands.
  3. Click the red button: **`ZeroDivision (FREE100)`**.
  4. Observe the failure:
     * A 100% discount promo code (`FREE100`) is applied to the cart.
     * Net payable drops to ₹0.00.
     * The modal turns red: `⚠️ Order Processing Failed — HTTP 500 Internal Server Error: float division by zero`.
     * The Network Events log displays: `POST /api/checkout -> 500 FAILED`.
  5. Switch attention to the terminal output:
     ```text
     ERROR:shopflow.api:Unhandled service failure on POST /api/checkout: float division by zero
     Traceback (most recent call last):
       File ".../test_bed/app/services/billing.py", line 25, in calculate_order_summary
         effective_ratio = round(subtotal / net_payable_base, 2)
     ZeroDivisionError: float division by zero
     ```
* **Presenter Script:**
  > *"When a 100% promotional discount was applied, the payable base became zero. The billing logic attempted to compute the discount ratio by dividing by the payable base, triggering a ZeroDivisionError. In a traditional team, this pages an engineer at 3 AM. Now let's see how OpsMind AI remediates this autonomously."*

---

### Act 3: Autonomous Remediation in Action (90 Seconds)
* **Goal:** Walk through OpsMind's 4-step autonomous pipeline and show the verified patch.
* **Actions:**
  Run the verified test suite in a second terminal to demonstrate each pipeline stage:
  ```bash
  pytest -v test_parser.py test_chroma.py test_patcher.py
  ```
  Highlight the key outputs:
  1. **Coordinate Isolation (`parser.py`):** Filters out web framework noise and isolates line 25 of `billing.py` with the `>>` failure marker.
  2. **Vector RAG Retrieval (`seed_chroma.py`):** Retrieves historical post-mortem `INC-2024-041` and the official Billing runbook invariant: *"When discount == total, net payable is $0.00; return ratio 0.0 safely."*
  3. **Diagnostic Reasoning (`llm_client.py`):** Synthesizes exact `SEARCH` and `REPLACE` blocks in under 1.5 seconds.
  4. **AST Pre-flight Guard (`patcher.py`):** Parses the modified code with Python's native `ast.parse()` to guarantee syntax integrity, checks for unambiguous targeting, and generates the clean mathematical diff:
     ```diff
     --- a/test_bed/app/services/billing.py
     +++ b/test_bed/app/services/billing.py
     @@ -22,4 +22,4 @@
     -    effective_ratio = round(subtotal / net_payable_base, 2)
     +    effective_ratio = 0.0 if net_payable_base == 0 else round(subtotal / net_payable_base, 2)
     ```
  5. **Safety Guarantee:** Emphasize that the original source code on the host machine was **never directly mutated**.
* **Presenter Script:**
  > *"OpsMind isolated the exact failure coordinates, pulled the relevant runbook invariant from our vector store, synthesized a surgical patch with Groq LPU, compiled the Python AST in memory to guarantee zero syntax errors, and generated a clean mathematical unified diff—all in under 2 seconds, without touching the host filesystem."*

---

## 3. Failure Scenarios Reference Matrix

Use this table when evaluators ask to test other failure modes:

| Injection Button | Trigger Condition | Code Root Cause | Runbook Invariant |
|:---|:---|:---|:---|
| **ZeroDivision** | Promo: `FREE100` | Division by zero in `billing.py` | Return `0.0` safely when denominator is zero |
| **KeyError** | Guest Checkout | Missing `shipping_address` key | Use `.get()` with `"STANDARD_DELIVERY"` fallback |
| **IndexError** | Warehouse Tier 99 | Out-of-bounds array indexing in `inventory.py` | Clamp requested tier to `len(tiers) - 1` |
| **TypeError** | Revoked Session | Subscripting `None` in `auth.py` | Verify `session is not None` before reading attributes |
| **ValueError** | Promo: `MALFORMED_MINUS50` | Negative percentage in `promotions.py` | Disallow negative rates; raise handled 400 |
| **TimeoutError** | Network Hang | External bank gateway latency hang | Require timeout boundary and retry once |
