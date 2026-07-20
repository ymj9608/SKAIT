import asyncio
from pathlib import Path
import unittest

from app.config import Settings
from app.schemas import TranscriptSegment
from app.services.stt import MlxWhisperSpeechToText
from app.services.study import (
    HuggingFaceStudyAssistant,
    LocalStudyAssistant,
    OllamaStudyAssistant,
    build_summary_context,
    build_study_assistant,
    extractive_summary,
    format_timestamp,
    rank_sources,
)


class StudyServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.segments = [
            TranscriptSegment(
                start_seconds=10,
                text="REST API는 클라이언트와 서버가 HTTP로 소통하는 방식입니다.",
            ),
            TranscriptSegment(
                start_seconds=42,
                text="Pydantic 모델은 FastAPI 요청 데이터를 검증합니다.",
            ),
        ]

    def test_timestamp(self) -> None:
        self.assertEqual(format_timestamp(125), "02:05")

    def test_summary_contains_material(self) -> None:
        material = extractive_summary(self.segments)
        self.assertTrue(material.summary)
        self.assertGreaterEqual(len(material.key_points), 2)
        self.assertIn("api", material.keywords)

    def test_rank_sources_prefers_matching_segment(self) -> None:
        sources = rank_sources("Pydantic은 무엇을 검증하나요?", self.segments)
        self.assertEqual(sources[0].start_seconds, 42)

    def test_local_answer_is_marked_as_class_only(self) -> None:
        assistant = LocalStudyAssistant()
        result = asyncio.run(
            assistant.answer(
                "Pydantic은 무엇인가요?",
                self.segments,
                extractive_summary(self.segments),
            )
        )
        self.assertEqual(result.knowledge_scope, "class_only")
        self.assertTrue(result.class_context)
        self.assertIsNone(result.supplementary_explanation)
        self.assertTrue(result.sources)

    def test_huggingface_answer_separates_class_and_general_knowledge(self) -> None:
        assistant = object.__new__(HuggingFaceStudyAssistant)
        assistant._chat = lambda messages, max_tokens=700: """{
          "class_context": "수업에서는 화살표 함수가 함수 작성법 중 하나라고만 언급했습니다.",
          "supplementary_explanation": "화살표 함수는 자신만의 this를 만들지 않고 외부 this를 사용합니다.",
          "answer": "콜백에서 외부 this를 유지할 때 유용합니다."
        }"""
        result = asyncio.run(
            assistant.answer(
                "화살표 함수를 사용하는 이유가 뭐야?",
                self.segments,
                extractive_summary(self.segments),
            )
        )
        self.assertEqual(result.knowledge_scope, "class_plus_general")
        self.assertIn("언급", result.class_context)
        self.assertIn("this", result.supplementary_explanation)

    def test_local_apple_providers_are_valid_settings(self) -> None:
        settings = Settings(
            stt_provider="mlx_whisper",
            llm_provider="ollama",
            _env_file=None,
        )
        self.assertEqual(settings.mlx_whisper_model, "mlx-community/whisper-large-v3-turbo")
        self.assertEqual(settings.ollama_model, "qwen3:8b")
        self.assertIsInstance(build_study_assistant(settings), OllamaStudyAssistant)

    def test_ollama_chat_uses_local_structured_output(self) -> None:
        assistant = OllamaStudyAssistant("http://127.0.0.1:11434", "test:4b")
        captured = {}

        def fake_request(path, payload=None, timeout=None):
            captured.update({"path": path, "payload": payload})
            return {"message": {"content": '{"answer":"로컬 응답"}'}}

        assistant._request_json = fake_request
        result = assistant._chat([{"role": "user", "content": "질문"}], 321)
        self.assertEqual(result, '{"answer":"로컬 응답"}')
        self.assertEqual(captured["path"], "/api/chat")
        self.assertFalse(captured["payload"]["stream"])
        self.assertFalse(captured["payload"]["think"])
        self.assertEqual(captured["payload"]["format"], "json")
        self.assertEqual(captured["payload"]["options"]["num_predict"], 321)

    def test_ollama_answer_adds_general_knowledge(self) -> None:
        assistant = OllamaStudyAssistant("http://127.0.0.1:11434", "test:4b")
        assistant._chat = lambda messages, max_tokens=700: """{
          "class_context": "수업에서는 화살표 함수를 함수 작성법으로만 소개했습니다.",
          "supplementary_explanation": "화살표 함수는 lexical this를 사용해 콜백에서 외부 this를 유지합니다.",
          "answer": "콜백의 this 변경 문제를 줄일 때 유용합니다."
        }"""
        result = asyncio.run(
            assistant.answer(
                "화살표 함수를 사용하는 이유가 뭐야?",
                self.segments,
                extractive_summary(self.segments),
            )
        )
        self.assertEqual(result.knowledge_scope, "class_plus_general")
        self.assertIn("this", result.supplementary_explanation)
        self.assertIn("콜백", result.answer)

    def test_short_lecture_summary_stays_grounded(self) -> None:
        assistant = OllamaStudyAssistant("http://127.0.0.1:11434", "test:4b")
        assistant._chat = lambda *args: self.fail("짧은 전사는 생성 모델을 호출하면 안 됩니다.")
        segment = TranscriptSegment(
            text="자바스크립트에서 함수를 만드는 방법은 함수 표현식, 함수 선언식, 화살표 함수가 있습니다."
        )
        material = asyncio.run(assistant.summarize([segment]))
        self.assertEqual(material.summary, segment.text)
        self.assertEqual(material.key_points, [segment.text])

    def test_long_summary_context_keeps_early_and_late_sections(self) -> None:
        segments = [
            TranscriptSegment(
                start_seconds=index * 30,
                text=f"{index}번째 구간에서 고유개념{index}을 설명합니다.",
            )
            for index in range(100)
        ]
        context = build_summary_context(segments)
        self.assertIn("고유개념0", context)
        self.assertIn("고유개념99", context)
        self.assertLess(len(context), sum(len(item.text) for item in segments) + 1000)

    def test_ollama_readiness_checks_installed_model(self) -> None:
        assistant = OllamaStudyAssistant("http://127.0.0.1:11434", "qwen3:8b")
        assistant._request_json = lambda *args: {
            "models": [{"name": "qwen3:8b"}]
        }
        self.assertTrue(asyncio.run(assistant.is_ready()))

    def test_mlx_stt_cleans_up_temporary_audio(self) -> None:
        captured_path = None

        class FakeMlxWhisper:
            @staticmethod
            def transcribe(path, **kwargs):
                nonlocal captured_path
                captured_path = path
                self.assertTrue(Path(path).exists())
                self.assertEqual(kwargs["language"], "ko")
                return {"text": "테스트 음성입니다.", "segments": []}

        stt = object.__new__(MlxWhisperSpeechToText)
        stt.client = FakeMlxWhisper()
        stt.model_name = "test-whisper"
        stt._lock = asyncio.Lock()
        result = asyncio.run(stt.transcribe(b"fake audio", "lecture.webm"))
        self.assertEqual(result.text, "테스트 음성입니다.")
        self.assertIsNone(result.confidence)
        self.assertFalse(Path(captured_path).exists())


if __name__ == "__main__":
    unittest.main()
