#!/bin/sh

set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

if ! GIT_ROOT=$(git -C "$PROJECT_DIR" rev-parse --show-toplevel 2>/dev/null); then
  echo "오류: 이 프로젝트는 아직 독립된 Git 저장소가 아닙니다." >&2
  exit 1
fi

if [ "$GIT_ROOT" != "$PROJECT_DIR" ]; then
  echo "오류: Git 루트가 프로젝트 폴더와 다릅니다: $GIT_ROOT" >&2
  echo "올바른 저장소를 clone하거나 이 폴더를 독립 저장소로 만든 뒤 다시 실행하세요." >&2
  exit 1
fi

cd "$PROJECT_DIR"

tracked_sensitive=$(git ls-files | grep -E '(^|/)\.env($|\.)|\.(db|sqlite|sqlite3)(-(wal|shm))?$|\.(pem|p12|pfx|gguf|safetensors|ckpt|pt|pth)$|^backend/data/' | grep -vE '(^|/)\.env\.example$|^backend/data/\.gitkeep$' || true)
if [ -n "$tracked_sensitive" ]; then
  echo "오류: Git이 로컬 전용 파일을 추적하고 있습니다:" >&2
  echo "$tracked_sensitive" >&2
  exit 1
fi

secret_files=$(git grep -IlE 'hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}' -- . ':(exclude)scripts/check-secrets.sh' 2>/dev/null || true)
if [ -n "$secret_files" ]; then
  echo "오류: 다음 추적 파일에서 API 키로 보이는 문자열을 찾았습니다:" >&2
  echo "$secret_files" >&2
  exit 1
fi

echo "통과: 추적 중인 로컬 데이터·모델·고신뢰 API 키 패턴이 없습니다."
