import asyncio
import importlib.util
import shutil
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings


@dataclass(slots=True)
class TranscriptionResult:
    text: str
    confidence: float | None = None


class SpeechToText(ABC):
    name: str
    model_name: str | None = None

    async def is_ready(self) -> bool:
        return True

    @abstractmethod
    async def transcribe(self, audio: bytes, filename: str) -> TranscriptionResult:
        raise NotImplementedError


class DemoSpeechToText(SpeechToText):
    name = "demo"
    _samples = (
        "오늘은 REST API가 무엇인지 살펴보겠습니다. 클라이언트와 서버는 HTTP 요청과 응답을 통해 데이터를 주고받습니다.",
        "FastAPI에서는 경로 연산 함수와 Pydantic 모델을 사용해서 입력값을 검증하고 API 문서를 자동으로 만들 수 있습니다.",
        "비동기 처리는 입출력을 기다리는 동안 다른 요청을 처리할 수 있게 해 주기 때문에 동시성이 필요한 서비스에 유용합니다.",
    )

    def __init__(self) -> None:
        self._cursor = 0

    async def transcribe(self, audio: bytes, filename: str) -> TranscriptionResult:
        # 실제 모델 설정 전에도 전체 UX를 점검할 수 있는 명시적인 데모 결과입니다.
        text = self._samples[self._cursor % len(self._samples)]
        self._cursor += 1
        return TranscriptionResult(text=text, confidence=0.96)


class HuggingFaceSpeechToText(SpeechToText):
    name = "huggingface"

    def __init__(self, token: str, model: str) -> None:
        from huggingface_hub import InferenceClient

        self.client = InferenceClient(token=token)
        self.model = model
        self.model_name = model

    async def transcribe(self, audio: bytes, filename: str) -> TranscriptionResult:
        def _request() -> TranscriptionResult:
            result = self.client.automatic_speech_recognition(audio, model=self.model)
            text = result.text if hasattr(result, "text") else str(result)
            return TranscriptionResult(text=text.strip(), confidence=None)

        return await asyncio.to_thread(_request)


class FasterWhisperSpeechToText(SpeechToText):
    name = "faster_whisper"

    def __init__(self, model_name: str) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "로컬 Whisper를 사용하려면 requirements-local-whisper.txt를 설치하세요."
            ) from exc
        self.model_name = model_name
        self.model = WhisperModel(model_name, device="auto", compute_type="auto")

    async def transcribe(self, audio: bytes, filename: str) -> TranscriptionResult:
        suffix = Path(filename).suffix or ".webm"

        def _run() -> TranscriptionResult:
            temp_path = ""
            try:
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
                    temporary.write(audio)
                    temp_path = temporary.name
                segments, info = self.model.transcribe(
                    temp_path,
                    language="ko",
                    vad_filter=True,
                    beam_size=5,
                )
                text = " ".join(segment.text.strip() for segment in segments).strip()
                confidence = getattr(info, "language_probability", None)
                return TranscriptionResult(text=text, confidence=confidence)
            finally:
                if temp_path:
                    Path(temp_path).unlink(missing_ok=True)

        return await asyncio.to_thread(_run)


class MlxWhisperSpeechToText(SpeechToText):
    """Apple Silicon의 Metal 가속을 사용하는 완전 로컬 Whisper."""

    name = "mlx_whisper"

    def __init__(self, model_name: str) -> None:
        if not shutil.which("ffmpeg"):
            raise RuntimeError("MLX Whisper 입력 변환에 ffmpeg가 필요합니다.")
        if importlib.util.find_spec("mlx_whisper") is None:
            raise RuntimeError(
                "MLX Whisper를 사용하려면 requirements-local-apple.txt를 설치하세요."
            )
        # import 시점에 Metal 장치를 초기화하므로 첫 STT 요청까지 지연합니다.
        # 덕분에 GPU가 잠시 사용 불가해도 텍스트 입력·챗봇 서버는 시작됩니다.
        self.client = None
        self.model_name = model_name
        self._lock = asyncio.Lock()

    async def transcribe(self, audio: bytes, filename: str) -> TranscriptionResult:
        suffix = Path(filename).suffix or ".webm"

        def _run() -> TranscriptionResult:
            if self.client is None:
                import mlx_whisper

                self.client = mlx_whisper
            temp_path = ""
            try:
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
                    temporary.write(audio)
                    temp_path = temporary.name
                result = self.client.transcribe(
                    temp_path,
                    path_or_hf_repo=self.model_name,
                    language="ko",
                    task="transcribe",
                    temperature=0,
                    verbose=None,
                    condition_on_previous_text=False,
                    word_timestamps=False,
                )
                text = str(result.get("text") or "").strip()
                # avg_logprob는 사용자에게 표시할 보정된 신뢰도가 아니므로
                # 임의의 백분율로 변환하지 않습니다.
                return TranscriptionResult(text=text, confidence=None)
            finally:
                if temp_path:
                    Path(temp_path).unlink(missing_ok=True)

        # MLX/Metal 모델을 여러 스레드에서 동시에 실행하지 않습니다.
        async with self._lock:
            return await asyncio.to_thread(_run)


def build_stt(settings: Settings) -> SpeechToText:
    if settings.stt_provider == "huggingface":
        if not settings.hf_token:
            raise RuntimeError("STT_PROVIDER=huggingface에는 HF_TOKEN이 필요합니다.")
        return HuggingFaceSpeechToText(settings.hf_token, settings.hf_stt_model)
    if settings.stt_provider == "faster_whisper":
        return FasterWhisperSpeechToText(settings.local_whisper_model)
    if settings.stt_provider == "mlx_whisper":
        return MlxWhisperSpeechToText(settings.mlx_whisper_model)
    return DemoSpeechToText()
