from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol


@dataclass(frozen=True, slots=True)
class ExecResult:
    success: bool
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True, slots=True)
class RecordedCommand:
    command: tuple[str, ...]
    user: str | None


class RecordingSandbox:
    def __init__(self) -> None:
        self.commands: list[RecordedCommand] = []
        self.executable_paths: set[str] = set()
        self.writes: list[tuple[str, bytes]] = []

    async def exec(self, cmd: list[str], user: str | None = None) -> ExecResult:
        self.commands.append(RecordedCommand(command=tuple(cmd), user=user))
        shell_command = cmd[-1]
        if shell_command.startswith("test -x "):
            path = shell_command.removeprefix("test -x ")
            return ExecResult(success=path in self.executable_paths)
        if shell_command.startswith("chmod 0755 "):
            self.executable_paths.add(shell_command.removeprefix("chmod 0755 "))
        return ExecResult(success=True)

    async def write_file(self, path: str, contents: bytes) -> None:
        self.writes.append((path, contents))


class FlowResponse(Protocol):
    status_code: int
    content: bytes
    headers: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class FakeRequest:
    pretty_host: str
    path: str
    content: bytes


@dataclass(slots=True)
class FakeFlow:
    request: FakeRequest
    response: FlowResponse | None = None


class FakeResponse:
    status_code: int = 200
    content: bytes = b"data: {}\n\n"
    headers: dict[str, str] = {"content-type": "text/event-stream"}
