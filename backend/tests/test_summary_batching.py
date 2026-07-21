import asyncio
import unittest

from app import main
from app.schemas import (
    BatchSummaryResult,
    LearningItem,
    LectureSession,
    SummaryTopic,
    TranscriptSegment,
)


class SummaryBatchingTests(unittest.TestCase):
    def test_unrefined_stt_is_never_sent_to_learning_item_detection(self) -> None:
        captured = {}

        class FakeAssistant:
            async def detect_learning_items(
                self,
                previous_context,
                current_context,
                recently_explained_items=None,
            ):
                captured["current"] = current_context
                return []

        session = LectureSession(
            duration_seconds=30,
            segments=[
                TranscriptSegment(
                    start_seconds=0,
                    text="프라이스 와이 언더버 트렌",
                    raw_text="프라이스 와이 언더버 트렌",
                    is_refined=False,
                ),
                TranscriptSegment(
                    start_seconds=15,
                    text="`y_train`의 평균을 기준으로 모델을 만듭니다.",
                    raw_text="와이 언더바 트레인의 평균으로 모델을 만듭니다",
                    is_refined=True,
                ),
            ],
        )
        previous_assistant = getattr(main.app.state, "assistant", None)
        main.app.state.assistant = FakeAssistant()
        try:
            asyncio.run(main.process_learning_item_batches(session, 30))
        finally:
            main.app.state.assistant = previous_assistant

        self.assertNotIn("프라이스", captured["current"])
        self.assertIn("`y_train`", captured["current"])

    def test_learning_items_are_detected_once_per_closed_thirty_second_window(self) -> None:
        calls = []

        class FakeAssistant:
            async def detect_learning_items(
                self,
                previous_context,
                current_context,
                recently_explained_items=None,
            ):
                calls.append(
                    {
                        "previous": previous_context,
                        "current": current_context,
                        "recent": recently_explained_items,
                    }
                )
                if len(calls) == 1:
                    return [
                        LearningItem(
                            type="term",
                            title="REST API",
                            explanation="요청과 응답으로 통신하는 방식으로 설명되었습니다.",
                        )
                    ]
                return [
                    LearningItem(
                        type="concept",
                        title="서버는 요청을 처리한 뒤 응답한다",
                        explanation="클라이언트 요청을 서버가 처리하고 결과를 돌려준다는 설명입니다.",
                    )
                ]

        session = LectureSession(
            duration_seconds=60,
            segments=[
                TranscriptSegment(start_seconds=0, text="REST API를 설명합니다."),
                TranscriptSegment(start_seconds=18, text="요청과 응답으로 통신합니다."),
                TranscriptSegment(start_seconds=30, text="서버가 요청을 처리합니다."),
            ],
        )
        previous_assistant = getattr(main.app.state, "assistant", None)
        main.app.state.assistant = FakeAssistant()
        try:
            asyncio.run(main.process_learning_item_batches(session, 29))
            self.assertEqual(calls, [])

            asyncio.run(main.process_learning_item_batches(session, 30))
            self.assertEqual(len(calls), 1)
            self.assertIn("REST API", calls[0]["current"])
            self.assertNotIn("서버가 요청", calls[0]["current"])
            self.assertEqual(session.material.learning_items[0].title, "REST API")

            asyncio.run(main.process_learning_item_batches(session, 60))
            self.assertEqual(len(calls), 2)
            self.assertIn("REST API", calls[1]["previous"])
            self.assertIn("서버가 요청", calls[1]["current"])
            self.assertEqual(calls[1]["recent"], ["REST API"])
            self.assertEqual(len(session.material.learning_items), 2)
            self.assertEqual(
                session.material.learning_items_processed_through_seconds,
                60,
            )
        finally:
            main.app.state.assistant = previous_assistant

    def test_llm_is_called_once_per_closed_two_minute_window(self) -> None:
        calls = []

        class FakeAssistant:
            async def summarize_batch(
                self,
                segments,
                previous_summary="",
                recent_topics=None,
            ):
                calls.append(
                    {
                        "segments": segments,
                        "previous_summary": previous_summary,
                        "recent_topics": recent_topics,
                    }
                )
                if len(calls) == 1:
                    return BatchSummaryResult(
                        has_meaningful_content=True,
                        topics=[
                            SummaryTopic(
                                title="첫 번째 주제",
                                summary="첫 2분 동안 설명한 수업 핵심입니다.",
                                key_points=["첫 번째 핵심입니다."],
                            )
                        ],
                    )
                return BatchSummaryResult()

        session = LectureSession(
            duration_seconds=240,
            segments=[
                TranscriptSegment(start_seconds=0, text="첫 번째 설명입니다."),
                TranscriptSegment(start_seconds=60, text="두 번째 설명입니다."),
                TranscriptSegment(start_seconds=119, text="첫 구간의 마지막 설명입니다."),
                TranscriptSegment(start_seconds=120, text="다음 구간의 안내뿐입니다."),
            ],
        )
        previous_assistant = getattr(main.app.state, "assistant", None)
        main.app.state.assistant = FakeAssistant()
        try:
            asyncio.run(main.process_summary_batches(session, 119))
            self.assertEqual(calls, [])

            asyncio.run(main.process_summary_batches(session, 120))
            self.assertEqual(len(calls), 1)
            self.assertEqual(
                [segment.start_seconds for segment in calls[0]["segments"]],
                [0, 60, 119],
            )
            self.assertEqual(len(session.material.summary_cards), 1)
            self.assertEqual(session.material.summary_processed_through_seconds, 120)

            asyncio.run(main.process_summary_batches(session, 240))
            self.assertEqual(len(calls), 2)
            self.assertIn("첫 2분", calls[1]["previous_summary"])
            self.assertEqual(calls[1]["recent_topics"], ["첫 번째 주제"])
            self.assertEqual(len(session.material.summary_cards), 1)
            self.assertEqual(session.material.summary_processed_through_seconds, 240)
        finally:
            main.app.state.assistant = previous_assistant


if __name__ == "__main__":
    unittest.main()
