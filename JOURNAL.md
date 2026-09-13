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

## 2026-08-21 (Day 9) — Parser Hardening & Unit Test Harness
- Hardened `parser.py` against path traversal attacks: enforced `os.path.commonpath` checks to block malicious tracebacks attempting to access arbitrary host files (e.g. `/etc/passwd`).
- Implemented chained exception unwinding (`raise ... from ...`) to isolate the root cause rather than outer wrapper frames.
- Created `test_parser.py` with 7 comprehensive unit tests (all passing).

## 2026-08-24 (Day 10) — Stage 2: ChromaDB Vector Store & Incident Seeding
- Implemented `data/seed_chroma.py` with local ONNX embeddings (`all-MiniLM-L6-v2`) eliminating external API dependency for embeddings.
- Structured and seeded `data/historical_incidents.json` containing 6 historical incident post-mortems and 6 service runbook invariants.

## 2026-08-25 (Day 11) — RAG Distance Gating & Hallucination Suppression
- Added cosine distance cutoff (`MAX_COSINE_DISTANCE = 0.65`) in `seed_chroma.py`.
- Queries exceeding distance threshold return `is_confident = False`, preventing irrelevant runbooks from polluting LLM diagnostic prompts.
- Created `test_chroma.py` validating retrieval precision and distance thresholding (5 tests passing).

## 2026-08-28 (Day 12) — Stage 3: Groq LPU Diagnostic Client
- Implemented `services/agent/llm_client.py` integrating Groq high-speed LPU inference with strict JSON schema output (`openai/gpt-oss-120b`).
- Optimized prompt structure: combined bounded 10-line source context with vector runbook snippet to fit within ~720 tokens per call (comfortably within 6,000 TPM limit).

## 2026-09-02 (Day 13) — Stage 4: In-Memory AST Validator & Unified Patcher
- Implemented `services/agent/patcher.py` enforcing strict safety invariants:
  - Exact-match validation: `search_block` must occur exactly once in target file.
  - Python AST syntax pre-flight check: validates modified code via `ast.parse()` in-memory before saving or testing.
  - Mathematical unified diff synthesis using `difflib.unified_diff`.
  - Zero direct file mutation: all patch operations execute purely in memory.

## 2026-09-05 (Day 14) — Engine Test Suite Completion
- Created `test_llm_client.py` (4 tests) validating JSON formatting, prompt construction, and mock inference.
- Created `test_patcher.py` (6 tests) verifying clean replacements, multi-match rejections, AST syntax error trapping, and diff output.
- Verified all 22 OpsMind unit tests pass in under 12 seconds.

## 2026-09-09 (Day 15) — End-to-End Orchestrator Pipeline
- Built `demo.py`: interactive CLI pipeline orchestrating Stage 1 (parser) -> Stage 2 (vector RAG) -> Stage 3 (Groq LLM) -> Stage 4 (AST patcher).
- Added Rich terminal formatting with step-by-step progress spinners, color-coded unified diff rendering, and timing metrics.

## 2026-09-12 (Day 16) — Security Threat Model & Architectural Documentation
- Authored `docs/SECURITY_MODEL.md` detailing STRIDE threat analysis, AST execution guards, and path boundary enforcement.
- Authored `docs/ARCHITECTURE.md` documenting the bounded token budget, data contracts, and self-correction feedback loop.
- Authored `docs/DEMO_GUIDE.md` outlining a 3-act live presentation script.

## 2026-09-13 (Day 17) — Final Hardening, Verification & Clean Packaging
- Executed full test suite: 22/22 unit tests passing.
- Verified ShopFlow fault injection test bed running stably on port 8000.
- Relocated exploratory prompt blueprints and research PDFs to external meta archive.
- Updated `README.md` and `ROADMAP.md` for production proposal delivery.