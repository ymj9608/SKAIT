import asyncio
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from app.main import chat
from app.schemas import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ConversationMessage,
    LectureSession,
    TranscriptSegment,
)
from app.services.study import (
    HuggingFaceStudyAssistant,
    build_contextual_query,
    extractive_summary,
)


class ChatContextTests(unittest.TestCase):
    def test_chat_endpoint_persists_exchange_and_reuses_stored_history(self) -> None:
        session = LectureSession(
            chat_messages=[
                ConversationMessage(role="user", text="REST API가 뭐야?"),
                ConversationMessage(role="assistant", text="HTTP 기반 통신 방식입니다."),
            ]
        )
        captured = {}

        class FakeAssistant:
            async def answer(self, question, segments, material, history=None):
                captured["history"] = history
                return ChatResponse(
                    answer="요청과 응답으로 통신합니다.",
                    class_context="수업에서 REST API를 설명했습니다.",
                )

        class FakeRepository:
            def append_chat_messages(self, session_id, messages):
                captured["session_id"] = session_id
                captured["messages"] = messages

        with (
            patch("app.main.get_session_or_404", return_value=session),
            patch("app.main.assistant_or_503", return_value=FakeAssistant()),
            patch("app.main.repository", return_value=FakeRepository()),
        ):
            result = asyncio.run(chat(session.id, ChatRequest(message="조금 더 설명해줘")))

        self.assertEqual(result.answer, "요청과 응답으로 통신합니다.")
        self.assertEqual(captured["history"][0].content, "REST API가 뭐야?")
        self.assertEqual(
            [message.role for message in captured["messages"]],
            ["user", "assistant"],
        )
        self.assertEqual(captured["messages"][1].class_context, result.class_context)

    def test_chat_request_remains_compatible_without_history(self) -> None:
        request = ChatRequest(message="첫 질문")
        self.assertEqual(request.history, [])

    def test_chat_request_limits_history_to_twelve_messages(self) -> None:
        history = [
            ChatMessage(role="user", content=f"질문 {index}")
            for index in range(13)
        ]
        with self.assertRaises(ValidationError):
            ChatRequest(message="새 질문", history=history)

    def test_contextual_query_uses_recent_user_questions(self) -> None:
        history = [
            ChatMessage(role="user", content="무시할 오래된 질문"),
            ChatMessage(role="assistant", content="오래된 답변"),
            ChatMessage(role="user", content="포스트맨으로 API를 테스트할 수 있어?"),
            ChatMessage(role="assistant", content="네, 테스트할 수 있습니다."),
        ]

        query = build_contextual_query("그럼 그거는 어디서 받아?", history)

        self.assertIn("포스트맨", query)
        self.assertIn("그거", query)
        self.assertNotIn("오래된 답변", query)

    def test_generated_answer_receives_history_and_searches_with_context(self) -> None:
        assistant = object.__new__(HuggingFaceStudyAssistant)
        assistant.model = "test-model"
        captured_messages = []

        def fake_chat(messages, max_tokens=700):
            captured_messages.extend(messages)
            return """{
              "has_class_evidence": false,
              "class_context": "수업 기록에는 Postman 다운로드 위치가 없습니다.",
              "supplementary_explanation": "Postman 공식 웹사이트에서 받을 수 있습니다.",
              "answer": "Postman 공식 웹사이트에서 다운로드하세요."
            }"""

        assistant._chat = fake_chat
        segments = [
            TranscriptSegment(text="Postman으로 REST API 요청을 테스트할 수 있습니다."),
            TranscriptSegment(text="FastAPI는 Python 웹 프레임워크입니다."),
        ]
        history = [
            ChatMessage(role="user", content="포스트맨으로 API 요청을 테스트할 수 있어?"),
            ChatMessage(role="assistant", content="네, 테스트할 수 있습니다."),
        ]

        result = asyncio.run(
            assistant.answer(
                "그럼 그거는 어디서 받아?",
                segments,
                extractive_summary(segments),
                history,
            )
        )

        self.assertEqual(captured_messages[1]["content"], history[0].content)
        self.assertEqual(captured_messages[2]["content"], history[1].content)
        self.assertIn("그럼 그거는 어디서 받아?", captured_messages[-1]["content"])
        self.assertEqual(result.sources, [])
        self.assertIn("Postman", result.answer)


if __name__ == "__main__":
    unittest.main()
