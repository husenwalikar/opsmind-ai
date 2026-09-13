# OpsMind AI

> **Autonomous Incident Triage & Zero-Shot Remediation Engine for Cloud Microservices**

OpsMind AI is an out-of-band Site Reliability Engineering (SRE) engine that autonomously detects, isolates, diagnoses, and synthesizes verified patches for unhandled production microservice crashes in under 10 seconds.

---

## 1. Problem Statement & Architecture

When an unhandled exception strikes a production microservice, **Mean Time to Remediation (MTTR)** is dominated by human coordination friction:
1. **Stack Trace Noise:** 80% of stack frames belong to web frameworks (`uvicorn`, `starlette`, `asyncio`) rather than business logic.
2. **Context Fragmentation:** On-call engineers must manually cross-reference past post-mortems, Slack threads, and domain runbook invariants.
3. **Patch Hallucination & Risk:** Naive LLM integrations that rewrite entire files or author hand-crafted unified diffs frequently break indentation, hallucinate APIs, or introduce syntax regressions.

### The OpsMind Pipeline

OpsMind decouples log ingestion, retrieval, reasoning, syntax verification, and sandbox execution into a 5-stage guarded pipeline:

```
[ Unhandled Crash in Target Service (ShopFlow) ]
                        │
                        ▼ (stdout / stderr JSON logs)
   ┌────────────────────────────────────────────────────────┐
   │ 1. Traceback Isolation (services/agent/parser.py)      │
   │    - Normalizes log escapes & path separators          │
   │    - Filters framework noise (site-packages, Lib/)     │
   │    - Isolates root cause in chained exceptions         │
   │    - Enforces workspace root path containment guard    │
   │    - Slices bounded 10-line source window with pointer │
   └────────────────────────────────────────────────────────┘
                        │
                        ▼ CrashLocation (file, line, window)
   ┌────────────────────────────────────────────────────────┐
   │ 2. Vector RAG Retrieval (data/seed_chroma.py)          │
   │    - ChromaDB persistent store (all-MiniLM-L6-v2 ONNX) │
   │    - Queries historical incidents & service runbooks   │
   │    - Distance threshold guard (cutoff <= 0.65)         │
   │    - Injects Top-1 remediation + Top-1 runbook invariant│
   └────────────────────────────────────────────────────────┘
                        │
                        ▼ Grounded Context (< 800 tokens)
   ┌────────────────────────────────────────────────────────┐
   │ 3. LLM Diagnostic Agent (services/agent/llm_client.py) │
   │    - Groq LPU inference (openai/gpt-oss-120b)          │
   │    - Temperature: 0.1 (deterministic code output)      │
   │    - Produces exact SEARCH and REPLACE blocks          │
   │    - Strict JSON schema enforcement                    │
   └────────────────────────────────────────────────────────┘
                        │
                        ▼ DiagnosticResult (search, replace)
   ┌────────────────────────────────────────────────────────┐
   │ 4. AST Guard & Patcher (services/agent/patcher.py)     │
   │    - Verifies search block exists EXACTLY ONCE         │
   │    - In-memory patch application (zero host mutation)  │
   │    - Python AST compilation pre-flight (ast.parse)     │
   │    - Mathematical diff generation (difflib)            │
   └────────────────────────────────────────────────────────┘
                        │
                        ▼ Unified .diff Artifact
   ┌────────────────────────────────────────────────────────┐
   │ 5. Ephemeral Docker Sandbox (services/sandbox/run.py)  │
   │    - Host mounted read-only (:ro)                      │
   │    - Patch applied to ephemeral container scratchpad   │
   │    - Pytest execution verified (exit code 0 required)  │
   │    - Iterative self-correction feedback loop (<= 3x)   │
   └────────────────────────────────────────────────────────┘
```

---

## 2. Security & Threat Model

OpsMind is engineered around a **defense-in-depth security perimeter**:

* **Air-Gapped Decoupling:** The target microservice (ShopFlow) has zero dependencies on OpsMind. OpsMind ingests logs out-of-band; ShopFlow never makes outbound HTTP calls to OpsMind.
* **Path Traversal Guard:** `parser.py` and `patcher.py` resolve all targets via `os.path.realpath()` and verify containment within the allowed workspace via `os.path.commonpath()`. Arbitrary file disclosures (e.g. `../../.env` or `/etc/passwd`) are blocked before disk reads.
* **Non-Mutating Execution:** Host repository files are **never modified directly**. Patches are synthesized in-memory, validated via AST compilation, and verified inside an ephemeral container with host volumes mounted read-only (`:ro`).
* **Hallucination Prevention:** The vector retriever enforces a maximum cosine distance threshold (`0.65`). Low-confidence matches are omitted rather than authoritatively injected into the prompt.
* **Zero Diff Guessing:** LLMs produce exact literal `SEARCH`/`REPLACE` blocks. Unified diffs are computed mathematically using `difflib.unified_diff()`, eliminating line-offset errors.

---

## 3. Project Structure

```text
opsmind-ai/
├── blueprints/                  # Architectural design specs per module
│   ├── data/
│   │   └── seed_chroma.md
│   └── services/agent/
│       ├── parser.md
│       ├── llm_client.md
│       └── patcher.md
├── data/
│   ├── historical_incidents.json # Past production post-mortems for RAG
│   └── seed_chroma.py           # ChromaDB seeder & semantic query interface
├── services/
│   ├── agent/
│   │   ├── parser.py            # Traceback normalizer & coordinate isolator
│   │   ├── llm_client.py        # Groq LPU diagnostic & patch generator
│   │   └── patcher.py           # AST pre-flight guard & difflib synthesizer
│   ├── sandbox/                 # Ephemeral Docker verification runner
│   └── api/                     # FastAPI autonomous triage orchestrator
├── test_bed/                    # Authentic e-commerce microservice (Patient)
│   ├── app/
│   │   ├── services/            # 6 business services with realistic edge cases
│   │   │   ├── billing.py       # ZeroDivisionError (100% discount)
│   │   │   ├── checkout.py      # KeyError (Guest shipping address)
│   │   │   ├── inventory.py     # IndexError (Out-of-bounds warehouse tier)
│   │   │   ├── auth.py          # TypeError (Revoked session token)
│   │   │   ├── promotions.py    # ValueError (Malformed negative promo)
│   │   │   └── gateway.py       # TimeoutError (External mock bank latency)
│   │   ├── static/              # Tailwind storefront & hidden DevOps panel
│   │   ├── database.py          # SQLAlchemy PostgreSQL + SQLite fallback
│   │   └── main.py              # Clean FastAPI server with logging middleware
│   └── docs/
│       └── SERVICE_RUNBOOK.md   # Domain invariants & contracts for RAG
├── test_parser.py               # Pytest suite for Step 1
├── test_chroma.py               # Pytest suite for Step 2
├── test_llm_client.py           # Pytest suite for Step 3
├── test_patcher.py              # Pytest suite for Step 4
├── requirements.txt             # Core dependencies
└── .env.example                 # Environment configuration template
```

---

## 4. Quickstart Guide

### Prerequisites
* Python 3.10+ (tested on Python 3.14)
* Docker Desktop (optional for test bed DB, required for Step 5 sandbox)
* A Groq Cloud API Key ([console.groq.com](https://console.groq.com))

### Installation
1. Clone repository and install dependencies:
   ```bash
   git clone https://github.com/your-username/opsmind-ai.git
   cd opsmind-ai
   pip install -r requirements.txt
   ```

2. Configure environment variables:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and add your Groq API credentials:
   ```env
   GROQ_API_KEY=gsk_your_actual_key_here
   GROQ_MODEL=openai/gpt-oss-120b
   ```

3. Seed the local vector knowledge base:
   ```bash
   python data/seed_chroma.py
   ```

4. Run the automated test suite:
   ```bash
   pytest -v
   ```
   *Expect: 22 passed across parser, chroma, llm_client, and patcher.*

---

## 5. Running the Interactive Demo (ShopFlow)

ShopFlow is an authentic e-commerce microservice built to test autonomous remediation under realistic conditions.

### Start the Storefront Server
```bash
python -m uvicorn test_bed.app.main:app --host 0.0.0.0 --port 8000
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser.

### Operating the Demo
1. **Explore the Store:** Add items to cart and complete a healthy checkout (produces `200 OK`).
2. **Open DevOps Panel:** Click the subtle **`DevOps ⚙`** button in the header (next to cart).
3. **Inject Authentic Failures:**
   * Click **`ZeroDivision (FREE100)`** to trigger an unhandled crash in `billing.py`.
   * Observe the red `500 Internal Server Error` modal in the UI and network stream.
   * Observe the structured JSON traceback emitted to the terminal log.
4. **Trigger Autonomous Remediation:**
   * Feed the crash log to OpsMind: the engine isolates line 25, pulls the billing invariant from ChromaDB, synthesizes a surgical guard with Groq, verifies the Python AST, and generates the exact unified diff:
   ```diff
   --- a/test_bed/app/services/billing.py
   +++ b/test_bed/app/services/billing.py
   @@ -22,4 +22,4 @@
   -    effective_ratio = round(subtotal / net_payable_base, 2)
   +    effective_ratio = 0.0 if net_payable_base == 0 else round(subtotal / net_payable_base, 2)
   ```

---

## 6. Fault-Injection Benchmark Matrix

| Service | Failure Scenario | Trigger Condition | Runbook Invariant |
|:---|:---|:---|:---|
| **Billing** | `ZeroDivisionError` | 100% discount makes payable base ₹0 | When discount == total, net payable is $0.00; return ratio `0.0` safely |
| **Checkout** | `KeyError` | Guest checkout lacks `shipping_address` | Guest orders permitted; use `.get(..., "STANDARD_DELIVERY")` |
| **Inventory** | `IndexError` | Request tier >= available warehouse tiers | Warehouse tiers bounded to 0-2; clamp with `min(tier, len-1)` |
| **Auth** | `TypeError` | Session token revoked or expired | Revoked token returns `None`; check `session is not None` |
| **Promotions** | `ValueError` | Promo code contains negative rate | Negative rates invalid; return handled 400 Bad Request |
| **Gateway** | `TimeoutError` | External bank gateway latency hang | Network calls must have timeouts and retry once before failing |

---

## 7. License & Disclaimers

OpsMind AI is an engineering research prototype designed for automated SRE workflows. All synthesized patches are subject to sandbox verification and human review policies prior to production deployment.
