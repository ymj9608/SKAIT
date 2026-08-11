#!/usr/bin/env python3
"""Start every SKAIT local service and open the app in Google Chrome."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Sequence


PROJECT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_DIR / "backend"
FRONTEND_DIR = PROJECT_DIR / "frontend"
BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://127.0.0.1:5173"


class OpenError(RuntimeError):
    """An actionable local startup failure."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SKAIT 서버를 모두 실행하고 Google Chrome으로 엽니다."
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Chrome을 열지 않고 서버만 실행합니다.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def venv_command(name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    directory = BACKEND_DIR / ".venv" / ("Scripts" if os.name == "nt" else "bin")
    return directory / f"{name}{suffix}"


def read_env() -> dict[str, str]:
    path = BACKEND_DIR / ".env"
    if not path.exists():
        raise OpenError("설정 파일이 없습니다. 먼저 `python3 setting.py`를 실행해 주세요.")

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def fetch(url: str, timeout: float = 2) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read()
    except (OSError, urllib.error.URLError):
        return None


def backend_is_ready() -> bool:
    body = fetch(f"{BACKEND_URL}/api/health")
    if not body:
        return False
    try:
        return json.loads(body).get("status") == "ok"
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        return False


def frontend_is_ready() -> bool:
    body = fetch(FRONTEND_URL)
    return bool(body and b"SKAIT" in body and b'id="app"' in body)


def ollama_is_ready(base_url: str) -> bool:
    return fetch(f"{base_url.rstrip('/')}/api/tags") is not None


def subprocess_options(*, quiet: bool = False) -> dict[str, object]:
    options: dict[str, object] = {}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    if quiet:
        options["stdout"] = subprocess.DEVNULL
        options["stderr"] = subprocess.DEVNULL
    return options


def start_process(
    command: Sequence[str | Path],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    quiet: bool = False,
) -> subprocess.Popen[bytes]:
    normalized = [str(part) for part in command]
    print("  $", subprocess.list2cmdline(normalized), flush=True)
    return subprocess.Popen(
        normalized,
        cwd=cwd,
        env=env,
        **subprocess_options(quiet=quiet),
    )


def stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass


def wait_until(
    label: str,
    check: Callable[[], bool],
    process: subprocess.Popen[bytes] | None,
    timeout: int = 90,
) -> None:
    print(f"{label} 준비를 기다리는 중입니다", end="", flush=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            print(" 완료")
            return
        if process is not None and process.poll() is not None:
            print()
            raise OpenError(f"{label}가 종료되었습니다(종료 코드 {process.returncode}).")
        print(".", end="", flush=True)
        time.sleep(1)
    print()
    raise OpenError(f"{label}가 {timeout}초 안에 준비되지 않았습니다.")


def ensure_ollama(
    env_values: dict[str, str], processes: list[subprocess.Popen[bytes]]
) -> None:
    if env_values.get("LLM_PROVIDER", "ollama").lower() != "ollama":
        return

    ollama = shutil.which("ollama")
    if not ollama:
        raise OpenError("Ollama가 없습니다. 먼저 `python3 setting.py`를 실행해 주세요.")

    base_url = env_values.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    ollama_env = dict(os.environ)
    ollama_env["OLLAMA_HOST"] = base_url
    process: subprocess.Popen[bytes] | None = None
    if ollama_is_ready(base_url):
        print("Ollama 서버 재사용")
    else:
        print("Ollama 서버 시작")
        process = start_process(
            [ollama, "serve"], cwd=PROJECT_DIR, env=ollama_env, quiet=True
        )
        processes.append(process)
        wait_until("Ollama", lambda: ollama_is_ready(base_url), process, timeout=30)

    model = env_values.get("OLLAMA_MODEL", "qwen3:4b-instruct-2507-q4_K_M")
    result = subprocess.run(
        [ollama, "show", model],
        env=ollama_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise OpenError(
            f"Ollama 모델 `{model}`이 없습니다. `python3 setting.py`를 다시 실행해 주세요."
        )


def unload_ollama_model(env_values: dict[str, str]) -> bool:
    """공유 Ollama 서버는 유지하면서 SKAIT가 사용한 모델만 메모리에서 내립니다."""
    if env_values.get("LLM_PROVIDER", "ollama").lower() != "ollama":
        return False
    ollama = shutil.which("ollama")
    if not ollama:
        return False
    base_url = env_values.get(
        "OLLAMA_BASE_URL",
        "http://127.0.0.1:11434",
    ).rstrip("/")
    if not ollama_is_ready(base_url):
        return False
    process_env = dict(os.environ)
    process_env["OLLAMA_HOST"] = base_url
    model = env_values.get("OLLAMA_MODEL", "qwen3:4b-instruct-2507-q4_K_M")
    try:
        result = subprocess.run(
            [ollama, "stop", model],
            env=process_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    print(f"Ollama 모델 종료: {model}")
    return True


def install_shutdown_signal_handlers() -> None:
    """터미널 종료 신호도 KeyboardInterrupt와 같은 정리 경로로 보냅니다."""
    def request_shutdown(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    for signal_name in ("SIGTERM", "SIGHUP"):
        shutdown_signal = getattr(signal, signal_name, None)
        if shutdown_signal is not None:
            signal.signal(shutdown_signal, request_shutdown)


def start_backend(
    env_values: dict[str, str], processes: list[subprocess.Popen[bytes]]
) -> subprocess.Popen[bytes] | None:
    if backend_is_ready():
        raise OpenError(
            "8000번 포트에 기존 SKAIT 백엔드가 실행 중입니다. "
            "이전 버전을 재사용하지 않도록 실행을 중단했습니다. "
            "기존 SKAIT 터미널에서 Ctrl+C로 서버를 종료한 뒤 다시 실행해 주세요."
        )

    python = venv_command("python")
    if not python.exists():
        raise OpenError("백엔드 가상환경이 없습니다. 먼저 `python3 setting.py`를 실행해 주세요.")

    process_env = dict(os.environ)
    if env_values.get("STT_PROVIDER", "mlx_whisper").lower() == "mlx_whisper":
        process_env["HF_HUB_OFFLINE"] = "1"

    print("백엔드 서버 시작")
    process = start_process(
        [
            python,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        cwd=BACKEND_DIR,
        env=process_env,
    )
    processes.append(process)
    wait_until("백엔드", backend_is_ready, process)
    return process


def start_frontend(processes: list[subprocess.Popen[bytes]]) -> subprocess.Popen[bytes] | None:
    if frontend_is_ready():
        raise OpenError(
            "5173번 포트에 기존 SKAIT 프론트엔드가 실행 중입니다. "
            "이전 버전을 재사용하지 않도록 실행을 중단했습니다. "
            "기존 SKAIT 터미널에서 Ctrl+C로 서버를 종료한 뒤 다시 실행해 주세요."
        )

    npm = shutil.which("npm")
    vite = FRONTEND_DIR / "node_modules" / ".bin" / (
        "vite.cmd" if os.name == "nt" else "vite"
    )
    if not npm or not vite.exists():
        raise OpenError("프론트엔드 패키지가 없습니다. 먼저 `python3 setting.py`를 실행해 주세요.")

    print("프론트엔드 서버 시작")
    process = start_process(
        [npm, "run", "dev", "--", "--host", "127.0.0.1", "--strictPort"],
        cwd=FRONTEND_DIR,
    )
    processes.append(process)
    wait_until("프론트엔드", frontend_is_ready, process)
    return process


def open_in_chrome(url: str) -> None:
    print("Google Chrome 열기")
    if sys.platform == "darwin":
        result = subprocess.run(
            ["/usr/bin/open", "-a", "Google Chrome", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return
    elif os.name == "nt":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        ]
        chrome = shutil.which("chrome") or next(
            (str(path) for path in candidates if path.is_file()), None
        )
        if chrome:
            subprocess.Popen([chrome, url])
            return
    else:
        chrome = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
        if chrome:
            subprocess.Popen([chrome, url], **subprocess_options(quiet=True))
            return
    raise OpenError("Google Chrome을 찾을 수 없습니다. Chrome 설치 여부를 확인해 주세요.")


def monitor(processes: list[subprocess.Popen[bytes]]) -> None:
    print("\nSKAIT가 Chrome에서 열렸습니다.")
    print("모든 서버를 종료하려면 이 터미널에서 Ctrl+C를 누르세요.\n")
    while True:
        for process in processes:
            if process.poll() is not None:
                raise OpenError(f"서버 하나가 예기치 않게 종료되었습니다({process.returncode}).")
        time.sleep(1)


def main() -> int:
    args = parse_args()
    processes: list[subprocess.Popen[bytes]] = []
    env_values: dict[str, str] = {}
    install_shutdown_signal_handlers()
    try:
        env_values = read_env()
        ensure_ollama(env_values, processes)
        start_backend(env_values, processes)
        start_frontend(processes)
        if not args.no_browser:
            open_in_chrome(FRONTEND_URL)
        if args.check:
            print("\nOllama, 백엔드, 프론트엔드 실행 확인을 완료했습니다.")
            return 0
        monitor(processes)
    except KeyboardInterrupt:
        print("\n서버를 종료합니다.")
    except (OpenError, OSError) as exc:
        print(f"\n실행 실패: {exc}", file=sys.stderr)
        return 1
    finally:
        for process in reversed(processes):
            stop_process(process)
        unload_ollama_model(env_values)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
