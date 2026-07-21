import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.main import generate_quiz, rebuild_study_material
from app.schemas import (
    LectureSession,
    QuizQuestion,
    StudyMaterial,
    SummaryCard,
    SummaryNote,
    SummaryTopic,
)
from app.services.study import (
    OllamaStudyAssistant,
    QUIZ_SYSTEM_PROMPT,
    build_quiz_context,
    quiz_items_are_similar,
    quiz_question_count,
    quiz_questions_are_similar,
    quiz_questions_from_payload,
)


def sample_card() -> SummaryCard:
    return SummaryCard(
        id="card-1",
        start_seconds=0,
        end_seconds=120,
        topics=[
            SummaryTopic(
                title="REST API 통신",
                summary="클라이언트는 HTTP 요청을 보내고 서버는 처리 결과를 응답합니다.",
                key_points=[
                    "GET은 주로 데이터 조회에 사용합니다.",
                    "POST는 주로 새로운 데이터 생성에 사용합니다.",
                ],
            )
        ],
    )


def sample_question(question_id: str = "quiz-1") -> QuizQuestion:
    return QuizQuestion(
        id=question_id,
        question="REST API의 요청과 응답 흐름을 가장 정확히 설명한 것은?",
        options=[
            "서버가 먼저 요청하고 클라이언트가 데이터를 응답한다.",
            "클라이언트가 요청하고 서버가 처리 결과를 응답한다.",
            "클라이언트와 서버는 요청 없이 상태 코드만 교환한다.",
            "서버는 요청을 저장하지만 처리 결과는 반환하지 않는다.",
        ],
        correct_option_index=1,
        explanation="요약에서는 클라이언트가 요청하고 서버가 결과를 응답한다고 설명합니다.",
    )


class RecordingRepository:
    def __init__(self) -> None:
        self.saved: LectureSession | None = None

    def save(self, session: LectureSession) -> LectureSession:
        self.saved = session.model_copy(deep=True)
        return self.saved


class RecordingQuizAssistant:
    def __init__(self, questions: list[QuizQuestion]) -> None:
        self.questions = questions
        self.context = ""
        self.question_count = 0

    async def generate_quiz(
        self,
        summary_context: str,
        question_count: int,
    ) -> list[QuizQuestion]:
        self.context = summary_context
        self.question_count = question_count
        return [question.model_copy(deep=True) for question in self.questions]


class QuizServiceTests(unittest.TestCase):
    def test_quiz_payload_keeps_only_valid_unique_questions(self) -> None:
        payload = {
            "questions": [
                {
                    "question": "HTTP 요청을 보내는 주체는 누구인가요?",
                    "options": ["클라이언트", "서버", "데이터베이스", "라우터"],
                    "correct_option_index": 0,
                    "explanation": "요약에서 클라이언트가 HTTP 요청을 보낸다고 했습니다.",
                },
                {
                    "question": " HTTP 요청을 보내는 주체는 누구인가요? ",
                    "options": ["클라이언트", "웹 브라우저", "서버", "라우터"],
                    "correct_option_index": 0,
                    "explanation": "중복 문항입니다.",
                },
                {
                    "question": "GET의 일반적인 용도는 무엇인가요?",
                    "options": ["조회", "조회", "생성", "삭제"],
                    "correct_option_index": 0,
                    "explanation": "중복 보기가 있어 제외되어야 합니다.",
                },
            ]
        }

        questions = quiz_questions_from_payload(payload)

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0].correct_option_index, 0)
        self.assertEqual(len(set(questions[0].options)), 4)

    def test_paraphrased_questions_are_treated_as_duplicates(self) -> None:
        previous_question = (
            "REST API에서 클라이언트와 서버의 상호작용을 가장 정확하게 설명한 것은?"
        )
        paraphrased_question = (
            "클라이언트와 서버가 REST API로 상호작용하는 방식으로 올바른 것은?"
        )
        shared_questions = [
            {
                "question": previous_question,
                "options": ["요청과 응답", "파일 복사", "화면 공유", "DB 종료"],
                "correct_option_index": 0,
                "explanation": "클라이언트의 요청에 서버가 응답합니다.",
            },
            {
                "question": paraphrased_question,
                "options": ["요청과 응답", "파일 복사", "화면 공유", "DB 종료"],
                "correct_option_index": 0,
                "explanation": "표현만 바꾼 이전 문항입니다.",
            },
            {
                "question": "POST의 일반적인 용도는 무엇인가요?",
                "options": ["데이터 생성", "서버 종료", "상태 코드 삭제", "연결 해제"],
                "correct_option_index": 0,
                "explanation": "POST는 새로운 데이터 생성에 주로 사용합니다.",
            },
        ]
        payload = {
            "questions": [
                shared_questions[1],
                shared_questions[2],
            ]
        }

        same_generation_questions = quiz_questions_from_payload(
            {"questions": shared_questions}
        )
        regenerated_questions = quiz_questions_from_payload(
            payload,
            excluded_questions=[previous_question],
        )

        self.assertTrue(
            quiz_questions_are_similar(previous_question, paraphrased_question)
        )
        self.assertEqual([question.question for question in same_generation_questions], [
            previous_question,
            "POST의 일반적인 용도는 무엇인가요?",
        ])
        self.assertEqual([question.question for question in regenerated_questions], [
            "POST의 일반적인 용도는 무엇인가요?",
        ])

    def test_different_concepts_are_not_removed_as_duplicates(self) -> None:
        self.assertFalse(
            quiz_questions_are_similar(
                "자바스크립트의 활용 범위로 올바른 것은?",
                "자바스크립트의 기본 성격으로 올바른 것은?",
            )
        )

    def test_same_answer_and_explanation_are_removed_even_when_wording_differs(self) -> None:
        first = QuizQuestion(
            question="자바스크립트는 어떤 분야에서 활용할 수 있는가?",
            options=[
                "웹 프론트엔드만",
                "모바일 앱만",
                "PC 애플리케이션만",
                "웹, 앱, PC 프로그램 개발 모두",
            ],
            correct_option_index=3,
            explanation=(
                "요약에서는 자바스크립트가 웹, 앱, PC 프로그램 개발에서 "
                "모두 활용 가능하다고 설명합니다."
            ),
        )
        repeated = QuizQuestion(
            question="자바스크립트를 배우면 어떤 분야의 개발이 가능해지는가?",
            options=[
                "웹 프론트엔드만",
                "백엔드만",
                "모바일 앱과 PC 앱만",
                "웹, 앱, PC 프로그램 개발 모두",
            ],
            correct_option_index=3,
            explanation=(
                "요약에서는 자바스크립트를 배우면 웹, 앱, PC 프로그램 개발이 "
                "가능하다고 설명합니다."
            ),
        )

        self.assertTrue(quiz_items_are_similar(first, repeated))
        questions = quiz_questions_from_payload(
            {
                "questions": [
                    first.model_dump(exclude={"id"}),
                    repeated.model_dump(exclude={"id"}),
                ]
            }
        )
        self.assertEqual([question.question for question in questions], [first.question])

    def test_subjective_and_ungrounded_questions_are_removed(self) -> None:
        source_context = (
            "요약: 강사는 실습을 통해 자바스크립트를 익힌다고 설명했습니다. "
            "자바스크립트 코드는 브라우저 개발자 도구에서 실행할 수 있습니다."
        )
        questions = quiz_questions_from_payload(
            {
                "questions": [
                    {
                        "question": "자바스크립트를 배우는 데 가장 중요한 요소는 무엇인가요?",
                        "options": ["문법 암기", "다른 언어 배제", "실습", "개발자 도구"],
                        "correct_option_index": 2,
                        "explanation": "실습이 가장 중요합니다.",
                        "evidence": "강사는 실습을 통해 자바스크립트를 익힌다고 설명했습니다.",
                    },
                    {
                        "question": "수업에서 자바스크립트 코드를 실행할 수 있다고 설명한 환경은?",
                        "options": ["문서 편집기", "개발자 도구", "이미지 뷰어", "PDF 리더"],
                        "correct_option_index": 1,
                        "explanation": "브라우저 개발자 도구에서 코드를 실행할 수 있습니다.",
                        "evidence": "자바스크립트 코드는 브라우저 개발자 도구에서 실행할 수 있습니다.",
                    },
                    {
                        "question": "수업에서 설명한 자바스크립트의 최초 발표 연도는?",
                        "options": ["1993년", "1994년", "1995년", "1996년"],
                        "correct_option_index": 2,
                        "explanation": "자바스크립트는 1995년에 발표되었습니다.",
                        "evidence": "자바스크립트는 1995년에 발표되었습니다.",
                    },
                    {
                        "question": "수업에서 자바스크립트 코드를 실행할 수 있다고 설명한 환경은?",
                        "options": ["문서 편집기", "개발자 도구", "이미지 뷰어", "PDF 리더"],
                        "correct_option_index": 3,
                        "explanation": "PDF 리더에서 실행할 수 있습니다.",
                        "evidence": "자바스크립트 코드는 브라우저 개발자 도구에서 실행할 수 있습니다.",
                    },
                ]
            },
            source_context=source_context,
        )

        self.assertEqual([question.question for question in questions], [
            "수업에서 자바스크립트 코드를 실행할 수 있다고 설명한 환경은?",
        ])

    def test_quiz_context_uses_visible_summary_and_personal_notes(self) -> None:
        material = StudyMaterial(
            summary_cards=[sample_card()],
            summary_notes=[SummaryNote(text="상태 코드의 의미도 복습하기")],
        )

        context = build_quiz_context(material)

        self.assertIn("주제: REST API 통신", context)
        self.assertIn("핵심: GET은 주로 데이터 조회", context)
        self.assertIn("사용자 추가 요약: 상태 코드의 의미", context)
        self.assertEqual(build_quiz_context(StudyMaterial()), "")

    def test_quiz_context_can_randomize_summary_sections(self) -> None:
        material = StudyMaterial(summary_cards=[sample_card()])

        with patch("app.services.study.QUIZ_RANDOM.shuffle") as shuffle:
            context = build_quiz_context(material, randomize_sections=True)

        shuffle.assert_called_once()
        self.assertIn("주제: REST API 통신", context)

    def test_question_count_is_always_between_one_and_ten(self) -> None:
        short_context = "요약: 하나의 짧은 주제입니다."
        long_context = "\n\n".join(
            f"주제: 주제 {index}\n요약: 서로 다른 내용 {index}"
            for index in range(12)
        )

        self.assertEqual(quiz_question_count(short_context), 1)
        self.assertEqual(quiz_question_count(long_context), 10)

    def test_model_prompt_requests_grounded_high_quality_options(self) -> None:
        assistant = OllamaStudyAssistant("http://127.0.0.1:11434", "test:8b")
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
              "questions": [
                {
                  "question": "REST API의 요청 흐름으로 알맞은 것은?",
                  "options": ["서버가 요청한다.", "클라이언트가 요청한다.", "DB가 요청한다.", "라우터가 요청한다."],
                  "correct_option_index": 1,
                  "explanation": "클라이언트가 HTTP 요청을 보냅니다.",
                  "evidence": "클라이언트가 HTTP 요청을 보냅니다."
                },
                {
                  "question": "POST의 일반적인 용도는 무엇인가요?",
                  "options": ["상태 코드 삭제", "서버 종료", "데이터 조회", "새 데이터 생성"],
                  "correct_option_index": 3,
                  "explanation": "POST는 새 데이터를 생성할 때 주로 사용합니다.",
                  "evidence": "POST는 새 데이터를 생성할 때 주로 사용합니다."
                }
              ]
            }"""

        assistant._chat = fake_chat
        questions = asyncio.run(
            assistant.generate_quiz(
                "요약: 클라이언트가 HTTP 요청을 보냅니다.\n"
                "핵심: POST는 새 데이터를 생성할 때 주로 사용합니다.",
                2,
            )
        )

        self.assertEqual(len(questions), 2)
        self.assertEqual(captured["max_tokens"], 2_800)
        self.assertEqual(captured["temperature"], 0.45)
        self.assertIn("Create between 1 and 2 questions", captured["messages"][-1]["content"])
        self.assertIn("Randomly sample", captured["messages"][-1]["content"])
        self.assertIn("Return fewer than 2", captured["messages"][-1]["content"])
        self.assertIn("objectively verifiable", captured["messages"][-1]["content"])
        self.assertIn("exact supporting sentence", captured["messages"][-1]["content"])
        self.assertIn("plausible misconceptions", QUIZ_SYSTEM_PROMPT)
        self.assertIn("only the supplied lecture summary", QUIZ_SYSTEM_PROMPT)

    def test_model_does_not_force_more_questions_than_the_content_supports(self) -> None:
        assistant = OllamaStudyAssistant("http://127.0.0.1:11434", "test:8b")
        call_count = 0

        def fake_chat(messages, max_tokens=700, temperature=0.2):
            nonlocal call_count
            call_count += 1
            return """{
              "questions": [{
                "question": "GET의 일반적인 용도는 무엇인가요?",
                "options": ["데이터 조회", "서버 종료", "연결 해제", "상태 코드 삭제"],
                "correct_option_index": 0,
                "explanation": "GET은 데이터 조회에 주로 사용합니다.",
                "evidence": "GET은 데이터 조회에 주로 사용합니다."
              }]
            }"""

        assistant._chat = fake_chat
        questions = asyncio.run(
            assistant.generate_quiz(
                "요약: GET은 데이터 조회에 주로 사용합니다.",
                5,
            )
        )

        self.assertEqual(len(questions), 1)
        self.assertEqual(call_count, 1)


class QuizApiTests(unittest.TestCase):
    def test_empty_summary_returns_the_requested_popup_message(self) -> None:
        session = LectureSession(material=StudyMaterial())

        with (
            patch("app.main.get_session_or_404", return_value=session),
            patch("app.main.assistant_or_503") as assistant_factory,
        ):
            with self.assertRaises(HTTPException) as context:
                asyncio.run(generate_quiz(session.id))

        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(
            context.exception.detail,
            "수업 내용이 없으므로 퀴즈를 생성할 수 없습니다.",
        )
        assistant_factory.assert_not_called()

    def test_generate_and_regenerate_replace_the_saved_quiz(self) -> None:
        old_question = sample_question("old-question")
        new_question = sample_question("new-question")
        new_question.question = "GET과 POST의 용도를 올바르게 연결한 것은?"
        session = LectureSession(
            material=StudyMaterial(
                summary_cards=[sample_card()],
                quiz_questions=[old_question],
            )
        )
        repository = RecordingRepository()
        assistant = RecordingQuizAssistant([new_question])

        with (
            patch("app.main.get_session_or_404", return_value=session),
            patch("app.main.assistant_or_503", return_value=assistant),
            patch("app.main.repository", return_value=repository),
        ):
            result = asyncio.run(generate_quiz(session.id))

        self.assertEqual([item.id for item in result.material.quiz_questions], ["new-question"])
        self.assertNotIn("old-question", [item.id for item in result.material.quiz_questions])
        self.assertIn("REST API 통신", assistant.context)
        self.assertGreaterEqual(assistant.question_count, 1)
        self.assertLessEqual(assistant.question_count, 10)
        self.assertIsNotNone(result.material.quiz_generated_at)
        self.assertIsNotNone(repository.saved)

    def test_background_generation_preserves_updates_made_while_waiting(self) -> None:
        initial_session = LectureSession(
            id="background-session",
            title="생성 시작 시점",
            material=StudyMaterial(summary_cards=[sample_card()]),
        )
        latest_session = initial_session.model_copy(deep=True)
        latest_session.title = "생성 중 수정한 제목"
        latest_session.material.summary_notes.append(
            SummaryNote(text="퀴즈 생성 중 추가한 요약")
        )
        repository = RecordingRepository()
        assistant = RecordingQuizAssistant([sample_question("background-quiz")])

        with (
            patch(
                "app.main.get_session_or_404",
                side_effect=[initial_session, latest_session],
            ),
            patch("app.main.assistant_or_503", return_value=assistant),
            patch("app.main.repository", return_value=repository),
        ):
            result = asyncio.run(generate_quiz(initial_session.id))

        self.assertEqual(result.title, "생성 중 수정한 제목")
        self.assertEqual(
            result.material.summary_notes[0].text,
            "퀴즈 생성 중 추가한 요약",
        )
        self.assertEqual(result.material.quiz_questions[0].id, "background-quiz")

    def test_summary_rebuild_does_not_delete_a_user_generated_quiz(self) -> None:
        question = sample_question()
        session = LectureSession(
            material=StudyMaterial(
                summary_cards=[sample_card()],
                quiz_questions=[question],
            )
        )

        with (
            patch("app.main.process_summary_batches", new=AsyncMock()),
            patch("app.main.process_learning_item_batches", new=AsyncMock()),
        ):
            asyncio.run(rebuild_study_material(session))

        self.assertEqual(session.material.quiz_questions[0].id, question.id)


if __name__ == "__main__":
    unittest.main()
