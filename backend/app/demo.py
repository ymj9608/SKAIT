from .schemas import LectureSession, StudyMaterial, TranscriptSegment


def build_demo_session() -> LectureSession:
    segments = [
        TranscriptSegment(
            start_seconds=12,
            speaker="교수님",
            confidence=0.97,
            text="오늘은 REST API의 기본 개념부터 시작하겠습니다. API는 서로 다른 프로그램이 약속된 방식으로 대화할 수 있게 해 주는 창구입니다.",
        ),
        TranscriptSegment(
            start_seconds=74,
            speaker="교수님",
            confidence=0.95,
            text="클라이언트가 서버에 HTTP 요청을 보내면 서버는 요청을 처리한 뒤 상태 코드와 데이터를 응답합니다. GET은 조회, POST는 생성을 표현할 때 주로 사용합니다.",
        ),
        TranscriptSegment(
            start_seconds=153,
            speaker="교수님",
            confidence=0.94,
            text="FastAPI의 경로 연산 함수에 Pydantic 모델을 연결하면 요청 데이터의 형식과 필수 값을 자동으로 검증할 수 있습니다.",
        ),
        TranscriptSegment(
            start_seconds=228,
            speaker="교수님",
            confidence=0.96,
            text="비동기 함수는 네트워크나 데이터베이스 응답을 기다리는 동안 다른 요청을 처리하게 해 줍니다. CPU 계산이 무조건 빨라진다는 뜻은 아닙니다.",
        ),
    ]
    return LectureSession(
        title="FastAPI와 REST API 기초",
        course_name="SKALA · 백엔드 프로그래밍",
        source_type="demo",
        status="ready",
        duration_seconds=305,
        segments=segments,
        material=StudyMaterial(
            summary="REST API는 클라이언트와 서버가 HTTP라는 약속으로 데이터를 주고받는 방식입니다. FastAPI는 Pydantic을 통해 입력을 검증하고, 비동기 처리로 입출력 대기 중 다른 요청을 처리할 수 있습니다.",
            key_points=[
                "API는 서로 다른 프로그램이 소통하는 약속된 창구입니다.",
                "HTTP 요청은 메서드와 경로로 의도를 표현하고, 응답은 상태 코드와 데이터를 담습니다.",
                "Pydantic 모델은 요청 데이터의 형식과 필수 값을 자동 검증합니다.",
                "비동기는 입출력 대기 시간을 활용하지만 CPU 작업 자체를 빠르게 만들지는 않습니다.",
            ],
            keywords=["REST API", "HTTP", "FastAPI", "Pydantic", "비동기", "상태 코드"],
            review_questions=[
                "GET과 POST는 각각 어떤 의도를 표현하나요?",
                "Pydantic이 잘못된 요청을 받으면 어떤 도움을 주나요?",
                "비동기 처리가 특히 유용한 상황은 언제인가요?",
            ],
        ),
    )
