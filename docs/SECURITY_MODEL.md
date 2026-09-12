# OpsMind AI — Security Architecture & Threat Model

This document establishes the security boundaries, threat mitigations, and safety invariants implemented within the OpsMind AI autonomous incident remediation engine.

---

## 1. Core Security Principles

Autonomous software remediation operates with elevated privileges over source code and execution environments. OpsMind is engineered under five foundational security guarantees:

1. **Zero Direct Host Mutation:** The engine never applies patches directly to the host filesystem. All transformations are synthesized in-memory and evaluated in ephemeral sandboxes.
2. **Air-Gap Observability:** Target microservices operate with zero awareness of OpsMind. Ingestion is strictly passive and out-of-band via stdout/stderr logs.
3. **Workspace Path Containment:** All file paths derived from external or untrusted log payloads are strictly confined within verified workspace boundaries.
4. **AST Pre-flight Gate:** No synthesized code reaches a compiler, runtime, or sandbox container unless it compiles as valid Python syntax.
5. **Proposal-Only Deployment Policy:** OpsMind generates mathematically verified diff proposals; human-in-the-loop (HITL) approval is strictly required before any code merges into production.

---

## 2. Threat Analysis & Defensive Controls (STRIDE)

### Threat 1: Arbitrary File Read via Log Poisoning (Information Disclosure)
* **Attack Vector:** An attacker deliberately crafts or triggers a traceback referencing sensitive host files:
  ```text
  File "/etc/shadow", line 1
  File "C:/Users/Administrator/.ssh/id_rsa", line 1
  ```
* **Vulnerability:** Unsanitized file opening allows the parser to read confidential host files and inject them into external LLM prompts.
* **OpsMind Defensive Control:**
  * Strict boundary validation via `os.path.realpath()` and `os.path.commonpath()`.
  * Every target path must share a common root with the designated `ALLOWED_WORKSPACE_ROOT`.
  * Path traversal sequences (`../`), cross-drive references, and symlink escapes are rejected before any filesystem read occurs.
  * Violations immediately abort context extraction and emit a `# Security Guard: Access denied` sentinel.

---

### Threat 2: Syntactic & Semantic Hallucination Regressions (Denial of Service)
* **Attack Vector:** LLMs frequently produce code with syntax errors (e.g. unclosed parentheses, broken indentation) or ambiguous edits that match multiple locations across a file.
* **Vulnerability:** Applying broken patches causes immediate compilation failure or corrupts multiple functions across the target service.
* **OpsMind Defensive Control:**
  * **Unambiguity Invariant:** The `search_block` must occur **exactly once** in the target file (`count == 1`). If the block matches 0 times or >1 times, the patch is rejected immediately.
  * **AST Compilation Pre-flight:** The patched source is evaluated in-memory using Python's native `ast.parse()`. Any syntax or indentation error halts the pipeline before container execution.
  * **Mathematical Diff Synthesis:** The unified diff is computed deterministically via `difflib.unified_diff()`. The LLM is never allowed to author diff headers or line offsets directly.

---

### Threat 3: Runbook Misguidance & Invariant Hallucination (Integrity Violation)
* **Attack Vector:** A novel or unfamiliar exception is queried against the vector database. Standard vector stores return the nearest vector regardless of actual similarity.
* **Vulnerability:** The engine authoritatively forces an unrelated runbook invariant (e.g. applying a division-by-zero rule to a database connection timeout).
* **OpsMind Defensive Control:**
  * Cosine distance threshold enforcement (`MAX_COSINE_DISTANCE = 0.65`).
  * If the nearest match exceeds the distance ceiling, the result is flagged as low-confidence (`is_confident = False`).
  * The diagnostic prompt explicitly indicates that no matching invariant was found, forcing the model to rely on safe, general defensive programming rather than hallucinated business rules.

---

### Threat 4: Host Execution Escape & Side-Channel Tampering (Elevation of Privilege)
* **Attack Vector:** A patch executes malicious setup commands or tampers with the local testing environment during verification.
* **Vulnerability:** Running test suites directly on the host machine exposes the host to destructive side effects.
* **OpsMind Defensive Control:**
  * All verification runs inside an isolated Docker container (`docker run --rm`).
  * Host project files are mounted strictly as **read-only (`:ro`)**.
  * The container copies the workspace to `/tmp/sandbox/`, applies the patch inside the isolated scratchpad, and executes tests.
  * On completion or failure, the container is destroyed immediately, leaving zero residual changes on the host.

---

### Threat 5: Supply Chain & Credential Leakage
* **Defensive Control:**
  * Credential isolation: `.env` is explicitly ignored by version control, and a template is provided via `.env.example`.
  * Local embedding inference: ChromaDB uses an embedded ONNX runtime (`all-MiniLM-L6-v2`) locally on CPU. Embeddings are generated offline with zero network egress.
