"""
Pytest Test Suite for services/agent/patcher.py
Run with: pytest test_patcher.py
"""

import os
import shutil
import tempfile
import pytest

from services.agent.patcher import (
    PatchResult,
    synthesize_patch,
    write_patch_to_sandbox,
)

TARGET_FILE = "test_bed/app/services/billing.py"


def test_valid_surgical_patch():
    search_block = "effective_ratio = round(subtotal / net_payable_base, 2)"
    replace_block = "effective_ratio = 0.0 if net_payable_base == 0 else round(subtotal / net_payable_base, 2)"

    result = synthesize_patch(
        target_file=TARGET_FILE,
        search_block=search_block,
        replace_block=replace_block,
    )

    assert result.success is True
    assert result.error is None
    assert "--- a/test_bed/app/services/billing.py" in result.diff
    assert "+++ b/test_bed/app/services/billing.py" in result.diff
    assert "+    effective_ratio = 0.0 if net_payable_base == 0 else round(subtotal / net_payable_base, 2)" in result.diff
    assert "-    effective_ratio = round(subtotal / net_payable_base, 2)" in result.diff


def test_search_block_not_found():
    result = synthesize_patch(
        target_file=TARGET_FILE,
        search_block="non_existent_variable_hallucination = True",
        replace_block="pass",
    )

    assert result.success is False
    assert "Search block not found in target file" in result.error


def test_ambiguous_search_block_rejected():
    # 'round(' appears multiple times in billing.py
    result = synthesize_patch(
        target_file=TARGET_FILE,
        search_block="round(",
        replace_block="round(",
    )

    assert result.success is False
    assert "Ambiguous transformation" in result.error


def test_ast_syntax_error_rejection():
    search_block = "effective_ratio = round(subtotal / net_payable_base, 2)"
    broken_syntax_replace = "effective_ratio = def broken_syntax("

    result = synthesize_patch(
        target_file=TARGET_FILE,
        search_block=search_block,
        replace_block=broken_syntax_replace,
    )

    assert result.success is False
    assert "AST Syntax Validation Failed" in result.error


def test_path_traversal_boundary_guard():
    result = synthesize_patch(
        target_file="C:/Windows/System32/drivers/etc/hosts",
        search_block="127.0.0.1",
        replace_block="127.0.0.1",
        allowed_root="C:/Zephyrus/Husen/Projects/opsmind-ai/test_bed",
    )

    assert result.success is False
    assert "Security Guard" in result.error


def test_write_patch_to_sandbox_isolation():
    search_block = "effective_ratio = round(subtotal / net_payable_base, 2)"
    replace_block = "effective_ratio = 0.0 if net_payable_base == 0 else round(subtotal / net_payable_base, 2)"

    result = synthesize_patch(
        target_file=TARGET_FILE,
        search_block=search_block,
        replace_block=replace_block,
    )
    assert result.success is True

    temp_sandbox = tempfile.mkdtemp(prefix="opsmind_sandbox_test_")
    try:
        sandbox_path = write_patch_to_sandbox(result, temp_sandbox)
        assert os.path.exists(sandbox_path)

        with open(sandbox_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "effective_ratio = 0.0 if net_payable_base == 0" in content

        # Verify host original file is 100% UNTOUCHED
        with open(TARGET_FILE, "r", encoding="utf-8") as f:
            host_content = f.read()
        assert "effective_ratio = round(subtotal / net_payable_base, 2)" in host_content
        assert "0.0 if net_payable_base == 0" not in host_content

    finally:
        shutil.rmtree(temp_sandbox, ignore_errors=True)


if __name__ == "__main__":
    pytest.main(["-v", __file__])
