# OpsMind AI — System Architecture Specification

This document provides a comprehensive technical breakdown of the OpsMind AI autonomous incident remediation architecture, detailing component interactions, data contracts, and algorithmic invariants.

---

## 1. High-Level System Topology

OpsMind implements an out-of-band feedback loop that monitors, diagnoses, and verifies software repairs without impacting target service availability.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        TARGET ENVIRONMENT (ShopFlow)                    │
│                                                                         │
│   FastAPI Web Server ───► Business Logic Services ───► PostgreSQL/DB    │
│            │                                                            │
│            ▼                                                            │
│     Unhandled 500 Crash (stderr / stdout JSON telemetry)                │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ (Out-of-band ingestion)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         OPSMIND AI CORE ENGINE                          │
│                                                                         │
│  ┌─────────────────────────┐       ┌─────────────────────────┐          │
│  │ 1. Traceback Isolator   │       │ 2. Vector RAG Engine    │          │
│  │    (services/parser.py) │       │    (data/seed_chroma.py)│          │
│  │    - Boundary guard     │       │    - Local ONNX embed   │          │
│  │    - Framework filter   │       │    - Distance threshold │          │
│  │    - Source window slice│       │    - Runbook invariants │          │
│  └────────────┬────────────┘       └────────────┬────────────┘          │
│               │                                 │                       │
│               └────────────────┬────────────────┘                       │
│                                ▼                                        │
│               ┌─────────────────────────────────┐                       │
│               │ 3. Diagnostic & Patch Agent     │                       │
│               │    (services/llm_client.py)     │                       │
│               │    - Groq LPU (gpt-oss-120b)    │                       │
│               │    - Deterministic temp (0.1)   │                       │
│               │    - Search/Replace JSON schema │                       │
│               └────────────────┬────────────────┘                       │
│                                │                                        │
│                                ▼                                        │
│               ┌─────────────────────────────────┐                       │
│               │ 4. AST Guard & Patcher          │                       │
│               │    (services/patcher.py)        │                       │
│               │    - Unambiguity check (count=1)│                       │
│               │    - In-memory ast.parse() gate │                       │
│               │    - difflib unified diff synth │                       │
│               └────────────────┬────────────────┘                       │
│                                │                                        │
│                                ▼                                        │
│               ┌─────────────────────────────────┐                       │
│               │ 5. Ephemeral Docker Sandbox     │ ◄── [Retry Loop <=3x] │
│               │    (services/sandbox/run.py)    │                       │
│               │    - Read-only volume mount     │                       │
│               │    - Containerized pytest run   │                       │
│               │    - Exit code 0 verification   │                       │
│               └────────────────┬────────────────┘                       │
│                                │                                        │
│                                ▼                                        │
│   [ Verified Patch Proposal: Diff Artifact + Incident Post-Mortem ]     │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Mathematical Token Budget Analysis

A primary operational constraint in production LLM triage is the provider rate-limit ceiling. For example, Groq's free tier imposes a **6,000 Tokens Per Minute (TPM)** limit.

### Naive Implementation (Unbounded Context):
* Full Repository Runbook: ~2,500 tokens
* 50 Historical Post-Mortem Records: ~6,000 tokens
* Full Target Source File: ~1,200 tokens
* System & User Prompt: ~500 tokens
* **Total Per Call:** **~10,200 tokens** (Immediately breaches TPM limit on Attempt 1; zero retry budget).

### OpsMind Bounded Context Architecture:
* Filtered 10-line Source Window: ~150 tokens
* Top-1 Semantic Incident Match: ~120 tokens
* Top-1 Runbook Invariant Match: ~100 tokens
* System Prompt & Schema Instructions: ~350 tokens
* **Total Per Call:** **~720 tokens**
* **Operational Implication:** OpsMind can execute **up to 8 self-correction retry cycles per minute** within the free tier ceiling, enabling robust iterative repair without rate limit exhaustion.

---

## 3. Data Contracts Across Pipeline Stages

### Stage 1: Traceback Coordinate Isolation (`CrashLocation`)
```python
@dataclass
class CrashLocation:
    file_path: str        # e.g., "test_bed/app/services/billing.py"
    line_number: int      # 1-indexed target line (e.g., 25)
    function_name: str    # Enclosing function (e.g., "calculate_order_summary")
    error_type: str       # e.g., "ZeroDivisionError"
    error_message: str    # e.g., "float division by zero"
    source_context: str   # Bounded 10-line slice with visual line pointers (">>")
```

### Stage 2: Vector RAG Retrieval (`QueryContextResult`)
```python
{
    "incident": {
        "id": "inc-INC-2024-041",
        "content": "Error Type: ZeroDivisionError\nRemediation: Guard denominator == 0...",
        "distance": 0.25,
        "is_confident": True
    },
    "runbook": {
        "id": "rb-billing-service",
        "content": "Service: Billing Service\nInvariant: When discount == total, return 0.0...",
        "distance": 0.37,
        "is_confident": True
    },
    "rag_prompt_snippet": "### Historical Incident Reference\n...\n### Service Runbook Invariant\n..."
}
```

### Stage 3: LLM Diagnostic Synthesis (`DiagnosticResult`)
```python
@dataclass
class DiagnosticResult:
    root_cause_analysis: str  # Technical diagnosis of the failure condition
    confidence_score: float   # Self-assessed confidence between 0.0 and 1.0
    target_file: str          # Verified relative target file path
    search_block: str         # Exact verbatim lines from source code
    replace_block: str        # Exact defensive replacement code
    explanation: str          # Human-readable rationale for the patch
```

### Stage 4: Patch Synthesis & AST Compilation (`PatchResult`)
```python
@dataclass
class PatchResult:
    success: bool             # True only if unambiguity and AST compilation pass
    target_file: str          # Path to target source file
    original_content: str     # Raw source code before patch
    patched_content: str      # In-memory patched source code
    diff: str                 # Standard unified diff representation
    error: Optional[str]      # Detailed error if validation halted
```

---

## 4. Self-Correction & Error Feedback Protocol

If sandbox execution in Step 5 fails (exit code $\neq$ 0), OpsMind does not abort or guess blindly. It feeds the failure context back to the diagnostic agent:

1. **Attempt 1:** LLM generates initial patch based on crash log + RAG invariants.
2. **Sandbox Run 1:** Tests fail (e.g., `AssertionError: expected float, got None`).
3. **Feedback Packaging:** The failed diff and verbatim pytest stderr are injected into the retry prompt.
4. **Attempt 2:** The model inspects its own prior mistake and synthesizes a revised patch.
5. **Ceiling Guard:** If the patch fails after **3 iterations**, the incident is tagged `ESCALATED_TO_HUMAN` and halts to avoid infinite token consumption.
