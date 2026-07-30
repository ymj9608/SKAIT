import asyncio
from pathlib import Path
import unittest

from app.config import Settings
from app.schemas import (
    BatchSummaryResult,
    LearningItem,
    StudyMaterial,
    SummaryCard,
    SummaryNote,
    SummaryTopic,
    TranscriptSegment,
)
from app.services.stt import MlxWhisperSpeechToText
from app.services.study import (
    HuggingFaceStudyAssistant,
    LocalStudyAssistant,
    OllamaStudyAssistant,
    batch_summary_from_payload,
    build_answer_messages,
    build_batch_summary_messages,
    build_transcript_refinement_messages,
    build_learning_item_detection_messages,
    build_reference_context,
    build_recent_learning_context,
    build_summary_context,
    build_study_assistant,
    extractive_summary,
    fallback_batch_summary,
    filter_instructional_text,
    format_timestamp,
    merge_learning_items,
    optimize_stored_material,
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

    def test_english_term_title_uses_only_its_canonical_spelling(self) -> None:
        english_term = LearningItem(
            type="term",
            title="임베딩(Embedding)",
            explanation="문장을 숫자 벡터로 표현하는 방식입니다.",
        )
        korean_term = LearningItem(
            type="term",
            title="상관계수",
            explanation="두 변수가 함께 움직이는 정도를 나타냅니다.",
        )
        concept = LearningItem(
            type="concept",
            title="화살표 함수(Arrow Function)는 자신만의 this를 만들지 않는다",
            explanation="정의된 바깥 범위의 this를 사용합니다.",
        )

        self.assertEqual(english_term.title, "Embedding")
        self.assertEqual(korean_term.title, "상관계수")
        self.assertEqual(
            concept.title,
            "화살표 함수(Arrow Function)는 자신만의 this를 만들지 않는다",
        )

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
        self.assertIn("evidence-grounded instructional editor", messages[0]["content"])
        self.assertIn("Accuracy and coverage of essential teaching", messages[0]["content"])
        self.assertIn("has_meaningful_content=false", messages[0]["content"])
        self.assertIn("casual conversation", messages[0]["content"])
        self.assertIn("off-topic tangents", messages[0]["content"])
        self.assertIn("at most two", messages[0]["content"])
        self.assertIn("copy one or more exact sentences or clauses", messages[0]["content"])
        self.assertIn("silently verify", messages[0]["content"])
        self.assertIn("직전에는 REST API", messages[-1]["content"])
        self.assertIn('"REST API 요청"', messages[-1]["content"])
        self.assertIn(self.segments[0].text, messages[-1]["content"])
        self.assertNotIn("<PDF_RAG_CONTEXT>", messages[-1]["content"])
        self.assertTrue(
            any(
                message["role"] == "assistant"
                and '"has_meaningful_content":false' in message["content"].replace(" ", "")
                for message in messages
            )
        )

    def test_fallback_batch_summary_omits_casual_conversation(self) -> None:
        result = fallback_batch_summary(
            [
                TranscriptSegment(
                    start_seconds=0,
                    text="어제 야구 보셨어요? 정말 재미있더라고요.",
                ),
                TranscriptSegment(
                    start_seconds=30,
                    text="점심은 뭐 드셨어요? 요즘 앞에 새로 생긴 식당이 괜찮대요.",
                ),
            ]
        )

        self.assertFalse(result.has_meaningful_content)
        self.assertEqual(result.topics, [])

    def test_instructional_filter_removes_orientation_but_keeps_lesson_facts(self) -> None:
        filtered = filter_instructional_text(
            "음성이 안 들리면 매니저님에게 알려주세요. "
            "실전 수준까지 끌어올리고 동료와 협업하는 것이 중요합니다. "
            "Pydantic 모델은 요청 필드와 타입을 검증합니다."
        )
        self.assertNotIn("매니저", filtered)
        self.assertNotIn("협업", filtered)
        self.assertIn("Pydantic", filtered)

    def test_fallback_batch_summary_omits_course_orientation(self) -> None:
        result = fallback_batch_summary(
            [
                TranscriptSegment(
                    text="이 과정에서는 실전 수준까지 끌어올리는 것이 중요합니다."
                ),
                TranscriptSegment(
                    text="동료들과 의사소통하고 협업하는 능력이 필요합니다."
                ),
                TranscriptSegment(
                    text="도움이 필요하면 매니저님에게 알려주세요."
                ),
            ]
        )
        self.assertFalse(result.has_meaningful_content)

    def test_existing_orientation_cards_are_removed_without_touching_notes(self) -> None:
        orientation_segment = TranscriptSegment(
            id="orientation",
            start_seconds=0,
            text="실전 수준까지 성장하고 동료들과 협업하는 것이 중요합니다.",
        )
        material = StudyMaterial(
            summary="실습 운영 안내입니다.",
            summary_cards=[
                SummaryCard(
                    start_seconds=0,
                    end_seconds=120,
                    source_segment_ids=[orientation_segment.id],
                    topics=[
                        SummaryTopic(
                            title="실습 운영",
                            summary="실습 진행 방식과 협업을 안내합니다.",
                            key_points=["협업이 중요합니다."],
                        )
                    ],
                )
            ],
            summary_notes=[SummaryNote(text="사용자가 작성한 메모")],
            learning_items=[
                LearningItem(
                    type="concept",
                    title="협업이 중요하다",
                    explanation="동료와 함께 일해야 한다는 뜻입니다.",
                )
            ],
        )
        optimized = optimize_stored_material(material, [orientation_segment])
        self.assertEqual(optimized.summary_cards, [])
        self.assertEqual(optimized.learning_items, [])
        self.assertEqual(optimized.summary_notes[0].text, "사용자가 작성한 메모")

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

    def test_batch_payload_requires_exact_evidence_and_removes_ungrounded_points(self) -> None:
        source = (
            "Pydantic 모델은 요청 필드와 타입을 검증합니다. "
            "검증에 실패하면 경로 함수 실행 전에 오류를 반환합니다."
        )
        result = batch_summary_from_payload(
            {
                "has_meaningful_content": True,
                "topics": [
                    {
                        "title": "Pydantic 요청 검증",
                        "summary": "Pydantic 모델은 요청 필드와 타입을 검증합니다.",
                        "key_points": [
                            "검증 실패는 경로 함수 실행 전에 오류로 처리됩니다.",
                            "평가 기준은 Biz 가치와 협업 능력입니다.",
                        ],
                        "evidence": "Pydantic 모델은 요청 필드와 타입을 검증합니다.",
                    }
                ],
            },
            source,
        )
        self.assertTrue(result.has_meaningful_content)
        self.assertEqual(
            result.topics[0].key_points,
            ["검증 실패는 경로 함수 실행 전에 오류로 처리됩니다."],
        )

        missing_evidence = batch_summary_from_payload(
            {
                "has_meaningful_content": True,
                "topics": [
                    {
                        "title": "근거 없는 주제",
                        "summary": "Pydantic 모델은 요청 필드를 검증합니다.",
                        "key_points": [],
                    }
                ],
            },
            source,
        )
        self.assertFalse(missing_evidence.has_meaningful_content)

    def test_batch_payload_rejects_an_unsupported_extra_summary_sentence(self) -> None:
        source = "Pydantic 모델은 요청 필드와 타입을 검증합니다."
        result = batch_summary_from_payload(
            {
                "has_meaningful_content": True,
                "topics": [
                    {
                        "title": "Pydantic 요청 검증",
                        "summary": (
                            "Pydantic 모델은 요청 필드와 타입을 검증합니다. "
                            "또한 NASA의 달 탐사 비행 계획을 자동으로 만듭니다."
                        ),
                        "key_points": [],
                        "evidence": [source],
                    }
                ],
            },
            source,
        )

        self.assertFalse(result.has_meaningful_content)

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
                "key_points": ["요청과 응답을 사용합니다."],
                "evidence": "REST API는 클라이언트와 서버가 HTTP로 소통하는 방식입니다."
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

    def test_batch_summary_falls_back_when_meaningful_model_output_lacks_evidence(self) -> None:
        assistant = OllamaStudyAssistant("http://127.0.0.1:11434", "test:4b")
        assistant._chat = lambda messages, max_tokens=700: """{
          "has_meaningful_content": true,
          "topics": [{
            "title": "REST API 통신",
            "summary": "REST API의 통신 방식을 설명합니다.",
            "key_points": []
          }]
        }"""

        result = asyncio.run(assistant.summarize_batch(self.segments))

        self.assertTrue(result.has_meaningful_content)
        self.assertTrue(result.topics)
        self.assertIn("REST API", result.topics[0].summary)

    def test_batch_summary_uses_pdf_only_as_optional_term_reference(self) -> None:
        assistant = OllamaStudyAssistant("http://127.0.0.1:11434", "test:4b")
        captured = {}

        def fake_chat(messages, max_tokens=700):
            captured.update({"messages": messages, "max_tokens": max_tokens})
            return '{"has_meaningful_content":false,"topics":[]}'

        assistant._chat = fake_chat
        asyncio.run(
            assistant.summarize_batch(
                [TranscriptSegment(text="트렌 세트로 모델을 학습합니다.")],
                reference_text="[PDF 2페이지] train set으로 모델을 학습합니다.",
            )
        )

        prompt = captured["messages"][-1]["content"]
        self.assertIn("<PDF_RAG_CONTEXT>", prompt)
        self.assertIn("train set", prompt)
        self.assertIn("not\nlecture evidence", captured["messages"][0]["content"])

    def test_summary_contains_material(self) -> None:
        material = extractive_summary(self.segments)
        self.assertTrue(material.summary)
        self.assertGreaterEqual(len(material.key_points), 2)
        self.assertIn("api", material.keywords)

    def test_rank_sources_prefers_matching_segment(self) -> None:
        sources = rank_sources("Pydantic은 무엇을 검증하나요?", self.segments)
        self.assertEqual(sources[0].start_seconds, 42)

    def test_rank_sources_returns_empty_without_matching_lecture_content(self) -> None:
        sources = rank_sources("양자역학의 불확정성 원리를 설명해줘", self.segments)
        self.assertEqual(sources, [])

    def test_rank_sources_returns_empty_for_question_without_search_terms(self) -> None:
        self.assertEqual(rank_sources("왜?", self.segments), [])

    def test_reference_context_selects_relevant_pdf_section(self) -> None:
        reference = "\n".join(
            [
                "[PDF 1페이지] 머신러닝 수업 자료",
                "[PDF 2페이지] 데이터셋은 train set과 test set으로 나눕니다.",
                "[PDF 3페이지] 배포와 모니터링을 설명합니다.",
            ]
        )
        context = build_reference_context(reference, "데이터셋을 학습용과 평가용으로 나눕니다.")
        self.assertIn("train set", context)

    def test_reference_context_rejects_generic_overlap_and_keeps_domain_terms(self) -> None:
        reference = "\n".join(
            [
                "[PDF 1페이지] 다양한 기법과 구조를 다음 연구에서 설명합니다.",
                "[PDF 2페이지] 클라우드 컴퓨팅은 딥러닝 모델의 연산을 지원합니다.",
                "[PDF 3페이지] 프롬프트 작성과 컨텍스트 관리 방법입니다.",
            ]
        )

        context = build_reference_context(
            reference,
            "클라우드 컴퓨팅이 등장한 뒤 딥러닝 모델을 설명했습니다.",
        )

        self.assertIn("[PDF 2페이지]", context)
        self.assertNotIn("[PDF 1페이지]", context)

    def test_reference_context_is_optional_when_no_pdf_or_no_related_term(self) -> None:
        self.assertEqual(build_reference_context(None, "딥러닝을 설명합니다."), "")
        self.assertEqual(
            build_reference_context(
                "[PDF 1페이지] 벡터 데이터베이스와 임베딩 검색",
                "오늘 점심은 무엇을 먹을까요?",
            ),
            "",
        )

    def test_reference_context_preserves_file_and_page_for_multiple_pdfs(self) -> None:
        reference = "\n".join(
            [
                "[PDF 파일: embeddings.pdf]",
                "[PDF 2페이지] 임베딩은 문장의 의미를 벡터로 표현합니다.",
                "[PDF 파일: retrieval.pdf]",
                "[PDF 7페이지] 벡터 데이터베이스는 유사한 임베딩을 검색합니다.",
            ]
        )

        context = build_reference_context(
            reference,
            "문장의 의미를 임베딩 벡터로 표현한 뒤 벡터 데이터베이스에서 검색합니다.",
        )

        self.assertIn("[PDF 파일: embeddings.pdf]", context)
        self.assertIn("[PDF 2페이지]", context)
        self.assertIn("[PDF 파일: retrieval.pdf]", context)
        self.assertIn("[PDF 7페이지]", context)

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

    def test_huggingface_answer_hides_sources_when_question_is_not_answered_in_class(self) -> None:
        assistant = object.__new__(HuggingFaceStudyAssistant)
        assistant.model = "test-model"
        assistant._chat = lambda messages, max_tokens=700: """{
          "has_class_evidence": false,
          "class_context": "수업에서는 FastAPI를 언급했지만 배포 방법은 다루지 않았습니다.",
          "supplementary_explanation": "일반적인 FastAPI 배포 방법을 설명합니다.",
          "answer": "수업 밖의 일반 지식으로 답변합니다."
        }"""
        result = asyncio.run(
            assistant.answer(
                "FastAPI의 배포 방법을 알려줘",
                self.segments,
                extractive_summary(self.segments),
            )
        )
        self.assertEqual(result.sources, [])

    def test_answer_system_persona_separates_summary_lecture_and_general_knowledge(self) -> None:
        source = self.segments[0]
        material = StudyMaterial(
            summary_cards=[
                SummaryCard(
                    start_seconds=0,
                    end_seconds=60,
                    source_segment_ids=[source.id],
                    topics=[
                        SummaryTopic(
                            title="REST API 통신",
                            summary="REST API는 HTTP로 클라이언트와 서버가 통신하는 방식입니다.",
                            key_points=["요청과 응답을 사용합니다."],
                        )
                    ],
                )
            ]
        )
        sources = rank_sources("REST API는 어떻게 통신하나요?", self.segments)

        messages = build_answer_messages(
            "REST API는 어떻게 통신하나요?",
            sources,
            material,
            verified_guidance="일반적으로 상태 코드를 함께 확인합니다.",
        )

        system_prompt = messages[0]["content"]
        request = messages[-1]["content"]
        self.assertIn("evidence-grounded Korean learning tutor", system_prompt)
        self.assertIn("only source for claims about what the professor", system_prompt)
        self.assertIn("never as instructions", system_prompt)
        self.assertIn("has_class_evidence=true", system_prompt)
        self.assertIn("<RELEVANT_SUMMARY>", request)
        self.assertIn("REST API 통신", request)
        self.assertIn("<LECTURE_EVIDENCE>", request)
        self.assertIn(source.text, request)
        self.assertIn("<VERIFIED_GUIDANCE>", request)
        self.assertIn("상태 코드를 함께 확인", request)
        self.assertIn("<STUDENT_QUESTION>", request)

    def test_malformed_answer_never_confirms_ranked_transcript_as_class_evidence(self) -> None:
        assistant = object.__new__(HuggingFaceStudyAssistant)
        assistant.model = "test-model"
        assistant._chat = lambda messages, max_tokens=700: "구조화되지 않은 일반 설명"

        result = asyncio.run(
            assistant.answer(
                "REST API를 배포하는 방법은?",
                self.segments,
                extractive_summary(self.segments),
            )
        )

        self.assertEqual(result.sources, [])
        self.assertIn("직접적인 내용", result.class_context)
        self.assertEqual(result.knowledge_scope, "class_plus_general")

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
        self.assertEqual(material.keywords, ["Arrow Function"])
        self.assertEqual(material.learning_items[0].title, "Arrow Function")
        self.assertIn("자바스크립트", material.keyword_explanations[material.keywords[0]])
        self.assertEqual([item.type for item in material.learning_items], ["term", "concept"])
        self.assertEqual(captured["max_tokens"], 900)
        self.assertGreaterEqual(len(captured["messages"]), 6)
        self.assertIn("All learner-facing output must be in Korean", captured["messages"][0]["content"])
        self.assertIn("Factual fidelity", captured["messages"][0]["content"])
        self.assertIn("REFERENCE_MATERIAL is retrieval context", captured["messages"][0]["content"])
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

    def test_pdf_reference_enables_short_summary_term_correction(self) -> None:
        assistant = object.__new__(HuggingFaceStudyAssistant)
        captured = {}

        def fake_chat(messages, max_tokens=700):
            captured.update({"messages": messages, "max_tokens": max_tokens})
            return """{
              "summary": "데이터를 train set과 test set으로 나누는 내용입니다.",
              "key_points": ["train set은 모델 학습에 사용합니다."],
              "learning_items": [{
                "type": "term",
                "title": "train set",
                "explanation": "모델을 학습시키는 데이터 모음입니다."
              }],
              "review_questions": ["train set의 역할은 무엇인가요?"]
            }"""

        assistant._chat = fake_chat
        material = asyncio.run(
            assistant.summarize(
                [TranscriptSegment(text="트렌드 셋으로 모델을 학습합니다.")],
                "[PDF 4페이지] train set은 모델 학습에 사용하고 test set은 평가에 사용합니다.",
            )
        )
        prompt = captured["messages"][-1]["content"]
        self.assertIn("<REFERENCE_MATERIAL>", prompt)
        self.assertIn("train set", prompt)
        self.assertIn("train set", material.summary)

    def test_pdf_reference_corrects_only_supported_stt_terms(self) -> None:
        assistant = object.__new__(HuggingFaceStudyAssistant)
        captured = {}

        def fake_chat(messages, max_tokens=700):
            captured.update({"messages": messages, "max_tokens": max_tokens})
            return '{"corrected_text":"train set으로 모델을 학습합니다."}'

        assistant._chat = fake_chat
        corrected = asyncio.run(
            assistant.correct_transcript(
                "트렌드 셋으로 모델을 학습합니다.",
                "[PDF 2페이지] train set으로 모델을 학습합니다.",
                "앞에서 데이터를 학습용과 평가용으로 분리한다고 설명했습니다.",
            )
        )
        self.assertEqual(corrected, "train set으로 모델을 학습합니다.")
        self.assertIn("Do not summarize", captured["messages"][-1]["content"])
        self.assertIn("PREVIOUS_LECTURE_CONTEXT", captured["messages"][-1]["content"])

    def test_transcript_is_unchanged_without_pdf_reference(self) -> None:
        assistant = object.__new__(HuggingFaceStudyAssistant)
        assistant._chat = lambda *args: self.fail("PDF가 없으면 보정 모델을 호출하면 안 됩니다.")
        original = "트렌드 셋으로 모델을 학습합니다."
        corrected = asyncio.run(assistant.correct_transcript(original, None))
        self.assertEqual(corrected, original)

    def test_learning_item_prompt_separates_context_and_uses_icl(self) -> None:
        messages = build_learning_item_detection_messages(
            "직전에는 REST API 요청 흐름을 설명했습니다.",
            "오늘은 실습 파일을 저장하고 잠시 쉬겠습니다.",
            ["REST API"],
        )
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("Select zero or one total item", messages[0]["content"])
        self.assertIn("Most chunks should return no item", messages[0]["content"])
        self.assertIn("term:", messages[0]["content"])
        self.assertIn("concept:", messages[0]["content"])
        self.assertIn("only its canonical English spelling", messages[0]["content"])
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
                and '"Outlier"' in message["content"]
                and '"아울라(Outlier)"' not in message["content"]
                for message in messages
            )
        )
        self.assertIn("<PREVIOUS_CONTEXT>", messages[-1]["content"])
        self.assertIn("<CURRENT_CONTEXT>", messages[-1]["content"])
        self.assertIn('["REST API"]', messages[-1]["content"])

    def test_detect_learning_items_keeps_only_the_single_most_important_item(self) -> None:
        assistant = OllamaStudyAssistant("http://127.0.0.1:11434", "test:4b")
        assistant._chat = lambda messages, max_tokens=700: """{
          "items": [
            {
              "type": "term",
              "title": "Self-Attention",
              "explanation": "각 토큰이 다른 토큰을 얼마나 참고할지 계산하는 방식입니다.",
              "evidence": "셀프 어텐션으로 입력 토큰 사이의 관계를 계산합니다."
            },
            {
              "type": "concept",
              "title": "Self-Attention은 입력 토큰 사이의 관계를 계산한다",
              "explanation": "각 입력이 다른 입력과 맺는 관련성을 계산해 문맥을 반영합니다.",
              "evidence": "셀프 어텐션으로 입력 토큰 사이의 관계를 계산합니다."
            },
            {
              "type": "term",
              "title": "Unknown",
              "explanation": "English explanation only",
              "evidence": "셀프 어텐션으로 입력 토큰 사이의 관계를 계산합니다."
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
        self.assertEqual([item.type for item in detected], ["term"])
        self.assertEqual(detected[0].title, "Self-Attention")

    def test_merge_learning_items_keeps_all_unique_items_and_syncs_legacy_terms(self) -> None:
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
        self.assertEqual(len(merged.learning_items), 22)
        self.assertEqual(merged.learning_items[0].title, "기존용어0")
        self.assertEqual(merged.learning_items[-1].type, "concept")
        self.assertIn("REST API", merged.keywords)
        self.assertIn("HTTP", merged.keyword_explanations["REST API"])
        self.assertLessEqual(len(merged.keywords), 6)

        preserved_without_new_items = merge_learning_items(material, [])
        self.assertEqual(len(preserved_without_new_items.learning_items), 20)

    def test_merge_learning_items_removes_parenthetical_spelling_duplicates(self) -> None:
        material = StudyMaterial(
            learning_items=[
                LearningItem(
                    type="term",
                    title="임베딩(Embedding)",
                    explanation="문장을 숫자 벡터로 표현하는 방식입니다.",
                )
            ]
        )
        merged = merge_learning_items(
            material,
            [
                LearningItem(
                    type="term",
                    title="임베딩(Embedding)",
                    explanation="의미를 비교할 수 있도록 문장을 숫자로 바꾼 표현입니다.",
                )
            ],
        )
        self.assertEqual(len(merged.learning_items), 1)
        self.assertEqual(merged.learning_items[0].title, "Embedding")

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
