# OpsMind AI — From Zero to Autonomous SRE
### A Complete Engineering Reference: Architecture, Code, Concepts & Testing

> **Author:** Husen Walikar  
> **Repository:** [github.com/husenwalikar/opsmind-ai](https://github.com/husenwalikar/opsmind-ai)  
> **Stack:** Python 3.14 · FastAPI · ChromaDB · Groq LPU · ONNX Embeddings

---

## Table of Contents

1. [Project Overview & Vision](#1-project-overview--vision)
2. [System Architecture](#2-system-architecture)
3. [Project Structure](#3-project-structure)
4. [The Patient Microservice — ShopFlow](#4-the-patient-microservice--shopflow)
5. [Stage 1 — Crash Log Parser](#5-stage-1--crash-log-parser)
6. [Stage 2 — Vector RAG Knowledge Base](#6-stage-2--vector-rag-knowledge-base)
7. [Stage 3 — Groq LPU Diagnostic Agent](#7-stage-3--groq-lpu-diagnostic-agent)
8. [Stage 4 — AST Guard & Patch Synthesizer](#8-stage-4--ast-guard--patch-synthesizer)
9. [The Orchestrator — demo.py](#9-the-orchestrator--demopy)
10. [Unit Testing Strategy](#10-unit-testing-strategy)
11. [Security Model](#11-security-model)
12. [Key Concepts Explained](#12-key-concepts-explained)
13. [Running the Project](#13-running-the-project)
14. [Engineering Decisions & Tradeoffs](#14-engineering-decisions--tradeoffs)
15. [Roadmap — Phases 2-4](#15-roadmap--phases-2-4)
16. [Appendices](#appendices)

---

## 1. Project Overview & Vision

### What is OpsMind AI?

OpsMind AI is an **autonomous incident remediation engine** for Python microservices. When a service crashes and emits a traceback, OpsMind AI:

1. **Parses** the crash log to find exactly which file and line caused the failure
2. **Retrieves** the most relevant historical incident post-mortem and service runbook from a vector database
3. **Asks** a Groq LPU-powered large language model to propose a surgical code fix
4. **Validates** that fix by parsing the patched file with Python's AST compiler
5. **Produces** a standard `git diff`-compatible unified diff — ready for review or automated PR creation

All of this happens **without touching a single production file**. The entire patching process runs in-memory.

### The Problem It Solves

In production SRE workflows, incident remediation involves a painful manual loop:

```
Alert fires → Engineer wakes up → Reads logs → Reads runbook
→ Identifies root cause → Writes fix → Tests locally → Creates PR
```

This cycle averages **45 minutes** per incident, even for well-documented bugs. OpsMind AI compresses this to **under 30 seconds** for known error classes.

### Core Design Philosophy

| Principle | Implementation |
|:---|:---|
| **Zero host mutation** | All patches generated in RAM via `difflib`. No file is ever written to disk. |
| **Hallucination guard** | ChromaDB distance gating (`MAX_COSINE_DISTANCE = 0.65`) prevents irrelevant context poisoning the LLM prompt |
| **Fail safe, not fail fast** | Path traversal guards, AST pre-flight checks, ambiguity rejection |
| **Surgical precision** | SEARCH/REPLACE contracts instead of line-number arithmetic |
| **Production-grade types** | Strict `dataclass` and `Optional` typing throughout |

---

## 2. System Architecture

### High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                     SHOPFLOW MICROSERVICE                           │
│  POST /api/checkout → ZeroDivisionError raised in billing.py        │
│  FastAPI middleware catches → logs structured JSON traceback stdout  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  Raw Python Traceback Text
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  STAGE 1: CRASH LOG PARSER                          │
│  services/agent/parser.py                                           │
│                                                                     │
│  1. Normalize escaped newlines, path separators                     │
│  2. Split chained exceptions → isolate root cause block            │
│  3. Scan frames bottom-up → discard site-packages / stdlib          │
│  4. Read 10-line source window with >> pointer at failing line      │
│  5. Enforce path traversal security guard                           │
│                                                                     │
│  OUTPUT: CrashLocation(file, line, function, error_type, context)   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  CrashLocation dataclass
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  STAGE 2: VECTOR RAG STORE                          │
│  data/seed_chroma.py  →  ChromaDB (persistent, HNSW cosine index)   │
│                                                                     │
│  Two collections:                                                   │
│  ┌─────────────────────────┐  ┌────────────────────────────────┐   │
│  │ historical_incidents    │  │ service_runbooks               │   │
│  │ 6 post-mortems          │  │ 6 service invariants           │   │
│  │ (abstract root causes + │  │ (business contracts +          │   │
│  │  remediation patterns)  │  │  defensive coding invariants)  │   │
│  └─────────────────────────┘  └────────────────────────────────┘   │
│                                                                     │
│  Query: "{error_type}: {message}\n{source_context}"                 │
│  Distance Gate: cosine_distance <= 0.65 → is_confident: True        │
│                                                                     │
│  OUTPUT: rag_prompt_snippet (markdown text block for LLM)           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  RAG Context Dict
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  STAGE 3: GROQ LPU DIAGNOSTIC AGENT                 │
│  services/agent/llm_client.py                                       │
│                                                                     │
│  Prompt Budget: ~720 tokens per call                                 │
│  Temperature: 0.1 (near-deterministic)                              │
│  Response Format: JSON object (strict schema enforcement)           │
│                                                                     │
│  System Role: "Principal SRE & Senior Systems Architect"            │
│  Contract: SEARCH block must match file verbatim, char-for-char     │
│                                                                     │
│  OUTPUT: DiagnosticResult(target_file, search_block, replace_block) │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  DiagnosticResult dataclass
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  STAGE 4: AST GUARD & PATCH SYNTHESIZER             │
│  services/agent/patcher.py                                          │
│                                                                     │
│  1. Path containment guard (workspace boundary enforcement)         │
│  2. Exact-match search: must find search_block 1 and only 1 time   │
│  3. In-memory string replacement (no disk writes)                   │
│  4. ast.parse() pre-flight: validates Python syntax of result       │
│  5. difflib.unified_diff → git-compatible diff output               │
│                                                                     │
│  OUTPUT: PatchResult(success, diff, original, patched)              │
└─────────────────────────────────────────────────────────────────────┘
```

### Token Budget Math

```
Source window (10 lines)         ≈  300 tokens
RAG incident post-mortem         ≈  180 tokens
RAG runbook invariant            ≈  120 tokens
Crash coordinates + headers      ≈  120 tokens
────────────────────────────────────────────────
Total per Groq call              ≈  720 tokens

Groq rate limit: 6,000 TPM (tokens per minute)
Max calls per minute: 6,000 ÷ 720 = 8 self-correction retries/minute
```

---

## 3. Project Structure

```
opsmind-ai/
│
├── services/
│   └── agent/
│       ├── parser.py          ← Stage 1: Traceback → CrashLocation
│       ├── llm_client.py      ← Stage 3: Groq LPU → DiagnosticResult
│       └── patcher.py         ← Stage 4: Search/Replace → Unified Diff
│
├── data/
│   ├── seed_chroma.py         ← Stage 2: ChromaDB seeder + query interface
│   ├── historical_incidents.json ← 6 abstract post-mortem records
│   └── chroma_db/             ← Persisted vector index (gitignored)
│
├── test_bed/
│   ├── app/
│   │   ├── main.py            ← FastAPI app server (ShopFlow)
│   │   ├── database.py        ← SQLAlchemy ORM + SQLite seed
│   │   ├── logger.py          ← Structured JSON logger
│   │   ├── models/
│   │   │   └── domain.py      ← Pydantic domain schemas
│   │   ├── services/
│   │   │   ├── billing.py     ← Fault: ZeroDivisionError
│   │   │   ├── checkout.py    ← Fault: KeyError
│   │   │   ├── inventory.py   ← Fault: IndexError
│   │   │   ├── auth.py        ← Fault: TypeError
│   │   │   ├── promotions.py  ← Fault: ValueError
│   │   │   └── gateway.py     ← Fault: TimeoutError
│   │   └── static/
│   │       └── index.html     ← E-commerce storefront (Tailwind CSS)
│   ├── docs/
│   │   └── SERVICE_RUNBOOK.md ← Service contracts & invariants
│   └── tests/                 ← 6 fault-reproducing integration tests
│
├── test_parser.py             ← 7 unit tests for parser.py
├── test_patcher.py            ← 6 unit tests for patcher.py
├── test_llm_client.py         ← 4 unit tests for llm_client.py
├── test_chroma.py             ← 5 unit tests for seed_chroma.py
│
├── demo.py                    ← End-to-end CLI orchestrator
├── docs/
│   ├── ARCHITECTURE.md
│   ├── SECURITY_MODEL.md
│   ├── DEMO_GUIDE.md
│   └── DEEP_DIVE.md           ← This file
├── README.md
├── ROADMAP.md
├── JOURNAL.md
└── .env.example
```

---

## 4. The Patient Microservice — ShopFlow

ShopFlow is a realistic, production-style **FastAPI e-commerce backend** built specifically to be the test bed. It has **6 intentionally broken services** — each one failing in a different, realistic way.

### 4.1 Domain Models — `domain.py`

Before looking at services, understand the data contracts:

```python
"""
Domain Data Contracts & Pydantic Schemas for ShopFlow Microservice
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class Product(BaseModel):
    id: int
    name: str
    sku: str
    price: float
    category: str
    stock: int


class OrderSummary(BaseModel):
    subtotal: float
    tax: float
    discount_amount: float
    total_payable: float
    effective_discount_ratio: float   # ← Division happens here


class OrderConfirmation(BaseModel):
    order_id: str
    total_amount: float
    status: str
    fulfillment_tier: str
    shipping_destination: str        # ← KeyError happens trying to populate this
```

**Key concept — Pydantic `BaseModel`:**
Pydantic validates that all fields have the correct Python types at runtime. If you pass `price="hello"` where `float` is expected, Pydantic raises a `ValidationError` automatically — no manual type checking needed.

---

### 4.2 Database Layer — `database.py`

```python
"""Catalog persistence layer — PostgreSQL via SQLAlchemy with local fallback."""

import os
from sqlalchemy import Column, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

def _get_engine():
    db_url = os.getenv("DATABASE_URL", "")
    if db_url and "postgresql" in db_url:
        try:
            eng = create_engine(db_url, pool_pre_ping=True)
            with eng.connect():
                pass
            return eng
        except Exception:
            pass
    # Fallback to local SQLite when container is offline
    sqlite_url = "sqlite:///test_bed/shopflow.db"
    return create_engine(sqlite_url, connect_args={"check_same_thread": False})


engine = _get_engine()
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"
    id       = Column(Integer, primary_key=True)
    name     = Column(String, nullable=False)
    sku      = Column(String, unique=True, nullable=False)
    price    = Column(Float, nullable=False)
    category = Column(String, nullable=False)
    stock    = Column(Integer, nullable=False)
    emoji    = Column(String, default="📦")


_SEED = [
    Product(id=1, name="Asus Zephyrus G14 Gaming Laptop",    sku="ASUS-G14-6700S", price=120000.0, category="Electronics", stock=15,  emoji="💻"),
    Product(id=2, name="Keychron Q1 Pro Mechanical Keyboard", sku="KEY-Q1-PRO",     price=14500.0,  category="Peripherals", stock=40,  emoji="⌨️"),
    Product(id=3, name="Dell UltraSharp 27-inch 4K Monitor",  sku="DELL-U2723QE",   price=48000.0,  category="Monitors",    stock=22,  emoji="🖥️"),
    Product(id=4, name="Sony WH-1000XM5 Headphones",          sku="SONY-WH-XM5",    price=29900.0,  category="Audio",       stock=35,  emoji="🎧"),
    Product(id=5, name="Cloud GPU Compute Voucher (100hr)",    sku="GPU-CR-100H",    price=8500.0,   category="Cloud",       stock=100, emoji="☁️"),
    Product(id=6, name="Logitech MX Master 3S Mouse",         sku="LOG-MX3S",       price=9500.0,   category="Peripherals", stock=60,  emoji="🖱️"),
]
```

**Key concept — SQLAlchemy ORM:**
Instead of writing raw SQL like `SELECT * FROM products WHERE id = 1`, SQLAlchemy lets you write `db.get(Product, 1)`. The ORM maps Python objects to database rows.

**Key concept — Dual-engine fallback:**
The `_get_engine()` function tries PostgreSQL first (for production containers) and silently falls back to SQLite (a local file) if the connection fails. This makes local development work without Docker.

---

### 4.3 Structured Logger — `logger.py`

```python
"""Enterprise Structured JSON Logger"""
import json
import logging
import sys
from datetime import datetime, timezone
import uuid

class StructuredJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": "shopflow-api",
            "message": record.getMessage(),
            "logger": record.name,
            "correlation_id": getattr(record, "correlation_id", str(uuid.uuid4())[:8])
        }
        if record.exc_info:
            log_entry["stack_trace"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)

def get_structured_logger(name: str = "shopflow"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredJsonFormatter())
        logger.addHandler(handler)
    return logger

log = get_structured_logger()
```

**Key concept — Structured logging:**
Instead of `print("Error: division by zero")`, structured logging outputs machine-readable JSON:
```json
{
  "timestamp": "2026-09-30T05:27:22Z",
  "level": "ERROR",
  "service": "shopflow-api",
  "message": "Unhandled exception: float division by zero",
  "correlation_id": "f654e4a7"
}
```
This is what log aggregators (Datadog, Grafana Loki) ingest and parse.

---

### 4.4 FastAPI Application Server — `main.py`

```python
"""ShopFlow E-Commerce Microservice — Core API Server"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any


# ── Request Schemas ────────────────────────────────────────────────────────
class CheckoutRequest(BaseModel):
    coupon_code: Optional[str] = None
    customer_payload: Dict[str, Any] = {}
    warehouse_tier: int = 0


# ── Application Lifespan ──────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()                             # Seed SQLite on startup
    log.info("ShopFlow application initialized successfully")
    yield                                 # App runs here


app = FastAPI(title="ShopFlow API", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="test_bed/app/static"), name="static")


# ── Error Catching Middleware ──────────────────────────────────────────────
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        log.error(                       # Log the full traceback to stdout
            f"Unhandled exception during {request.method} {request.url.path}: {exc}",
            exc_info=True,               # ← This captures the stack trace
        )
        return JSONResponse(             # Return structured error to client
            status_code=500,
            content={
                "status": "error",
                "error_type": type(exc).__name__,   # e.g. "ZeroDivisionError"
                "message": str(exc),                # e.g. "float division by zero"
            },
        )


# ── API Routes ────────────────────────────────────────────────────────────
@app.post("/api/checkout")
async def checkout(req: CheckoutRequest):
    discount = evaluate_coupon_discount(req.coupon_code, 500.0) if req.coupon_code else 0.0
    summary  = calculate_order_summary(subtotal=500.0, discount_amount=discount)
    facility = allocate_warehouse_facility(req.warehouse_tier)
    order    = process_order_checkout(summary.total_payable, req.customer_payload)
    return {"order": order.model_dump(), "billing": summary.model_dump(), "facility": facility}
```

**Key concept — FastAPI middleware:**
Middleware wraps every HTTP request. The `call_next` function passes the request to the actual route handler. If the handler raises an unhandled exception, the middleware catches it, logs the full stack trace (which OpsMind AI ingests), and returns a clean JSON error to the client instead of crashing the server.

**Key concept — `lifespan` context manager:**
The `@asynccontextmanager` pattern replaces the older `@app.on_event("startup")` approach. Code before `yield` runs on startup; code after `yield` runs on shutdown.

---

### 4.5 The 6 Fault Scenarios

#### Fault 1 — ZeroDivisionError in `billing.py`

**Trigger:** Cart → Apply promo code `FREE100` → Place Order

```python
"""Billing and financial settlement service for order checkouts."""
from test_bed.app.models.domain import OrderSummary

TAX_RATE: float = 0.18

def calculate_order_summary(subtotal: float, discount_amount: float) -> OrderSummary:
    net_payable_base = round(subtotal - discount_amount, 2)
    tax_amount       = round(net_payable_base * TAX_RATE, 2)
    final_total      = round(net_payable_base + tax_amount, 2)

    effective_ratio  = round(subtotal / net_payable_base, 2)  # ← BUG
    #                                                           When FREE100 applied:
    #                                                           subtotal = 500.0
    #                                                           discount = 500.0
    #                                                           net_payable_base = 0.0
    #                                                           500.0 / 0.0 → ZeroDivisionError

    return OrderSummary(
        subtotal=subtotal,
        tax=tax_amount,
        discount_amount=discount_amount,
        total_payable=final_total,
        effective_discount_ratio=effective_ratio,
    )
```

**OpsMind Fix:**
```python
# BEFORE
effective_ratio = round(subtotal / net_payable_base, 2)

# AFTER
effective_ratio = 0.0 if net_payable_base == 0 else round(subtotal / net_payable_base, 2)
```

---

#### Fault 2 — KeyError in `checkout.py`

**Trigger:** Cart → Leave address field empty → Place Order

```python
"""Order dispatch and fulfillment routing service."""

def process_order_checkout(total_amount: float, customer_payload: Dict[str, Any]) -> OrderConfirmation:
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"

    shipping_destination = customer_payload["shipping_address"]  # ← BUG
    #                                                             Guest users may omit this key
    #                                                             → KeyError: 'shipping_address'

    return OrderConfirmation(
        order_id=order_id,
        total_amount=total_amount,
        status="CONFIRMED",
        fulfillment_tier="TIER-PRIMARY",
        shipping_destination=shipping_destination,
    )
```

**OpsMind Fix:**
```python
# BEFORE
shipping_destination = customer_payload["shipping_address"]

# AFTER
shipping_destination = customer_payload.get("shipping_address", "STANDARD_DELIVERY")
```

---

#### Fault 3 — IndexError in `inventory.py`

**Trigger:** Cart → Delivery: "Rural Relay / Remote SpeedPost" → Place Order

```python
"""Warehouse inventory routing and fulfillment center allocation service."""

WAREHOUSE_FACILITIES = [
    "BLR-Central-Warehouse-0",    # index 0
    "BLR-North-Distribution-1",   # index 1
    "BLR-South-Overflow-2",       # index 2
]

def allocate_warehouse_facility(requested_tier_index: int) -> str:
    allocated_hub = WAREHOUSE_FACILITIES[requested_tier_index]  # ← BUG
    #                                                            Rural SpeedPost sends tier=99
    #                                                            WAREHOUSE_FACILITIES[99] → IndexError
    return allocated_hub
```

**OpsMind Fix:**
```python
# BEFORE
allocated_hub = WAREHOUSE_FACILITIES[requested_tier_index]

# AFTER
clamped_index = min(requested_tier_index, len(WAREHOUSE_FACILITIES) - 1)
allocated_hub = WAREHOUSE_FACILITIES[clamped_index]
```

---

#### Fault 4 — TypeError in `auth.py`

**Trigger:** Click Account → "Refresh Membership Privileges"

```python
"""Session token verification and access control module."""

def decode_session_token(token: Optional[str]) -> Optional[Dict[str, str]]:
    if token == "BEARER_VALID_CUSTOMER_TOKEN":
        return {"user_id": "usr_94821", "role": "PREMIUM_CUSTOMER"}
    return None   # ← Returns None for expired/invalid tokens


def verify_user_permissions(session_token: Optional[str]) -> str:
    session   = decode_session_token(session_token)
    user_role = session["role"]   # ← BUG: TypeError: 'NoneType' object is not subscriptable
    #                              When session is None (expired token), this crashes
    return user_role
```

**OpsMind Fix:**
```python
# BEFORE
session   = decode_session_token(session_token)
user_role = session["role"]

# AFTER
session = decode_session_token(session_token)
if session is None:
    raise ValueError("Session token is invalid or has expired.")
user_role = session["role"]
```

---

#### Fault 5 — ValueError in `promotions.py`

**Trigger:** Cart → Apply promo code `MALFORMED_MINUS50` → Apply

```python
"""Promotional campaign engine and markdown calculation service."""

ACTIVE_PROMOTIONS = {
    "SAVE10": 10.0,
    "SAVE20": 20.0,
    "FREE100": 100.0,
    "MALFORMED_MINUS50": -50.0,   # ← Corrupted data: negative rate
}

def evaluate_coupon_discount(coupon_code: str, base_amount: float) -> float:
    rate = ACTIVE_PROMOTIONS.get(coupon_code, 0.0)

    if rate < 0:
        raise ValueError(f"Invalid promotional rate configured for campaign: {rate}%")
        # ← Correctly raises ValueError, but the middleware doesn't translate
        #   this to 400 Bad Request — it propagates as an unhandled 500 error

    discount_value = round(base_amount * (rate / 100.0), 2)
    return discount_value
```

---

#### Fault 6 — TimeoutError in `gateway.py`

**Trigger:** Cart → Payment: "NetBanking (Direct Bank Wire Transfer)" → Place Order

```python
"""Payment gateway settlement client for external processing networks."""

def dispatch_card_charge(order_id: str, amount: float, simulate_network_hang: bool = False) -> Dict[str, str]:
    log.info(f"Dispatching settlement request for order {order_id} (amount={amount:.2f})")

    if simulate_network_hang:
        raise TimeoutError("Upstream payment network gateway timed out after 3000ms")
        # ← No timeout handler, no retry logic, bare raise — propagates to middleware

    return {
        "status": "CHARGED",
        "order_id": order_id,
        "transaction_id": "TXN_7741892",
    }
```

---

## 5. Stage 1 — Crash Log Parser

**File:** `services/agent/parser.py`
**Purpose:** Convert a raw Python traceback string into a structured `CrashLocation` object containing the file path, line number, function name, error type, and a 10-line source code window.

### 5.1 Data Contract — `CrashLocation`

```python
@dataclass
class CrashLocation:
    file_path: str = ""
    line_number: int = 0
    function_name: str = "<module>"
    error_type: str = ""
    error_message: str = ""
    source_context: str = ""  # 10-line window, >> marks failing line
```

**Key concept — Python dataclass:**
`@dataclass` automatically generates `__init__`, `__repr__`, and `__eq__` methods. It's a lightweight alternative to writing full class boilerplate manually. The `=` defaults mean every field is optional — `CrashLocation()` with no arguments creates an empty, valid object.

### 5.2 Regular Expressions Explained

Three pre-compiled regular expressions drive the parser:

```python
# Matches: File "path/to/file.py", line 25, in function_name
FRAME_REGEX = re.compile(
    r'File\s+"(?P<file>[^"]+)",\s+line\s+(?P<line>\d+)(?:,\s+in\s+(?P<func>[\w<>]+))?'
)
```

Breaking down `FRAME_REGEX`:
- `File\s+` — Literal "File" followed by one or more whitespace characters
- `"(?P<file>[^"]+)"` — A double-quoted string; `[^"]+` matches everything except `"`. Named group: `file`
- `,\s+line\s+` — Literal ", line " with flexible whitespace
- `(?P<line>\d+)` — One or more digits. Named group: `line`
- `(?:,\s+in\s+(?P<func>[\w<>]+))?` — Optionally: ", in function_name". `[\w<>]+` matches word chars plus `<>` (for `<module>`)

```python
# Matches: ZeroDivisionError: float division by zero
EXCEPTION_REGEX = re.compile(
    r'^(?P<type>[a-zA-Z_][a-zA-Z0-9_.]*(?:Error|Exception|Interrupt|Exit)):\s*(?P<msg>.*)$'
)
```

Breaking down `EXCEPTION_REGEX`:
- `^` — Start of line (multiline mode)
- `[a-zA-Z_][a-zA-Z0-9_.]*` — Valid Python identifier characters
- `(?:Error|Exception|Interrupt|Exit)` — Must end in one of these suffixes (filters out non-exception lines)
- `:\s*` — Colon followed by optional whitespace
- `(?P<msg>.*)$` — Everything to end of line. Named group: `msg`

**Key concept — Named capture groups:**
`(?P<name>...)` creates a named group in the regex match. Access it with `match.group("name")` instead of positional `match.group(1)`. This makes code far more readable — `match.group("file")` is unambiguous.

**Key concept — Pre-compiled regex:**
`re.compile()` compiles the pattern once at module load time. Calling `FRAME_REGEX.search(line)` in a loop is faster than `re.search(pattern, line)` because Python doesn't re-parse the pattern on each iteration.

### 5.3 The Exclusion Filter

```python
EXCLUSION_PATTERNS = (
    "site-packages/",   # Third-party libraries (FastAPI, SQLAlchemy, etc.)
    "dist-packages/",   # System-installed packages
    "lib/python3.",     # Python standard library (Linux)
    "Lib/",             # Python stdlib on Windows
    "<frozen",          # Python frozen modules
    "<string>",         # Code evaluated via eval/exec
)
```

A FastAPI traceback contains 15-30 stack frames — most from Uvicorn, Starlette, FastAPI, and SQLAlchemy internals. The filter discards all of these:

```
FULL TRACEBACK (7 frames):
  File "site-packages/uvicorn/httptools_impl.py"    ← EXCLUDED
  File "site-packages/starlette/routing.py"         ← EXCLUDED
  File "site-packages/starlette/routing.py"         ← EXCLUDED
  File "site-packages/fastapi/routing.py"           ← EXCLUDED
  File "site-packages/fastapi/routing.py"           ← EXCLUDED
  File "test_bed/app/main.py"                       ← EXCLUDED (framework glue)
  File "test_bed/app/services/billing.py", line 25  ← ✅ KEPT
```

### 5.4 Bottom-Up Frame Scanning

```python
def extract_failing_frame(lines: List[str]) -> Optional[dict]:
    app_frames = []
    for line in lines:
        match = FRAME_REGEX.search(line)
        if not match:
            continue

        raw_file    = match.group("file")
        line_number = int(match.group("line"))
        func        = match.group("func") or "<module>"

        if any(pattern in raw_file for pattern in EXCLUSION_PATTERNS):
            continue

        app_frames.append({
            "file_path": raw_file,
            "line_number": line_number,
            "function_name": func,
        })

    return app_frames[-1] if app_frames else None  # Last = innermost = actual failure
```

**Why the last frame?** Python tracebacks list frames outermost (caller) first. The **last** application frame is the innermost call — the one that actually raised the exception. Using `app_frames[-1]` instead of `app_frames[0]` is critical.

### 5.5 Source Window Extraction with Security Guard

```python
def extract_source_window(
    file_path: str,
    line_number: int,
    padding: int = 10,
    allowed_root: Optional[str] = None,
) -> str:
    # 1. Resolve canonical absolute path
    root_boundary   = os.path.realpath(allowed_root or os.getcwd())
    resolved_target = os.path.realpath(
        file_path if os.path.isabs(file_path) else os.path.join(root_boundary, file_path)
    )

    # 2. Path Traversal Guard
    try:
        common = os.path.commonpath([root_boundary, resolved_target])
    except ValueError:
        # ValueError raised on Windows when paths are on different drives
        return f"# Security Guard: Target '{file_path}' traverses across storage boundaries"

    if common != root_boundary:
        return f"# Security Guard: Access denied for path outside workspace boundary: {file_path}"

    # 3. Read and slice the source file
    with open(resolved_target, "r", encoding="utf-8") as f:
        all_lines = f.readlines()

    start = max(0, line_number - 1 - padding)
    end   = min(len(all_lines), line_number + padding)

    # 4. Format with >> pointer
    formatted_lines = []
    for idx in range(start, end):
        curr_line    = idx + 1
        code_content = all_lines[idx].rstrip("\r\n")
        marker       = ">>" if curr_line == line_number else "  "
        formatted_lines.append(f"{marker} {curr_line:4d} | {code_content}")

    return "\n".join(formatted_lines)
```

**Key concept — Path traversal attack:**
Imagine a crafted traceback saying `File "../../etc/passwd"`. Without the guard, the code would read the system password file. `os.path.realpath()` resolves `..` and symlinks to the true canonical absolute path. `os.path.commonpath()` then verifies the resolved path shares the workspace root as its prefix.

**Output example:**
```
   20 |     net_payable_base = round(subtotal - discount_amount, 2)
   21 |     tax_amount       = round(net_payable_base * TAX_RATE, 2)
   22 |     final_total      = round(net_payable_base + tax_amount, 2)
   23 |
   24 |     # Compute effective discount ratio for analytics reporting
>> 25 |     effective_ratio  = round(subtotal / net_payable_base, 2)
   26 |
   27 |     return OrderSummary(
```

### 5.6 Chained Exception Handling

Python 3 supports chained exceptions:

```python
try:
    result = subtotal / net_payable_base    # ZeroDivisionError
except ZeroDivisionError as e:
    raise RuntimeError("Payment pipeline failed") from e    # Chained!
```

This produces a traceback with TWO exception blocks separated by the chain separator. OpsMind AI always targets the **root cause block**:

```python
def parse_crash_traceback(raw_traceback: str, ...) -> CrashLocation:
    # Split on chain separator — take first block = root cause
    blocks = CHAIN_SEPARATOR_REGEX.split(raw_traceback)
    primary_block = blocks[0] if blocks else raw_traceback
    ...
```

Without this, a chained exception would point to the outer wrapper (`RuntimeError: Payment pipeline failed`) rather than the actual bug (`ZeroDivisionError` in `billing.py`).

---

## 6. Stage 2 — Vector RAG Knowledge Base

**File:** `data/seed_chroma.py`
**Purpose:** Store and query historical incident post-mortems and service runbook invariants using semantic similarity search.

### 6.1 What is RAG?

**RAG (Retrieval-Augmented Generation)** is a pattern where you retrieve relevant context documents from a database and inject them into an LLM prompt, rather than relying on the LLM's training data alone.

```
Without RAG:
  LLM prompt: "This code crashed. Fix it."
  LLM: [Guesses based on general training data]

With RAG:
  LLM prompt: "This code crashed. Here's a post-mortem from a similar
               incident 6 months ago + the exact business invariant
               from the service runbook. Fix it."
  LLM: [Applies the documented remediation pattern precisely]
```

### 6.2 Vector Embeddings — How Text Becomes Numbers

ChromaDB stores documents as **embedding vectors** — arrays of ~384 floating-point numbers that encode the semantic meaning of text. Similar texts produce vectors that are close together in 384-dimensional space.

```
"ZeroDivisionError: float division by zero"
→ [0.234, -0.891, 0.445, 0.023, ..., -0.119]  # 384 numbers

"division by zero calculation bug"
→ [0.229, -0.883, 0.441, 0.019, ..., -0.114]  # Very similar vectors!

"HTTP 404 page not found"
→ [0.823, 0.111, -0.672, 0.891, ..., 0.445]   # Very different vectors!
```

ChromaDB generates these embeddings locally using **ONNX** (Open Neural Network Exchange) — a portable ML model format that runs without a GPU.

### 6.3 The HNSW Index

ChromaDB uses **HNSW (Hierarchical Navigable Small World)** for fast approximate nearest-neighbor search:

```
Naive approach: Compare query vector against ALL stored vectors
→ O(n) time — slow for large databases

HNSW approach: Build a multi-layer graph where nearby vectors are connected.
Higher layers: fewer nodes, long-range "highway" connections
Lower layers: all nodes, fine-grained local connections

→ O(log n) time — fast even with millions of vectors
```

This is configured when creating collections:
```python
incidents_col = client.get_or_create_collection(
    name="historical_incidents",
    metadata={"hnsw:space": "cosine"},  # Use cosine distance metric (not Euclidean)
)
```

### 6.4 The Two Collections

**Collection 1 — Historical Incidents** (`data/historical_incidents.json`):

Each record represents an abstract post-mortem from a legacy system:

```json
{
  "incident_id": "INC-2024-041",
  "service_context": "Legacy Subscription Engine (LegacySubApp)",
  "error_type": "ZeroDivisionError",
  "signature": "ZeroDivisionError: division by zero",
  "abstract_root_cause": "Calculation attempted to divide by a variable that evaluated
                          to zero during full 100% discount calculations.",
  "remediation_pattern": "Inspect the denominator before performing division.
                          Add a guard clause: if denominator == 0, return 0.0."
}
```

6 records cover: ZeroDivisionError, KeyError, IndexError, TypeError, ValueError, TimeoutError.

**Collection 2 — Service Runbook Invariants** (parsed from `SERVICE_RUNBOOK.md`):

```markdown
## 1. Billing Service (`app/services/billing.py`)
* **Contract:** Calculates the discount factor and net payable ratio for an order.
* **Domain Rule:** A 100% promotional discount yields a net payable of ₹0.00.
* **Invariant:** When `discount_amount == total_amount`, net payable is ₹0.00.
  The function MUST NOT divide by zero. It must return `effective_discount_ratio = 0.0` safely.
```

### 6.5 Seeding the Database

```python
def seed_vector_db(
    incidents_path: str = "data/historical_incidents.json",
    runbook_path: str   = "test_bed/docs/SERVICE_RUNBOOK.md",
    persist_dir: str    = "data/chroma_db",
) -> Dict[str, int]:

    client = chromadb.PersistentClient(path=persist_dir)

    incidents_col = client.get_or_create_collection(
        name="historical_incidents",
        metadata={"hnsw:space": "cosine"},
    )

    with open(incidents_path, "r", encoding="utf-8") as f:
        incidents_data = json.load(f)

    inc_ids, inc_docs, inc_metas = [], [], []

    for inc in incidents_data:
        # Concatenate all fields into a single searchable string
        doc = (
            f"Error Type: {inc.get('error_type', '')}\n"
            f"Signature: {inc.get('signature', '')}\n"
            f"Context: {inc.get('service_context', '')}\n"
            f"Root Cause: {inc.get('abstract_root_cause', '')}\n"
            f"Remediation Pattern: {inc.get('remediation_pattern', '')}"
        )
        inc_ids.append(f"inc-{inc['incident_id']}")
        inc_docs.append(doc)
        inc_metas.append({
            "incident_id": inc.get("incident_id", ""),
            "error_type":  inc.get("error_type", ""),
            "service":     inc.get("service_context", ""),
        })

    # upsert = insert or update (idempotent — safe to run multiple times)
    incidents_col.upsert(ids=inc_ids, documents=inc_docs, metadatas=inc_metas)
```

**Key concept — Idempotency:**
`upsert` ("update or insert") means: if a document with this `id` already exists, update it. If not, insert it. Running `seed_vector_db()` 10 times produces the same result as running it once — no duplicates.

### 6.6 Cosine Distance Gating

```python
MAX_COSINE_DISTANCE = 0.65
```

Cosine distance measures how different two vectors are:
- `0.0` = identical meaning
- `1.0` = completely unrelated meaning
- `0.65` = our threshold — "similar enough to be useful"

```python
inc_dist      = inc_res["distances"][0][0]       # The distance of the best match
inc_confident = inc_dist <= distance_threshold   # True = match is relevant

# Only inject the document if we're confident the match is relevant
inc_doc = inc_res["documents"][0][0] if inc_confident else ""
```

**Why this matters:** Without distance gating, a query about a `KeyError` in billing might retrieve a post-mortem about a `MemoryError` in a completely different system with distance `0.82`. Injecting irrelevant context into the LLM prompt causes hallucination. The gate prevents this.

### 6.7 The RAG Prompt Snippet

The final output of Stage 2 is a formatted text block injected into the LLM prompt:

```
### Historical Incident Reference
Error Type: ZeroDivisionError
Signature: ZeroDivisionError: division by zero
Context: Legacy Subscription Engine (LegacySubApp)
Root Cause: Calculation attempted to divide by a variable that evaluated to zero.
Remediation Pattern: Inspect the denominator. If 0, return 0.0 safely.

### Service Runbook Invariant
Service: Billing Service (app/services/billing.py)
Contract: Calculates the discount factor and net payable ratio for an order.
Domain Rule: A 100% promotional discount yields a net payable of Rs.0.00.
Invariant & Remediation: When discount_amount == total_amount, return 0.0 safely.
```

### 6.8 The gRPC Windows Compatibility Fix

On Windows with Application Control policies enforced, the compiled `grpc` C-extension (`cygrpc.pyd`) is blocked. ChromaDB uses gRPC internally and fails to import. The fix pre-populates Python's module registry before ChromaDB is imported:

```python
from unittest.mock import MagicMock
import warnings, sys

# Suppress version-mismatch warnings from the mock
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Resilient fallback for environments restricting compiled gRPC C-extensions
try:
    import grpc  # noqa: F401 — try the real one first
except ImportError:
    mock_grpc = MagicMock()
    mock_grpc.__version__ = "1.65.0"   # Match installed version to suppress warnings
    sys.modules["grpc"]              = mock_grpc
    sys.modules["grpc._compression"] = MagicMock()
    sys.modules["grpc._cython"]      = MagicMock()

import chromadb   # ← Now succeeds; uses local ONNX embedding path instead
```

**Key concept — `sys.modules` injection:**
`sys.modules` is Python's dictionary of all currently loaded modules. By pre-populating it with `MagicMock` objects before `import chromadb`, Python's import system finds the mocks when ChromaDB internally runs `import grpc`. Any subsequent call like `mock_grpc.some_method()` returns another MagicMock harmlessly. ChromaDB's ONNX-based local embedding path is used instead.

**Order is critical:** This block must appear before `import chromadb`. If `chromadb` is imported first and fails, adding mocks afterward won't help.

---

## 7. Stage 3 — Groq LPU Diagnostic Agent

**File:** `services/agent/llm_client.py`
**Purpose:** Format a structured LLM prompt combining crash coordinates + RAG context, call the Groq API, and parse the JSON response into a `DiagnosticResult`.

### 7.1 Data Contract — `DiagnosticResult`

```python
@dataclass
class DiagnosticResult:
    root_cause_analysis: str    # "net_payable_base becomes 0 with FREE100 coupon"
    confidence_score: float     # 0.0 to 1.0
    target_file: str            # "test_bed/app/services/billing.py"
    search_block: str           # Exact buggy code to find in file
    replace_block: str          # Replacement code
    explanation: str            # Human-readable rationale
```

### 7.2 The System Prompt

```python
SYSTEM_PROMPT = """You are a Principal Site Reliability Engineer and Senior Systems Architect.
Your task is to analyze application crash logs, review relevant runbook business invariants,
and synthesize a surgical code fix.

CRITICAL OPERATIONAL RULES:
1. Produce an exact SEARCH block containing the existing buggy lines.
   The SEARCH block must match character-for-character, including indentation.
2. Produce an exact REPLACE block containing the defensive bug fix.
3. Obey the Service Runbook Invariant strictly.
   Do not introduce breaking behavioral side effects.
4. Keep edits surgical: do NOT rewrite entire functions or classes.
   Only modify the minimum lines needed to prevent the failure.
5. Always respond in strict, valid JSON matching the required schema. No conversational filler.

REQUIRED JSON OUTPUT FORMAT:
{
  "root_cause_analysis": "<1-2 sentence technical root cause>",
  "confidence_score": <float between 0.0 and 1.0>,
  "target_file": "<path to file being edited>",
  "search_block": "<exact snippet to replace>",
  "replace_block": "<replacement code snippet>",
  "explanation": "<1-2 sentence rationale for the change>"
}
"""
```

**Key design decisions:**

1. **SEARCH/REPLACE contract over line numbers:** The LLM provides the exact verbatim string to search for. This is robust — line numbers change every time code is edited. The buggy code string stays identifiable.

2. **Temperature 0.1:** Near-zero temperature makes the LLM near-deterministic. For code fixes, creativity is the enemy — we want the most likely, documented, well-established solution.

3. **`response_format={"type": "json_object"}`:** Groq's JSON mode guarantees valid JSON output. Without this, the LLM might wrap the JSON in markdown fences or add preamble text.

### 7.3 Prompt Construction

```python
def format_diagnostic_prompt(
    crash_location: CrashLocation,
    rag_context: Dict[str, Any],
    previous_error: Optional[str] = None,
) -> str:
    prompt_parts = [
        f"CRASH COORDINATES:",
        f"- Error Type: {crash_location.error_type}",
        f"- Error Message: {crash_location.error_message}",
        f"- Target File: {crash_location.file_path}",
        f"- Target Line: {crash_location.line_number}",
        f"- Enclosing Function: {crash_location.function_name}",
        "",
        "SOURCE CODE CONTEXT (with '>>' indicating failure line):",
        "```python",
        crash_location.source_context,    # The 10-line window from Stage 1
        "```",
        "",
        "RETRIEVED RUNBOOK & REMEDIATION KNOWLEDGE:",
        rag_context.get("rag_prompt_snippet", "No runbook context available."),
    ]

    if previous_error:          # Self-correction loop — inject previous failure
        prompt_parts.extend([
            "",
            "PREVIOUS PATCH VALIDATION FAILURE:",
            "The previous patch failed sandbox testing with this error. Correct your approach:",
            "```text",
            previous_error.strip(),
            "```",
        ])

    prompt_parts.append(
        "Synthesize the fix now. Remember: The SEARCH block must exist verbatim in the source file."
    )

    return "\n".join(prompt_parts)
```

### 7.4 Calling the Groq API

```python
def diagnose_and_generate_patch(
    crash_location: CrashLocation,
    rag_context: Dict[str, Any],
    previous_error: Optional[str] = None,
    client: Optional[Groq] = None,     # Allows injection for tests (DI pattern)
) -> DiagnosticResult:

    api_key = os.getenv("GROQ_API_KEY")
    model   = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

    groq_client = client or Groq(api_key=api_key)   # Use injected client or create one

    response = groq_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        response_format={"type": "json_object"},   # Guaranteed valid JSON
        temperature=0.1,                            # Near-deterministic output
        max_tokens=1000,                            # Cap output to control cost
    )

    raw_content = response.choices[0].message.content or "{}"
    parsed      = clean_json_response(raw_content)

    return DiagnosticResult(
        root_cause_analysis=parsed.get("root_cause_analysis", ""),
        confidence_score=float(parsed.get("confidence_score", 0.9)),
        target_file=parsed.get("target_file", crash_location.file_path),
        search_block=parsed.get("search_block", "").strip("\r\n"),
        replace_block=parsed.get("replace_block", "").strip("\r\n"),
        explanation=parsed.get("explanation", ""),
    )
```

**Key concept — Dependency Injection for testing:**
The `client: Optional[Groq] = None` parameter allows tests to pass a mock Groq client: `diagnose_and_generate_patch(crash, rag, client=mock_groq)`. This avoids making real API calls in unit tests, making them fast and cost-free.

**Key concept — Defensive `.get()` with defaults:**
Even with JSON mode enabled, the LLM might return JSON missing some keys. Using `.get("key", default)` instead of `["key"]` means the response parsing code won't crash with its own `KeyError`.

### 7.5 JSON Response Cleaning

```python
def clean_json_response(content: str) -> Dict[str, Any]:
    """
    Strips markdown code fences if present and parses string into a JSON dictionary.
    """
    clean_text = content.strip()
    if clean_text.startswith("```"):
        clean_text = re.sub(r"^```(?:json)?\n?", "", clean_text)
        clean_text = re.sub(r"\n?```$", "", clean_text)
    return json.loads(clean_text)
```

Despite `response_format={"type": "json_object"}`, some model versions still wrap output in markdown fences. This function handles both cases robustly.

---

## 8. Stage 4 — AST Guard & Patch Synthesizer

**File:** `services/agent/patcher.py`
**Purpose:** Apply the LLM's proposed SEARCH/REPLACE transformation with multiple safety guards, then produce a standard unified diff. Zero host files are modified.

### 8.1 Data Contract — `PatchResult`

```python
@dataclass
class PatchResult:
    success: bool
    target_file: str
    original_content: str = ""    # The file before the patch
    patched_content: str  = ""    # The file after the patch (in memory only)
    diff: str             = ""    # Git-compatible unified diff
    error: Optional[str]  = None  # Human-readable error if success=False
```

### 8.2 The 6-Step Patch Pipeline

```python
def synthesize_patch(
    target_file: str,
    search_block: str,
    replace_block: str,
    allowed_root: Optional[str] = None,
) -> PatchResult:
```

**Step 1 — Path Containment Guard:**
```python
root_boundary   = os.path.realpath(allowed_root or os.getcwd())
resolved_target = os.path.realpath(target_file)

try:
    common = os.path.commonpath([root_boundary, resolved_target])
except ValueError:
    return PatchResult(success=False, error="Security Guard: cross-boundary path detected")

if common != root_boundary:
    return PatchResult(success=False, error="Security Guard: path outside workspace")
```

**Step 2 — Read Source Content:**
```python
with open(resolved_target, "r", encoding="utf-8") as f:
    original_content = f.read()

norm_original = normalize_line_endings(original_content)    # CRLF → LF
norm_search   = normalize_line_endings(search_block).strip("\n")
norm_replace  = normalize_line_endings(replace_block).strip("\n")
```

**Key concept — Line ending normalization:**
Windows files use `\r\n` (CRLF). Unix/Mac files use `\n` (LF). If the file has CRLF but the LLM returns LF in the search block, `"CRLF string".count("LF search")` returns 0 — the match fails. Normalizing everything to LF before matching prevents this class of spurious failures.

**Step 3 — Unambiguity Guard:**
```python
match_count = norm_original.count(norm_search)

if match_count == 0:
    return PatchResult(success=False, error="Search block not found in target file.")

if match_count > 1:
    return PatchResult(
        success=False,
        error=f"Ambiguous transformation: Search block matched {match_count} locations."
    )
```

**Why this matters:** If `search_block = "pass"` appears 5 times in a file, replacing blindly corrupts all 5 locations. OpsMind AI refuses ambiguous patches — the LLM must provide a more specific, unique search block.

**Step 4 — In-Memory Patching:**
```python
patched_content = norm_original.replace(norm_search, norm_replace, 1)
#                                                                    ^
#                                                                    Limit to 1 replacement
#                                                                    (belt-and-suspenders)
```

This is a pure string operation. No file is opened for writing.

**Step 5 — AST Pre-flight Guard:**
```python
try:
    ast.parse(patched_content, filename=resolved_target)
except SyntaxError as e:
    return PatchResult(
        success=False,
        error=f"AST Syntax Validation Failed on line {e.lineno}: {e.msg}",
    )
```

**Key concept — AST (Abstract Syntax Tree):**
`ast.parse()` parses Python source code into an in-memory tree representing the code's structure — the same step the Python interpreter takes before compiling to bytecode. If the LLM generates a fix with a missing colon, mismatched parenthesis, or invalid indentation, `ast.parse()` raises `SyntaxError`. We catch this immediately, before any deployment decision.

**Step 6 — Unified Diff Generation:**
```python
rel_path    = os.path.relpath(resolved_target, root_boundary).replace("\\", "/")
orig_lines  = norm_original.splitlines(keepends=True)
patch_lines = patched_content.splitlines(keepends=True)

diff_lines = list(
    difflib.unified_diff(
        orig_lines,
        patch_lines,
        fromfile=f"a/{rel_path}",   # Matches git diff format
        tofile=f"b/{rel_path}",
    )
)
unified_diff = "".join(diff_lines)
```

**Output:**
```diff
--- a/test_bed/app/services/billing.py
+++ b/test_bed/app/services/billing.py
@@ -22,7 +22,7 @@
     net_payable_base = round(subtotal - discount_amount, 2)
     tax_amount       = round(net_payable_base * TAX_RATE, 2)
     final_total      = round(net_payable_base + tax_amount, 2)
-    effective_ratio  = round(subtotal / net_payable_base, 2)
+    effective_ratio  = 0.0 if net_payable_base == 0 else round(subtotal / net_payable_base, 2)
 
     return OrderSummary(
```

This format is directly pasteable into a GitHub PR, applied with `git apply patch.diff`, or used to open an automated pull request.

---

## 9. The Orchestrator — `demo.py`

`demo.py` wires all four stages into a single end-to-end pipeline with terminal output:

```python
"""
Live Demonstration Script for OpsMind AI (Steps 1 through 4).
Pipeline: Raw Crash Traceback → Stage 1 → Stage 2 → Stage 3 → Stage 4
"""

SCENARIOS = {
    "billing": {
        "name": "Billing Service — ZeroDivisionError (FREE100 promo code)",
        "traceback": """Traceback (most recent call last):
  File "C:/Zephyrus/Husen/Projects/opsmind-ai/test_bed/app/services/billing.py",
       line 25, in calculate_order_summary
    effective_ratio = round(subtotal / net_payable_base, 2)
ZeroDivisionError: float division by zero""",
    },
    "checkout": {
        "name": "Checkout Service — KeyError (Guest checkout missing shipping_address)",
        "traceback": """...""",
    },
}


def run_demo(scenario_key: str = "billing"):
    scenario = SCENARIOS.get(scenario_key, SCENARIOS["billing"])
    raw_tb   = scenario["traceback"]

    # ── Stage 1 ──────────────────────────────────────────────────────
    print("[STEP 1] Ingesting Crash Telemetry & Isolating Coordinates...")
    crash_loc = parse_crash_traceback(raw_tb)
    print(f"  --> Failure Target:    {crash_loc.file_path}:{crash_loc.line_number}")
    print(f"  --> Exception Type:    {crash_loc.error_type}")
    print(f"  --> Source Window:\n{crash_loc.source_context}")

    # ── Stage 2 ──────────────────────────────────────────────────────
    print("[STEP 2] Querying ChromaDB Vector Knowledge Base...")
    rag_context = query_incident_context(
        crash_loc.error_type, crash_loc.error_message, crash_loc.source_context,
        persist_dir="data/chroma_db",
    )
    inc = rag_context.get("incident", {})
    rb  = rag_context.get("runbook", {})
    print(f"  --> Incident Match:    {inc.get('id', 'N/A')} (Distance: {inc.get('distance', 1.0):.4f})")
    print(f"  --> Runbook Invariant: {rb.get('id', 'N/A')} (Distance: {rb.get('distance', 1.0):.4f})")

    # ── Stage 3 ──────────────────────────────────────────────────────
    print("[STEP 3] Synthesizing Surgical Patch via Groq LPU...")
    t0         = time.time()
    diagnostic = diagnose_and_generate_patch(crash_loc, rag_context)
    latency    = time.time() - t0
    print(f"  --> Generation Time:   {latency:.2f}s")
    print(f"  --> Confidence Score:  {diagnostic.confidence_score * 100:.1f}%")
    print(f"  --> Root Cause:        {diagnostic.root_cause_analysis}")

    # ── Stage 4 ──────────────────────────────────────────────────────
    print("[STEP 4] Enforcing AST Guard & Synthesizing Unified Diff...")
    patch_result = synthesize_patch(
        target_file=diagnostic.target_file,
        search_block=diagnostic.search_block,
        replace_block=diagnostic.replace_block,
    )

    if patch_result.success:
        print("  --> AST Validation:    PASSED")
        print("  --> Host File Status:  UNTOUCHED (Patch applied strictly in-memory)")
        print(patch_result.diff)
        print("[SUCCESS] Remediation proposal synthesized and verified!")
    else:
        print(f"  --> AST Validation FAILED: {patch_result.error}")


if __name__ == "__main__":
    choice = sys.argv[1] if len(sys.argv) > 1 else "billing"
    run_demo(choice)
```

**Usage:**
```bash
python demo.py billing    # ZeroDivisionError scenario
python demo.py checkout   # KeyError scenario
```

---

## 10. Unit Testing Strategy

### 10.1 Testing Philosophy

The project follows a strict two-layer testing strategy:

| Layer | Files | Count | Pass/Fail |
|:---|:---|:---|:---|
| Unit tests (offline) | `test_parser.py`, `test_patcher.py`, `test_chroma.py`, `test_llm_client.py` | 22 | All PASS |
| Fault integration tests | `test_bed/tests/test_billing.py`, etc. | 6 | All FAIL by design |

The fault tests **are expected to fail**. They prove the bugs exist. OpsMind AI's job is to produce a fix that makes them pass.

### 10.2 Parser Tests — `test_parser.py`

```python
# Test 1: Exception extraction works
def test_extract_exception_details():
    lines = normalize_traceback_text(TB_STANDARD)
    err_type, err_msg = extract_exception_details(lines)
    assert err_type == "ZeroDivisionError"
    assert "division by zero" in err_msg

# Test 2: Framework frames are excluded, only app frame kept
def test_extract_failing_frame_pollution():
    lines = normalize_traceback_text(TB_POLLUTED)  # Has uvicorn + starlette frames
    frame = extract_failing_frame(lines)
    assert frame is not None
    assert "checkout.py" in frame["file_path"]   # App code, not uvicorn
    assert frame["line_number"] == 23

# Test 3: Chained exceptions target root cause
def test_chained_exception_targeting_root_cause():
    location = parse_crash_traceback(TB_CHAINED)
    assert location.error_type == "ZeroDivisionError"   # Root cause, not outer RuntimeError
    assert "billing.py" in location.file_path

# Test 4: Path traversal is blocked
def test_path_traversal_guard():
    output = extract_source_window(
        file_path="C:/Windows/System32/drivers/etc/hosts",
        line_number=1,
        allowed_root="C:/Zephyrus/Husen/Projects/opsmind-ai/test_bed",
    )
    assert "Security Guard" in output

# Test 5: Source window has >> pointer
def test_parse_crash_traceback_full():
    location = parse_crash_traceback(TB_STANDARD)
    assert isinstance(location, CrashLocation)
    assert ">>" in location.source_context
```

### 10.3 Patcher Tests — `test_patcher.py`

```python
# Test 1: Valid patch generates correct unified diff
def test_successful_patch_synthesis():
    result = synthesize_patch(
        TARGET_FILE,
        "effective_ratio = round(subtotal / net_payable_base, 2)",
        "effective_ratio = 0.0 if net_payable_base == 0 else round(subtotal / net_payable_base, 2)",
    )
    assert result.success is True
    assert "-    effective_ratio = round(subtotal / net_payable_base, 2)" in result.diff
    assert "+    effective_ratio = 0.0 if net_payable_base == 0" in result.diff

# Test 2: Missing search block returns clear error
def test_search_block_not_found():
    result = synthesize_patch(TARGET_FILE, "this code does not exist in the file", "replacement")
    assert result.success is False
    assert "Search block not found" in result.error

# Test 3: Syntactically broken code rejected by AST
def test_ast_syntax_error_rejection():
    result = synthesize_patch(
        TARGET_FILE,
        "effective_ratio = round(subtotal / net_payable_base, 2)",
        "effective_ratio = def broken_syntax(",   # Invalid Python!
    )
    assert result.success is False
    assert "AST Syntax Validation Failed" in result.error

# Test 4: Host file untouched after sandbox write
def test_write_patch_to_sandbox_isolation():
    result = synthesize_patch(...)
    assert result.success is True

    temp_sandbox = tempfile.mkdtemp(prefix="opsmind_sandbox_test_")
    sandbox_path = write_patch_to_sandbox(result, temp_sandbox)

    # Sandbox file has the fix
    with open(sandbox_path, "r") as f:
        assert "0.0 if net_payable_base == 0" in f.read()

    # Host file untouched
    with open(TARGET_FILE, "r") as f:
        assert "effective_ratio = round(subtotal / net_payable_base, 2)" in f.read()
        assert "0.0 if net_payable_base == 0" not in f.read()
```

### 10.4 ChromaDB Tests — `test_chroma.py`

```python
# Test 1: Correct incident for ZeroDivisionError
def test_query_high_confidence_zerodiv():
    res = query_incident_context(
        error_type="ZeroDivisionError",
        error_message="float division by zero",
        source_context="effective_discount_ratio = subtotal / net_payable_base",
        persist_dir=TEST_DB_DIR,
    )
    assert res["incident"]["is_confident"] is True
    assert res["incident"]["id"] == "inc-INC-2024-041"
    assert "Billing" in res["runbook"]["metadata"]["service_name"]

# Test 2: Unrelated query filtered by distance gate
def test_distance_threshold_guard():
    res = query_incident_context(
        error_type="UnrelatedKernelPanicError",
        error_message="corrupted hardware interrupt memory segment",
        source_context="asm volatile('cli')",
        persist_dir=TEST_DB_DIR,
    )
    assert res["incident"]["is_confident"] is False    # Gate rejected the match
    assert res["runbook"]["is_confident"] is False
    assert "No domain runbook invariant defined" in res["rag_prompt_snippet"]

# Test 3: Seeding is idempotent
def test_seed_vector_db_idempotency():
    counts_1 = seed_vector_db(..., persist_dir=TEST_DB_DIR)
    counts_2 = seed_vector_db(..., persist_dir=TEST_DB_DIR)   # Run again
    assert counts_2["incidents"] == counts_1["incidents"]     # Same count, no duplicates
```

### 10.5 Running the Tests

```bash
# All 22 unit tests (must all pass)
python -m pytest test_parser.py test_chroma.py test_llm_client.py test_patcher.py -v

# ShopFlow fault tests (all 6 expected to FAIL)
python -m pytest test_bed/tests/ -v

# Coverage report
python -m pytest test_parser.py test_chroma.py test_patcher.py --cov=services --cov=data --cov-report=term-missing
```

> **Windows note:** Use `python -m pytest` NOT `pytest.exe` directly. On Windows with Application Control policies, the `pytest.exe` binary may be blocked. Running as a Python module bypasses this restriction.

---

## 11. Security Model

OpsMind AI follows a STRIDE threat model analysis:

| Threat | Attack Vector | Mitigation |
|:---|:---|:---|
| **Spoofing** | Malicious traceback claims arbitrary file path | `os.path.realpath()` resolves canonical path; workspace boundary check rejects anything outside |
| **Tampering** | LLM generates syntactically broken replacement code | `ast.parse()` pre-flight rejects invalid Python before any diff is generated |
| **Repudiation** | Patch applied without audit trail | `difflib.unified_diff` produces a permanent, human-readable audit record of every change |
| **Information Disclosure** | Traceback uses `../../etc/passwd` style path | `os.path.commonpath()` guard returns safe error message instead of file content |
| **Denial of Service** | Flood Groq API with 100x concurrent requests | Distance gating stops unnecessary LLM calls for low-confidence matches |
| **Elevation of Privilege** | LLM attempts to patch system files | Two-layer path guard in both parser and patcher; sandbox writes to isolated tempdir only |

### Zero Host Mutation Guarantee

`synthesize_patch()` never opens a file for writing:

```python
# Only reads:
with open(resolved_target, "r", encoding="utf-8") as f:
    original_content = f.read()

# All transformation is pure string operations in RAM:
patched_content = norm_original.replace(norm_search, norm_replace, 1)

# Returns the result — does NOT write anything:
return PatchResult(success=True, diff=unified_diff, ...)
```

`write_patch_to_sandbox()` is the only function that writes files, and it always writes to an isolated `tempfile.mkdtemp()` directory — never to the source tree:

```python
def write_patch_to_sandbox(patch_result: PatchResult, sandbox_root: str) -> str:
    root_boundary   = os.path.realpath(os.getcwd())
    resolved_target = os.path.realpath(patch_result.target_file)
    rel_path        = os.path.relpath(resolved_target, root_boundary)

    destination_file = os.path.join(sandbox_root, rel_path)   # Inside sandbox, not project
    os.makedirs(os.path.dirname(destination_file), exist_ok=True)

    with open(destination_file, "w", encoding="utf-8") as f:
        f.write(patch_result.patched_content)

    return destination_file
```

---

## 12. Key Concepts Explained

### 12.1 Python Dataclasses vs Regular Classes

```python
# WITHOUT @dataclass — verbose boilerplate (40+ lines for 3 fields)
class CrashLocation:
    def __init__(self, file_path="", line_number=0, error_type=""):
        self.file_path   = file_path
        self.line_number = line_number
        self.error_type  = error_type
    def __repr__(self):
        return f"CrashLocation(file_path={self.file_path!r}, ...)"
    def __eq__(self, other):
        return (self.file_path == other.file_path
                and self.line_number == other.line_number ...)

# WITH @dataclass — all of the above, auto-generated (4 lines)
@dataclass
class CrashLocation:
    file_path: str   = ""
    line_number: int = 0
    error_type: str  = ""
```

### 12.2 `Optional[str]` vs `str`

```python
from typing import Optional

def decode_session_token(token: Optional[str]) -> Optional[Dict[str, str]]:
    #                           ↑                         ↑
    #                           Accepts str OR None       Returns dict OR None
```

`Optional[X]` is shorthand for `Union[X, None]`. It explicitly signals that `None` is a valid value — forcing callers to handle the `None` case rather than assuming the function always returns a value.

### 12.3 Context Managers

```python
# WITHOUT context manager — resource leak risk
f = open("billing.py", "r")
content = f.read()
f.close()   # Might never execute if an exception occurs first!

# WITH context manager — guaranteed cleanup
with open("billing.py", "r", encoding="utf-8") as f:
    content = f.read()
# f.close() is called automatically here, even if an exception occurred inside
```

### 12.4 Cosine Similarity vs Euclidean Distance

For text embedding similarity search, **cosine similarity** is preferred because it's insensitive to vector magnitude (length). A short sentence and a long paragraph on the same topic have similar cosine similarity even though their Euclidean distance would be large:

```
cosine_similarity(A, B) = (A · B) / (|A| × |B|)
cosine_distance = 1 - cosine_similarity

0.0 = identical meaning
0.65 = our threshold (similar enough to be useful)
1.0 = completely unrelated
```

### 12.5 The AST in Detail

```python
import ast

source = """
effective_ratio = round(subtotal / net_payable_base, 2)
"""

tree = ast.parse(source)
# tree is a Module containing an Assign node:
#   Assign(
#     targets=[Name(id='effective_ratio')],
#     value=Call(
#       func=Name(id='round'),
#       args=[
#         BinOp(left=Name(id='subtotal'), op=Div(), right=Name(id='net_payable_base')),
#         Constant(value=2)
#       ]
#     )
#   )
```

`ast.parse()` validates Python syntax without executing the code. It's the same parser the Python interpreter uses internally. A failed parse means the code has a syntax error that would crash the interpreter. Using it as a pre-flight check catches LLM mistakes before they reach any deployment system.

### 12.6 The Unified Diff Format

```diff
--- a/services/billing.py       ← Original file label
+++ b/services/billing.py       ← Patched file label
@@ -22,7 +22,7 @@             ← Hunk: starting at line 22, 7 lines in original; 7 lines in patched
 net_payable_base = round(...)  ← Context (space prefix = unchanged)
 tax_amount = round(...)        ← Context
-effective_ratio = round(...)   ← Removed (- prefix)
+effective_ratio = 0.0 if ...   ← Added (+ prefix)
 return OrderSummary(           ← Context
```

This format is understood natively by `git apply`, `patch`, GitHub's PR view, GitLab, Gerrit, and all major code review tools.

### 12.7 Python f-strings with Format Specifiers

```python
curr_line = 25
marker    = ">>"
code      = "    effective_ratio = round(..."

formatted = f"{marker} {curr_line:4d} | {code}"
#                            ^^^
#                            :4d = format as integer, pad to 4 chars wide
# Result: ">>   25 |    effective_ratio = round(..."
```

The `:4d` format specifier right-aligns the line number in a 4-character field, ensuring the `>>` pointer columns stay aligned regardless of whether line numbers are 1 or 999.

---

## 13. Running the Project

### 13.1 Prerequisites

```powershell
# Python 3.11+ required (project developed on 3.14.7)
python --version

# Install dependencies
pip install fastapi uvicorn pydantic groq chromadb python-dotenv sqlalchemy
```

### 13.2 Environment Setup

```powershell
# Copy the example env file
Copy-Item .env.example .env

# Edit .env with your Groq API key:
#   GROQ_API_KEY=gsk_your_key_here
#   GROQ_MODEL=openai/gpt-oss-120b
notepad .env
```

### 13.3 Seed the Knowledge Base

```powershell
# Run from the project root
python -m data.seed_chroma

# Expected output:
# [*] Re-indexing ChromaDB vector storage with updated runbook paths...
# [+] Seeding complete. Incidents indexed: 6, Runbooks indexed: 6
```

### 13.4 Start ShopFlow

```powershell
# Start the patient microservice
python -m uvicorn test_bed.app.main:app --port 8001

# Open in browser: http://127.0.0.1:8001
# Health check:    http://127.0.0.1:8001/api/health
```

> **Note:** Use port 8001 instead of 8000. Windows maintains TIME_WAIT sockets for 4 minutes after a connection is closed — if you previously ran on port 8000 and killed the process, the port may not be immediately reusable.

### 13.5 Trigger the 6 Faults

| Fault | Trigger via UI |
|:---|:---|
| `ZeroDivisionError` | Cart → Promo: `FREE100` → Place Order |
| `KeyError` | Cart → Leave address blank → Place Order |
| `IndexError` | Cart → Delivery: "Rural Relay / Remote SpeedPost" → Place Order |
| `TypeError` | Click Account → "Refresh Membership Privileges" |
| `ValueError` | Cart → Promo: `MALFORMED_MINUS50` → Apply |
| `TimeoutError` | Cart → Payment: "NetBanking (Direct Bank Wire Transfer)" → Place Order |

### 13.6 Run the Remediation Pipeline

```powershell
# Billing scenario (ZeroDivisionError)
python demo.py billing

# Checkout scenario (KeyError)
python demo.py checkout
```

### 13.7 Run the Test Suite

```powershell
# 22 unit tests (must all pass)
python -m pytest test_parser.py test_chroma.py test_llm_client.py test_patcher.py -v

# 6 fault tests (all expected to FAIL — they reproduce bugs)
python -m pytest test_bed/tests/ -v

# Coverage report
python -m pytest test_parser.py test_chroma.py test_patcher.py --cov=services --cov=data --cov-report=term-missing
```

---

## 14. Engineering Decisions & Tradeoffs

### Decision 1: SEARCH/REPLACE Over Line Numbers

**Alternative:** Ask the LLM for a target line number and new content.

**Problem:** Line numbers shift constantly as code evolves. A fix targeting "line 25" may be wrong after 3 other PRs are merged that add lines above it.

**Our approach:** The LLM provides the verbatim string to find. If the code changes so much the string no longer exists, the patcher cleanly rejects the patch with "Search block not found" — rather than silently corrupting the wrong line.

**Inspiration:** Princeton SWE-agent paper (2024) demonstrated this approach for robust autonomous code editing.

---

### Decision 2: 10-Line Source Window Over Full File

**Alternative:** Send the entire source file to the LLM.

**Problem:** Some services could be 500+ lines. Sending full files would consume 5,000-15,000 tokens per call, making the 6,000 TPM Groq rate limit a hard blocker.

**Our approach:** 10 lines before + 10 lines after = ~300 tokens. The failing line is marked with `>>`. For simple bugs (null checks, division guards, bounds clamps), 10 lines of context is sufficient.

**Tradeoff:** The LLM can't see the full function signature or imports. Complex refactors may need more context. Phase 2 will make `padding` configurable.

---

### Decision 3: Distance Gating Over Always-Inject

**Alternative:** Always inject RAG context regardless of match quality.

**Problem:** Injecting irrelevant post-mortems confuses the LLM. A `TimeoutError` in a payment service doesn't benefit from a `MemoryError` post-mortem from a logging service. The LLM might use the wrong remediation pattern.

**Our approach:** `MAX_COSINE_DISTANCE = 0.65` — if the closest match is further than `0.65`, inject "No high-confidence match found" rather than noise. The LLM then relies on its general training knowledge.

---

### Decision 4: AST Pre-flight Over Runtime Sandbox (Phase 1)

**Alternative:** Deploy patch to a Docker sandbox and run `pytest`.

**Problem:** Docker requires infrastructure, adds 30-60 seconds per attempt, and increases complexity significantly.

**Our approach:** `ast.parse()` catches ~80% of LLM errors (syntax mistakes, indentation errors, mismatched brackets) in under 1ms with zero external dependencies.

**Tradeoff:** AST validation is purely syntactic — it won't catch semantic errors (e.g., a fix that introduces a new `NameError`). Phase 2 adds the Docker sandbox for runtime validation.

---

### Decision 5: Structured JSON Logging

**Alternative:** Plain text logs like `ERROR: billing.py line 25 ZeroDivisionError`.

**Problem:** Text logs require custom regex parsing for every monitoring tool. Each tool has different capabilities.

**Our approach:** Every log line is valid JSON with consistent fields: `timestamp`, `level`, `service`, `message`, `correlation_id`, optionally `stack_trace`. Any log aggregator (Datadog, Grafana Loki, CloudWatch) can parse this without configuration.

---

## 15. Roadmap — Phases 2-4

### Phase 2 — Ephemeral Docker Sandbox

```
tests/test_parser.py → PASS ✓
tests/test_chroma.py → PASS ✓
AST pre-flight       → PASS ✓
Docker sandbox       → Run pytest in isolated container → [Phase 2]
```

```python
# Planned API: services/sandbox/run.py
def run_in_sandbox(patch_result: PatchResult, test_command: str = "pytest") -> SandboxResult:
    """
    1. docker run --rm python:3.11-slim
    2. Mount project read-only (:ro)
    3. Copy patched file to /tmp/sandbox/
    4. Run pytest inside container
    5. If exit_code == 0: verified
       If exit_code != 0: feed stderr back to Groq → self-correction loop
    """
```

### Phase 3 — Webhook Ingestion API

```python
# Planned: services/api/main.py
@app.post("/api/v1/triage")
async def triage(payload: CrashPayload):
    """
    Accept crash payloads from:
    - Datadog webhook alerts
    - Prometheus Alertmanager
    - Sentry issue webhooks
    - GitHub Actions CI failure notifications

    Returns: PatchResult with unified diff + confidence score
    """
```

### Phase 4 — GitHub PR Automation

```python
# Planned: services/github/pr_creator.py
from github import Github

def create_remediation_pr(patch_result: PatchResult, diagnostic: DiagnosticResult):
    g    = Github(os.getenv("GITHUB_TOKEN"))
    repo = g.get_repo("husenwalikar/opsmind-ai")

    pr = repo.create_pull(
        title=f"fix(auto): {diagnostic.root_cause_analysis[:60]}",
        body=f"""## OpsMind AI Autonomous Remediation

**Root Cause:** {diagnostic.root_cause_analysis}
**Confidence:** {diagnostic.confidence_score * 100:.0f}%

```diff
{patch_result.diff}
```

*Generated by OpsMind AI — requires human review before merge*
""",
        head=branch_name,
        base="main",
        draft=True    # Always draft — human must review and approve
    )
```

---

## Appendices

### Appendix A — Technology Reference

| Technology | Version | Purpose |
|:---|:---|:---|
| Python | 3.14.7 | Core language |
| FastAPI | 0.115+ | ShopFlow web framework |
| Uvicorn | 0.52+ | ASGI server (production-grade HTTP) |
| Pydantic | 2.x | Request/response validation, domain models |
| SQLAlchemy | 2.x | ORM for product catalog (SQLite fallback) |
| ChromaDB | 0.6+ | Vector database (HNSW cosine similarity index) |
| Groq Python SDK | 0.13+ | Groq LPU API client |
| ONNX | (via ChromaDB) | Local embedding model runtime (no GPU) |
| `difflib` | stdlib | Unified diff generation |
| `ast` | stdlib | Python AST pre-flight syntax validation |
| `os.path.realpath` | stdlib | Canonical path resolution (security) |
| `re` | stdlib | Regular expression matching for parser |
| pytest | 8.x | Test framework |
| Tailwind CSS | CDN | Storefront UI styling |

### Appendix B — Conventional Commits Reference

The repository uses the Conventional Commits specification for all commit messages:

```
<type>(<scope>): <description>

Types:
  feat    New feature (parser, patcher, UI redesign)
  fix     Bug fix (gRPC compat, port hardcoding, UI labels)
  test    Test suite additions or modifications
  docs    Documentation (README, ARCHITECTURE, JOURNAL)
  chore   Tooling, config, .gitignore, dependencies
  refactor Code restructuring without behavior change

Examples:
  feat(parser): add chained exception root cause isolation
  fix(ui): replace hardcoded API base URL with dynamic origin
  test(patcher): add path traversal boundary guard test
  docs(readme): update quick-start instructions for port 8001
```

### Appendix C — Environment Variables

| Variable | Required | Default | Purpose |
|:---|:---|:---|:---|
| `GROQ_API_KEY` | Yes | — | Groq API authentication key |
| `GROQ_MODEL` | No | `openai/gpt-oss-120b` | LLM model for diagnosis |
| `DATABASE_URL` | No | SQLite local file | PostgreSQL connection string |
| `LOG_LEVEL` | No | `INFO` | Python logging level |

### Appendix D — API Endpoint Reference

| Method | Endpoint | Trigger | Expected Fault |
|:---|:---|:---|:---|
| `GET` | `/api/health` | Always | None |
| `GET` | `/api/products` | Always | None |
| `POST` | `/api/checkout` | `coupon_code=FREE100` | `ZeroDivisionError` |
| `POST` | `/api/checkout` | `customer_payload={}` | `KeyError` |
| `POST` | `/api/checkout` | `warehouse_tier=99` | `IndexError` |
| `POST` | `/api/auth/verify` | `session_token=EXPIRED_JWT_XYZ` | `TypeError` |
| `POST` | `/api/promotions/apply` | `coupon_code=MALFORMED_MINUS50` | `ValueError` |
| `POST` | `/api/payment/charge` | `simulate_network_hang=true` | `TimeoutError` |

---

*OpsMind AI — Built with production engineering discipline.*
*Every design decision documented. Every security boundary enforced. Every test justified.*
