# SKAIT - 로컬 AI 학습 도우미

SKAIT는 **SKALA AI TUTOR**의 줄임말입니다. Zoom·YouTube 수업을 기록하고 AI가 요약, 핵심 개념, 퀴즈와 질문 답변을 제공하는 개인 학습 도우미입니다. AI 처리와 학습 기록 저장은 내 컴퓨터에서 이루어집니다.

![SKAIT 주요 기능](docs/images/skait-main-features.png)

> [!IMPORTANT]
> **데스크톱 Google Chrome에서 사용해 주세요. Safari는 지원하지 않습니다.**
>
> 수업을 녹음할 때 Chrome 공유 창에서 수업 탭을 선택하고 `탭 오디오 공유`를 켜야 합니다. Zoom은 데스크톱 앱 대신 Chrome의 Zoom Web을 이용해 주세요.

## 핵심 기능

- Zoom·YouTube 수업 음성 자동 기록 및 AI 요약
- 주요 용어와 중요 개념 정리
- 수업 요약 기반 `QUIZ` 생성·재생성(최대 10문제)
- 수업 근거를 확인할 수 있는 AI 질문 답변
- PDF 참고 자료를 활용한 전문 용어 보정과 요약
- 수업 요약, 직접 추가한 내용과 AI 대화 기록의 로컬 저장

## 설치 및 실행

macOS에서는 [Google Chrome](https://www.google.com/chrome/)과 [Homebrew](https://brew.sh/)를 먼저 설치해 주세요.

```bash
git clone https://github.com/ymj9608/study-agent.git zoom_study_agent
cd zoom_study_agent
python3 setting.py
```

최초 설정이 끝나면 아래 명령으로 실행합니다.

```bash
python3 open.py
```

준비가 완료되면 SKAIT가 Chrome에서 자동으로 열립니다. 종료할 때는 터미널에서 `Ctrl+C`를 누르세요.

로컬 LLM은 Ollama의 `qwen3:8b`를 사용합니다. 최초 설정에서는 약 5.2GB 모델을 내려받으므로 시간이 걸릴 수 있습니다.

## 빠른 사용 및 기능 확인

1. `새 학습 시작`에서 Zoom 또는 YouTube를 선택하고 수업을 만듭니다. PDF 첨부는 선택 사항입니다.
2. `학습 시작`을 누른 뒤 Chrome 공유 창에서 수업 탭과 `탭 오디오 공유`를 선택합니다.
3. 수업을 재생하면 요약, 주요 용어와 중요 개념이 자동으로 정리됩니다.
4. 요약이 표시되면 `퀴즈 생성`으로 문제를 풀거나 `질문하기`에서 수업 내용을 질문합니다.
5. 수업이 끝나면 `학습 종료`를 누릅니다.

## 기록과 업데이트

수업과 대화 기록은 `backend/data/reclass.sqlite3`에 저장되며 서버를 다시 실행하거나 코드를 업데이트해도 유지됩니다.

새 버전을 받으려면 프로젝트 폴더에서 실행합니다.

```bash
git pull
python3 setting.py
python3 open.py
```

중요한 기록은 업데이트 전에 `backend/data/reclass.sqlite3` 파일을 별도로 복사해 두는 것을 권장합니다.
