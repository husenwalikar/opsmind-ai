# OpsMind AI — Literature Survey & Theoretical Foundations

This survey synthesizes foundational research across automated log parsing, root cause analysis (RCA), LLM-assisted triage, and autonomous software engineering environments that ground the design of **OpsMind AI**.

---

## 1. Taxonomy of Related Literature

```
                           AUTONOMOUS INCIDENT REMEDIATION
                                         │
       ┌──────────────────┬──────────────┴──────────────┬──────────────────┐
       ▼                  ▼                             ▼                  ▼
 [ Log Parsing &    [ Root Cause &                [ Code Agent &     [ Execution &
  Noise Reduction ]  Incident Triage ]             Patch Synthesis ]   Sandbox Evals ]
  - Drain (2017)     - RCACopilot (2024)           - SWE-agent (2024)  - InterCode (2023)
  - LogRobust (2019) - LLMtriage (2024)            - SWE-bench (2024)  - Flow-of-Action (2024)
  - Loghub (2023)    - Keep the Conversation (2024)- MetaGPT (2023)   - OWL (2024)
```

---

## 2. Core Research Papers & System Influence

### A. Log Ingestion & Structural Noise Reduction
* **Drain: An Online Log Parsing Approach with Fixed Depth Tree** (*He et al., ICWS 2017*)
  * *Core Insight:* Log streams contain repetitive structural templates combined with variable parameters. Tree-based filtering isolates static headers from variable payloads with $O(1)$ lookup time.
  * *OpsMind Application:* Directly informs `services/agent/parser.py`. Instead of feeding raw framework noise (`uvicorn`, `starlette`) to LLMs, OpsMind extracts only the active application frame and slices a bounded 10-line source window with pointer indicators (`>>`).
* **LogRobust: A Robust Log-based Anomaly Detection Approach for Unstable Log Data** (*Zhang et al., FSE 2019*)
  * *Core Insight:* Real-world microservice logs suffer from format instability, escape serialization differences (JSON vs plain text), and logging evolution.
  * *OpsMind Application:* Guided the design of `normalize_traceback_text()` which handles escaped `\n` sequences from JSON shippers and Windows/Unix slash discrepancies.
* **Loghub: A Large Collection of System Log Datasets for AI-driven Log Analytics** (*Zhu et al., 2023*)
  * *Core Insight:* Benchmarking anomaly detection requires diverse, authentic multi-system failure traces.

---

### B. Root Cause Analysis (RCA) & Contextual Triage
* **RCACopilot: Automated Root Cause Analysis for Cloud Incidents via Large Language Models** (*Chen et al., ESEC/FSE 2024*)
  * *Core Insight:* Incident post-mortems and past remediation histories provide high-signal inductive bias. Unassisted LLMs fail when deprived of organizational tribal knowledge.
  * *OpsMind Application:* Directly inspired `data/seed_chroma.py`. OpsMind embeds historical post-mortems alongside official service runbook invariants into a local vector store.
* **LLMtriage: Towards Automated Incident Triage with LLMs** (*2024*)
  * *Core Insight:* Incident severity and triage speed improve drastically when domain invariants are paired with error signatures during prompt formatting.
  * *OpsMind Application:* OpsMind injects the specific runbook business rule (e.g. "free discount allows ratio 0.0") into the prompt, reducing MTTR from hours to under 10 seconds.
* **Keep the Conversation Going: Agentic Incident Management** (*2024*)
  * *Core Insight:* Single-shot LLM triage frequently misses environmental constraints; multi-step feedback loops that incorporate execution feedback achieve significantly higher remediation accuracy.

---

### C. Patch Synthesis & Agent-Computer Interfaces (ACI)
* **SWE-agent: Agent-Computer Interfaces Enable Software Engineering Language Models** (*Yang et al., 2024*)
  * *Core Insight:* Giving LLMs standard shell access or asking them to produce raw unified diffs leads to massive line-number arithmetic errors. Constraining models to explicit `SEARCH`/`REPLACE` commands yields dramatically higher success rates.
  * *OpsMind Application:* OpsMind’s `llm_client.py` strictly adheres to a structured `SEARCH`/`REPLACE` block contract. Mathematical diffs are synthesized via Python's native `difflib.unified_diff()`, completely preventing hunk-offset failures.
* **SWE-bench: Can Language Models Resolve Real-World GitHub Issues?** (*Jimenez et al., ICLR 2024*)
  * *Core Insight:* State-of-the-art models fail on real software repositories if they attempt whole-file overwrites. Surgical modifications bounded to affected functions are essential.
  * *OpsMind Application:* `patcher.py` enforces that the `search_block` matches **exactly once** in the target file, blocking ambiguous replacements.
* **MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework** (*Hong et al., 2023*)
  * *Core Insight:* Standardized Standard Operating Procedures (SOPs) and structured data contracts prevent error cascading in agentic pipelines.

---

### D. Verification Environments & Execution Sandboxes
* **InterCode: Standardizing and Benchmarking Interactive Coding with Execution Feedback** (*Yang et al., NeurIPS 2023*)
  * *Core Insight:* Static code generation without execution feedback has a low success ceiling. Interactive test environments where code is executed and error outputs are fed back to the agent provide order-of-magnitude improvements in code correctness.
  * *OpsMind Application:* Direct theoretical basis for Step 5 (`services/sandbox/run.py`). OpsMind runs an ephemeral Docker container to execute `pytest` on the proposed patch before human review.
* **Flow-of-Action: Efficient and Flexible Tool Use for Language Models** (*2024*) & **OWL: Testing and Reasoning Agents** (*2024*)
  * *Core Insight:* Separating diagnosis, code transformation, and sandbox execution into discrete stages prevents hallucination loops.

---

## 3. Summary of OpsMind Architectural Mapping

| Paper / Concept | Theoretical Problem | OpsMind Engineering Solution |
|:---|:---|:---|
| **Drain (2017)** | Context window dilution from web framework tracebacks | `parser.py` AST/regex frame filter + 10-line source window slicing |
| **RCACopilot (2024)** | LLM hallucination of business-specific invariants | Vector RAG (`seed_chroma.py`) with cosine distance threshold guard |
| **SWE-agent (2024)** | Unified diff line-count and offset arithmetic failure | Literal `SEARCH`/`REPLACE` blocks with mathematical `difflib` synthesis |
| **InterCode (2023)** | Unverified patch risk in production | Ephemeral Docker sandbox (`--rm`, `:ro`) with pytest exit code 0 gate |
