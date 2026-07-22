#!/bin/zsh

set -euo pipefail

PROJECT_DIR="${0:A:h}"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"

env_value() {
  local key="$1"
  local fallback="$2"
  local line=""
  if [[ -f "$BACKEND_DIR/.env" ]]; then
    line=$(grep -E "^${key}=" "$BACKEND_DIR/.env" | tail -n 1 || true)
  fi
  [[ -n "$line" ]] && print -r -- "${line#*=}" || print -r -- "$fallback"
}

if [[ ! -x "$BACKEND_DIR/.venv/bin/uvicorn" ]]; then
  print -u2 "Python 3.12 가상환경이 없습니다. README의 로컬 설치 단계를 먼저 실행하세요."
  exit 1
fi

if [[ ! -f "$BACKEND_DIR/.env" ]]; then
  print -u2 "backend/.env가 없습니다. 'cp backend/.env.example backend/.env'를 먼저 실행하세요."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1 || [[ ! -x "$FRONTEND_DIR/node_modules/.bin/vite" ]]; then
  print -u2 "프론트엔드 패키지가 없습니다. 프로젝트 루트에서 'npm --prefix frontend ci'를 실행하세요."
  exit 1
fi

STT_PROVIDER=$(env_value STT_PROVIDER mlx_whisper)
if [[ "$STT_PROVIDER" == "mlx_whisper" ]]; then
  WHISPER_MODEL=$(env_value MLX_WHISPER_MODEL mlx-community/whisper-large-v3-turbo)
  if ! HF_HUB_OFFLINE=1 "$BACKEND_DIR/.venv/bin/python" -c 'import sys; from huggingface_hub import snapshot_download; snapshot_download(sys.argv[1], local_files_only=True)' "$WHISPER_MODEL" >/dev/null 2>&1; then
    print -u2 "MLX Whisper 모델이 로컬에 없습니다. 다음 명령으로 한 번 내려받으세요:"
    print -u2 "backend/.venv/bin/hf download $WHISPER_MODEL"
    exit 1
  fi
  # 모델 준비가 끝난 뒤에는 Hub를 조회하지 않고 완전히 로컬로 실행합니다.
  export HF_HUB_OFFLINE=1
fi

LLM_PROVIDER=$(env_value LLM_PROVIDER ollama)
if [[ "$LLM_PROVIDER" == "ollama" ]]; then
  OLLAMA_MODEL=$(env_value OLLAMA_MODEL qwen3:8b)
  if ! command -v ollama >/dev/null 2>&1; then
    print -u2 "Ollama가 없습니다. 'brew install ollama'를 먼저 실행하세요."
    exit 1
  fi

  if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    brew services start ollama >/dev/null
    sleep 2
  fi

  if ! ollama show "$OLLAMA_MODEL" >/dev/null 2>&1; then
    print -u2 "$OLLAMA_MODEL 모델이 없습니다. 'ollama pull $OLLAMA_MODEL'을 실행하세요."
    exit 1
  fi
fi

BACKEND_PID=0
FRONTEND_PID=0
cleanup() {
  (( BACKEND_PID > 0 )) && kill "$BACKEND_PID" 2>/dev/null || true
  (( FRONTEND_PID > 0 )) && kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

(
  cd "$BACKEND_DIR"
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
) &
BACKEND_PID=$!

(
  cd "$FRONTEND_DIR"
  npm run dev -- --host 127.0.0.1
) &
FRONTEND_PID=$!

print ""
print "SKAIT 로컬 AI 학습 도우미를 시작했습니다."
print "웹사이트: http://127.0.0.1:5173"
print "API 상태: http://127.0.0.1:8000/api/health"
print "종료하려면 Ctrl+C를 누르세요."
print ""

wait
