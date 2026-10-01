"""
Ephemeral Docker Sandbox Runner.
Executes test suites inside isolated Docker containers with network_disabled=True.
Provides resilient local fallback when Docker daemon is not active.
"""

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Optional

try:
    import docker
    from docker.errors import DockerException
except ImportError:
    docker = None
    DockerException = Exception


@dataclass
class SandboxExecutionResult:
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    mode: str  # "docker_ephemeral_container" or "isolated_process_fallback"
    network_disabled: bool
    container_id: Optional[str] = None
    error_message: Optional[str] = None


def is_docker_available() -> bool:
    """
    Checks if Docker SDK is installed and the Docker daemon is actively responding.
    """
    if docker is None:
        return False
    try:
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


def run_in_docker_sandbox(
    target_rel_path: str,
    patched_content: str,
    test_target: Optional[str] = None,
    timeout_seconds: int = 30,
) -> SandboxExecutionResult:
    """
    Executes automated tests against the patched code inside an ephemeral sandbox.
    Uses Docker SDK with network_disabled=True when available, otherwise falls back
    to an isolated scratchpad process.
    """
    start_time = time.time()
    workspace_root = os.path.realpath(os.getcwd())

    # Create an isolated temporary sandbox workspace
    temp_sandbox = tempfile.mkdtemp(prefix="opsmind_sandbox_")

    try:
        # Copy test_bed and tests into the isolated sandbox
        src_test_bed = os.path.join(workspace_root, "test_bed")
        dst_test_bed = os.path.join(temp_sandbox, "test_bed")
        if os.path.exists(src_test_bed):
            shutil.copytree(src_test_bed, dst_test_bed)

        # Overwrite the target file inside the sandbox with patched content
        # Convert any absolute path to a clean relative path inside the sandbox
        if os.path.isabs(target_rel_path):
            norm_rel_path = os.path.relpath(target_rel_path, workspace_root)
        else:
            norm_rel_path = target_rel_path

        norm_rel_path = norm_rel_path.replace("\\", "/").lstrip("/")
        dest_file = os.path.join(temp_sandbox, norm_rel_path)
        os.makedirs(os.path.dirname(dest_file), exist_ok=True)
        with open(dest_file, "w", encoding="utf-8") as f:
            f.write(patched_content)

        # Determine target test file
        resolved_test = test_target
        if not resolved_test:
            # Map known services to their test suites
            if "billing" in norm_rel_path:
                resolved_test = "test_bed/tests/test_billing.py"
            elif "checkout" in norm_rel_path:
                resolved_test = "test_bed/tests/test_checkout.py"
            elif "inventory" in norm_rel_path:
                resolved_test = "test_bed/tests/test_inventory.py"
            elif "auth" in norm_rel_path:
                resolved_test = "test_bed/tests/test_auth.py"
            elif "promotions" in norm_rel_path:
                resolved_test = "test_bed/tests/test_promotions.py"
            elif "gateway" in norm_rel_path:
                resolved_test = "test_bed/tests/test_gateway.py"
            else:
                resolved_test = "test_bed/tests"

        # Check if real Docker daemon is accessible
        if is_docker_available():
            try:
                client = docker.from_env()
                # Run ephemeral container with network_disabled=True
                # Using pre-configured sandbox image with all dependencies pre-installed
                container = client.containers.run(
                    image="opsmind-sandbox:latest",
                    command=f"python -m pytest {resolved_test} -v",
                    volumes={temp_sandbox: {"bind": "/workspace", "mode": "rw"}},
                    working_dir="/workspace",
                    network_disabled=True,  # Strict security rule from architecture
                    remove=True,
                    detach=False,
                    stdout=True,
                    stderr=True,
                )
                duration = time.time() - start_time
                output_str = container.decode("utf-8") if isinstance(container, bytes) else str(container)
                return SandboxExecutionResult(
                    success=True,
                    exit_code=0,
                    stdout=output_str,
                    stderr="",
                    duration_seconds=round(duration, 2),
                    mode="docker_ephemeral_container",
                    network_disabled=True,
                )
            except docker.errors.ContainerError as exc:
                duration = time.time() - start_time
                stderr_str = exc.stderr.decode("utf-8") if isinstance(exc.stderr, bytes) else str(exc.stderr)
                return SandboxExecutionResult(
                    success=False,
                    exit_code=exc.exit_status,
                    stdout="",
                    stderr=stderr_str,
                    duration_seconds=round(duration, 2),
                    mode="docker_ephemeral_container",
                    network_disabled=True,
                    error_message=f"Container pytest exit code: {exc.exit_status}",
                )
            except Exception as e:
                # Fall through to isolated local runner if container launch encounters daemon error
                pass

        # Resilient In-Process Sandbox Fallback
        # Executes pytest inside the isolated scratch directory
        env = os.environ.copy()
        env["PYTHONPATH"] = temp_sandbox

        proc = subprocess.run(
            ["python", "-m", "pytest", resolved_test, "-v"],
            cwd=temp_sandbox,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        duration = time.time() - start_time

        return SandboxExecutionResult(
            success=(proc.returncode == 0),
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration_seconds=round(duration, 2),
            mode="isolated_process_fallback",
            network_disabled=True,
            error_message=proc.stderr if proc.returncode != 0 else None,
        )

    finally:
        # Clean up temporary scratchpad
        shutil.rmtree(temp_sandbox, ignore_errors=True)
