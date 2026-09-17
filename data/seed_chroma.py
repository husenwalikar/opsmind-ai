"""
ChromaDB Vector Seeder and Context Retrieval Service.
Provides ingestion for historical post-mortems and service runbook invariants,
and semantic query interfaces with similarity threshold guards.
"""

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import warnings

# Filter upstream OpenTelemetry/gRPC version mismatch and deprecation notices
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Resilient fallback for environments restricting compiled gRPC C-extensions
try:
    import grpc  # noqa: F401
except ImportError:
    mock_grpc = MagicMock()
    mock_grpc.__version__ = "1.65.0"
    sys.modules["grpc"] = mock_grpc
    sys.modules["grpc._compression"] = MagicMock()
    sys.modules["grpc._cython"] = MagicMock()

import chromadb

# Maximum permissible cosine distance (1 - cosine_similarity).
# Matches with distance > 0.65 represent low-confidence / irrelevant noise.
MAX_COSINE_DISTANCE = 0.65


def parse_runbook_markdown(runbook_path: str) -> List[Dict[str, str]]:
    """
    Parses SERVICE_RUNBOOK.md into structured service specifications.
    Extracts service name, target source file, contract, domain rule, and invariant.
    """
    if not os.path.exists(runbook_path):
        raise FileNotFoundError(f"Runbook file not found at: {runbook_path}")

    with open(runbook_path, "r", encoding="utf-8") as f:
        content = f.read()

    sections = re.split(r"(?m)^##\s+\d+\.\s+", content)
    parsed_services: List[Dict[str, str]] = []

    for block in sections[1:]:
        header_match = re.match(r"^([^\n\(`]+)(?:\s*\(`?([^`\)\n]+)`?\))?", block.strip())
        if not header_match:
            continue

        service_name = header_match.group(1).strip()
        file_target = (header_match.group(2) or "").strip()

        contract_match = re.search(r"\*\s*\*\*Contract:\*\*\s*(.+)", block)
        domain_rule_match = re.search(r"\*\s*\*\*Domain Rule:\*\*\s*(.+)", block)
        invariant_match = re.search(r"\*\s*\*\*Invariant:\*\*\s*(.+)", block)

        parsed_services.append({
            "service_name": service_name,
            "file_target": file_target,
            "contract": contract_match.group(1).strip() if contract_match else "",
            "domain_rule": domain_rule_match.group(1).strip() if domain_rule_match else "",
            "invariant": invariant_match.group(1).strip() if invariant_match else "",
        })

    return parsed_services


def seed_vector_db(
    incidents_path: str = "data/historical_incidents.json",
    runbook_path: str = "test_bed/docs/SERVICE_RUNBOOK.md",
    persist_dir: str = "data/chroma_db",
) -> Dict[str, int]:
    """
    Populates ChromaDB with historical incidents and service invariants.
    Uses upsert operations to ensure idempotent execution.
    """
    if not os.path.exists(incidents_path):
        raise FileNotFoundError(f"Incidents file not found at: {incidents_path}")

    os.makedirs(persist_dir, exist_ok=True)
    client = chromadb.PersistentClient(path=persist_dir)

    # 1. Seed Historical Incidents
    incidents_col = client.get_or_create_collection(
        name="historical_incidents",
        metadata={"hnsw:space": "cosine"},
    )

    with open(incidents_path, "r", encoding="utf-8") as f:
        incidents_data = json.load(f)

    inc_ids: List[str] = []
    inc_docs: List[str] = []
    inc_metas: List[Dict[str, str]] = []

    for inc in incidents_data:
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
            "error_type": inc.get("error_type", ""),
            "service": inc.get("service_context", ""),
        })

    if inc_ids:
        incidents_col.upsert(ids=inc_ids, documents=inc_docs, metadatas=inc_metas)

    # 2. Seed Service Runbook Invariants
    runbook_col = client.get_or_create_collection(
        name="service_runbooks",
        metadata={"hnsw:space": "cosine"},
    )

    runbook_entries = parse_runbook_markdown(runbook_path)
    rb_ids: List[str] = []
    rb_docs: List[str] = []
    rb_metas: List[Dict[str, str]] = []

    for entry in runbook_entries:
        slug = re.sub(r"[^a-zA-Z0-9_-]", "", entry["service_name"].lower().replace(" ", "-"))
        doc = (
            f"Service: {entry['service_name']} ({entry['file_target']})\n"
            f"Contract: {entry['contract']}\n"
            f"Domain Rule: {entry['domain_rule']}\n"
            f"Invariant & Remediation: {entry['invariant']}"
        )
        rb_ids.append(f"rb-{slug}")
        rb_docs.append(doc)
        rb_metas.append({
            "service_name": entry["service_name"],
            "file_target": entry["file_target"],
        })

    if rb_ids:
        runbook_col.upsert(ids=rb_ids, documents=rb_docs, metadatas=rb_metas)

    return {
        "incidents": incidents_col.count(),
        "runbooks": runbook_col.count(),
    }


def query_incident_context(
    error_type: str,
    error_message: str,
    source_context: str = "",
    persist_dir: str = "data/chroma_db",
    n_results: int = 1,
    distance_threshold: float = MAX_COSINE_DISTANCE,
) -> Dict[str, Any]:
    """
    Performs semantic vector search across incidents and service invariants.
    Applies distance threshold filtering to avoid injecting irrelevant context.
    """
    if not os.path.exists(persist_dir):
        return {
            "incident": {"id": "", "content": "", "metadata": {}, "distance": 1.0, "is_confident": False},
            "runbook": {"id": "", "content": "", "metadata": {}, "distance": 1.0, "is_confident": False},
            "rag_prompt_snippet": "",
        }

    client = chromadb.PersistentClient(path=persist_dir)
    query_text = f"{error_type}: {error_message}\n{source_context}".strip()

    # Query Incidents
    try:
        incidents_col = client.get_collection(name="historical_incidents")
        inc_res = incidents_col.query(
            query_texts=[query_text],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        inc_dist = inc_res["distances"][0][0] if inc_res.get("distances") and inc_res["distances"][0] else 1.0
        inc_confident = inc_dist <= distance_threshold

        inc_id = inc_res["ids"][0][0] if (inc_confident and inc_res.get("ids") and inc_res["ids"][0]) else ""
        inc_doc = inc_res["documents"][0][0] if (inc_confident and inc_res.get("documents") and inc_res["documents"][0]) else ""
        inc_meta = inc_res["metadatas"][0][0] if (inc_confident and inc_res.get("metadatas") and inc_res["metadatas"][0]) else {}
    except Exception:
        inc_id, inc_doc, inc_meta, inc_dist, inc_confident = "", "", {}, 1.0, False

    # Query Runbooks
    try:
        runbook_col = client.get_collection(name="service_runbooks")
        rb_res = runbook_col.query(
            query_texts=[query_text],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        rb_dist = rb_res["distances"][0][0] if rb_res.get("distances") and rb_res["distances"][0] else 1.0
        rb_confident = rb_dist <= distance_threshold

        rb_id = rb_res["ids"][0][0] if (rb_confident and rb_res.get("ids") and rb_res["ids"][0]) else ""
        rb_doc = rb_res["documents"][0][0] if (rb_confident and rb_res.get("documents") and rb_res["documents"][0]) else ""
        rb_meta = rb_res["metadatas"][0][0] if (rb_confident and rb_res.get("metadatas") and rb_res["metadatas"][0]) else {}
    except Exception:
        rb_id, rb_doc, rb_meta, rb_dist, rb_confident = "", "", {}, 1.0, False

    # Build prompt block
    prompt_sections = []
    if inc_doc:
        prompt_sections.append(f"### Historical Incident Reference\n{inc_doc}")
    else:
        prompt_sections.append("### Historical Incident Reference\nNo high-confidence historical incident match found.")

    if rb_doc:
        prompt_sections.append(f"### Service Runbook Invariant\n{rb_doc}")
    else:
        prompt_sections.append("### Service Runbook Invariant\nNo domain runbook invariant defined for this failure. Rely on standard defensive programming.")

    rag_prompt_snippet = "\n\n".join(prompt_sections)

    return {
        "incident": {
            "id": inc_id,
            "content": inc_doc,
            "metadata": inc_meta,
            "distance": inc_dist,
            "is_confident": inc_confident,
        },
        "runbook": {
            "id": rb_id,
            "content": rb_doc,
            "metadata": rb_meta,
            "distance": rb_dist,
            "is_confident": rb_confident,
        },
        "rag_prompt_snippet": rag_prompt_snippet,
    }


if __name__ == "__main__":
    print("[*] Re-indexing ChromaDB vector storage with updated runbook paths...")
    counts = seed_vector_db()
    print(f"[+] Seeding complete. Incidents indexed: {counts['incidents']}, Runbooks indexed: {counts['runbooks']}")
