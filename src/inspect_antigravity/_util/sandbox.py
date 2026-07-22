from typing import Literal, TypeAlias, cast

from inspect_ai.util import SandboxEnvironment

SandboxPlatform: TypeAlias = Literal[
    "linux-x64", "linux-arm64", "linux-x64-musl", "linux-arm64-musl"
]
"""Target platform identifier for sandbox binary downloads."""

SANDBOX_INSTALL_DIR = "/var/tmp/.5c95f967ca830048"


async def detect_sandbox_platform(sandbox: SandboxEnvironment) -> SandboxPlatform:
    os_name = await sandbox_exec(sandbox, "uname -s")
    if os_name != "Linux":
        raise ValueError(f"Unsupported OS: {os_name}")

    arch = await sandbox_exec(sandbox, "uname -m")
    if arch in ["x86_64", "amd64"]:
        arch_type = "x64"
    elif arch in ["arm64", "aarch64"]:
        arch_type = "arm64"
    else:
        raise ValueError(f"Unsupported architecture: {arch}")

    musl_check_cmd = (
        "if [ -f /lib/libc.musl-x86_64.so.1 ] || "
        "[ -f /lib/libc.musl-aarch64.so.1 ] || "
        "ldd /bin/ls 2>&1 | grep -q musl; then "
        "echo 'musl'; else echo 'glibc'; fi"
    )
    libc_type = await sandbox_exec(sandbox, musl_check_cmd)
    platform = (
        f"linux-{arch_type}-musl" if libc_type == "musl" else f"linux-{arch_type}"
    )
    return cast(SandboxPlatform, platform)


def bash_command(cmd: str) -> list[str]:
    return ["bash", "-c", cmd]


async def sandbox_exec(
    sandbox: SandboxEnvironment,
    cmd: str,
    user: str | None = None,
    cwd: str | None = None,
) -> str:
    result = await sandbox.exec(bash_command(cmd), user=user, cwd=cwd)
    if not result.success:
        raise RuntimeError(f"Error executing sandbox command {cmd}: {result.stderr}")
    return result.stdout.strip()
