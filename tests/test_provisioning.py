from __future__ import annotations

import io
import tarfile
from pathlib import Path

import anyio
import pytest

from inspect_antigravity._util.sandbox import SANDBOX_INSTALL_DIR
from inspect_antigravity.agentbinary import (
    ensure_antigravity_cli_setup,
    provision_antigravity_home,
)
from inspect_antigravity.interceptor import (
    MITMDUMP_PATH,
    MITMPROXY_ARCHIVE_PATH,
    MITMPROXY_INSTALL_DIR,
    ensure_mitmproxy,
)

from ._support import ExecResult, RecordedCommand, RecordingSandbox


def test_ensure_antigravity_cli_setup_writes_an_executable_once(tmp_path: Path) -> None:
    async def provision() -> None:
        binary_source = tmp_path / "antigravity"
        binary_data = b"agy-binary"
        binary_source.write_bytes(binary_data)
        sandbox = RecordingSandbox()
        agy_path = f"{SANDBOX_INSTALL_DIR}/antigravity-cli/agy"

        result = await ensure_antigravity_cli_setup(
            sandbox,
            binary_source=str(binary_source),
            user="root",
        )

        assert result == agy_path
        assert sandbox.writes == [(agy_path, binary_data)]
        assert (
            RecordedCommand(
                command=("bash", "-c", f"chmod 0755 {agy_path}"),
                user="root",
            )
            in sandbox.commands
        )

        result = await ensure_antigravity_cli_setup(
            sandbox,
            binary_source=str(binary_source),
            user="root",
        )

        assert result == agy_path
        assert sandbox.writes == [(agy_path, binary_data)]

    anyio.run(provision)


def test_provision_antigravity_home_archives_only_runtime_tokens(
    tmp_path: Path,
) -> None:
    async def provision() -> None:
        token_source = tmp_path / "antigravity-cli"
        token_source.mkdir()
        (token_source / "antigravity-oauth-token").write_text(
            "test-token", encoding="utf-8"
        )
        for excluded_directory in (
            "log",
            "cache",
            "crashes",
            "conversations",
            "scratch",
        ):
            directory = token_source / excluded_directory
            directory.mkdir()
            (directory / "ignored.txt").write_text("ignored", encoding="utf-8")

        sandbox = RecordingSandbox()
        result = await provision_antigravity_home(
            sandbox,
            sandbox_home="/root",
            token_source=str(token_source),
            user="root",
        )

        archive_path, archive_data = sandbox.writes[0]
        with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:gz") as archive:
            archive_names = archive.getnames()

        assert archive_path == "/tmp/antigravity-cli-home.tgz"
        assert result == "/root/.gemini/antigravity-cli"
        assert "antigravity-cli/antigravity-oauth-token" in archive_names
        assert not any(
            excluded_directory in Path(name).parts
            for name in archive_names
            for excluded_directory in (
                "log",
                "cache",
                "crashes",
                "conversations",
                "scratch",
            )
        )
        assert (
            RecordedCommand(
                command=("bash", "-c", "mkdir -p /root/.gemini"),
                user="root",
            )
            in sandbox.commands
        )
        assert (
            RecordedCommand(
                command=(
                    "bash",
                    "-c",
                    f"tar -xzf {archive_path} -C /root/.gemini",
                ),
                user="root",
            )
            in sandbox.commands
        )

    anyio.run(provision)


def test_ensure_mitmproxy_extracts_flat_archive_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MitmproxySandbox(RecordingSandbox):
        async def exec(self, cmd: list[str], user: str | None = None) -> ExecResult:
            if cmd[-1].startswith("tar -xzf "):
                self.executable_paths.add(MITMDUMP_PATH)
            return await super().exec(cmd, user=user)

    async def download_file(_: str) -> bytes:
        return b"mitmproxy-archive"

    async def provision() -> None:
        monkeypatch.setattr(
            "inspect_antigravity.interceptor.download_file", download_file
        )
        sandbox = MitmproxySandbox()

        result = await ensure_mitmproxy(sandbox, "linux-x64", "root")

        assert result == MITMDUMP_PATH
        assert sandbox.writes == [(MITMPROXY_ARCHIVE_PATH, b"mitmproxy-archive")]
        assert (
            RecordedCommand(
                command=(
                    "bash",
                    "-c",
                    f"tar -xzf {MITMPROXY_ARCHIVE_PATH} -C {MITMPROXY_INSTALL_DIR} && rm -f {MITMPROXY_ARCHIVE_PATH}",
                ),
                user="root",
            )
            in sandbox.commands
        )
        assert not any(
            "--strip-components" in recorded.command[-1]
            for recorded in sandbox.commands
        )

        result = await ensure_mitmproxy(sandbox, "linux-x64", "root")

        assert result == MITMDUMP_PATH
        assert len(sandbox.writes) == 1
        assert sandbox.commands[-1] == RecordedCommand(
            command=("bash", "-c", f"test -x {MITMDUMP_PATH}"), user="root"
        )

    anyio.run(provision)


def test_start_interceptor_waits_for_listening_socket_before_returning() -> None:
    async def exercise() -> None:
        interceptor_module = __import__(
            "inspect_antigravity.interceptor", fromlist=["start_interceptor"]
        )

        class FakeProcess:
            def __aiter__(self) -> FakeProcess:
                return self

            async def __anext__(self) -> object:
                await anyio.sleep_forever()
                raise StopAsyncIteration

        class PortProbeSandbox(RecordingSandbox):
            def __init__(self) -> None:
                super().__init__()
                self.port_probe_attempts = 0

            async def exec_remote(
                self, *, cmd: list[str], options: object
            ) -> FakeProcess:
                return FakeProcess()

            async def exec(self, cmd: list[str], user: str | None = None) -> ExecResult:
                shell_command = cmd[-1]
                if "/dev/tcp/" in shell_command:
                    self.port_probe_attempts += 1
                    return ExecResult(success=self.port_probe_attempts >= 3)
                return await super().exec(cmd, user=user)

        sandbox = PortProbeSandbox()
        (
            process,
            ca_cert_path,
            monitor_task,
        ) = await interceptor_module.start_interceptor(
            sandbox,
            listen_port=8001,
            bridge_port=3001,
            confdir="/root/.mitmproxy-antigravity",
            user="root",
        )

        assert isinstance(process, FakeProcess)
        assert ca_cert_path == "/root/.mitmproxy-antigravity/mitmproxy-ca-cert.pem"
        assert sandbox.port_probe_attempts == 3
        monitor_task.cancel()

    anyio.run(exercise)
