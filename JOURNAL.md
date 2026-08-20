# OpsMind AI — Engineering Journal

A day-by-day technical log documenting the design decisions, implementation hurdles, security hardening, and testing milestones of the OpsMind autonomous incident remediation engine.

---

## 2026-08-10 (Day 1) — Repository Initialization & Exploratory Baseline
- Initialized `opsmind-ai` repository structure, Git configuration, and Python 3.14 virtual environment.
- Configured Groq API access and conducted an exploratory inference test (`test_brain.py`) against raw log strings.
- Identified core challenge: raw tracebacks overwhelm LLM context windows and cause hallucinated line numbers unless strictly framed.

## 2026-08-11 (Day 2) — Literature Review & Architectural Foundations
- Surveyed foundational papers on log parsing (Drain, LogRobust), cloud RCA (RCACopilot, LLMtriage), and autonomous code generation (SWE-agent, InterCode).
- Synthesized findings into `docs/literature_survey.md`. Key takeaway from SWE-agent: LLMs fail on raw unified diffs; constraining output to structured `SEARCH`/`REPLACE` blocks drastically improves patch accuracy.
- Established strict security baseline: created `.env.example` template and updated `.gitignore` to prevent leaking provider credentials or vector store binaries.

## 2026-08-12 (Day 3) — Dataset Ingestion & Prototype Cleanup
- Downloaded and ingested the `Linux_2k.log` benchmark dataset from Loghub into `data/` for offline anomaly pattern evaluation.
- Retired the exploratory Day 1 spike script (`test_brain.py`) in preparation for building a modular, production-grade pipeline.

## 2026-08-14 (Day 4) — Patient Microservice Scaffolding ("ShopFlow")
- Architected the standalone target microservice: **ShopFlow** (`test_bed/`), representing a realistic multi-tier e-commerce backend.
- Implemented modular domain services: `billing.py`, `checkout.py`, `gateway.py`, `inventory.py`, `promotions.py`, and `auth.py`.
- Added resilient database layer (`database.py`) with automatic SQLite fallback if a PostgreSQL container is unavailable locally.
- Integrated structured JSON logging via `logger.py` to emulate production cloud observability streams.

## 2026-08-15 (Day 5) — Operational Runbooks & Service Invariants
- Authored ground-truth operational documentation in `test_bed/docs/SERVICE_RUNBOOK.md`.
- Defined clear mathematical and business invariants for each subsystem (e.g. billing ratio handling on 100% discount vouchers, tier overflow clamping in inventory allocation).

## 2026-08-17 (Day 6) — Fault Injection Test Suite
- Constructed 6 deterministic reproducing test fixtures in `test_bed/tests/` modeling realistic microservice failure modes:
  1. `ZeroDivisionError` in billing calculation during 100% coupon markdown.
  2. `KeyError` in guest checkout when optional metadata payload is omitted.
  3. `IndexError` in fulfillment routing when tier index exceeds facility list size.
  4. `ValueError` when marketing promotion rate is configured as negative.
  5. `TimeoutError` when upstream card settlement network hangs.
  6. `TokenExpiredError` when customer session JWT timestamp exceeds expiry window.
- Verified all 6 test cases fail cleanly under faulty conditions.

## 2026-08-18 (Day 7) — Interactive Storefront & DevOps Operator Panel
- Built single-page responsive storefront in `test_bed/app/static/index.html`.
- Implemented collapsible **DevOps ⚙** control panel enabling one-click live fault injection directly from the browser for visual demonstrations.

## 2026-08-20 (Day 8) — Stage 1: Traceback Parser & Frame Filtering
- Implemented `services/agent/parser.py` using bottom-up exception scanning.
- Designed regex-based stack frame extraction that discards standard library, virtual environment, and ASGI framework frames (`uvicorn`, `starlette`).
- Isolated innermost application frame with bounded 10-line source window with pointer indicator (`>>`).
