# OpsMind AI — Engineering Roadmap

This document outlines the phased milestone progression of the OpsMind autonomous incident remediation engine.

---

## 🧭 Milestone Summary

```
   PHASE 1: Core Engine             PHASE 2: Verification API         PHASE 3: Enterprise Fleet
   (Completed - Sep 2026)          (Current - Sep 2026)              (Upcoming - Sem 4)
┌───────────────────────────┐   ┌───────────────────────────┐   ┌───────────────────────────┐
│ • Parser & Log Isolation  │   │ • Ephemeral Docker Sandbox│   │ • Automated GitHub PR Bot │
│ • Vector RAG (ChromaDB)   │──►│ • Pytest Exit Code 0 Gate │──►│ • Kafka Stream Ingestion  │
│ • Groq LPU Search/Replace │   │ • FastAPI /triage API     │   │ • PagerDuty & Slack Bot   │
│ • AST Guard & Diff Engine │   │ • Out-of-band Log Tailing │   │ • Multi-Repo Support      │
│ • ShopFlow Test Bed (6x)  │   │ • Retry Feedback Loop (3x)│   │ • Human-in-the-Loop UI    │
└───────────────────────────┘   └───────────────────────────┘   └───────────────────────────┘
```

---

## Phase 1: Core Autonomous Reasoning Engine (Completed ✅)

- [x] **Step 1: Traceback Coordinate Isolation (`services/agent/parser.py`)**
  - Unescape JSON log payloads and normalize Windows/Unix path separators.
  - Filter third-party runtime pollution (`site-packages`, `starlette`, `uvicorn`).
  - Extract exact file path, 1-indexed line number, and enclosing function.
  - Slices a bounded 10-line source window with failure line pointers (`>>`).
  - **Hardened:** Enforced workspace path containment guard preventing arbitrary file traversal.
  - **Hardened:** Isolated root-cause traceback blocks in chained exceptions (`raise ... from ...`).

- [x] **Step 2: Vector RAG Knowledge Ingestion (`data/seed_chroma.py`)**
  - Seeded ChromaDB persistent vector store (`data/chroma_db/`).
  - Parsed historical post-mortems and service runbook invariants.
  - Embedded via local ONNX `all-MiniLM-L6-v2` (zero external API tokens consumed).
  - **Hardened:** Implemented `MAX_COSINE_DISTANCE = 0.65` threshold guard to eliminate hallucinated context on unknown errors.
  - **Hardened:** Aligned service file paths to actual repository structure.

- [x] **Step 3: Diagnostic Reasoning & Search/Replace Synthesis (`services/agent/llm_client.py`)**
  - Integrated Groq LPU cloud inference (`openai/gpt-oss-120b`).
  - Deterministic temperature (`0.1`) and strict JSON schema enforcement.
  - Structured `SEARCH` and `REPLACE` block contracts.
  - Built-in error feedback loop for iterative retries.

- [x] **Step 4: AST Pre-flight Guard & Mathematical Diff Synthesis (`services/agent/patcher.py`)**
  - Unambiguity check: `search_block` must match exactly once in the target file.
  - In-memory patch application guaranteeing zero mutation of host files.
  - AST pre-flight validation (`ast.parse`) blocking syntax regressions before container launch.
  - Mathematical unified diff generation using Python's `difflib`.

- [x] **Target Patient: ShopFlow E-Commerce Microservice (`test_bed/`)**
  - Clean FastAPI microservice with catalog database (PostgreSQL / SQLite fallback).
  - 6 authentic, production-grade failure scenarios (Billing, Checkout, Inventory, Auth, Promotions, Gateway).
  - Tailwind storefront with collapsible **`DevOps ⚙`** traffic and failure control bar.
  - Zero coupling between ShopFlow and OpsMind.

---

## Phase 2: Automated Sandbox & Triage Orchestrator (Current Sprint ⏳)

- [ ] **Step 5: Ephemeral Docker Sandbox (`services/sandbox/run.py`)**
  - Mount host repository as read-only (`:ro`).
  - Copy workspace to `/tmp/sandbox/` inside the container.
  - Apply the in-memory patch to the isolated scratchpad.
  - Execute test suite (`pytest`) inside the container.
  - Enforce exit code 0 gate:
    - **Exit 0:** Patch verified effective with zero regression.
    - **Exit Non-Zero:** Capture failure stderr and trigger self-correction retry in Step 3 (ceiling: 3 attempts).
  - Ephemeral container cleanup (`--rm`) leaving zero persistent state.

- [ ] **Step 6: FastAPI Triage Controller (`services/api/main.py`)**
  - Expose `/api/v1/triage` endpoint receiving raw crash logs.
  - Wire Steps 1 through 5 into an end-to-end self-healing pipeline.
  - Return structured incident reports:
    ```json
    {
      "incident_id": "INC-AUTO-8921",
      "status": "VERIFIED_PATCH_READY",
      "target_file": "test_bed/app/services/billing.py",
      "root_cause": "Division by zero on 100% discount",
      "diff": "--- a/... +++ b/...",
      "sandbox_result": "6 passed in 0.18s",
      "attempts": 1
    }
    ```

- [ ] **Out-of-Band Log Watcher Daemon**
  - Tail application stdout/stderr logs or inspect Docker container event stream.
  - Automatically dispatch unhandled 500 error logs to `/api/v1/triage`.

---

## Phase 3: Production Hardening & Fleet Governance (Semester 4 🔮)

- [ ] **Automated GitHub Pull Request Bot**
  - Automatically create a git branch `opsmind/fix-<incident-id>`.
  - Commit verified diff and open a Pull Request with detailed post-mortem, runbook citations, and sandbox test proofs.
  - Enforce Human-in-the-Loop (HITL) approval policy.

- [ ] **Kafka Distributed Log Streaming**
  - Ingest high-volume application logs across distributed Kubernetes pods via Apache Kafka.
  - Deduplicate recurring exceptions via fingerprint clustering.

- [ ] **Incident Response Integrations**
  - PagerDuty incident annotation with suggested diff and confidence scores.
  - Slack Bot providing interactive `[Approve Patch]` and `[Reject]` controls for on-call SREs.
