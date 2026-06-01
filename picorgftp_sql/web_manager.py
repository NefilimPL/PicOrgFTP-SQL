"""Small Windows GUI for running and supervising the LAN web panel."""

from __future__ import annotations

import argparse
import ctypes
from datetime import datetime
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from .assets import set_tk_window_icon
from .assets import pic_asset_path
from .version import get_display_version


DEFAULT_PORT = int(os.environ.get("PICORG_WEB_PORT") or 8010)
DEFAULT_HOST = os.environ.get("PICORG_WEB_HOST") or "0.0.0.0"
TASK_NAME = "PicOrgFTP-SQL Web"
FIREWALL_RULE_NAME = "PicOrgFTP-SQL Web"


@dataclass
class ActionResult:
    ok: bool
    message: str


def app_root() -> Path:
    """Return the directory used for local settings, pid files and logs."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def pid_file(root: Path | None = None) -> Path:
    return (root or app_root()) / ".picorg_web.pid"


def log_dir(root: Path | None = None) -> Path:
    return (root or app_root()) / "logs"


def out_log_path(root: Path | None = None) -> Path:
    return log_dir(root) / "picorg_web_out.log"


def err_log_path(root: Path | None = None) -> Path:
    return log_dir(root) / "picorg_web_err.log"


def active_clients_path(root: Path | None = None) -> Path:
    return log_dir(root) / "web_active_clients.json"


def web_account_rows() -> list[tuple[str, str, str, str, str, str]]:
    try:
        from .web_data import load_users

        users = load_users()
    except Exception as exc:
        return [("blad", "", "", str(exc), "", "")]
    rows: list[tuple[str, str, str, str, str, str]] = []
    for user in users:
        locked = bool(user.get("locked"))
        if locked and user.get("lock_manual"):
            lock_text = "reczne odblokowanie"
        elif locked:
            lock_text = f"do {user.get('lock_expires_at') or '-'}"
        else:
            lock_text = "nie"
        last_parts = [
            str(user.get("last_failed_login_at") or ""),
            str(user.get("last_failed_login_ip") or ""),
        ]
        rows.append(
            (
                str(user.get("username") or ""),
                str(user.get("role") or ""),
                "tak" if user.get("enabled") else "nie",
                lock_text,
                str(user.get("failed_login_count") or 0),
                " / ".join(part for part in last_parts if part) or "-",
            )
        )
    return rows or [("brak", "", "", "", "", "")]


def unlock_web_account(username: str) -> ActionResult:
    if not username or username in {"brak", "blad"}:
        return ActionResult(False, "Wybierz konto do odblokowania.")
    try:
        from .logging_utils import log_info
        from .web_data import unlock_user

        unlock_user(username)
        log_info(f"WEB admin unlock account from starter panel: {username}")
    except Exception as exc:
        return ActionResult(False, f"Nie udalo sie odblokowac konta {username}: {exc}")
    return ActionResult(True, f"Odblokowano konto {username}.")


def _creationflags() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0


def _run_command(args: list[str], *, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=_creationflags(),
    )


def _tail_text(path: Path, *, line_count: int = 8, max_chars: int = 1200) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    relevant = [line.strip() for line in lines if line.strip()]
    text = "\n".join(relevant[-line_count:]).strip()
    if len(text) > max_chars:
        return text[-max_chars:].strip()
    return text


def _startup_error_hint(root: Path) -> str:
    error_tail = _tail_text(err_log_path(root))
    if not error_tail:
        return f"Sprawdz log: {err_log_path(root)}"
    if "Could not import module" in error_tail:
        return (
            "Backend webowy nie zostal zaladowany z pliku EXE. "
            "Przebuduj PicOrgFTP-SQL-WEB.exe aktualnym generatorem albo GitHub Actions. "
            f"Ostatni blad: {error_tail}"
        )
    return f"Ostatni blad: {error_tail}"


def _powershell_json(script: str, *, timeout: int = 8) -> Any:
    try:
        result = _run_command(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        return [payload]
    return payload if isinstance(payload, list) else []


def is_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def read_metadata(root: Path | None = None) -> dict[str, Any]:
    path = pid_file(root)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="ascii"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_metadata(port: int, host: str, *, launcher: str) -> None:
    root = app_root()
    payload = {
        "pid": os.getpid(),
        "port": int(port),
        "host": host,
        "launcher": launcher,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "firewall_rule_name": FIREWALL_RULE_NAME,
        "firewall_rule_created": False,
        "firewall_remove_on_stop": False,
    }
    pid_file(root).write_text(json.dumps(payload, indent=2), encoding="ascii")


def remove_metadata_for_current_process() -> None:
    path = pid_file()
    data = read_metadata()
    if _safe_int(data.get("pid")) == os.getpid():
        try:
            path.unlink()
        except OSError:
            pass


def get_process_command_line(pid: int) -> str:
    pid = int(pid)
    if pid <= 0:
        return ""
    if os.name == "nt":
        script = (
            "$p = Get-CimInstance Win32_Process -Filter "
            f"\"ProcessId = {pid}\" -ErrorAction SilentlyContinue; "
            "if ($p) { $p.CommandLine }"
        )
        try:
            result = _run_command(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    script,
                ],
                timeout=5,
            )
            return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    proc_path = Path("/proc") / str(pid) / "cmdline"
    try:
        return proc_path.read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="replace")
    except OSError:
        return ""


def is_web_process(pid: int, command_line: str = "", process_name: str = "") -> bool:
    text = f"{command_line} {process_name}".lower()
    markers = (
        "picorgftp_sql.web.app",
        "picorgftp-sql-web",
        "picorgftp_sql.web_manager",
        "--service-run",
    )
    return any(marker in text for marker in markers)


def _parse_netstat_listeners(port: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    try:
        result = _run_command(["netstat", "-ano"], timeout=8)
    except (OSError, subprocess.SubprocessError):
        return items
    pattern = re.compile(rf"^\s*TCP\s+(\S+):{port}\s+\S+\s+LISTENING\s+(\d+)\s*$", re.I)
    for line in result.stdout.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        pid_value = _safe_int(match.group(2))
        items.append(
            {
                "LocalAddress": match.group(1),
                "LocalPort": port,
                "Pid": pid_value,
                "ProcessName": "",
                "CommandLine": get_process_command_line(pid_value),
            }
        )
    return items


def get_port_listeners(port: int) -> list[dict[str, Any]]:
    if os.name == "nt":
        script = rf"""
$items = Get-NetTCPConnection -LocalPort {int(port)} -State Listen -ErrorAction SilentlyContinue | ForEach-Object {{
    $proc = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.OwningProcess)" -ErrorAction SilentlyContinue).CommandLine
    [pscustomobject]@{{
        LocalAddress = [string]$_.LocalAddress
        LocalPort = [int]$_.LocalPort
        Pid = [int]$_.OwningProcess
        ProcessName = if ($proc) {{ [string]$proc.ProcessName }} else {{ "" }}
        CommandLine = if ($cmd) {{ [string]$cmd }} else {{ "" }}
    }}
}}
$items | ConvertTo-Json -Depth 4
"""
        payload = _powershell_json(script)
        if payload:
            return [item for item in payload if isinstance(item, dict)]
    return _parse_netstat_listeners(port)


def get_established_connections(port: int) -> list[dict[str, Any]]:
    if os.name == "nt":
        script = rf"""
$items = Get-NetTCPConnection -LocalPort {int(port)} -State Established -ErrorAction SilentlyContinue | ForEach-Object {{
    [pscustomobject]@{{
        LocalAddress = [string]$_.LocalAddress
        LocalPort = [int]$_.LocalPort
        RemoteAddress = [string]$_.RemoteAddress
        RemotePort = [int]$_.RemotePort
        State = [string]$_.State
        Pid = [int]$_.OwningProcess
    }}
}}
$items | ConvertTo-Json -Depth 4
"""
        payload = _powershell_json(script)
        if payload:
            return [item for item in payload if isinstance(item, dict)]
    return []


def local_url(port: int) -> str:
    return f"http://127.0.0.1:{int(port)}"


def lan_urls(port: int) -> list[str]:
    addresses: set[str] = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            address = str(info[4][0])
            if not address.startswith(("127.", "169.254.")):
                addresses.add(address)
    except OSError:
        pass
    if not addresses and os.name == "nt":
        try:
            result = _run_command(["ipconfig"], timeout=8)
            for address in re.findall(r"IPv4[^:\r\n]*:\s*([0-9.]+)", result.stdout):
                if not address.startswith(("127.", "169.254.")):
                    addresses.add(address)
        except (OSError, subprocess.SubprocessError):
            pass
    return [f"http://{address}:{int(port)}" for address in sorted(addresses)]


def check_http_health(port: int, *, timeout: float = 1.5) -> dict[str, Any]:
    url = f"{local_url(port)}/api/health"
    try:
        with urlopen(url, timeout=timeout) as response:
            raw = response.read(4096).decode("utf-8", errors="replace")
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {"ok": True}
    except (OSError, URLError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}


def wait_web_ready(port: int, *, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check_http_health(port, timeout=1.0).get("ok"):
            return True
        time.sleep(0.5)
    return False


def task_exists() -> bool:
    if os.name != "nt":
        return False
    try:
        result = _run_command(["schtasks", "/Query", "/TN", TASK_NAME], timeout=10)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def task_enabled() -> bool:
    if os.name != "nt" or not task_exists():
        return False
    try:
        result = _run_command(["schtasks", "/Query", "/TN", TASK_NAME, "/XML"], timeout=10)
    except (OSError, subprocess.SubprocessError):
        return True
    if result.returncode != 0:
        return True
    match = re.search(r"<Enabled>\s*(true|false)\s*</Enabled>", result.stdout, re.I)
    if not match:
        return True
    return match.group(1).lower() == "true"


def _pythonw_executable() -> str:
    exe = Path(sys.executable)
    if exe.name.lower() == "python.exe":
        candidate = exe.with_name("pythonw.exe")
        if candidate.exists():
            return str(candidate)
    return str(exe)


def service_command_parts(port: int, host: str) -> list[str]:
    root = app_root()
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve()), "--service-run", "--port", str(port), "--host", host]
    return [
        _pythonw_executable(),
        str(root / "PicOrgFTP-SQL-WEB.pyw"),
        "--service-run",
        "--port",
        str(port),
        "--host",
        host,
    ]


def ensure_firewall_rule(port: int) -> None:
    if os.name != "nt" or not is_admin():
        return
    show = _run_command(
        ["netsh", "advfirewall", "firewall", "show", "rule", f"name={FIREWALL_RULE_NAME}"],
        timeout=10,
    )
    if show.returncode == 0:
        return
    _run_command(
        [
            "netsh",
            "advfirewall",
            "firewall",
            "add",
            "rule",
            f"name={FIREWALL_RULE_NAME}",
            "dir=in",
            "action=allow",
            "protocol=TCP",
            f"localport={int(port)}",
        ],
        timeout=10,
    )


def install_system_service(port: int, host: str) -> ActionResult:
    if os.name != "nt":
        return ActionResult(False, "Usluga systemowa jest dostepna tylko na Windows.")
    if not is_admin():
        return ActionResult(False, "Uruchom WEB EXE jako administrator, zeby zainstalowac usluge SYSTEM.")
    command = subprocess.list2cmdline(service_command_parts(port, host))
    result = _run_command(
        [
            "schtasks",
            "/Create",
            "/TN",
            TASK_NAME,
            "/SC",
            "ONSTART",
            "/RU",
            "SYSTEM",
            "/RL",
            "HIGHEST",
            "/TR",
            command,
            "/F",
        ],
        timeout=30,
    )
    if result.returncode != 0:
        return ActionResult(False, (result.stderr or result.stdout or "Nie udalo sie utworzyc zadania.").strip())
    ensure_firewall_rule(port)
    return ActionResult(True, "Zainstalowano usluge systemowa SYSTEM.")


def remove_system_service() -> ActionResult:
    if os.name != "nt":
        return ActionResult(False, "Usluga systemowa jest dostepna tylko na Windows.")
    if not task_exists():
        return ActionResult(True, "Usluga nie byla zainstalowana.")
    if not is_admin():
        return ActionResult(False, "Uruchom WEB EXE jako administrator, zeby usunac usluge SYSTEM.")
    result = _run_command(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], timeout=20)
    if result.returncode != 0:
        return ActionResult(False, (result.stderr or result.stdout or "Nie udalo sie usunac zadania.").strip())
    return ActionResult(True, "Usunieto usluge systemowa.")


def set_system_service_enabled(enabled: bool) -> ActionResult:
    if os.name != "nt":
        return ActionResult(False, "Autostart uslugi jest dostepny tylko na Windows.")
    if not task_exists():
        return ActionResult(False, "Najpierw zainstaluj usluge systemowa.")
    if not is_admin():
        return ActionResult(False, "Uruchom WEB EXE jako administrator, zeby zmienic autostart.")
    flag = "/ENABLE" if enabled else "/DISABLE"
    result = _run_command(["schtasks", "/Change", "/TN", TASK_NAME, flag], timeout=20)
    if result.returncode != 0:
        return ActionResult(False, (result.stderr or result.stdout or "Nie udalo sie zmienic autostartu.").strip())
    return ActionResult(True, "Autostart wlaczony." if enabled else "Autostart wylaczony.")


def run_system_service() -> ActionResult:
    if os.name != "nt" or not task_exists():
        return ActionResult(False, "Usluga systemowa nie jest zainstalowana.")
    result = _run_command(["schtasks", "/Run", "/TN", TASK_NAME], timeout=20)
    if result.returncode != 0:
        return ActionResult(False, (result.stderr or result.stdout or "Nie udalo sie uruchomic uslugi.").strip())
    return ActionResult(True, "Uruchomiono zadanie uslugi systemowej.")


def end_system_service() -> None:
    if os.name != "nt" or not task_exists():
        return
    try:
        _run_command(["schtasks", "/End", "/TN", TASK_NAME], timeout=15)
    except (OSError, subprocess.SubprocessError):
        pass


def start_user_web(port: int, host: str) -> ActionResult:
    root = app_root()
    log_dir(root).mkdir(parents=True, exist_ok=True)
    ensure_firewall_rule(port)
    env = os.environ.copy()
    env["PICORGFTP_SQL_HEADLESS"] = "1"
    env["PICORG_WEB_PORT"] = str(port)
    env["PICORG_WEB_HOST"] = host
    args = service_command_parts(port, host)
    out_handle = out_log_path(root).open("a", encoding="utf-8", buffering=1)
    err_handle = err_log_path(root).open("a", encoding="utf-8", buffering=1)
    try:
        process = subprocess.Popen(
            args,
            cwd=str(root),
            env=env,
            stdout=out_handle,
            stderr=err_handle,
            stdin=subprocess.DEVNULL,
            creationflags=_creationflags(),
            close_fds=True,
        )
    except OSError as exc:
        return ActionResult(False, f"Nie udalo sie uruchomic panelu: {exc}")
    finally:
        try:
            out_handle.close()
            err_handle.close()
        except OSError:
            pass
    if wait_web_ready(port):
        return ActionResult(True, "Panel webowy zostal uruchomiony.")
    exit_code = process.poll()
    if exit_code is not None:
        return ActionResult(
            False,
            f"Panel zamknal sie przy starcie (kod {exit_code}). {_startup_error_hint(root)}",
        )
    return ActionResult(
        False,
        f"Proces dziala, ale strona nie odpowiedziala w limicie czasu. {_startup_error_hint(root)}",
    )


def start_web(port: int, host: str, *, prefer_system_service: bool = True) -> ActionResult:
    listeners = get_port_listeners(port)
    web_listeners = [
        item
        for item in listeners
        if is_web_process(
            _safe_int(item.get("Pid")),
            str(item.get("CommandLine") or ""),
            str(item.get("ProcessName") or ""),
        )
    ]
    if web_listeners and check_http_health(port).get("ok"):
        return ActionResult(True, "Panel webowy juz dziala.")
    if prefer_system_service and task_exists():
        result = run_system_service()
        if result.ok and wait_web_ready(port):
            return ActionResult(True, "Panel webowy dziala jako usluga systemowa.")
        if result.ok:
            return ActionResult(False, "Uruchomiono usluge, ale strona nie odpowiedziala w limicie czasu.")
    return start_user_web(port, host)


def stop_web(port: int) -> ActionResult:
    end_system_service()
    stopped = False
    data = read_metadata()
    candidates = []
    if data.get("pid"):
        candidates.append(_safe_int(data.get("pid")))
    for listener in get_port_listeners(port):
        candidates.append(_safe_int(listener.get("Pid")))
    for pid_value in sorted({pid for pid in candidates if pid > 0}):
        command_line = get_process_command_line(pid_value)
        if not is_web_process(pid_value, command_line):
            continue
        try:
            if os.name == "nt":
                _run_command(["taskkill", "/PID", str(pid_value), "/T", "/F"], timeout=10)
            else:
                os.kill(pid_value, 15)
            stopped = True
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        pid_file().unlink()
    except OSError:
        pass
    if stopped:
        return ActionResult(True, "Zatrzymano panel webowy.")
    return ActionResult(True, "Panel webowy nie byl uruchomiony albo dziala inna usluga na tym porcie.")


def read_active_clients(root: Path | None = None, *, max_age_seconds: int = 180) -> list[dict[str, Any]]:
    path = active_clients_path(root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    now = time.time()
    clients = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            last_seen = float(item.get("last_seen_epoch") or 0)
        except (TypeError, ValueError):
            continue
        if last_seen and now - last_seen > max_age_seconds:
            continue
        clients.append(item)
    clients.sort(key=lambda item: float(item.get("last_seen_epoch") or 0), reverse=True)
    return clients


def current_status(port: int) -> dict[str, Any]:
    listeners = get_port_listeners(port)
    health = check_http_health(port)
    web_listeners = [
        item
        for item in listeners
        if is_web_process(
            _safe_int(item.get("Pid")),
            str(item.get("CommandLine") or ""),
            str(item.get("ProcessName") or ""),
        )
    ]
    return {
        "port": port,
        "listeners": listeners,
        "web_listeners": web_listeners,
        "health": health,
        "running": bool(health.get("ok")),
        "urls": [local_url(port), *lan_urls(port)],
        "task_exists": task_exists(),
        "task_enabled": task_enabled(),
        "admin": is_admin(),
        "metadata": read_metadata(),
        "clients": read_active_clients(),
        "connections": get_established_connections(port),
    }


def open_as_admin() -> ActionResult:
    if os.name != "nt":
        return ActionResult(False, "Uruchamianie jako administrator jest dostepne tylko na Windows.")
    root = app_root()
    if getattr(sys, "frozen", False):
        file_path = str(Path(sys.executable).resolve())
        params = ""
    else:
        file_path = _pythonw_executable()
        params = subprocess.list2cmdline([str(root / "PicOrgFTP-SQL-WEB.pyw")])
    try:
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", file_path, params, str(root), 1)
    except Exception as exc:
        return ActionResult(False, f"Nie udalo sie poprosic o uprawnienia administratora: {exc}")
    if int(rc) <= 32:
        return ActionResult(False, "System odrzucil uruchomienie jako administrator.")
    return ActionResult(True, "Uruchomiono nowe okno jako administrator.")


def run_service_mode(port: int, host: str) -> int:
    root = app_root()
    os.chdir(root)
    log_dir(root).mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PICORGFTP_SQL_HEADLESS", "1")
    os.environ["PICORG_WEB_PORT"] = str(port)
    os.environ["PICORG_WEB_HOST"] = host
    write_metadata(port, host, launcher="service-run")
    try:
        out_handle = out_log_path(root).open("a", encoding="utf-8", buffering=1)
        err_handle = err_log_path(root).open("a", encoding="utf-8", buffering=1)
        sys.stdout = out_handle
        sys.stderr = err_handle
    except OSError:
        pass
    try:
        import uvicorn
        from picorgftp_sql.web.app import app as web_app

        uvicorn.run(
            web_app,
            host=host,
            port=int(port),
            log_level="info",
            access_log=True,
        )
        return 0
    finally:
        remove_metadata_for_current_process()


class Tooltip:
    def __init__(self, widget: object, text: str) -> None:
        self.widget = widget
        self.text = text
        self.window = None
        try:
            widget.bind("<Enter>", self.show)
            widget.bind("<Leave>", self.hide)
            widget.bind("<ButtonPress>", self.hide)
        except Exception:
            pass

    def show(self, _event=None) -> None:
        if self.window or not self.text:
            return
        try:
            import tkinter as tk

            x = self.widget.winfo_rootx() + 16
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
            self.window = tk.Toplevel(self.widget)
            self.window.wm_overrideredirect(True)
            self.window.wm_geometry(f"+{x}+{y}")
            label = tk.Label(
                self.window,
                text=self.text,
                justify="left",
                background="#ffffe8",
                relief="solid",
                borderwidth=1,
                padx=8,
                pady=6,
                wraplength=420,
            )
            label.pack()
        except Exception:
            self.window = None

    def hide(self, _event=None) -> None:
        window = self.window
        self.window = None
        if window is not None:
            try:
                window.destroy()
            except Exception:
                pass


class WebManagerApp:
    def __init__(self) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = tk.Tk()
        self.root.title(f"PicOrgFTP-SQL WEB {get_display_version()}")
        self.root.geometry("1040x760")
        self.root.minsize(860, 620)
        self.root.protocol("WM_DELETE_WINDOW", self.close_window)
        set_tk_window_icon(self.root, "PIC_WEB.png")
        self.port_var = tk.StringVar(value=str(DEFAULT_PORT))
        self.host_var = tk.StringVar(value=DEFAULT_HOST)
        self.status_var = tk.StringVar(value="Sprawdzam status...")
        self.service_var = tk.StringVar(value="Usluga: sprawdzam...")
        self.autostart_var = tk.BooleanVar(value=False)
        self.busy = False
        self.refreshing = False
        self.pending_refresh = False
        self.status_override_until = 0.0
        self.tray_icon = None
        self._build()
        self.request_refresh(clear_status=True)
        self.root.after(10000, self._auto_refresh)

    def _build(self) -> None:
        tk = self.tk
        ttk = self.ttk
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        header = ttk.Frame(main)
        header.pack(fill="x")
        ttk.Label(header, text="PicOrgFTP-SQL WEB", font=("Segoe UI", 15, "bold")).pack(side="left")
        ttk.Label(header, textvariable=self.status_var).pack(side="right")

        controls = ttk.Frame(main)
        controls.pack(fill="x", pady=(12, 8))
        ttk.Label(controls, text="Port").pack(side="left")
        ttk.Entry(controls, textvariable=self.port_var, width=8).pack(side="left", padx=(6, 14))
        ttk.Label(controls, text="Host nasluchu").pack(side="left")
        host_entry = ttk.Entry(controls, textvariable=self.host_var, width=13)
        host_entry.pack(side="left", padx=(6, 14))
        Tooltip(host_entry, "Zwykle zostaw 0.0.0.0. To oznacza nasluch na wszystkich kartach sieciowych. 127.0.0.1 ogranicza panel tylko do tego komputera.")
        start_btn = ttk.Button(controls, text="Uruchom panel", command=self.start)
        start_btn.pack(side="left", padx=3)
        Tooltip(start_btn, "Startuje panel webowy w tle. Jezeli usluga SYSTEM jest zainstalowana, uruchomi ja; w przeciwnym razie startuje zwykly proces tego uzytkownika.")
        stop_btn = ttk.Button(controls, text="Zatrzymaj", command=self.stop)
        stop_btn.pack(side="left", padx=3)
        Tooltip(stop_btn, "Zatrzymuje proces panelu webowego albo zadanie SYSTEM, jezeli jest uruchomione.")
        restart_btn = ttk.Button(controls, text="Restart", command=self.restart)
        restart_btn.pack(side="left", padx=3)
        Tooltip(restart_btn, "Zatrzymuje panel i uruchamia go ponownie na wybranym porcie i hoscie.")
        open_btn = ttk.Button(controls, text="Otworz strone", command=self.open_web)
        open_btn.pack(side="left", padx=3)
        Tooltip(open_btn, "Otwiera lokalny adres panelu w przegladarce.")
        refresh_btn = ttk.Button(controls, text="Odswiez status", command=lambda: self.request_refresh(clear_status=True))
        refresh_btn.pack(side="left", padx=3)
        Tooltip(refresh_btn, "Ponownie sprawdza port, adresy, stan strony i aktywne polaczenia. Dziala w tle, bez blokowania okna.")
        tray_btn = ttk.Button(controls, text="Do zasobnika", command=self.minimize_to_tray)
        tray_btn.pack(side="right")
        Tooltip(tray_btn, "Chowa to okno do obszaru powiadomien Windows obok zegara. Sam panel webowy nadal dziala.")

        ttk.Label(
            main,
            text="Host 0.0.0.0 = dostep z innych komputerow w LAN. Host 127.0.0.1 = tylko ten komputer.",
            foreground="#555555",
        ).pack(anchor="w", pady=(0, 6))

        service = ttk.LabelFrame(main, text="Usluga systemowa")
        service.pack(fill="x", pady=(2, 8))
        ttk.Label(
            service,
            text="Bez instalacji przycisk uruchamia panel jako proces aktualnego uzytkownika. Instalacja SYSTEM tworzy zadanie Harmonogramu zadan uruchamiane dla calego komputera, takze przed zalogowaniem uzytkownika.",
            foreground="#555555",
            wraplength=980,
        ).pack(fill="x", padx=8, pady=(8, 0))
        service_row = ttk.Frame(service, padding=8)
        service_row.pack(fill="x")
        ttk.Label(service_row, textvariable=self.service_var).pack(side="left")
        install_btn = ttk.Button(service_row, text="Zainstaluj usluge SYSTEM", command=self.install_service)
        install_btn.pack(side="right", padx=3)
        Tooltip(install_btn, "Tworzy zadanie Harmonogramu zadan Windows uruchamiane jako SYSTEM. Wymaga administratora. Dzieki temu panel moze startowac dla calego komputera, nie tylko dla obecnego uzytkownika.")
        remove_btn = ttk.Button(service_row, text="Usun usluge", command=self.remove_service)
        remove_btn.pack(side="right", padx=3)
        Tooltip(remove_btn, "Usuwa zadanie SYSTEM z Harmonogramu zadan. Nie usuwa programu ani danych.")
        admin_btn = ttk.Button(service_row, text="Otworz jako administrator", command=self.run_as_admin)
        admin_btn.pack(side="right", padx=3)
        Tooltip(admin_btn, "Otwiera drugie okno tego menedzera z uprawnieniami administratora. Jest potrzebne do instalacji/usuniecia uslugi SYSTEM i reguly firewall.")
        autostart = ttk.Checkbutton(
            service_row,
            text="Autostart przy starcie systemu",
            variable=self.autostart_var,
            command=self.toggle_autostart,
        )
        autostart.pack(side="right", padx=12)
        Tooltip(autostart, "Wlacza albo wylacza automatyczne uruchamianie zadania SYSTEM przy starcie Windows. Dziala dopiero po zainstalowaniu uslugi.")

        content = ttk.PanedWindow(main, orient="vertical")
        content.pack(fill="both", expand=True)

        upper = ttk.Frame(content)
        lower = ttk.Frame(content)
        content.add(upper, weight=1)
        content.add(lower, weight=2)

        addresses = ttk.LabelFrame(upper, text="Adresy do otwarcia strony")
        addresses.pack(side="left", fill="both", expand=True, padx=(0, 6))
        ttk.Label(
            addresses,
            text="Uzyj 127.0.0.1 na tym komputerze albo adresu LAN z innego komputera.",
            foreground="#555555",
            wraplength=360,
        ).pack(anchor="w", padx=8, pady=(8, 0))
        self.urls_list = tk.Listbox(addresses, height=6)
        self.urls_list.pack(fill="both", expand=True, padx=8, pady=8)

        ports = ttk.LabelFrame(upper, text="Proces nasluchujacy na porcie")
        ports.pack(side="right", fill="both", expand=True, padx=(6, 0))
        ttk.Label(
            ports,
            text="To jest techniczny widok procesu, ktory otworzyl port. Pomaga wykryc konflikt portu.",
            foreground="#555555",
            wraplength=560,
        ).pack(anchor="w", padx=8, pady=(8, 0))
        self.listeners_tree = ttk.Treeview(ports, columns=("addr", "pid", "process"), show="headings", height=6)
        self.listeners_tree.heading("addr", text="Adres")
        self.listeners_tree.heading("pid", text="PID")
        self.listeners_tree.heading("process", text="Proces")
        self.listeners_tree.column("addr", width=160)
        self.listeners_tree.column("pid", width=70)
        self.listeners_tree.column("process", width=190)
        self.listeners_tree.pack(fill="both", expand=True, padx=8, pady=8)

        accounts = ttk.LabelFrame(lower, text="Konta web i blokady logowania")
        accounts.pack(fill="x", pady=(0, 8))
        ttk.Label(
            accounts,
            text="Tu widac konta zablokowane po blednych haslach. Konto admina po limicie wymaga recznego odblokowania tutaj albo z innego aktywnego konta administratora.",
            foreground="#555555",
            wraplength=980,
        ).pack(anchor="w", padx=8, pady=(8, 0))
        account_toolbar = ttk.Frame(accounts, padding=(8, 4, 8, 0))
        account_toolbar.pack(fill="x")
        unlock_btn = ttk.Button(account_toolbar, text="Odblokuj zaznaczone konto", command=self.unlock_selected_account)
        unlock_btn.pack(side="left")
        Tooltip(unlock_btn, "Czyści licznik blednych hasel i blokade logowania dla zaznaczonego konta.")
        self.accounts_tree = ttk.Treeview(
            accounts,
            columns=("user", "role", "enabled", "lock", "failed", "last"),
            show="headings",
            height=5,
        )
        self.accounts_tree.heading("user", text="Uzytkownik")
        self.accounts_tree.heading("role", text="Rola")
        self.accounts_tree.heading("enabled", text="Aktywne")
        self.accounts_tree.heading("lock", text="Blokada")
        self.accounts_tree.heading("failed", text="Bledne")
        self.accounts_tree.heading("last", text="Ostatnia bledna proba")
        self.accounts_tree.column("user", width=130)
        self.accounts_tree.column("role", width=80)
        self.accounts_tree.column("enabled", width=70)
        self.accounts_tree.column("lock", width=190)
        self.accounts_tree.column("failed", width=70)
        self.accounts_tree.column("last", width=260)
        self.accounts_tree.pack(fill="x", padx=8, pady=8)

        users = ttk.LabelFrame(lower, text="Aktywni uzytkownicy strony i polaczenia TCP")
        users.pack(fill="both", expand=True)
        ttk.Label(
            users,
            text="Tu widac ostatnie przegladarki odwiedzajace panel. Dodatkowe wpisy TCP bez uzytkownika oznaczaja samo polaczenie sieciowe, zanim backend rozpozna zalogowanego uzytkownika.",
            foreground="#555555",
            wraplength=980,
        ).pack(anchor="w", padx=8, pady=(8, 0))
        self.users_tree = ttk.Treeview(
            users,
            columns=("user", "remote", "seen", "path"),
            show="headings",
        )
        self.users_tree.heading("user", text="Uzytkownik")
        self.users_tree.heading("remote", text="Adres")
        self.users_tree.heading("seen", text="Ostatnio")
        self.users_tree.heading("path", text="Widok / stan")
        self.users_tree.column("user", width=120)
        self.users_tree.column("remote", width=160)
        self.users_tree.column("seen", width=150)
        self.users_tree.column("path", width=420)
        self.users_tree.pack(fill="both", expand=True, padx=8, pady=8)

    def _port(self) -> int:
        value = _safe_int(self.port_var.get(), DEFAULT_PORT)
        if value < 1 or value > 65535:
            value = DEFAULT_PORT
            self.port_var.set(str(value))
        return value

    def _host(self) -> str:
        return self.host_var.get().strip() or DEFAULT_HOST

    def _run_action(self, action) -> None:
        if self.busy:
            return
        self.busy = True
        self.status_var.set("Pracuje...")

        def worker() -> None:
            try:
                result = action()
            except Exception as exc:
                result = ActionResult(False, str(exc))
            self.root.after(0, lambda: self._finish_action(result))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_action(self, result: ActionResult) -> None:
        self.busy = False
        self.status_override_until = time.time() + 18
        self.status_var.set(result.message)
        self.request_refresh()

    def start(self) -> None:
        port = self._port()
        host = self._host()
        self._run_action(lambda: start_web(port, host, prefer_system_service=True))

    def stop(self) -> None:
        port = self._port()
        self._run_action(lambda: stop_web(port))

    def restart(self) -> None:
        port = self._port()
        host = self._host()

        def action() -> ActionResult:
            stop_web(port)
            time.sleep(1)
            return start_web(port, host, prefer_system_service=True)

        self._run_action(action)

    def install_service(self) -> None:
        port = self._port()
        host = self._host()
        self._run_action(lambda: install_system_service(port, host))

    def remove_service(self) -> None:
        self._run_action(remove_system_service)

    def toggle_autostart(self) -> None:
        enabled = bool(self.autostart_var.get())
        self._run_action(lambda: set_system_service_enabled(enabled))

    def run_as_admin(self) -> None:
        result = open_as_admin()
        self.status_override_until = time.time() + 12
        self.status_var.set(result.message)

    def open_web(self) -> None:
        webbrowser.open(local_url(self._port()))

    def unlock_selected_account(self) -> None:
        selection = self.accounts_tree.selection()
        if not selection:
            self.status_override_until = time.time() + 8
            self.status_var.set("Wybierz konto do odblokowania.")
            return
        values = self.accounts_tree.item(selection[0], "values")
        username = str(values[0] if values else "")
        result = unlock_web_account(username)
        self.status_override_until = time.time() + 12
        self.status_var.set(result.message)
        self._refresh_account_rows()

    def _set_rows(self, tree, rows: list[tuple[str, ...]]) -> None:
        for item in tree.get_children():
            tree.delete(item)
        for row in rows:
            tree.insert("", "end", values=row)

    def _refresh_account_rows(self) -> None:
        self._set_rows(self.accounts_tree, web_account_rows())

    def refresh(self) -> None:
        self.request_refresh(clear_status=True)

    def request_refresh(self, *, clear_status: bool = False) -> None:
        if clear_status:
            self.status_override_until = 0.0
        if self.refreshing:
            self.pending_refresh = True
            return
        self.refreshing = True
        port = self._port()

        def worker() -> None:
            try:
                status = current_status(port)
            except Exception as exc:
                status = {"error": str(exc)}
            self.root.after(0, lambda: self._apply_status(status))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_status(self, status: dict[str, Any]) -> None:
        self.refreshing = False
        self._refresh_account_rows()
        if status.get("error"):
            if time.time() >= self.status_override_until:
                self.status_var.set(f"Status: blad odswiezania: {status['error']}")
            if self.pending_refresh:
                self.pending_refresh = False
                self.request_refresh()
            return

        if time.time() >= self.status_override_until:
            if status["running"]:
                self.status_var.set("Status: dziala")
            elif status["listeners"]:
                self.status_var.set("Status: port zajety przez inny proces")
            else:
                self.status_var.set("Status: zatrzymany")

        service_parts = []
        service_parts.append("SYSTEM: zainstalowana" if status["task_exists"] else "SYSTEM: brak")
        service_parts.append("autostart: tak" if status["task_enabled"] else "autostart: nie")
        service_parts.append("admin: tak" if status["admin"] else "admin: nie")
        self.service_var.set(" | ".join(service_parts))
        self.autostart_var.set(bool(status["task_enabled"]))

        self.urls_list.delete(0, "end")
        for url in status["urls"]:
            self.urls_list.insert("end", url)
        if not status["urls"]:
            self.urls_list.insert("end", "Brak wykrytych adresow.")

        listener_rows = []
        for listener in status["listeners"]:
            process = str(listener.get("ProcessName") or "")
            if is_web_process(
                _safe_int(listener.get("Pid")),
                str(listener.get("CommandLine") or ""),
                process,
            ):
                process = f"{process or 'process'} (WEB)"
            listener_rows.append(
                (
                    f"{listener.get('LocalAddress')}:{listener.get('LocalPort')}",
                    str(listener.get("Pid") or ""),
                    process,
                )
            )
        if not listener_rows:
            listener_rows.append(("brak", "", ""))
        self._set_rows(self.listeners_tree, listener_rows)

        user_rows = []
        for client in status["clients"]:
            user_rows.append(
                (
                    str(client.get("username") or "-"),
                    str(client.get("remote_address") or "-"),
                    str(client.get("last_seen") or "-"),
                    str(client.get("path") or "-"),
                )
            )
        seen_remotes = {row[1] for row in user_rows}
        for connection in status["connections"]:
            remote = f"{connection.get('RemoteAddress')}:{connection.get('RemotePort')}"
            if str(connection.get("RemoteAddress")) in seen_remotes or remote in seen_remotes:
                continue
            user_rows.append(
                (
                    "-",
                    remote,
                    "-",
                    str(connection.get("State") or "TCP"),
                )
            )
        if not user_rows:
            user_rows.append(("brak", "", "", ""))
        self._set_rows(self.users_tree, user_rows)
        if self.pending_refresh:
            self.pending_refresh = False
            self.request_refresh()

    def _auto_refresh(self) -> None:
        if not self.busy:
            self.request_refresh()
        self.root.after(10000, self._auto_refresh)

    def minimize_to_tray(self) -> None:
        try:
            import pystray
            from PIL import Image

            image = Image.open(pic_asset_path("PIC_WEB.png"))
            if self.tray_icon is None:
                self.tray_icon = pystray.Icon(
                    "PicOrgFTP-SQL WEB",
                    image,
                    "PicOrgFTP-SQL WEB",
                    menu=pystray.Menu(
                        pystray.MenuItem("Pokaz okno", lambda _icon, _item: self.root.after(0, self.show_from_tray)),
                        pystray.MenuItem("Zamknij menedzer", lambda _icon, _item: self.root.after(0, self.close_window)),
                    ),
                )
                self.tray_icon.run_detached()
            self.root.withdraw()
        except Exception as exc:
            self.status_override_until = time.time() + 12
            self.status_var.set(f"Nie udalo sie schowac do zasobnika: {exc}. Minimalizuje do paska zadan.")
            self.root.iconify()

    def show_from_tray(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def close_window(self) -> None:
        icon = self.tray_icon
        self.tray_icon = None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service-run", action="store_true")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default=DEFAULT_HOST)
    args = parser.parse_args(argv)
    if args.service_run:
        return run_service_mode(args.port, args.host)
    WebManagerApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
