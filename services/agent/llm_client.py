"""
Diagnostic Reasoning and Patch Synthesis Agent.
Integrates Groq API with RAG context to produce surgical Search/Replace patches.
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional
from dotenv import load_dotenv
from groq import Groq

from services.agent.parser import CrashLocation

load_dotenv()


@dataclass
class DiagnosticResult:
    root_cause_analysis: str
    confidence_score: float
    target_file: str
    search_block: str
    replace_block: str
    explanation: str


SYSTEM_PROMPT = """You are a Principal Site Reliability Engineer and Senior Systems Architect.
Your task is to analyze application crash logs, review relevant runbook business invariants, and synthesize a surgical code fix.

CRITICAL OPERATIONAL RULES:
1. Produce an exact SEARCH block containing the existing buggy lines. The SEARCH block must match character-for-character, including indentation.
2. Produce an exact REPLACE block containing the defensive bug fix.
3. Obey the Service Runbook Invariant strictly. Do not introduce breaking behavioral side effects.
4. Keep edits surgical: do NOT rewrite entire functions or classes. Only modify the minimum lines needed to prevent the failure.
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


def format_diagnostic_prompt(
    crash_location: CrashLocation,
    rag_context: Dict[str, Any],
    previous_error: Optional[str] = None,
) -> str:
    """
    Constructs the diagnostic prompt by combining crash coordinates,
    source context window, and retrieved RAG invariants.
    """
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
        crash_location.source_context,
        "```",
        "",
        "RETRIEVED RUNBOOK & REMEDIATION KNOWLEDGE:",
        rag_context.get("rag_prompt_snippet", "No runbook context available."),
    ]

    if previous_error:
        prompt_parts.extend([
            "",
            "PREVIOUS PATCH VALIDATION FAILURE:",
            "The previous patch failed sandbox testing with this error. Correct your approach:",
            "```text",
            previous_error.strip(),
            "```",
        ])

    prompt_parts.extend([
        "",
        "Synthesize the fix now. Remember: The SEARCH block must exist verbatim in the source file."
    ])

    return "\n".join(prompt_parts)


def clean_json_response(content: str) -> Dict[str, Any]:
    """
    Strips markdown code fences if present and parses raw string into a JSON dictionary.
    """
    clean_text = content.strip()
    if clean_text.startswith("```"):
        clean_text = re.sub(r"^```(?:json)?\n?", "", clean_text)
        clean_text = re.sub(r"\n?```$", "", clean_text)
    return json.loads(clean_text)


def diagnose_and_generate_patch(
    crash_location: CrashLocation,
    rag_context: Dict[str, Any],
    previous_error: Optional[str] = None,
    client: Optional[Groq] = None,
) -> DiagnosticResult:
    """
    Invokes the LLM to analyze the crash and generate a structured Search/Replace patch.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not configured in the environment.")

    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    groq_client = client or Groq(api_key=api_key)

    user_prompt = format_diagnostic_prompt(crash_location, rag_context, previous_error)

    response = groq_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_tokens=1000,
    )

    raw_content = response.choices[0].message.content or "{}"
    parsed = clean_json_response(raw_content)

    return DiagnosticResult(
        root_cause_analysis=parsed.get("root_cause_analysis", "Root cause identified."),
        confidence_score=float(parsed.get("confidence_score", 0.9)),
        target_file=parsed.get("target_file", crash_location.file_path),
        search_block=parsed.get("search_block", "").strip("\r\n"),
        replace_block=parsed.get("replace_block", "").strip("\r\n"),
        explanation=parsed.get("explanation", ""),
    )
