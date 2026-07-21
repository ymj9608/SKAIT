#!/usr/bin/env python3
"""SKAIT local development environment bootstrapper.

Run this file from anywhere with ``python setting.py``.  The script is
intentionally idempotent: existing environment files and user data are never
overwritten, and already downloaded dependencies/models are reused.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Sequence


PROJECT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_DIR / "backend"
FRONTEND_DIR = PROJECT_DIR / "frontend"
VENV_DIR = BACKEND_DIR / ".venv"


class SetupError(RuntimeError):
    """An actionable setup failure."""


class Installer:
    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self.step = 0

    def heading(self, message: str) -> None:
        self.step += 1
        print(f"\n[{self.step}] {message}")

    def run(
        self,
        command: Sequence[str | Path],
        *,
        cwd: Path = PROJECT_DIR,
        env: dict[str, str] | None = None,
    ) -> None:
        normalized = [str(part) for part in command]
        print("  $", subprocess.list2cmdline(normalized))
        if self.dry_run:
            return
        subprocess.run(normalized, cwd=cwd, env=env, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SKAIT의 백엔드, 프론트엔드와 로컬 AI 모델을 한 번에 설정합니다."
    )
    parser.add_argument(
        "--reset-venv",
        action="store_true",
        help="기존 backend/.venv를 지우고 새로 만듭니다.",
    )
    parser.add_argument(
        "--skip-models",
        action="store_true",
        help="Whisper와 Ollama 모델 다운로드를 건너뜁니다.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="파일을 변경하지 않고 실행할 명령만 출력합니다.",
    )
    return parser.parse_args()


def is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine().lower() in {"arm64", "aarch64"}


def command_python_version(command: Sequence[str]) -> tuple[int, int] | None:
    try:
        result = subprocess.run(
            [*command, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            check=True,
            capture_output=True,
            text=True,
        )
        major, minor = result.stdout.strip().split(".", maxsplit=1)
        return int(major), int(minor)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def find_python_312() -> list[str] | None:
    if sys.version_info[:2] == (3, 12):
        return [sys.executable]

    executable = shutil.which("python3.12")
    if executable and command_python_version([executable]) == (3, 12):
        return [executable]

    if os.name == "nt" and shutil.which("py"):
        command = [str(shutil.which("py")), "-3.12"]
        if command_python_version(command) == (3, 12):
            return command
    return None


def select_python(installer: Installer) -> list[str]:
    command = find_python_312()
    if command:
        print(f"  Python 3.12: {' '.join(command)}")
        return command

    if sys.platform == "darwin" and shutil.which("brew"):
        installer.run([str(shutil.which("brew")), "install", "python@3.12"])
        if installer.dry_run:
            return ["python3.12"]
        command = find_python_312()
        if command:
            return command

        result = subprocess.run(
            [str(shutil.which("brew")), "--prefix", "python@3.12"],
            check=True,
            capture_output=True,
            text=True,
        )
        brewed_python = Path(result.stdout.strip()) / "bin" / "python3.12"
        if brewed_python.exists():
            return [str(brewed_python)]

    if (3, 10) <= sys.version_info[:2] < (3, 14):
        print(
            f"  Python 3.12를 찾지 못해 현재 Python "
            f"{sys.version_info.major}.{sys.version_info.minor}을 사용합니다."
        )
        return [sys.executable]

    raise SetupError(
        "Python 3.12가 필요합니다. Python 3.12를 설치한 뒤 다시 실행해 주세요."
    )


def ensure_system_dependencies(installer: Installer) -> None:
    required = {"ffmpeg": "ffmpeg", "node": "node", "npm": "node", "ollama": "ollama"}
    missing_packages = sorted(
        {package for command, package in required.items() if not shutil.which(command)}
    )
    if not missing_packages:
        print("  ffmpeg, Node.js/npm, Ollama가 준비되어 있습니다.")
        return

    brew = shutil.which("brew")
    if sys.platform == "darwin" and brew:
        installer.run([brew, "install", *missing_packages])
        if installer.dry_run:
            return
        still_missing = [command for command in required if not shutil.which(command)]
        if not still_missing:
            return
        raise SetupError(f"설치 후에도 다음 명령을 찾을 수 없습니다: {', '.join(still_missing)}")

    commands = ", ".join(sorted(command for command in required if not shutil.which(command)))
    raise SetupError(
        f"다음 필수 프로그램을 먼저 설치해 주세요: {commands}. "
        "macOS에서는 Homebrew를 설치하면 setting.py가 자동으로 준비합니다."
    )


def copy_example(installer: Installer, example: Path, destination: Path) -> bool:
    if destination.exists():
        print(f"  유지: {destination.relative_to(PROJECT_DIR)}")
        return False
    print(f"  생성: {destination.relative_to(PROJECT_DIR)}")
    if not installer.dry_run:
        shutil.copyfile(example, destination)
    return True


def read_env(path: Path, fallback: Path) -> dict[str, str]:
    source = path if path.exists() else fallback
    values: dict[str, str] = {}
    for raw_line in source.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def replace_env_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    prefix = f"{key}="
    changed = False
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = f"{prefix}{value}"
            changed = True
            break
    if not changed:
        lines.append(f"{prefix}{value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def prepare_environment_files(installer: Installer) -> dict[str, str]:
    backend_env = BACKEND_DIR / ".env"
    backend_created = copy_example(installer, BACKEND_DIR / ".env.example", backend_env)
    copy_example(installer, FRONTEND_DIR / ".env.example", FRONTEND_DIR / ".env")

    if backend_created and not is_apple_silicon() and not installer.dry_run:
        replace_env_value(backend_env, "STT_PROVIDER", "faster_whisper")
        print("  Apple Silicon이 아니므로 STT_PROVIDER=faster_whisper로 설정했습니다.")

    values = read_env(backend_env, BACKEND_DIR / ".env.example")
    if backend_created and not is_apple_silicon():
        values["STT_PROVIDER"] = "faster_whisper"
    return values


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def venv_command(name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    directory = VENV_DIR / ("Scripts" if os.name == "nt" else "bin")
    return directory / f"{name}{suffix}"


def prepare_virtualenv(
    installer: Installer, python_command: Sequence[str], reset: bool
) -> Path:
    selected_version = command_python_version(python_command)
    existing_version = command_python_version([str(venv_python())]) if venv_python().exists() else None
    should_reset = reset or (existing_version is not None and existing_version != selected_version)

    if should_reset and VENV_DIR.exists():
        print(f"  재생성: {VENV_DIR.relative_to(PROJECT_DIR)}")
        if not installer.dry_run:
            shutil.rmtree(VENV_DIR)

    if not venv_python().exists() or should_reset:
        installer.run([*python_command, "-m", "venv", VENV_DIR])
    else:
        print(f"  재사용: {VENV_DIR.relative_to(PROJECT_DIR)} (Python {existing_version[0]}.{existing_version[1]})")
    return venv_python()


def install_backend(
    installer: Installer, python: Path, env_values: dict[str, str]
) -> None:
    provider = env_values.get("STT_PROVIDER", "mlx_whisper").lower()
    if provider == "mlx_whisper":
        if not is_apple_silicon():
            raise SetupError(
                "MLX Whisper는 Apple Silicon Mac에서만 사용할 수 있습니다. "
                "backend/.env의 STT_PROVIDER를 faster_whisper로 변경해 주세요."
            )
        requirements = BACKEND_DIR / "requirements-local-apple.txt"
    elif provider == "faster_whisper":
        requirements = BACKEND_DIR / "requirements-local-whisper.txt"
    else:
        requirements = BACKEND_DIR / "requirements.txt"

    installer.run([python, "-m", "pip", "install", "--upgrade", "pip"], cwd=BACKEND_DIR)
    installer.run([python, "-m", "pip", "install", "-r", requirements], cwd=BACKEND_DIR)


def install_frontend(installer: Installer) -> None:
    npm = shutil.which("npm") or "npm"
    installer.run([npm, "ci"], cwd=FRONTEND_DIR)


def url_is_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def start_ollama(installer: Installer, base_url: str) -> None:
    if url_is_ready(f"{base_url}/api/tags"):
        print("  Ollama 서버가 실행 중입니다.")
        return

    brew = shutil.which("brew")
    if sys.platform == "darwin" and brew:
        installer.run([brew, "services", "start", "ollama"])
    elif installer.dry_run:
        print("  $ ollama serve")
        return
    else:
        kwargs: dict[str, object] = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen([str(shutil.which("ollama") or "ollama"), "serve"], **kwargs)

    if installer.dry_run:
        return
    for _ in range(30):
        if url_is_ready(f"{base_url}/api/tags"):
            return
        time.sleep(1)
    raise SetupError("Ollama 서버를 시작하지 못했습니다. `ollama serve` 실행 여부를 확인해 주세요.")


def command_succeeds(command: Sequence[str | Path], cwd: Path = PROJECT_DIR) -> bool:
    try:
        subprocess.run(
            [str(part) for part in command],
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def install_models(
    installer: Installer, python: Path, env_values: dict[str, str]
) -> None:
    stt_provider = env_values.get("STT_PROVIDER", "mlx_whisper").lower()
    if stt_provider == "mlx_whisper":
        model = env_values.get(
            "MLX_WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo"
        )
        check = [
            python,
            "-c",
            (
                "from huggingface_hub import snapshot_download; "
                f"snapshot_download({model!r}, local_files_only=True)"
            ),
        ]
        if command_succeeds(check, cwd=BACKEND_DIR):
            print(f"  Whisper 모델 재사용: {model}")
        else:
            installer.run([venv_command("hf"), "download", model], cwd=BACKEND_DIR)
    elif stt_provider == "faster_whisper":
        model = env_values.get("LOCAL_WHISPER_MODEL", "small")
        repository = f"Systran/faster-whisper-{model}"
        if "/" not in model:
            installer.run([venv_command("hf"), "download", repository], cwd=BACKEND_DIR)
        else:
            print("  사용자 지정 Faster Whisper 모델은 첫 실행 시 내려받습니다.")

    if env_values.get("LLM_PROVIDER", "ollama").lower() != "ollama":
        return

    base_url = env_values.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model = env_values.get("OLLAMA_MODEL", "qwen3:8b")
    start_ollama(installer, base_url)
    ollama = shutil.which("ollama") or "ollama"
    if not installer.dry_run and command_succeeds([ollama, "show", model]):
        print(f"  Ollama 모델 재사용: {model}")
    else:
        installer.run([ollama, "pull", model])


def validate_project_files() -> None:
    required = [
        BACKEND_DIR / "requirements.txt",
        BACKEND_DIR / ".env.example",
        FRONTEND_DIR / "package-lock.json",
        FRONTEND_DIR / ".env.example",
    ]
    missing = [str(path.relative_to(PROJECT_DIR)) for path in required if not path.exists()]
    if missing:
        raise SetupError(f"프로젝트 파일이 누락되었습니다: {', '.join(missing)}")


def main() -> int:
    args = parse_args()
    installer = Installer(dry_run=args.dry_run)
    print("SKAIT 자동 설정을 시작합니다.")
    print(f"프로젝트: {PROJECT_DIR}")

    try:
        validate_project_files()

        installer.heading("Python 확인")
        python_command = select_python(installer)

        installer.heading("시스템 프로그램 확인")
        ensure_system_dependencies(installer)

        installer.heading("환경 파일 준비")
        env_values = prepare_environment_files(installer)

        installer.heading("백엔드 가상환경 준비")
        python = prepare_virtualenv(installer, python_command, args.reset_venv)

        installer.heading("백엔드 패키지 설치")
        install_backend(installer, python, env_values)

        installer.heading("프론트엔드 패키지 설치")
        install_frontend(installer)

        if args.skip_models:
            print("\n[건너뜀] --skip-models 옵션으로 AI 모델 설치를 생략했습니다.")
        else:
            installer.heading("로컬 AI 모델 준비")
            install_models(installer, python, env_values)
    except (SetupError, OSError, subprocess.CalledProcessError) as exc:
        print(f"\n설정 실패: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n사용자가 설정을 중단했습니다.", file=sys.stderr)
        return 130

    if args.dry_run:
        print("\n점검이 끝났습니다. --dry-run을 빼면 실제로 설정합니다.")
    else:
        print("\n설정이 모두 끝났습니다.")
        print("실행 및 Chrome 열기: python3 open.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
