"""
AST Guard & Patch Synthesis Engine.
Validates search/replace code transformations, enforces AST syntax guarantees,
and generates standard unified diffs without modifying host source files.
"""

import ast
import difflib
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class PatchResult:
    success: bool
    target_file: str
    original_content: str = ""
    patched_content: str = ""
    diff: str = ""
    error: Optional[str] = None


def normalize_line_endings(text: str) -> str:
    """
    Standardizes line endings to Unix-style newlines for consistent matching and diffing.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def synthesize_patch(
    target_file: str,
    search_block: str,
    replace_block: str,
    allowed_root: Optional[str] = None,
) -> PatchResult:
    """
    Validates and executes an in-memory surgical search/replace patch.
    Enforces workspace boundary checks, ambiguity detection, and AST compilation pre-flight.
    """
    root_boundary = os.path.realpath(allowed_root or os.getcwd())
    resolved_target = os.path.realpath(
        target_file if os.path.isabs(target_file) else os.path.join(root_boundary, target_file)
    )

    # 1. Path Containment Guard
    try:
        common = os.path.commonpath([root_boundary, resolved_target])
    except ValueError:
        return PatchResult(
            success=False,
            target_file=target_file,
            error=f"Security Guard: Target path '{target_file}' is on an invalid storage boundary.",
        )

    if common != root_boundary:
        return PatchResult(
            success=False,
            target_file=target_file,
            error=f"Security Guard: Access denied for path outside workspace boundary: {target_file}",
        )

    if not os.path.exists(resolved_target):
        return PatchResult(
            success=False,
            target_file=target_file,
            error=f"Target source file not found on disk: {target_file}",
        )

    # 2. Read Source Content
    try:
        with open(resolved_target, "r", encoding="utf-8") as f:
            original_content = f.read()
    except Exception as e:
        return PatchResult(
            success=False,
            target_file=target_file,
            error=f"Failed to read source file '{target_file}': {e}",
        )

    norm_original = normalize_line_endings(original_content)
    norm_search = normalize_line_endings(search_block).strip("\n")
    norm_replace = normalize_line_endings(replace_block).strip("\n")

    if not norm_search:
        return PatchResult(
            success=False,
            target_file=target_file,
            original_content=original_content,
            error="Search block cannot be empty.",
        )

    # 3. Unambiguity Guard
    match_count = norm_original.count(norm_search)
    if match_count == 0:
        return PatchResult(
            success=False,
            target_file=target_file,
            original_content=original_content,
            error="Search block not found in target file.",
        )

    if match_count > 1:
        return PatchResult(
            success=False,
            target_file=target_file,
            original_content=original_content,
            error=f"Ambiguous transformation: Search block matched {match_count} locations in target file.",
        )

    # 4. In-Memory Patching
    patched_content = norm_original.replace(norm_search, norm_replace, 1)

    # 5. AST Pre-flight Guard
    try:
        ast.parse(patched_content, filename=resolved_target)
    except SyntaxError as e:
        return PatchResult(
            success=False,
            target_file=target_file,
            original_content=original_content,
            patched_content=patched_content,
            error=f"AST Syntax Validation Failed on line {e.lineno}: {e.msg}",
        )

    # 6. Mathematical Diff Generation
    rel_path = os.path.relpath(resolved_target, root_boundary).replace("\\", "/")
    orig_lines = norm_original.splitlines(keepends=True)
    patched_lines = patched_content.splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            orig_lines,
            patched_lines,
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
        )
    )
    unified_diff = "".join(diff_lines)

    return PatchResult(
        success=True,
        target_file=target_file,
        original_content=original_content,
        patched_content=patched_content,
        diff=unified_diff,
        error=None,
    )


def write_patch_to_sandbox(patch_result: PatchResult, sandbox_root: str) -> str:
    """
    Safely writes the validated patch content to a target sandbox directory.
    Never modifies host repository files.
    """
    if not patch_result.success:
        raise ValueError(f"Cannot apply failed patch: {patch_result.error}")

    root_boundary = os.path.realpath(os.getcwd())
    resolved_target = os.path.realpath(patch_result.target_file)
    rel_path = os.path.relpath(resolved_target, root_boundary)

    destination_file = os.path.join(sandbox_root, rel_path)
    os.makedirs(os.path.dirname(destination_file), exist_ok=True)

    with open(destination_file, "w", encoding="utf-8") as f:
        f.write(patch_result.patched_content)

    return destination_file
