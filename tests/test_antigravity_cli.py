from __future__ import annotations

import importlib
from types import ModuleType

import anyio
import pytest
from inspect_ai.agent import Agent, AgentState
from inspect_ai.model import ChatMessageUser
from inspect_ai.tool import MCPServerConfigStdio
from inspect_ai.tool._mcp._config import MCPServerConfigHTTP

from ._support import ExecResult, RecordingSandbox


def _antigravity_module() -> ModuleType:
    try:
        return importlib.import_module("inspect_antigravity.antigravity_cli")
    except ModuleNotFoundError:
        pytest.fail("the Antigravity CLI agent module has not been implemented")


def test_resolve_mcp_servers_stdio() -> None:
    agent_module = _antigravity_module()
    server = MCPServerConfigStdio(
        name="taiga-mcp",
        command="/opt/venv/bin/browser_injections",
        args=["mcp"],
    )

    result = agent_module.resolve_mcp_servers_antigravity([server])

    assert result == (
        "{\n"
        '  "mcpServers": {\n'
        '    "taiga-mcp": {\n'
        '      "command": "/opt/venv/bin/browser_injections",\n'
        '      "args": [\n'
        '        "mcp"\n'
        "      ]\n"
        "    }\n"
        "  }\n"
        "}"
    )


def test_resolve_mcp_servers_http_uses_server_url() -> None:
    agent_module = _antigravity_module()
    server = MCPServerConfigHTTP(
        name="remote", type="http", url="https://mcp.example.test"
    )

    result = agent_module.resolve_mcp_servers_antigravity([server])

    assert result == (
        "{\n"
        '  "mcpServers": {\n'
        '    "remote": {\n'
        '      "serverUrl": "https://mcp.example.test"\n'
        "    }\n"
        "  }\n"
        "}"
    )


def test_agent_env_no_base_url_dynamic_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    async def exercise() -> None:
        agent_module = _antigravity_module()
        captured: dict[str, int | str | bool] = {}

        class FakeStore:
            def get(self, _: str, default: int) -> int:
                return default

            def set(self, _: str, value: int) -> None:
                captured["stored_bridge_port"] = value

        class FakeBridge:
            port = 24680

            def __init__(self, state: AgentState) -> None:
                self.state = state

            async def __aenter__(self) -> FakeBridge:
                return self

            async def __aexit__(self, *_: object) -> None:
                return None

        class FakeProcess:
            async def kill(self) -> None:
                captured["proxy_killed"] = True

        class FakeMonitor:
            def cancel(self) -> None:
                captured["monitor_cancelled"] = True

        class AgentSandbox(RecordingSandbox):
            async def exec_remote(
                self, *, cmd: list[str], options: object, stream: bool
            ) -> ExecResult:
                captured["https_proxy"] = options.env["HTTPS_PROXY"]
                captured["has_base_url"] = "GOOGLE_GEMINI_BASE_URL" in options.env
                return ExecResult(success=True)

        sandbox = AgentSandbox()

        def fake_bridge(state: AgentState, **_: object) -> FakeBridge:
            return FakeBridge(state)

        async def fake_ensure_cli(*_: object, **__: object) -> str:
            return "/usr/local/bin/agy"

        async def fake_provision_home(*_: object, **__: object) -> str:
            return "/root/.gemini/antigravity-cli"

        async def fake_ensure_mitmproxy(*_: object, **__: object) -> str:
            return "/usr/local/bin/mitmdump"

        async def fake_detect_sandbox_platform(_: RecordingSandbox) -> str:
            return "linux-x64"

        async def fake_start_interceptor(
            _: RecordingSandbox,
            *,
            listen_port: int,
            bridge_port: int,
            confdir: str,
            user: str | None,
        ) -> tuple[FakeProcess, str, FakeMonitor]:
            captured["intercept_port"] = listen_port
            captured["bridge_port"] = bridge_port
            captured["confdir"] = confdir
            captured["interceptor_user"] = user or ""
            return FakeProcess(), "/root/mitmproxy-ca-cert.pem", FakeMonitor()

        monkeypatch.setattr(agent_module, "store", lambda: FakeStore())
        monkeypatch.setattr(agent_module, "sandbox_agent_bridge", fake_bridge)
        monkeypatch.setattr(agent_module, "sandbox_env", lambda _: sandbox)
        monkeypatch.setattr(
            agent_module, "detect_sandbox_platform", fake_detect_sandbox_platform
        )
        monkeypatch.setattr(
            agent_module, "ensure_antigravity_cli_setup", fake_ensure_cli
        )
        monkeypatch.setattr(
            agent_module, "provision_antigravity_home", fake_provision_home
        )
        monkeypatch.setattr(agent_module, "ensure_mitmproxy", fake_ensure_mitmproxy)
        monkeypatch.setattr(agent_module, "start_interceptor", fake_start_interceptor)
        monkeypatch.setattr(agent_module, "trace", lambda _: None)

        agent = agent_module.antigravity_cli()
        await agent(AgentState(messages=[ChatMessageUser(content="Solve the task")]))

        assert captured["stored_bridge_port"] == 3001
        assert captured["intercept_port"] == 8001
        assert captured["bridge_port"] == 24680
        assert captured["https_proxy"] == "http://127.0.0.1:8001"
        assert captured["has_base_url"] is False
        assert captured["monitor_cancelled"] is True
        assert captured["proxy_killed"] is True

    anyio.run(exercise)


def test_antigravity_cli_returns_an_agent() -> None:
    result = _antigravity_module().antigravity_cli()

    assert isinstance(result, Agent)
