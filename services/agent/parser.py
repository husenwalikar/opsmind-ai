"""
Crash Log & Source Context Parser.
Extracts failure coordinates, isolates root cause frames from chained exceptions,
and safely retrieves bounded source code context within allowed workspace boundaries.
"""

import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class CrashLocation:
    file_path: str = ""
    line_number: int = 0
    function_name: str = "<module>"
    error_type: str = ""
    error_message: str = ""
    source_context: str = ""


FRAME_REGEX = re.compile(
    r'File\s+"(?P<file>[^"]+)",\s+line\s+(?P<line>\d+)(?:,\s+in\s+(?P<func>[\w<>]+))?'
)

EXCEPTION_REGEX = re.compile(
    r'^(?P<type>[a-zA-Z_][a-zA-Z0-9_.]*(?:Error|Exception|Interrupt|Exit)):\s*(?P<msg>.*)$'
)

CHAIN_SEPARATOR_REGEX = re.compile(
    r"(?:The above exception was the direct cause of the following exception:|During handling of the above exception, another exception occurred:)"
)

EXCLUSION_PATTERNS = (
    "site-packages/",
    "dist-packages/",
    "lib/python3.",
    "Lib/",
    "<frozen",
    "<string>",
)


def normalize_traceback_text(raw_traceback: str) -> List[str]:
    """
    Normalizes escaped newlines and path separators into a clean list of lines.
    """
    if "\\n" in raw_traceback:
        raw_traceback = raw_traceback.replace("\\n", "\n")

    raw_traceback = raw_traceback.replace("\\", "/")
    return [line.rstrip() for line in raw_traceback.splitlines() if line.strip()]


def extract_exception_details(lines: List[str]) -> Tuple[str, str]:
    """
    Extracts exception type and message by scanning lines from the bottom up.
    """
    for line in reversed(lines):
        clean_line = line.strip()
        match = EXCEPTION_REGEX.match(clean_line)
        if match:
            error_type = match.group("type")
            error_message = match.group("msg").strip()
            return error_type, error_message

    if lines:
        return "UnknownError", lines[-1].strip()
    return "UnknownError", "No Exception Message Found"


def extract_failing_frame(lines: List[str]) -> Optional[dict]:
    """
    Filters runtime and third-party frames, returning the active application failure frame.
    """
    app_frames = []
    for line in lines:
        match = FRAME_REGEX.search(line)
        if not match:
            continue

        raw_file = match.group("file")
        line_number = int(match.group("line"))
        func = match.group("func") or "<module>"

        if any(pattern in raw_file for pattern in EXCLUSION_PATTERNS):
            continue

        app_frames.append({
            "file_path": raw_file,
            "line_number": line_number,
            "function_name": func,
        })

    return app_frames[-1] if app_frames else None


def extract_source_window(
    file_path: str,
    line_number: int,
    padding: int = 10,
    allowed_root: Optional[str] = None,
) -> str:
    """
    Reads a bounded window of source lines around line_number with visual pointers.
    Enforces path traversal containment within allowed_root to prevent arbitrary file disclosure.
    """
    root_boundary = os.path.realpath(allowed_root or os.getcwd())
    resolved_target = os.path.realpath(
        file_path if os.path.isabs(file_path) else os.path.join(root_boundary, file_path)
    )

    try:
        common = os.path.commonpath([root_boundary, resolved_target])
    except ValueError:
        return f"# Security Guard: Target '{file_path}' traverses across storage boundaries"

    if common != root_boundary:
        return f"# Security Guard: Access denied for path outside workspace boundary: {file_path}"

    if not os.path.exists(resolved_target):
        return f"# Source file unavailable on disk: {file_path}"

    try:
        with open(resolved_target, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
    except Exception as e:
        return f"# Error reading source file: {e}"

    total_lines = len(all_lines)
    target_idx = line_number - 1

    start = max(0, target_idx - padding)
    end = min(total_lines, target_idx + padding + 1)

    formatted_lines = []
    for idx in range(start, end):
        curr_line = idx + 1
        code_content = all_lines[idx].rstrip("\r\n")
        marker = ">>" if curr_line == line_number else "  "
        formatted_lines.append(f"{marker} {curr_line:4d} | {code_content}")

    return "\n".join(formatted_lines)


def parse_crash_traceback(
    raw_traceback: str,
    padding: int = 10,
    allowed_root: Optional[str] = None,
) -> CrashLocation:
    """
    Orchestrates traceback parsing. For chained exceptions, targets the root cause
    block rather than outer wrappers.
    """
    # Isolate root-cause block when chained exceptions are present
    blocks = CHAIN_SEPARATOR_REGEX.split(raw_traceback)
    primary_block = blocks[0] if blocks else raw_traceback

    lines = normalize_traceback_text(primary_block)
    if not lines:
        return CrashLocation()

    error_type, error_message = extract_exception_details(lines)
    frame = extract_failing_frame(lines)
    if not frame:
        return CrashLocation(
            error_type=error_type,
            error_message=error_message,
            source_context="# No application frame identified",
        )

    source_context = extract_source_window(
        file_path=frame["file_path"],
        line_number=frame["line_number"],
        padding=padding,
        allowed_root=allowed_root,
    )

    return CrashLocation(
        file_path=frame["file_path"],
        line_number=frame["line_number"],
        function_name=frame["function_name"],
        error_type=error_type,
        error_message=error_message,
        source_context=source_context,
    )
