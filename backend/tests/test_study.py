import asyncio
from pathlib import Path
import unittest

from app.config import Settings
from app.schemas import (
    BatchSummaryResult,
    LearningItem,
    SummaryCard,
    SummaryTopic,
    TranscriptSegment,
)
from app.services.stt import MlxWhisperSpeechToText
from app.services.study import (
    HuggingFaceStudyAssistant,
    LocalStudyAssistant,
    OllamaStudyAssistant,
    batch_summary_from_payload,
    build_batch_summary_messages,
    build_transcript_refinement_messages,
    build_learning_item_detection_messages,
    build_recent_learning_context,
    build_summary_context,
    build_study_assistant,
    extractive_summary,
    format_timestamp,
    merge_learning_items,
    rank_sources,
    refined_transcript_from_payload,
    remove_duplicate_topics,
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

    def test_transcript_refinement_prompt_uses_clean_context(self) -> None:
        messages = build_transcript_refinement_messages(
            "정답 레이블은 `y_train`에 저장했습니다.",
            "와이 언더바 트레인의 평균을 구합니다",
        )
        self.assertIn("transcription, not summarization", messages[0]["content"])
        self.assertIn("Never invent", messages[0]["content"])
        self.assertIn("`y_train`", messages[-1]["content"])
        self.assertIn("와이 언더바", messages[-1]["content"])
        self.assertTrue(
            any(
                message["role"] == "assistant"
                and "이상치(Outlier)" in message["content"]
                for message in messages
            )
        )

    def test_refined_transcript_requires_explicit_usable_content(self) -> None:
        self.assertIsNone(
            refined_transcript_from_payload(
                {"has_usable_content": False, "clean_transcript": "추측된 내용"}
            )
        )
        self.assertEqual(
            refined_transcript_from_payload(
                {
                    "has_usable_content": True,
                    "clean_transcript": "  `y_train`의 평균을 사용합니다.  ",
                }
            ),
            "`y_train`의 평균을 사용합니다.",
        )

    def test_ollama_transcript_refinement_uses_zero_temperature(self) -> None:
        assistant = OllamaStudyAssistant("http://127.0.0.1:11434", "test:4b")
        captured = {}

        def fake_chat(messages, max_tokens=700, temperature=0.2):
            captured.update(
                {
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
            )
            return """{
              "has_usable_content": true,
              "clean_transcript": "`y_train`의 평균을 기준으로 모델을 만듭니다."
            }"""

        assistant._chat = fake_chat
        cleaned = asyncio.run(
            assistant.refine_transcript(
                "정답은 `y_train`입니다.",
                "와이 언더바 트레인 평균으로 모델을 만듭니다",
            )
        )
        self.assertEqual(
            cleaned,
            "`y_train`의 평균을 기준으로 모델을 만듭니다.",
        )
        self.assertEqual(captured["temperature"], 0.0)
        self.assertEqual(captured["max_tokens"], 600)

    def test_batch_prompt_carries_previous_summary_and_enforces_grounding(self) -> None:
        messages = build_batch_summary_messages(
            self.segments,
            "직전에는 REST API 요청을 설명했습니다.",
            ["REST API 요청"],
        )
        self.assertIn("only factual evidence", messages[0]["content"])
        self.assertIn("has_meaningful_content=false", messages[0]["content"])
        self.assertIn("at most two", messages[0]["content"])
        self.assertIn("직전에는 REST API", messages[-1]["content"])
        self.assertIn('"REST API 요청"', messages[-1]["content"])
        self.assertIn(self.segments[0].text, messages[-1]["content"])
        self.assertTrue(
            any(
                message["role"] == "assistant"
                and '"has_meaningful_content":false' in message["content"].replace(" ", "")
                for message in messages
            )
        )

    def test_batch_payload_omits_meaningless_content_and_limits_topics(self) -> None:
        meaningless = batch_summary_from_payload(
            {
                "has_meaningful_content": False,
                "topics": [{"title": "무시", "summary": "노출되면 안 됩니다."}],
            }
        )
        self.assertFalse(meaningless.has_meaningful_content)
        self.assertEqual(meaningless.topics, [])

        meaningful = batch_summary_from_payload(
            {
                "has_meaningful_content": True,
                "topics": [
                    {
                        "title": f"주제 {index}",
                        "summary": f"수업에서 확인한 요약 {index}입니다.",
                        "key_points": ["근거가 있는 핵심입니다."],
                    }
                    for index in range(3)
                ],
                "learning_items": [],
            }
        )
        self.assertTrue(meaningful.has_meaningful_content)
        self.assertEqual(len(meaningful.topics), 2)

    def test_duplicate_batch_topic_is_removed_after_model_response(self) -> None:
        previous = SummaryCard(
            start_seconds=0,
            end_seconds=120,
            topics=[
                SummaryTopic(
                    title="REST API 요청",
                    summary="클라이언트는 HTTP 요청을 보내고 서버는 응답합니다.",
                    key_points=["요청과 응답으로 통신합니다."],
                )
            ],
        )
        repeated = BatchSummaryResult(
            has_meaningful_content=True,
            topics=[previous.topics[0].model_copy(deep=True)],
        )
        filtered = remove_duplicate_topics(repeated, [previous])
        self.assertFalse(filtered.has_meaningful_content)
        self.assertEqual(filtered.topics, [])

    def test_batch_summary_calls_llm_even_for_short_two_minute_transcript(self) -> None:
        assistant = OllamaStudyAssistant("http://127.0.0.1:11434", "test:4b")
        captured = {}

        def fake_chat(messages, max_tokens=700):
            captured.update({"messages": messages, "max_tokens": max_tokens})
            return """{
              "has_meaningful_content": true,
              "topics": [{
                "title": "REST API 통신",
                "summary": "클라이언트와 서버가 HTTP로 통신하는 방식입니다.",
                "key_points": ["요청과 응답을 사용합니다."]
              }],
              "learning_items": []
            }"""

        assistant._chat = fake_chat
        result = asyncio.run(
            assistant.summarize_batch(
                [self.segments[0]],
                "직전 요약",
                ["이전 주제"],
            )
        )
        self.assertTrue(result.has_meaningful_content)
        self.assertEqual(result.topics[0].title, "REST API 통신")
        self.assertEqual(captured["max_tokens"], 900)
        self.assertIn("직전 요약", captured["messages"][-1]["content"])

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

    def test_long_summary_uses_english_icl_and_returns_korean_term_explanations(self) -> None:
        assistant = OllamaStudyAssistant("http://127.0.0.1:11434", "test:4b")
        captured = {}

        def fake_chat(messages, max_tokens=700):
            captured.update({"messages": messages, "max_tokens": max_tokens})
            return """{
              "summary": "화살표 함수의 작성법을 소개합니다.",
              "key_points": ["화살표 함수는 함수를 작성하는 문법입니다."],
              "learning_items": [
                {
                  "type": "term",
                  "title": "화살표 함수(Arrow Function)",
                  "explanation": "function 키워드 대신 화살표 기호를 사용하는 자바스크립트 함수 문법입니다."
                },
                {
                  "type": "concept",
                  "title": "화살표 함수는 자신만의 this를 만들지 않는다",
                  "explanation": "함수가 정의된 바깥 범위의 this를 사용한다는 의미입니다."
                }
              ],
              "review_questions": ["화살표 함수는 어떤 문법인가요?"]
            }"""

        assistant._chat = fake_chat
        lecture_text = "자바스크립트에서 함수를 만드는 방법은 함수 표현식, 함수 선언식, 화살표 함수가 있습니다."
        segments = [
            TranscriptSegment(text=lecture_text * 5),
            TranscriptSegment(text="화살표 함수 문법과 함수 표현식의 차이를 예제 코드로 비교합니다." * 5),
        ]
        self.assertGreaterEqual(sum(len(item.text) for item in segments), 300)
        material = asyncio.run(assistant.summarize(segments))
        self.assertIn("화살표 함수", material.summary)
        self.assertEqual(material.keywords, ["화살표 함수(Arrow Function)"])
        self.assertIn("자바스크립트", material.keyword_explanations[material.keywords[0]])
        self.assertEqual([item.type for item in material.learning_items], ["term", "concept"])
        self.assertEqual(captured["max_tokens"], 900)
        self.assertGreaterEqual(len(captured["messages"]), 6)
        self.assertIn("All learner-facing output must be in Korean", captured["messages"][0]["content"])
        self.assertIn("Requirements:", captured["messages"][-1]["content"])
        self.assertIn(lecture_text, captured["messages"][-1]["content"])

    def test_short_summary_stays_extractive_and_leaves_terms_to_detector(self) -> None:
        assistant = OllamaStudyAssistant("http://127.0.0.1:11434", "test:4b")
        assistant._chat = lambda *args: self.fail("짧은 전체 요약은 생성 모델을 호출하면 안 됩니다.")
        segment = TranscriptSegment(
            text="트랜스포머에서는 멀티헤드 어텐션으로 여러 관계를 병렬로 학습합니다."
        )
        material = asyncio.run(assistant.summarize([segment]))
        self.assertEqual(material.summary, segment.text)
        self.assertEqual(material.key_points, [segment.text])
        self.assertEqual(material.keywords, [])
        self.assertEqual(material.keyword_explanations, {})
        self.assertEqual(material.learning_items, [])

    def test_learning_item_prompt_separates_context_and_uses_icl(self) -> None:
        messages = build_learning_item_detection_messages(
            "직전에는 REST API 요청 흐름을 설명했습니다.",
            "오늘은 실습 파일을 저장하고 잠시 쉬겠습니다.",
            ["REST API"],
        )
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("Select zero to three total items", messages[0]["content"])
        self.assertIn("term:", messages[0]["content"])
        self.assertIn("concept:", messages[0]["content"])
        self.assertTrue(
            any(
                message["role"] == "assistant"
                and message["content"] == '{"items":[]}'
                for message in messages
            )
        )
        self.assertTrue(
            any(
                message["role"] == "assistant"
                and '"이상치(Outlier)"' in message["content"]
                and '"아울라(Outlier)"' not in message["content"]
                for message in messages
            )
        )
        self.assertIn("<PREVIOUS_CONTEXT>", messages[-1]["content"])
        self.assertIn("<CURRENT_CONTEXT>", messages[-1]["content"])
        self.assertIn('["REST API"]', messages[-1]["content"])

    def test_detect_learning_items_returns_term_and_concept_in_korean(self) -> None:
        assistant = OllamaStudyAssistant("http://127.0.0.1:11434", "test:4b")
        assistant._chat = lambda messages, max_tokens=700: """{
          "items": [
            {
              "type": "term",
              "title": "Self-Attention",
              "explanation": "각 토큰이 다른 토큰을 얼마나 참고할지 계산하는 방식입니다."
            },
            {
              "type": "concept",
              "title": "Self-Attention은 입력 토큰 사이의 관계를 계산한다",
              "explanation": "각 입력이 다른 입력과 맺는 관련성을 계산해 문맥을 반영합니다."
            },
            {
              "type": "term",
              "title": "Unknown",
              "explanation": "English explanation only"
            }
          ]
        }"""
        detected = asyncio.run(
            assistant.detect_learning_items(
                "앞에서 트랜스포머 구조를 설명했습니다.",
                "셀프 어텐션으로 입력 토큰 사이의 관계를 계산합니다.",
                [],
            )
        )
        self.assertEqual([item.type for item in detected], ["term", "concept"])
        self.assertEqual(detected[0].title, "Self-Attention")
        self.assertIn("관련성", detected[1].explanation)

    def test_merge_learning_items_keeps_recent_twenty_and_syncs_legacy_terms(self) -> None:
        material = extractive_summary(self.segments)
        material.learning_items = [
            LearningItem(type="term", title=f"기존용어{index}", explanation="기존 한국어 설명입니다.")
            for index in range(20)
        ]
        detected = [
            LearningItem(
                type="term",
                title="REST API",
                explanation="HTTP를 이용해 클라이언트와 서버가 통신하도록 정한 인터페이스 방식입니다.",
            ),
            LearningItem(
                type="concept",
                title="서버는 요청과 응답으로 클라이언트와 통신한다",
                explanation="클라이언트가 요청을 보내면 서버가 처리 결과를 응답으로 돌려준다는 의미입니다.",
            ),
        ]
        merged = merge_learning_items(material, detected)
        self.assertEqual(len(merged.learning_items), 20)
        self.assertEqual(merged.learning_items[-1].type, "concept")
        self.assertIn("REST API", merged.keywords)
        self.assertIn("HTTP", merged.keyword_explanations["REST API"])
        self.assertLessEqual(len(merged.keywords), 8)

    def test_recent_learning_context_uses_previous_ninety_seconds(self) -> None:
        segments = [
            TranscriptSegment(start_seconds=0, text="범위 밖 초기 문맥"),
            TranscriptSegment(start_seconds=30, text="90초 전 문맥"),
            TranscriptSegment(start_seconds=60, text="60초 전 문맥"),
            TranscriptSegment(start_seconds=90, text="30초 전 문맥"),
            TranscriptSegment(start_seconds=120, text="현재 문맥"),
        ]
        previous, current = build_recent_learning_context(segments)
        self.assertNotIn("범위 밖 초기 문맥", previous)
        self.assertIn("90초 전 문맥", previous)
        self.assertIn("30초 전 문맥", previous)
        self.assertNotIn("현재 문맥", previous)
        self.assertIn("현재 문맥", current)

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
