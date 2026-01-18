from __future__ import annotations

import os
import re
import shutil
import threading
import sys
from pathlib import Path
from typing import List, Optional

from cursor_cli_manager.update import _default_runner


ENV_CURSOR_AGENT_PATH = "CURSOR_AGENT_PATH"

# Default cursor-agent flags we want enabled for interactive runs.
DEFAULT_CURSOR_AGENT_FLAGS = ["--approve-mcps", "--browser", "--force"]


_PROBE_LOCK = threading.Lock()
_PROBE_STARTED = False
_PROBED_CURSOR_AGENT_FLAGS: Optional[List[str]] = None

_FORCE_LOCK = threading.Lock()
_FORCE_SUPPORTED: Optional[bool] = None
_FORCE_SUPPORTED_AGENT: Optional[str] = None


def _help_supports_flag(help_text: str, flag: str) -> bool:
    # Match "--flag" as a standalone token in help output.
    # Allow common separators after a flag: whitespace, comma, "=", or "[".
    pat = r"(^|\s)" + re.escape(flag) + r"(\s|,|=|\[|$)"
    return bool(re.search(pat, help_text or "", flags=re.MULTILINE))


def start_cursor_agent_flag_probe(*, timeout_s: float = 1.0) -> None:
    """
    Best-effort, non-blocking probe to detect which optional flags are supported.

    This is intentionally async: if the probe hasn't finished when the user opens
    a chat, we do NOT block.
    """
    global _PROBE_STARTED
    with _PROBE_LOCK:
        if _PROBE_STARTED:
            return
        _PROBE_STARTED = True

    def _run() -> None:
        global _PROBED_CURSOR_AGENT_FLAGS
        try:
            agent = resolve_cursor_agent_path()
            if not agent:
                return
            rc, out, err = _default_runner([agent, "--help"], timeout_s)
            if rc != 0:
                # Leave as unknown; we will keep using defaults.
                return
            txt = (out or "") + ("\n" if out and err else "") + (err or "")
            supported: List[str] = []
            for flag in DEFAULT_CURSOR_AGENT_FLAGS:
                if _help_supports_flag(txt, flag):
                    supported.append(flag)
            _PROBED_CURSOR_AGENT_FLAGS = supported
        except Exception:
            return

    threading.Thread(target=_run, daemon=True).start()


def get_cursor_agent_flags() -> List[str]:
    """
    Optional flags to pass to cursor-agent (best-effort).
    """
    probed = _PROBED_CURSOR_AGENT_FLAGS
    return list(probed) if probed is not None else list(DEFAULT_CURSOR_AGENT_FLAGS)


def _supports_force_flag(agent: str, *, timeout_s: float = 1.0) -> bool:
    """
    Best-effort check whether the installed cursor-agent supports `--force`.

    We validate by invoking `agent --force --help`:
    - If it exits 0, the flag is accepted.
    - If it fails, we will avoid passing `--force` when launching a chat.
    """
    global _FORCE_SUPPORTED, _FORCE_SUPPORTED_AGENT
    cached = _FORCE_SUPPORTED
    if cached is not None and _FORCE_SUPPORTED_AGENT == agent:
        return cached
    with _FORCE_LOCK:
        cached = _FORCE_SUPPORTED
        if cached is not None and _FORCE_SUPPORTED_AGENT == agent:
            return cached
        ok = False
        try:
            rc, _out, _err = _default_runner([agent, "--force", "--help"], timeout_s)
            ok = rc == 0
        except Exception:
            ok = False
        _FORCE_SUPPORTED = ok
        _FORCE_SUPPORTED_AGENT = agent
        return ok


def _without_force_flag(cmd: List[str]) -> List[str]:
    return [c for c in cmd if c not in ("--force", "-f")]


def _prepare_exec_command(cmd: List[str]) -> List[str]:
    """
    Apply last-mile compatibility tweaks before exec'ing cursor-agent.
    """
    if "--force" in cmd or "-f" in cmd:
        agent = cmd[0] if cmd else ""
        if agent and not _supports_force_flag(agent):
            return _without_force_flag(cmd)
    return cmd


def resolve_cursor_agent_path(explicit: Optional[str] = None) -> Optional[str]:
    """
    Resolve the `cursor-agent` executable.

    Priority:
    - explicit arg
    - $CURSOR_AGENT_PATH
    - PATH lookup
    - ~/.local/bin/cursor-agent
    """
    if explicit:
        p = Path(explicit).expanduser()
        return str(p) if p.exists() else None

    env = os.environ.get(ENV_CURSOR_AGENT_PATH)
    if env:
        p = Path(env).expanduser()
        return str(p) if p.exists() else None

    found = shutil.which("cursor-agent")
    if found:
        return found

    default = Path.home() / ".local" / "bin" / "cursor-agent"
    if default.exists():
        return str(default)

    return None


def build_resume_command(
    chat_id: str,
    *,
    workspace_path: Optional[Path] = None,
    cursor_agent_path: Optional[str] = None,
) -> List[str]:
    agent = resolve_cursor_agent_path(cursor_agent_path)
    if not agent:
        raise RuntimeError("cursor-agent not found. Install it or set CURSOR_AGENT_PATH.")

    cmd: List[str] = [agent]
    if workspace_path is not None:
        cmd.extend(["--workspace", str(workspace_path)])
    cmd.extend(get_cursor_agent_flags())
    cmd.extend(["--resume", chat_id])
    return cmd


def build_new_command(
    *,
    workspace_path: Optional[Path] = None,
    cursor_agent_path: Optional[str] = None,
) -> List[str]:
    """
    Build a command that starts a new cursor-agent chat session.
    """
    agent = resolve_cursor_agent_path(cursor_agent_path)
    if not agent:
        raise RuntimeError("cursor-agent not found. Install it or set CURSOR_AGENT_PATH.")

    cmd: List[str] = [agent]
    if workspace_path is not None:
        cmd.extend(["--workspace", str(workspace_path)])
    cmd.extend(get_cursor_agent_flags())
    return cmd


def exec_resume_command(cmd: List[str]) -> "os.NoReturn":
    os.execvp(cmd[0], cmd)


def exec_resume_chat(
    chat_id: str,
    *,
    workspace_path: Optional[Path],
    cursor_agent_path: Optional[str] = None,
) -> "os.NoReturn":
    """
    Exec into cursor-agent and resume a chat session.

    Important: cursor-agent stores chats under ~/.cursor/chats/<md5(cwd)>,
    so we `chdir()` into the workspace path (when available) to ensure the
    correct chat store is used.
    """
    if workspace_path is not None:
        os.chdir(workspace_path)
    cmd = build_resume_command(chat_id, workspace_path=workspace_path, cursor_agent_path=cursor_agent_path)
    cmd = _prepare_exec_command(cmd)
    try:
        ws = f" in {workspace_path}" if workspace_path is not None else ""
        print(f"Launching cursor-agent{ws}… (resume {chat_id})", file=sys.stderr, flush=True)
    except Exception:
        pass
    os.execvp(cmd[0], cmd)


def exec_new_chat(
    *,
    workspace_path: Optional[Path],
    cursor_agent_path: Optional[str] = None,
) -> "os.NoReturn":
    """
    Exec into cursor-agent and start a new chat session.

    Similar to `exec_resume_chat`, we `chdir()` into the workspace to ensure the
    correct ~/.cursor/chats/<md5(cwd)> bucket is used.
    """
    if workspace_path is not None:
        os.chdir(workspace_path)
    cmd = build_new_command(workspace_path=workspace_path, cursor_agent_path=cursor_agent_path)
    cmd = _prepare_exec_command(cmd)
    try:
        ws = f" in {workspace_path}" if workspace_path is not None else ""
        print(f"Launching cursor-agent{ws}…", file=sys.stderr, flush=True)
    except Exception:
        pass
    os.execvp(cmd[0], cmd)

