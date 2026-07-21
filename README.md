# SKAIT — 완전 로컬 AI 학습 도우미

빠르게 진행되는 Zoom·YouTube 수업을 실시간 전사하고, 핵심 노트와 복습 질문을 만들며, 수업 근거와 LLM 사전학습 지식을 구분해 답하는 개인용 학습 웹사이트입니다. FastAPI, Vue 3, MLX Whisper, Ollama를 사용하며 배포 서버나 유료 API 없이 Apple Silicon Mac 한 대에서 실행됩니다.

## 현재 구현 범위

- Zoom 브라우저 탭, YouTube 브라우저 탭 또는 마이크 음성을 최대 30초·5초 무음 단위로 STT하고 원시 전사는 내부에만 저장
- 선택형 PDF 참고 자료와 직전 60~90초 정제 문맥을 참고해 Qwen3가 `temperature=0`으로 현재 STT를 보수적으로 교정
- 정제에 성공한 Clean Transcript만 30초 용어·중요 개념 탐지와 2분 요약 카드에 사용
- 의미 없는 구간은 건너뛰고, 한 배치에 최대 2개 Topic만 생성하며 최근 Topic과 유사한 중복 요약 제거
- 요약 생성 시각을 한국 표준시로 표시하고, LLM과 분리된 개인 필기를 좌우 말풍선으로 함께 저장
- 수업에서 확인된 내용과 로컬 LLM 보충 설명을 분리한 챗봇 답변
- 개인 기록을 `backend/data/reclass.sqlite3`에 저장해 서버 재시작 후에도 유지
- 예전 `backend/data/sessions.json` 기록의 안전한 1회 자동 이관
- YouTube 영상을 서버가 다운로드하거나 가져오지 않는 Chrome 탭 오디오 테스트
- 오디오 조각은 STT 처리 직후 폐기하고 전사·요약·질문만 저장

## 처리 구조

```text
Zoom/YouTube Chrome 탭 또는 마이크
          │ 브라우저 메모리에서 최대 30초 또는 5초 무음까지 오디오 조각 생성
          ▼
       Vue 3 ───────────────▶ FastAPI
                                ├─ MLX Whisper: 30초 STT
                                ├─ Qwen3 8B: 직전 60~90초 문맥 기반 전사 정제 (temperature=0)
                                ├─ Qwen3 8B: Clean Transcript의 30초 개념 탐지·2분 요약·챗봇
                                └─ SQLite: 원시·정제 전사와 학습 기록
          ◀──── 요약 카드·노트·근거·보충 설명 ────┘
```

YouTube URL은 영상 탭을 여는 링크로만 사용합니다. 백엔드는 URL에 접속하거나 `yt-dlp` 같은 도구로 미디어를 내려받지 않습니다. MLX Whisper가 파일 경로를 요구하므로 전송된 오디오 조각은 운영체제 임시 폴더에 잠깐 생성되지만, 변환 성공·실패와 관계없이 즉시 삭제됩니다.

## 이 Mac에 맞춘 기본 모델

확인된 환경은 Apple M5, 16GB 통합 메모리의 MacBook Pro입니다.

| 역할 | 기본 모델 | 이유 |
| --- | --- | --- |
| STT | `mlx-community/whisper-large-v3-turbo` | Apple Silicon Metal 가속과 한국어 정확도·속도의 균형 |
| LLM | `qwen3:8b` | 16GB에서 실행 가능하면서 한국어·코딩 보충 설명 품질이 좋은 편 |

모델은 설치할 때 한 번만 받습니다. 이후 `start-local.sh`는 Whisper Hub 오프라인 모드로 실행하고, STT·요약·챗봇 요청을 외부 API로 보내지 않습니다.

## GitHub clone 후 최초 설정

아래 절차는 Apple Silicon Mac과 데스크톱 Chrome 기준입니다.

### 1. 저장소 받기

```bash
git clone git@github.com:ymj9608/study-agent.git zoom_study_agent
cd zoom_study_agent
```

아직 원격 저장소를 만들기 전이라면 이 폴더 자체가 Git 루트가 되게 구성해야 합니다. 상위 홈 폴더를 Git 저장소로 사용하지 마세요.

### 2. 한 번에 자동 설정

[Homebrew](https://brew.sh/)와 [Chrome](https://www.google.com/chrome/)을 준비한 뒤 프로젝트 루트에서 한 번만 실행합니다.

```bash
python setting.py
```

`python` 명령이 없는 macOS에서는 `python3 setting.py`로 실행해도 됩니다. 이 스크립트는 Python 3.12, ffmpeg, Node.js, Ollama를 확인하고, 필요한 Homebrew 패키지 설치, `backend/.venv` 생성, 백엔드·프론트엔드 패키지 설치, `.env` 생성, Whisper·Qwen 모델 다운로드까지 처리합니다. 기존 `.env`와 개인 수업 DB는 덮어쓰지 않으며, 다시 실행하면 이미 설치된 항목을 재사용합니다.

모델 다운로드를 나중에 하려면 `python setting.py --skip-models`, 가상환경을 완전히 다시 만들려면 `python setting.py --reset-venv`를 사용합니다. 공개 Whisper 체크포인트에는 Hugging Face 토큰이 필요하지 않습니다.

### 3. 실행

```bash
python3 open.py
```

`open.py`가 Ollama, 백엔드, 프론트엔드 서버를 순서대로 실행하고 준비가 끝나면 `http://127.0.0.1:5173`을 Google Chrome으로 엽니다. 가상환경을 별도로 활성화할 필요가 없습니다. 모든 서버를 종료하려면 실행한 터미널에서 `Ctrl+C`를 누릅니다. API 상태는 `http://127.0.0.1:8000/api/health`, API 문서는 `http://127.0.0.1:8000/docs`입니다.

정상 상태에는 다음 값이 표시됩니다.

```json
{
  "status": "ok",
  "version": "0.2.0",
  "stt_provider": "mlx_whisper",
  "llm_provider": "ollama",
  "stt_ready": true,
  "llm_ready": true
}
```

## 테스트 순서

### 1. 텍스트 입력 테스트

1. `새 학습 시작`에서 Zoom/마이크 세션을 만듭니다.
2. `직접 입력`에 수업 내용을 붙여 넣습니다.
3. AI 노트가 갱신되는지 확인합니다.
4. 챗봇에 수업에서 말한 질문과 말하지 않은 보충 질문을 각각 합니다.

예를 들어 수업에는 화살표 함수가 있다는 사실만 입력하고 “왜 사용하나요?”라고 질문하면, 답변은 수업 언급 범위와 `lexical this`, 콜백에서의 `this` 변경 문제 같은 LLM 보충 지식을 나누어 보여 줍니다.

### 2. YouTube 실시간 STT·요약 테스트

Mac에서는 반드시 데스크톱 Chrome을 사용하세요. Safari와 Firefox에서는 탭 오디오 공유가 제공되지 않을 수 있습니다.

1. `새 학습 시작` → `YouTube`를 선택하고 한국어 강의 URL을 입력합니다.
2. `학습 공간 만들기` 후 `강의 열기`를 눌러 새 탭을 엽니다.
3. 광고를 넘기고 강의 시작 지점에서 영상을 일시정지합니다.
4. SKAIT 탭으로 돌아와 `학습 시작`을 누릅니다.
5. Chrome 공유 창에서 해당 YouTube **탭**을 선택하고 **탭 오디오 공유**를 켭니다.
6. YouTube 탭에서 영상을 재생합니다. 원시 STT는 최대 30초 또는 5초 무음 단위로 내부 저장된 뒤 Qwen3로 정제됩니다. 정제된 전사에서 용어·중요 개념은 30초마다 갱신되고, 화면에는 2분마다 의미 있는 요약 카드가 추가됩니다.
7. SKAIT의 `학습 종료` 또는 Chrome 공유 막대의 `공유 중지`를 누릅니다.
8. 마지막 구간 업로드와 최종 요약이 끝난 뒤 챗봇 질문을 시험합니다.
9. 서버를 `Ctrl+C`로 끄고 다시 실행해 같은 세션이 남아 있는지 확인합니다.

짧은 공개 테스트 후보는 생활코딩의 [JavaScript 함수의 활용(4분 35초)](https://youtu.be/WsPJ8FsoMcU)입니다. 강의 목차와 예제는 [생활코딩 동영상·예제 링크 모음](https://wikibook.github.io/html-css-js/js.html)에서 함께 확인할 수 있습니다.

공유 권한창에서 탭 선택은 브라우저 보안상 매번 사용자가 직접 해야 합니다. 타임스탬프는 YouTube 영상의 절대 재생 시간이 아니라 SKAIT가 수집을 시작한 뒤의 경과 시간입니다. 영상 저작권과 강의자의 녹음·활용 동의를 확인하고 개인 학습 범위에서 사용하세요.

### 3. Zoom 실시간 테스트

1. Chrome의 Zoom Web에서 수업에 참여합니다.
2. SKAIT의 Zoom 세션에서 `학습 시작`을 누릅니다.
3. 공유 창에서 Zoom 탭과 `탭 오디오 공유`를 선택합니다.
4. 데스크톱 Zoom 앱을 사용한다면 마이크 모드로 스피커 음성을 받거나 별도 가상 오디오 장치가 필요합니다.

## 로컬 DB와 백업

- 개인 데이터 파일: `backend/data/reclass.sqlite3`
- SQLite 보조 파일: `reclass.sqlite3-wal`, `reclass.sqlite3-shm`
- 서버를 껐다 켜도 세션, 전사, 요약, 질문 자료가 유지됩니다.
- 이전 버전의 `sessions.json`이 있으면 전체 내용을 먼저 검증한 후 한 번만 가져옵니다. 원본 JSON은 삭제하지 않습니다.
- Whisper 모델은 `~/.cache/huggingface`, Ollama 모델은 `~/.ollama`에 있어 DB와 별도로 유지됩니다.

안전한 백업은 서버를 끈 상태에서 수행합니다.

```bash
cp backend/data/reclass.sqlite3 "$HOME/reclass-$(date +%Y%m%d).sqlite3"
```

초기화하려면 서버를 끄고 SQLite 파일과 WAL/SHM 파일을 직접 삭제해야 합니다. 이 작업은 복구할 수 없으므로 먼저 백업하세요.

## 로컬 설정

기본 `backend/.env`의 핵심 값은 다음과 같습니다.

```dotenv
STT_PROVIDER=mlx_whisper
MLX_WHISPER_MODEL=mlx-community/whisper-large-v3-turbo
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:8b
LEARNING_ITEM_BATCH_SECONDS=30
SUMMARY_BATCH_SECONDS=120
DATABASE_FILE=data/reclass.sqlite3
DATA_FILE=data/sessions.json
MAX_PDF_MB=20
```

메모리가 부족하면 `OLLAMA_MODEL=qwen3.5:4b`로 바꾸고 먼저 `ollama pull qwen3.5:4b`를 실행하세요. `LLM_PROVIDER=local`은 생성형 모델 없이 추출식 요약·수업 근거 답변만 사용합니다.

## GitHub push 전 비밀정보 점검

`.gitignore`는 다음 파일을 제외합니다.

- `backend/.env`와 각종 환경별 `.env.*`
- SQLite·JSON 개인 수업 기록과 WAL/SHM 파일
- 임시 오디오·영상, 로컬 모델 가중치, 캐시
- Python 가상환경, `node_modules`, 빌드 결과

`VITE_*` 값은 프론트엔드 번들에 포함되어 브라우저에서 보입니다. API 키나 토큰을 `frontend/.env*` 또는 `VITE_*`에 넣지 마세요.

push 직전에 실행합니다.

```bash
git check-ignore -v backend/.env backend/data/reclass.sqlite3
./scripts/check-secrets.sh
git status --short
```

두 로컬 파일은 `git check-ignore`에 표시되어야 하고, 비밀정보 점검은 `통과`여야 합니다. `git add -f backend/.env`를 사용하지 마세요. 토큰이 과거 커밋에 들어간 적이 있다면 해당 서비스에서 즉시 폐기·재발급하고 Git 이력도 정리해야 합니다.

## 개발 검증

```bash
cd backend
.venv/bin/python -m unittest discover -s tests -v

cd ../frontend
npm run build
```

화면 공유 권한창은 사용자 동작을 요구하므로 실제 YouTube·Zoom 탭 오디오 검증은 위 수동 테스트 절차가 필요합니다.

## 문제 해결

- `STT가 준비되지 않음`: `ffmpeg -version`과 Whisper 사전 다운로드 여부를 확인합니다.
- `LLM이 준비되지 않음`: `ollama list`에서 `.env`의 모델이 있는지 확인합니다.
- `공유한 화면에 오디오가 없음`: Chrome에서 창/전체 화면이 아닌 탭을 선택하고 `탭 오디오 공유`를 켭니다.
- 포트 충돌: 5173 또는 8000 포트를 사용 중인 기존 프로세스를 종료합니다.
- 손상된 기존 JSON 때문에 시작 실패: `backend/data/sessions.json`을 먼저 백업하고 JSON 형식을 수정합니다. 앱은 부분 이관하거나 원본을 덮어쓰지 않습니다.

## 주요 API

| 메서드 | 경로 | 역할 |
| --- | --- | --- |
| `GET` | `/api/health` | STT·LLM 준비 상태 |
| `GET/POST` | `/api/sessions` | 저장된 세션 조회·생성 |
| `POST` | `/api/sessions/{id}/audio` | 원시 STT 내부 저장 + Qwen 정제 + Clean Transcript의 30초 학습 항목 탐지·닫힌 2분 요약 |
| `POST/PATCH` | `/api/sessions/{id}/transcript` | 텍스트 수업 내용 추가·일괄 수정 |
| `POST/DELETE` | `/api/sessions/{id}/reference` | 선택형 PDF 참고 자료 연결·삭제 |
| `POST/PATCH` | `/api/sessions/{id}/summary` | AI 노트 재생성·요약 일괄 수정 |
| `POST` | `/api/sessions/{id}/summary-notes` | 개인 필기 추가 |
| `POST` | `/api/sessions/{id}/chat` | 수업 근거 + 사전학습 보충 답변 |

공식 참고 문서: [FastAPI 파일 업로드](https://fastapi.tiangolo.com/tutorial/request-files/), [MDN getDisplayMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia), [MLX Whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper), [Ollama API](https://docs.ollama.com/api/introduction)
