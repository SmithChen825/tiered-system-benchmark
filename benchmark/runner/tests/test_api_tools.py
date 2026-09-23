from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmark.runner.api_wrapper.contracts import ToolCall, ToolCommandTimeout
from benchmark.runner.api_wrapper.tools import (
    ClarificationPolicy,
    CommandResult,
    DockerCommandSandbox,
    SandboxedLogicalToolExecutor,
    _classify_clarification_request,
)
from benchmark.runner.common import REPOSITORY_ROOT, TASKS_ROOT, load_json


class FakeCommandSandbox:
    def __init__(self, result: CommandResult | None = None, error: Exception | None = None):
        self.result = result or CommandResult(0, "ok")
        self.error = error
        self.calls = []

    def run(self, *, workspace, command, timeout_seconds):
        self.calls.append((workspace, command, timeout_seconds))
        if self.error:
            raise self.error
        return self.result


class FakeProcess:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", exit_code: int = 0):
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.exit_code = exit_code
        self.returncode = exit_code
        self.killed = False

    def wait(self, timeout=None):
        return self.exit_code

    def kill(self):
        self.killed = True


class ApiToolTests(unittest.TestCase):
    def setUp(self) -> None:
        parent = REPOSITORY_ROOT / "tmp"
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="api-tools-", dir=parent)
        self.root = Path(self.temporary.name).resolve()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.fake_sandbox = FakeCommandSandbox()
        self.executor = SandboxedLogicalToolExecutor(
            command_sandbox=self.fake_sandbox,
            max_read_bytes=16,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def execute(self, name: str, arguments: dict):
        return self.executor.execute(
            ToolCall("call-1", name, arguments),
            workspace=self.workspace,
            command_timeout_seconds=180,
        )

    def test_read_file_reads_utf8_and_reports_deterministic_truncation(self) -> None:
        (self.workspace / "hello.txt").write_text("0123456789abcdefghij", encoding="utf-8")
        result = self.execute("read_file", {"path": "hello.txt"})
        self.assertFalse(result.is_error)
        self.assertIn("0123456789abcdef", result.output)
        self.assertIn("file truncated", result.output)
        self.assertTrue(result.metadata["output_truncated"])

    def test_read_file_rejects_absolute_traversal_binary_and_extra_arguments(self) -> None:
        (self.workspace / "binary.bin").write_bytes(b"\xff\xfe")
        for arguments in (
            {"path": "../outside.txt"},
            {"path": str((self.root / "outside.txt").resolve())},
            {"path": "binary.bin"},
            {"path": "hello.txt", "encoding": "utf-8"},
        ):
            with self.subTest(arguments=arguments):
                self.assertTrue(self.execute("read_file", arguments).is_error)

    def test_read_file_rejects_symbolic_link_components_when_supported(self) -> None:
        outside = self.root / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        link = self.workspace / "link.txt"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("Symbolic links require unavailable Windows privileges")
        result = self.execute("read_file", {"path": "link.txt"})
        self.assertTrue(result.is_error)
        self.assertNotIn("secret", result.output)

    def test_patch_file_applies_bounded_unified_diff(self) -> None:
        target = self.workspace / "hello.txt"
        target.write_text("old\n", encoding="utf-8")
        patch_text = """diff --git a/hello.txt b/hello.txt
--- a/hello.txt
+++ b/hello.txt
@@ -1 +1 @@
-old
+new
"""
        result = self.execute("patch_file", {"patch": patch_text})
        self.assertFalse(result.is_error, result.output)
        self.assertEqual(target.read_text(encoding="utf-8"), "new\n")
        self.assertEqual(result.metadata["affected_paths"], ["hello.txt"])

    def test_patch_file_rejects_traversal_git_metadata_and_unsafe_modes(self) -> None:
        patches = (
            "diff --git a/../outside.txt b/../outside.txt\n",
            "diff --git a/.git/config b/.git/config\n",
            "diff --git a/link b/link\nnew file mode 120000\n",
            "diff --git a/a b/b\nrename from a\nrename to b\n",
        )
        for patch_text in patches:
            with self.subTest(patch_text=patch_text):
                self.assertTrue(self.execute("patch_file", {"patch": patch_text}).is_error)

    def test_patch_file_rejects_invalid_or_oversized_patches_without_changes(self) -> None:
        target = self.workspace / "hello.txt"
        target.write_text("old\n", encoding="utf-8")
        invalid = """diff --git a/hello.txt b/hello.txt
--- a/hello.txt
+++ b/hello.txt
@@ -1 +1 @@
-not-old
+new
"""
        self.assertTrue(self.execute("patch_file", {"patch": invalid}).is_error)
        self.assertEqual(target.read_text(encoding="utf-8"), "old\n")
        limited = SandboxedLogicalToolExecutor(
            command_sandbox=self.fake_sandbox,
            max_patch_bytes=8,
        )
        oversized = limited.execute(
            ToolCall("patch", "patch_file", {"patch": invalid}),
            workspace=self.workspace,
            command_timeout_seconds=180,
        )
        self.assertTrue(oversized.is_error)

    def test_execute_bash_delegates_only_to_command_sandbox(self) -> None:
        self.fake_sandbox.result = CommandResult(7, "failure", output_truncated=True)
        result = self.execute("execute_bash", {"command": "pytest -q"})
        self.assertTrue(result.is_error)
        self.assertIn("process exited with code 7", result.output)
        self.assertEqual(
            self.fake_sandbox.calls,
            [(self.workspace, "pytest -q", 180)],
        )
        self.assertTrue(result.metadata["output_truncated"])

    def test_execute_bash_preserves_command_timeout_transition(self) -> None:
        self.fake_sandbox.error = ToolCommandTimeout("timeout", output="partial")
        with self.assertRaises(ToolCommandTimeout):
            self.execute("execute_bash", {"command": "sleep 200"})

    def test_malformed_normalized_arguments_are_returned_as_tool_errors(self) -> None:
        result = self.executor.execute(
            ToolCall(
                "bad",
                "read_file",
                {},
                argument_error="arguments_invalid_json",
            ),
            workspace=self.workspace,
            command_timeout_seconds=180,
        )
        self.assertTrue(result.is_error)
        self.assertIn("Malformed tool arguments", result.output)
        self.assertEqual(result.metadata["argument_error"], "arguments_invalid_json")

    def test_docker_backend_has_only_workspace_mount_and_security_limits(self) -> None:
        (self.workspace / ".git").mkdir()
        fake_process = FakeProcess(stdout=b"safe\n")
        backend = DockerCommandSandbox(image="frozen-image@sha256:abc")
        with patch(
            "benchmark.runner.api_wrapper.tools.subprocess.Popen",
            return_value=fake_process,
        ) as popen:
            result = backend.run(
                workspace=self.workspace,
                command="pwd",
                timeout_seconds=10,
            )
        arguments = popen.call_args.args[0]
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--read-only", arguments)
        self.assertIn("no-new-privileges=true", arguments)
        self.assertIn("ALL", arguments)
        self.assertEqual(arguments[arguments.index("--network") + 1], "none")
        mounts = [
            value
            for index, value in enumerate(arguments)
            if arguments[index - 1 : index] == ["--mount"]
        ]
        self.assertEqual(len(mounts), 2)
        self.assertIn(str(self.workspace), mounts[0])
        self.assertIn("target=/workspace/.git,readonly", mounts[1])
        self.assertNotIn("docker.sock", " ".join(arguments))

    def test_clarification_authorizes_once_without_exposing_policy_on_rejection(self) -> None:
        policy_path = TASKS_ROOT / "L2-02" / "clarification_policy.json"
        executor = SandboxedLogicalToolExecutor(
            command_sandbox=self.fake_sandbox,
            clarification_policy=ClarificationPolicy.load(policy_path),
        )
        rejected = executor.execute(
            ToolCall("one", "request_human_clarification", {"request": "Which file should I modify?"}),
            workspace=self.workspace,
            command_timeout_seconds=180,
        )
        self.assertFalse(rejected.metadata["clarification"]["authorized"])
        self.assertNotIn("due_date is optional", rejected.output)
        accepted = executor.execute(
            ToolCall(
                "two",
                "request_human_clarification",
                {"request": "May a task be created without a due date?"},
            ),
            workspace=self.workspace,
            command_timeout_seconds=180,
        )
        self.assertTrue(accepted.metadata["clarification"]["authorized"])
        self.assertEqual(
            accepted.metadata["clarification"]["response_card_id"], "L2-02-R1"
        )
        duplicate = executor.execute(
            ToolCall(
                "three",
                "request_human_clarification",
                {"request": "Is due_date required?"},
            ),
            workspace=self.workspace,
            command_timeout_seconds=180,
        )
        self.assertEqual(
            duplicate.metadata["clarification"]["reason_code"], "DUPLICATE_REQUEST"
        )
        self.assertNotIn("due_date is optional", duplicate.output)

    def test_frozen_clarification_examples_are_classified_consistently(self) -> None:
        policy = load_json(TASKS_ROOT / "L2-02" / "clarification_policy.json")
        for request in policy["accepted_examples"]:
            with self.subTest(accepted=request):
                qualifying, reason = _classify_clarification_request(request)
                self.assertTrue(qualifying)
                self.assertEqual(reason, "QUALIFYING_DUE_DATE_RULE")
        for example in policy["rejected_examples"]:
            with self.subTest(rejected=example["request"]):
                qualifying, reason = _classify_clarification_request(example["request"])
                self.assertFalse(qualifying)
                self.assertEqual(reason, example["reason_code"])

    def test_complete_brief_task_never_receives_information(self) -> None:
        executor = SandboxedLogicalToolExecutor.for_task(
            "L1-01", command_sandbox=self.fake_sandbox
        )
        result = executor.execute(
            ToolCall(
                "clarify",
                "request_human_clarification",
                {"request": "Is due_date optional?"},
            ),
            workspace=self.workspace,
            command_timeout_seconds=180,
        )
        self.assertFalse(result.metadata["clarification"]["authorized"])
        self.assertFalse(result.metadata["clarification"]["response_issued"])


if __name__ == "__main__":
    unittest.main()
