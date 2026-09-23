from __future__ import annotations

import codecs
import os
import re
import shlex
import subprocess
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Protocol

from ..common import TASKS_ROOT, load_json
from .contracts import (
    ToolCall,
    ToolCommandTimeout,
    ToolExecutionResult,
    ToolInfrastructureError,
)


DEFAULT_SANDBOX_IMAGE = (
    "python:3.12.8-slim-bookworm@"
    "sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0"
)
DEFAULT_MAX_OUTPUT_BYTES = 256 * 1024
DEFAULT_MAX_READ_BYTES = 256 * 1024
DEFAULT_MAX_PATCH_BYTES = 1024 * 1024
DEFAULT_MAX_PATCH_FILES = 64
MAX_PATH_CHARACTERS = 4096
MAX_COMMAND_CHARACTERS = 16 * 1024
MAX_CLARIFICATION_CHARACTERS = 4096


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    output: str
    output_truncated: bool = False


class CommandSandbox(Protocol):
    def run(
        self,
        *,
        workspace: Path,
        command: str,
        timeout_seconds: int,
    ) -> CommandResult:
        """Run one command without granting access outside the workspace."""


class _BoundedCollector:
    def __init__(self, maximum_bytes: int) -> None:
        self.maximum_bytes = maximum_bytes
        self.data = bytearray()
        self.truncated = False

    def consume(self, stream: Any) -> None:
        try:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    break
                remaining = self.maximum_bytes - len(self.data)
                if remaining > 0:
                    self.data.extend(chunk[:remaining])
                if len(chunk) > max(remaining, 0):
                    self.truncated = True
        finally:
            stream.close()

    def text(self) -> str:
        return bytes(self.data).decode("utf-8", errors="replace")


class DockerCommandSandbox:
    """Execute Bash in a locked-down container with only the run workspace mounted."""

    def __init__(
        self,
        *,
        image: str = DEFAULT_SANDBOX_IMAGE,
        docker_executable: str = "docker",
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
        memory: str = "1g",
        cpus: float = 2.0,
        pids_limit: int = 256,
        network_enabled: bool = False,
    ) -> None:
        if not image or not docker_executable:
            raise ValueError("image and docker_executable must be non-empty")
        if max_output_bytes < 1 or cpus <= 0 or pids_limit < 1:
            raise ValueError("Sandbox resource limits must be positive")
        self.image = image
        self.docker_executable = docker_executable
        self.max_output_bytes = max_output_bytes
        self.memory = memory
        self.cpus = cpus
        self.pids_limit = pids_limit
        self.network_enabled = network_enabled

    def run(
        self,
        *,
        workspace: Path,
        command: str,
        timeout_seconds: int,
    ) -> CommandResult:
        root = _validate_workspace(workspace)
        if not isinstance(command, str) or not command.strip():
            raise ValueError("command must be a non-empty string")
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive")

        container_name = f"tsb-tool-{uuid.uuid4().hex}"
        mount = f"type=bind,source={root},target=/workspace"
        arguments = [
            self.docker_executable,
            "run",
            "--rm",
            "--name",
            container_name,
            "--workdir",
            "/workspace",
            "--mount",
            mount,
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges=true",
            "--memory",
            self.memory,
            "--cpus",
            str(self.cpus),
            "--pids-limit",
            str(self.pids_limit),
            "--user",
            "65534:65534",
            "--env",
            "HOME=/tmp",
            "--env",
            "TMPDIR=/tmp",
            "--network",
            "bridge" if self.network_enabled else "none",
            self.image,
            "bash",
            "--noprofile",
            "--norc",
            "-lc",
            command,
        ]
        git_directory = root / ".git"
        if git_directory.is_dir() and not git_directory.is_symlink():
            image_index = arguments.index(self.image)
            arguments[image_index:image_index] = [
                "--mount",
                f"type=bind,source={git_directory},target=/workspace/.git,readonly",
            ]
        try:
            process = subprocess.Popen(
                arguments,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as error:
            raise ToolInfrastructureError(
                f"Docker executable is unavailable: {self.docker_executable}"
            ) from error
        except OSError as error:
            raise ToolInfrastructureError(f"Could not start Docker sandbox: {error}") from error

        assert process.stdout is not None
        assert process.stderr is not None
        stdout = _BoundedCollector(self.max_output_bytes)
        stderr = _BoundedCollector(self.max_output_bytes)
        readers = [
            threading.Thread(target=stdout.consume, args=(process.stdout,), daemon=True),
            threading.Thread(target=stderr.consume, args=(process.stderr,), daemon=True),
        ]
        for reader in readers:
            reader.start()
        timed_out = False
        try:
            exit_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            process.wait(timeout=10)
            exit_code = process.returncode if process.returncode is not None else -1
        finally:
            if timed_out:
                self._force_remove(container_name)
            for reader in readers:
                reader.join(timeout=10)

        output = _format_process_output(stdout.text(), stderr.text())
        truncated = stdout.truncated or stderr.truncated
        if truncated:
            output = _append_notice(output, "[tool output truncated at the frozen byte limit]")
        if timed_out:
            raise ToolCommandTimeout(
                f"Command exceeded the {timeout_seconds} second timeout.",
                output=output,
            )
        if exit_code == 125 and _looks_like_docker_failure(output):
            raise ToolInfrastructureError(f"Docker sandbox could not start: {output.strip()}")
        return CommandResult(exit_code=exit_code, output=output, output_truncated=truncated)

    def _force_remove(self, container_name: str) -> None:
        try:
            subprocess.run(
                [self.docker_executable, "rm", "--force", container_name],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return


@dataclass(frozen=True)
class ClarificationPolicy:
    task_id: str
    maximum_authorised_responses: int
    authorised_response_card_id: str
    authorised_response_text: str
    no_information_response: str

    @classmethod
    def load(cls, path: Path) -> "ClarificationPolicy":
        value = load_json(path)
        response = value.get("authorised_response")
        if not isinstance(response, dict):
            raise ValueError("Clarification policy lacks authorised_response")
        required = {
            "task_id": value.get("task_id"),
            "maximum_authorised_responses": value.get("maximum_authorised_responses"),
            "authorised_response_card_id": response.get("response_card_id"),
            "authorised_response_text": response.get("text"),
            "no_information_response": value.get("no_information_response"),
        }
        if not isinstance(required["task_id"], str):
            raise ValueError("Clarification policy task_id is invalid")
        if not isinstance(required["maximum_authorised_responses"], int):
            raise ValueError("Clarification response limit is invalid")
        if required["maximum_authorised_responses"] != 1:
            raise ValueError("The shared protocol requires exactly one authorised response")
        for field in (
            "authorised_response_card_id",
            "authorised_response_text",
            "no_information_response",
        ):
            if not isinstance(required[field], str) or not required[field]:
                raise ValueError(f"Clarification policy {field} is invalid")
        return cls(**required)  # type: ignore[arg-type]


@dataclass(frozen=True)
class ClarificationResolution:
    authorized: bool
    response_issued: bool
    response_card_id: str | None
    reason_code: str
    response_text: str


def resolve_clarification_request(
    request: str,
    *,
    policy: ClarificationPolicy | None,
    response_already_issued: bool,
) -> ClarificationResolution:
    """Apply the frozen clarification rule without exposing policy internals."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Clarification request must be a non-empty string")
    if "\x00" in request or len(request) > MAX_CLARIFICATION_CHARACTERS:
        raise ValueError("Clarification request is invalid or exceeds the frozen limit")
    no_information = (
        policy.no_information_response
        if policy is not None
        else "No additional information is available under the clarification protocol. "
        "Continue using the task brief and repository evidence."
    )
    if policy is None:
        return ClarificationResolution(
            False, False, None, "UNRELATED_REQUIREMENT", no_information
        )
    if response_already_issued:
        return ClarificationResolution(
            False, False, None, "DUPLICATE_REQUEST", no_information
        )
    qualifying, reason_code = _classify_clarification_request(request.strip())
    if not qualifying:
        return ClarificationResolution(False, False, None, reason_code, no_information)
    return ClarificationResolution(
        True,
        True,
        policy.authorised_response_card_id,
        "QUALIFYING_DUE_DATE_RULE",
        policy.authorised_response_text,
    )


class SandboxedLogicalToolExecutor:
    """Shared implementation of the four frozen logical actions."""

    def __init__(
        self,
        *,
        command_sandbox: CommandSandbox | None = None,
        clarification_policy: ClarificationPolicy | None = None,
        max_read_bytes: int = DEFAULT_MAX_READ_BYTES,
        max_patch_bytes: int = DEFAULT_MAX_PATCH_BYTES,
        max_patch_files: int = DEFAULT_MAX_PATCH_FILES,
        git_executable: str = "git",
    ) -> None:
        if max_read_bytes < 1 or max_patch_bytes < 1 or max_patch_files < 1:
            raise ValueError("Tool byte/file limits must be positive")
        self.command_sandbox = command_sandbox or DockerCommandSandbox()
        self.clarification_policy = clarification_policy
        self.max_read_bytes = max_read_bytes
        self.max_patch_bytes = max_patch_bytes
        self.max_patch_files = max_patch_files
        self.git_executable = git_executable
        self._clarification_responses_by_workspace: set[Path] = set()

    @classmethod
    def for_task(
        cls,
        task_id: str,
        *,
        tasks_root: Path = TASKS_ROOT,
        command_sandbox: CommandSandbox | None = None,
        **kwargs: Any,
    ) -> "SandboxedLogicalToolExecutor":
        policy_path = tasks_root / task_id / "clarification_policy.json"
        policy = ClarificationPolicy.load(policy_path) if policy_path.is_file() else None
        return cls(
            command_sandbox=command_sandbox,
            clarification_policy=policy,
            **kwargs,
        )

    def execute(
        self,
        call: ToolCall,
        *,
        workspace: Path,
        command_timeout_seconds: int,
    ) -> ToolExecutionResult:
        root = _validate_workspace(workspace)
        if call.argument_error is not None:
            return ToolExecutionResult(
                f"Malformed tool arguments: {call.argument_error}",
                is_error=True,
                metadata={"argument_error": call.argument_error},
            )
        if call.name == "read_file":
            return self._read_file(root, call.arguments)
        if call.name == "patch_file":
            return self._patch_file(root, call.arguments)
        if call.name == "execute_bash":
            return self._execute_bash(root, call.arguments, command_timeout_seconds)
        if call.name == "request_human_clarification":
            return self._request_clarification(root, call.arguments)
        return ToolExecutionResult(f"Unsupported logical tool: {call.name}", is_error=True)

    def _read_file(self, workspace: Path, arguments: dict[str, Any]) -> ToolExecutionResult:
        error = _validate_exact_string_argument(
            arguments, "path", max_characters=MAX_PATH_CHARACTERS
        )
        if error:
            return ToolExecutionResult(error, is_error=True)
        relative = arguments["path"]
        try:
            target = _safe_existing_path(workspace, relative)
        except ValueError as exc:
            return ToolExecutionResult(str(exc), is_error=True)
        if not target.is_file():
            return ToolExecutionResult(f"Path is not a regular file: {relative}", is_error=True)
        size = target.stat().st_size
        with target.open("rb") as stream:
            raw = stream.read(self.max_read_bytes + 4)
        prefix = raw[: self.max_read_bytes]
        try:
            decoder = codecs.getincrementaldecoder("utf-8")("strict")
            text = decoder.decode(prefix, final=size <= self.max_read_bytes)
        except UnicodeDecodeError:
            return ToolExecutionResult(f"File is not valid UTF-8 text: {relative}", is_error=True)
        truncated = size > self.max_read_bytes
        if truncated:
            text = _append_notice(
                text,
                f"[file truncated: {size} bytes total, {self.max_read_bytes} byte limit]",
            )
        return ToolExecutionResult(
            text,
            metadata={
                "path": PurePosixPath(relative).as_posix(),
                "size_bytes": size,
                "output_truncated": truncated,
            },
        )

    def _patch_file(self, workspace: Path, arguments: dict[str, Any]) -> ToolExecutionResult:
        error = _validate_exact_string_argument(arguments, "patch")
        if error:
            return ToolExecutionResult(error, is_error=True)
        patch = arguments["patch"]
        patch_size = len(patch.encode("utf-8"))
        if patch_size > self.max_patch_bytes:
            return ToolExecutionResult(
                f"Patch exceeds the {self.max_patch_bytes} byte limit.", is_error=True
            )
        try:
            affected_paths = _validate_patch(patch, workspace, self.max_patch_files)
        except ValueError as exc:
            return ToolExecutionResult(str(exc), is_error=True)
        check = self._git_apply(workspace, patch, check_only=True)
        if check.returncode != 0:
            return ToolExecutionResult(
                "Patch rejected by git apply.\n" + _decode_subprocess(check),
                is_error=True,
                metadata={"affected_paths": affected_paths},
            )
        applied = self._git_apply(workspace, patch, check_only=False)
        if applied.returncode != 0:
            raise ToolInfrastructureError(
                "Patch passed validation but failed during application: "
                + _decode_subprocess(applied)
            )
        return ToolExecutionResult(
            "Patch applied successfully.",
            metadata={"affected_paths": affected_paths, "patch_bytes": patch_size},
        )

    def _git_apply(
        self, workspace: Path, patch: str, *, check_only: bool
    ) -> subprocess.CompletedProcess[bytes]:
        arguments = [
            self.git_executable,
            "-c",
            "core.hooksPath=NUL" if os.name == "nt" else "core.hooksPath=/dev/null",
            "apply",
            "--recount",
            "--whitespace=nowarn",
        ]
        if check_only:
            arguments.append("--check")
        arguments.append("-")
        try:
            return subprocess.run(
                arguments,
                cwd=workspace,
                input=patch.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
        except FileNotFoundError as error:
            raise ToolInfrastructureError(
                f"Git executable is unavailable: {self.git_executable}"
            ) from error
        except subprocess.TimeoutExpired as error:
            raise ToolInfrastructureError("git apply exceeded its infrastructure timeout") from error
        except OSError as error:
            raise ToolInfrastructureError(f"Could not execute git apply: {error}") from error

    def _execute_bash(
        self,
        workspace: Path,
        arguments: dict[str, Any],
        command_timeout_seconds: int,
    ) -> ToolExecutionResult:
        error = _validate_exact_string_argument(
            arguments, "command", max_characters=MAX_COMMAND_CHARACTERS
        )
        if error:
            return ToolExecutionResult(error, is_error=True)
        result = self.command_sandbox.run(
            workspace=workspace,
            command=arguments["command"],
            timeout_seconds=command_timeout_seconds,
        )
        output = _append_notice(
            result.output,
            f"[process exited with code {result.exit_code}]",
        )
        return ToolExecutionResult(
            output,
            is_error=result.exit_code != 0,
            metadata={
                "exit_code": result.exit_code,
                "output_truncated": result.output_truncated,
                "sandbox": type(self.command_sandbox).__name__,
            },
        )

    def _request_clarification(
        self, workspace: Path, arguments: dict[str, Any]
    ) -> ToolExecutionResult:
        error = _validate_exact_string_argument(
            arguments, "request", max_characters=MAX_CLARIFICATION_CHARACTERS
        )
        if error:
            return ToolExecutionResult(
                error,
                is_error=True,
                metadata={"clarification": _clarification_metadata(False, False, "TOO_VAGUE")},
            )
        request = arguments["request"].strip()
        resolution = resolve_clarification_request(
            request,
            policy=self.clarification_policy,
            response_already_issued=(workspace in self._clarification_responses_by_workspace),
        )
        if resolution.response_issued:
            self._clarification_responses_by_workspace.add(workspace)
        return ToolExecutionResult(
            resolution.response_text,
            metadata={
                "clarification": _clarification_metadata(
                    resolution.authorized,
                    resolution.response_issued,
                    resolution.reason_code,
                    resolution.response_card_id,
                )
            },
        )


def _validate_workspace(workspace: Path) -> Path:
    if workspace.is_symlink():
        raise ToolInfrastructureError("Workspace root must not be a symbolic link")
    try:
        resolved = workspace.resolve(strict=True)
    except OSError as error:
        raise ToolInfrastructureError(f"Workspace cannot be resolved: {error}") from error
    if not resolved.is_dir():
        raise ToolInfrastructureError(f"Workspace is not a directory: {resolved}")
    return resolved


def _validate_exact_string_argument(
    arguments: dict[str, Any],
    name: str,
    *,
    max_characters: int | None = None,
) -> str | None:
    if set(arguments) != {name}:
        return f"Arguments must contain exactly one field named {name}."
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        return f"Argument {name} must be a non-empty string."
    if "\x00" in value:
        return f"Argument {name} must not contain NUL bytes."
    if max_characters is not None and len(value) > max_characters:
        return f"Argument {name} exceeds the {max_characters} character limit."
    return None


def _lexical_relative_path(value: str) -> PurePosixPath:
    if not value or "\x00" in value or "\\" in value or ":" in value:
        raise ValueError(f"Unsafe workspace path: {value!r}")
    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError(f"Path traversal or non-canonical path is not allowed: {value}")
    if any(part.endswith((".", " ")) for part in raw_parts):
        raise ValueError(f"Unsafe Windows-normalized workspace path: {value}")
    windows = PureWindowsPath(value)
    path = PurePosixPath(value)
    if windows.is_absolute() or windows.drive or path.is_absolute():
        raise ValueError(f"Absolute paths are not allowed: {value}")
    if any(part.casefold() == ".git" for part in path.parts):
        raise ValueError("The workspace Git metadata is not writable through tools")
    return path


def _reject_symlink_components(workspace: Path, relative: PurePosixPath) -> None:
    current = workspace
    try:
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError(
                    f"Symbolic-link paths are not allowed: {relative.as_posix()}"
                )
    except OSError as error:
        raise ValueError(f"Workspace path cannot be inspected safely: {relative}") from error


def _safe_existing_path(workspace: Path, value: str) -> Path:
    relative = _lexical_relative_path(value)
    _reject_symlink_components(workspace, relative)
    target = workspace.joinpath(*relative.parts)
    try:
        resolved = target.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"Path does not exist: {value}") from error
    if not resolved.is_relative_to(workspace):
        raise ValueError(f"Path escapes the workspace: {value}")
    return resolved


def _validate_patch(patch: str, workspace: Path, maximum_files: int) -> list[str]:
    if "\x00" in patch:
        raise ValueError("Patch must not contain NUL bytes")
    prohibited = (
        "GIT binary patch",
        "Binary files ",
        "rename from ",
        "rename to ",
        "copy from ",
        "copy to ",
        "new file mode 120000",
        "new mode 120000",
        "new file mode 160000",
        "new mode 160000",
    )
    if any(marker in patch for marker in prohibited):
        raise ValueError("Binary, rename, copy, and symbolic-link patches are not allowed")
    paths: set[str] = set()
    diff_headers = 0
    for line in patch.splitlines():
        candidates: list[str] = []
        if line.startswith("diff --git "):
            diff_headers += 1
            try:
                fields = shlex.split(line, posix=True)
            except ValueError as error:
                raise ValueError(f"Malformed diff header: {line}") from error
            if len(fields) != 4 or fields[:2] != ["diff", "--git"]:
                raise ValueError(f"Malformed diff header: {line}")
            candidates.extend(fields[2:])
        elif line.startswith("--- ") or line.startswith("+++ "):
            try:
                fields = shlex.split(line[4:], posix=True)
            except ValueError as error:
                raise ValueError(f"Malformed patch path header: {line}") from error
            if not fields:
                raise ValueError(f"Malformed patch path header: {line}")
            candidates.append(fields[0])
        for candidate in candidates:
            if candidate == "/dev/null":
                continue
            if candidate.startswith(("a/", "b/")):
                candidate = candidate[2:]
            relative = _lexical_relative_path(candidate)
            _reject_symlink_components(workspace, relative)
            paths.add(relative.as_posix())
    if diff_headers == 0 or not paths:
        raise ValueError("Patch must be a standard unified git diff with diff --git headers")
    if len(paths) > maximum_files:
        raise ValueError(f"Patch affects more than the {maximum_files} file limit")
    return sorted(paths)


def _classify_clarification_request(request: str) -> tuple[bool, str]:
    normalized = re.sub(r"[_-]+", " ", request.casefold())
    due_date = bool(
        re.search(r"\bdue\s+date\b|\bdeadline\b|截止日期|到期日", normalized)
    )
    missing_value_intent = bool(
        re.search(
            r"\b(optional|required|mandatory|omit(?:ted)?|without|empty|blank|missing|null|"
            r"none|nullable|absent|unspecified)\b|not\s+supplied|leave\s+(?:it\s+)?out|"
            r"可选|必填|必须|省略|空值|缺失|为空|存储|保存",
            normalized,
        )
    )
    if due_date and missing_value_intent:
        return True, "QUALIFYING_DUE_DATE_RULE"
    if re.sub(r"[^a-z0-9\s]", "", normalized).strip() == "what should i do":
        return False, "TOO_VAGUE"
    if re.search(r"which file|expected patch|test failing|debug|怎么修|哪个文件", normalized):
        return False, "DEBUGGING_ASSISTANCE"
    if re.search(r"pydantic|fastapi|sqlite|schema|technical|技术", normalized):
        return False, "TECHNICAL_FAULT"
    if len(normalized.split()) < 4:
        return False, "TOO_VAGUE"
    return False, "UNRELATED_REQUIREMENT"


def _clarification_metadata(
    authorized: bool,
    response_issued: bool,
    reason_code: str,
    response_card_id: str | None = None,
) -> dict[str, Any]:
    return {
        "authorized": authorized,
        "response_issued": response_issued,
        "response_card_id": response_card_id,
        "reason_code": reason_code,
    }


def _format_process_output(stdout: str, stderr: str) -> str:
    parts: list[str] = []
    if stdout:
        parts.append(stdout.rstrip("\n"))
    if stderr:
        parts.append("[stderr]\n" + stderr.rstrip("\n"))
    return "\n".join(parts)


def _append_notice(output: str, notice: str) -> str:
    return f"{output.rstrip()}\n{notice}" if output else notice


def _looks_like_docker_failure(output: str) -> bool:
    normalized = output.casefold()
    return "docker:" in normalized or "error response from daemon" in normalized


def _decode_subprocess(result: subprocess.CompletedProcess[bytes]) -> str:
    return _format_process_output(
        result.stdout.decode("utf-8", errors="replace"),
        result.stderr.decode("utf-8", errors="replace"),
    ).strip()
