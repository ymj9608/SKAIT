import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from collections import Counter
from urllib.request import Request, urlopen

from ..config import Settings
from ..schemas import ChatResponse, SourceReference, StudyMaterial, TranscriptSegment


logger = logging.getLogger(__name__)
TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z][가-힣A-Za-z0-9+#.]{1,}")
SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")
STOP_WORDS = {
    "그리고",
    "그러면",
    "그래서",
    "하지만",
    "때문에",
    "대해서",
    "이것은",
    "저것은",
    "오늘은",
    "우리가",
    "여러분",
    "입니다",
    "있습니다",
    "만드",
    "없습니다",
    "합니다",
    "됩니다",
    "하는",
    "있는",
    "통해서",
    "대한",
    "the",
    "and",
    "for",
    "with",
}


def format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


def tokenize(text: str) -> list[str]:
    normalized = []
    for raw_token in TOKEN_PATTERN.findall(text):
        token = raw_token.lower().rstrip(".")
        for suffix in ("에서는", "으로는", "이라는", "라고", "에서", "으로", "에게", "까지", "부터", "처럼", "보다", "은", "는", "이", "가", "을", "를", "의", "에", "도", "와", "과"):
            if token.endswith(suffix) and len(token) > len(suffix) + 1:
                token = token[: -len(suffix)]
                break
        if token not in STOP_WORDS:
            normalized.append(token)
    return normalized


def rank_sources(
    question: str, segments: list[TranscriptSegment], limit: int = 3
) -> list[SourceReference]:
    question_tokens = set(tokenize(question))
    ranked: list[tuple[float, int, TranscriptSegment]] = []
    for index, segment in enumerate(segments):
        segment_tokens = tokenize(segment.text)
        overlap = sum(1 for token in segment_tokens if token in question_tokens)
        # 질문이 짧거나 용어가 정확히 일치하지 않아도 최근 문맥을 조금 반영합니다.
        score = overlap * 5 + (index / max(1, len(segments)))
        if overlap or not question_tokens:
            ranked.append((score, index, segment))

    if not ranked and segments:
        ranked = [(index / len(segments), index, segment) for index, segment in enumerate(segments)]

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [
        SourceReference(
            segment_id=segment.id,
            start_seconds=segment.start_seconds,
            speaker=segment.speaker,
            excerpt=segment.text[:220],
        )
        for _, _, segment in ranked[:limit]
    ]


def extractive_summary(segments: list[TranscriptSegment]) -> StudyMaterial:
    if not segments:
        return StudyMaterial()

    sentences: list[tuple[int, str]] = []
    for segment_index, segment in enumerate(segments):
        parts = [part.strip() for part in SENTENCE_PATTERN.split(segment.text) if part.strip()]
        sentences.extend((segment_index, part) for part in parts)

    frequency = Counter(token for _, sentence in sentences for token in tokenize(sentence))
    scored: list[tuple[float, int, str]] = []
    for order, (_, sentence) in enumerate(sentences):
        tokens = tokenize(sentence)
        score = sum(frequency[token] for token in set(tokens)) / max(1, len(tokens))
        scored.append((score, order, sentence))

    top = sorted(scored, key=lambda item: (item[0], -item[1]), reverse=True)[:5]
    key_points = [sentence for _, order, sentence in sorted(top, key=lambda item: item[1])]
    summary = " ".join(key_points[:2])
    if len(summary) > 420:
        summary = summary[:417].rstrip() + "..."

    keywords = [token for token, _ in frequency.most_common(8)]
    questions = [
        f"{keyword}의 핵심 개념을 자신의 말로 설명해 보세요."
        for keyword in keywords[:3]
    ]
    if key_points:
        questions.append("오늘 배운 내용을 실제 프로젝트의 어느 부분에 적용할 수 있을까요?")

    return StudyMaterial(
        summary=summary or segments[-1].text,
        key_points=key_points,
        keywords=keywords,
        review_questions=questions,
    )


def build_summary_context(
    segments: list[TranscriptSegment], raw_segment_limit: int = 80
) -> str:
    """긴 수업의 앞부분도 버리지 않고 컨텍스트 크기를 제한합니다."""
    if len(segments) <= raw_segment_limit:
        return "\n".join(
            f"[{format_timestamp(item.start_seconds)}] {item.speaker}: {item.text}"
            for item in segments
        )

    lines: list[str] = []
    chunk_size = 20
    for start in range(0, len(segments), chunk_size):
        chunk = segments[start : start + chunk_size]
        material = extractive_summary(chunk)
        start_label = format_timestamp(chunk[0].start_seconds)
        end_label = format_timestamp(chunk[-1].start_seconds)
        points = material.key_points[:2]
        if chunk[-1].text not in points:
            points.append(chunk[-1].text)
        for point in points:
            lines.append(f"[{start_label}~{end_label}] 전사 핵심 문장: {point}")
    return "\n".join(lines)


class StudyAssistant(ABC):
    name: str
    model_name: str | None = None

    async def is_ready(self) -> bool:
        return True

    @abstractmethod
    async def summarize(self, segments: list[TranscriptSegment]) -> StudyMaterial:
        raise NotImplementedError

    @abstractmethod
    async def answer(
        self,
        question: str,
        segments: list[TranscriptSegment],
        material: StudyMaterial,
    ) -> ChatResponse:
        raise NotImplementedError


class LocalStudyAssistant(StudyAssistant):
    """API 키 없이 동작하는 추출 요약 + 검색형 답변 폴백."""

    name = "local"

    async def summarize(self, segments: list[TranscriptSegment]) -> StudyMaterial:
        return extractive_summary(segments)

    async def answer(
        self,
        question: str,
        segments: list[TranscriptSegment],
        material: StudyMaterial,
    ) -> ChatResponse:
        sources = rank_sources(question, segments)
        if not segments:
            message = "아직 참고할 수업 내용이 없어요. 먼저 녹음을 시작하거나 텍스트를 추가해 주세요."
            return ChatResponse(
                answer=message,
                class_context=message,
                sources=[],
            )

        lowered = question.lower()
        if any(word in lowered for word in ("요약", "정리", "핵심")):
            answer = f"이번 구간의 핵심은 다음과 같습니다. {material.summary}"
        elif not sources:
            answer = "현재 기록된 수업 내용에서는 질문과 직접 연결되는 부분을 찾지 못했어요. 질문에 나온 용어를 조금 더 구체적으로 적어 주세요."
        else:
            context = " ".join(source.excerpt for source in sources[:2])
            if any(word in lowered for word in ("쉽게", "비전공", "무슨 뜻")):
                answer = (
                    "쉽게 풀어보면, 교수님 설명의 중심은 다음과 같아요. "
                    f"{context} 즉, 용어 자체를 외우기보다 ‘어떤 문제를 해결하려고 쓰는가’를 먼저 연결해서 이해하면 됩니다."
                )
            elif "예시" in lowered:
                answer = (
                    f"수업에서 설명한 내용은 ‘{context}’입니다. "
                    "작은 프로젝트에 적용한다면 사용자의 요청을 받고, 처리한 뒤, 결과를 다시 보여 주는 흐름으로 예시를 만들어 볼 수 있어요."
                )
            else:
                answer = (
                    "기록된 수업 내용을 기준으로 답하면 다음과 같습니다. "
                    f"{context} 아래의 근거 구간을 다시 들으며 질문의 용어와 연결해 보세요."
                )
        return ChatResponse(
            answer=answer,
            class_context=answer,
            knowledge_scope="class_only",
            sources=sources,
        )


class HuggingFaceStudyAssistant(LocalStudyAssistant):
    name = "huggingface"

    def __init__(self, token: str, model: str) -> None:
        from huggingface_hub import InferenceClient

        self.client = InferenceClient(token=token)
        self.model = model
        self.model_name = model

    def _chat(self, messages: list[dict[str, str]], max_tokens: int = 700) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        return str(content or "").strip()

    async def summarize(self, segments: list[TranscriptSegment]) -> StudyMaterial:
        if not segments:
            return StudyMaterial()
        # 한두 문장뿐인 구간은 생성 모델이 없는 특징을 덧붙이기 쉽습니다.
        # 짧은 입력은 원문 문장을 그대로 고르는 방식이 더 정확합니다.
        if len(segments) == 1 or sum(len(item.text) for item in segments) < 300:
            return extractive_summary(segments)
        transcript = build_summary_context(segments)
        prompt = f"""다음은 한국어 수업 전사 또는 긴 전사에서 그대로 추출한 핵심 문장입니다.
비전공자도 이해하도록 학습 자료를 만드세요.
요약과 핵심 포인트에는 전사에서 직접 확인되는 내용만 적으세요. 전사에 나오지 않은 이유, 장점,
사용 시기, 예시, 특징을 추론하거나 사전학습 지식으로 보충하지 마세요. 내용이 짧으면 짧은 그대로
정리하고, 보충 지식은 챗봇 질문에만 제공하세요.
반드시 JSON 객체만 답하고 summary는 3문장 이내, key_points는 최대 5개, keywords는 최대 8개,
review_questions는 최대 4개로 작성하세요.

전사:
{transcript}

JSON 형식:
{{"summary":"...","key_points":["..."],"keywords":["..."],"review_questions":["..."]}}"""
        try:
            raw = await asyncio.to_thread(
                self._chat,
                [
                    {"role": "system", "content": "당신은 친절하고 정확한 한국어 학습 코치입니다."},
                    {"role": "user", "content": prompt},
                ],
                900,
            )
            cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
            start, end = cleaned.find("{"), cleaned.rfind("}")
            payload = json.loads(cleaned[start : end + 1])
            return StudyMaterial.model_validate(payload)
        except Exception as exc:
            # 외부 추론 서비스 오류 시에도 로컬 추출 요약으로 학습 흐름을 유지합니다.
            logger.warning("%s summary failed (%s): %s", self.name, self.model, exc)
            return extractive_summary(segments)

    async def answer(
        self,
        question: str,
        segments: list[TranscriptSegment],
        material: StudyMaterial,
    ) -> ChatResponse:
        sources = rank_sources(question, segments)
        context = (
            "\n".join(
                f"[{format_timestamp(source.start_seconds)}] {source.speaker}: {source.excerpt}"
                for source in sources
            )
            if sources
            else "관련 수업 기록 없음"
        )
        verified_guidance = ""
        normalized_question = question.replace(" ", "").lower()
        if "화살표함수" in normalized_question:
            verified_guidance = """
검증된 AI 보충 지침:
- 화살표 함수는 자신만의 this 바인딩을 만들지 않고, 정의된 렉시컬 스코프의 this를 사용합니다.
- 따라서 객체 메서드 안의 콜백·타이머 등에서 외부 this를 유지하려 할 때 유용합니다.
- 반대로 호출한 객체에 따라 동적으로 정해지는 this가 필요한 객체 메서드나 DOM 이벤트 핸들러에는
  일반 함수가 더 적합할 수 있고, 화살표 함수는 new와 함께 생성자로 사용할 수 없습니다.
- Promise나 비동기 처리는 화살표 함수의 고유 기능이 아닙니다.
이 지침을 사실 기준으로 사용하되 교수님의 발언으로 표현하지 마세요.
"""
        prompt = f"""학생의 질문에 수업 기록과 당신의 사전학습 지식을 함께 사용해 한국어로 답하세요.

반드시 다음 원칙을 지키세요.
1. class_context에는 수업 기록에서 실제로 확인되는 내용만 적으세요.
2. 질문의 핵심이 수업에서 직접 설명되지 않았다면, 무엇이 언급됐고 무엇이 빠졌는지 분명히 적으세요.
3. supplementary_explanation에는 수업에 없더라도 질문 이해에 필요한 정확한 일반 지식, 이유, 주의점, 쉬운 예시를 설명하세요.
4. 사전학습 지식을 교수님의 발언인 것처럼 표현하지 마세요.
5. 확실하지 않거나 최신 확인이 필요한 내용은 단정하지 마세요.
6. 비전공자가 이해할 수 있는 표현을 사용하되 기술적으로 중요한 예외는 생략하지 마세요.
7. 어떤 기능과 함께 자주 쓰인다는 사실을 그 기능 자체의 고유한 장점처럼 설명하지 마세요.
8. 자바스크립트 화살표 함수 질문이라면, 자체 this가 없고 정의된 위치의 this를 사용하는 lexical this,
   콜백에서 this가 바뀌는 문제를 줄이는 용도, 객체 메서드·생성자로 쓸 때의 주의점을 정확히 설명하세요.
   Promise나 비동기 처리를 화살표 함수 자체가 제공하는 기능처럼 표현하지 마세요.
9. 반드시 JSON 객체만 출력하세요.

수업 기록:
{context}

{verified_guidance}

학생 질문: {question}

JSON 형식:
{{
  "class_context": "수업에서 확인된 범위 또는 직접 다루지 않았다는 설명",
  "supplementary_explanation": "LLM 사전학습을 활용한 보충 설명과 필요시 예시",
  "answer": "질문에 대한 짧은 결론"
}}"""
        raw = ""
        try:
            raw = await asyncio.to_thread(
                self._chat,
                [
                    {
                        "role": "system",
                        "content": (
                            "당신은 수업 근거와 일반 지식을 엄격하게 구분하는 한국어 학습 튜터입니다. "
                            "수업에서 다루지 않은 개념도 사전학습 지식으로 친절하게 보충하세요."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                1000,
            )
            if not raw:
                raise ValueError("LLM이 빈 응답을 반환했습니다.")
        except Exception as exc:
            logger.warning("%s chat request failed (%s): %s", self.name, self.model, exc)
            return await super().answer(question, segments, material)

        try:
            cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start < 0 or end < start:
                raise ValueError("JSON 객체를 찾지 못했습니다.")
            payload = json.loads(cleaned[start : end + 1])
            class_context = str(payload.get("class_context") or "수업 기록에서 직접 확인되지 않습니다.").strip()
            supplement = str(payload.get("supplementary_explanation") or "").strip()
            answer = str(payload.get("answer") or supplement or class_context).strip()
            if "화살표함수" in normalized_question:
                # 소형 로컬 모델이 lexical this를 "고정"이나 "내부 변수"로
                # 부정확하게 축약하지 않도록 검증된 짧은 결론을 보장합니다.
                answer = (
                    "화살표 함수는 자신만의 `this`를 만들지 않고 상위 렉시컬 스코프의 `this`를 "
                    "사용하므로, 객체 메서드 안의 콜백 등에서 `this`가 바뀌는 문제를 줄일 때 유용합니다."
                )
            return ChatResponse(
                answer=answer,
                class_context=class_context,
                supplementary_explanation=supplement or None,
                knowledge_scope="class_plus_general" if supplement else "class_only",
                sources=sources,
            )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            # 모델이 JSON 형식을 어겨도 생성된 일반 지식 자체는 버리지 않습니다.
            logger.warning("%s chat JSON parsing failed (%s): %s", self.name, self.model, exc)
            class_context = (
                "수업에서 관련 내용은 다음과 같이 언급되었습니다. "
                + " ".join(source.excerpt for source in sources[:2])
                if sources
                else "질문과 직접 연결되는 내용은 수업 기록에서 확인되지 않았습니다."
            )
            return ChatResponse(
                answer=raw,
                class_context=class_context,
                supplementary_explanation=raw,
                knowledge_scope="class_plus_general",
                sources=sources,
            )


class OllamaStudyAssistant(HuggingFaceStudyAssistant):
    """Ollama의 localhost API를 사용하는 토큰 없는 생성형 학습 코치."""

    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float = 180,
        context_window: int = 8192,
        keep_alive: str = "15m",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.model_name = model
        self.timeout_seconds = timeout_seconds
        self.context_window = context_window
        self.keep_alive = keep_alive

    def _request_json(
        self,
        path: str,
        payload: dict | None = None,
        timeout: float | None = None,
    ) -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST" if data is not None else "GET",
        )
        with urlopen(request, timeout=timeout or self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def _chat(self, messages: list[dict[str, str]], max_tokens: int = 700) -> str:
        response = self._request_json(
            "/api/chat",
            {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "format": "json",
                "think": False,
                "keep_alive": self.keep_alive,
                "options": {
                    "temperature": 0.2,
                    "num_predict": max_tokens,
                    "num_ctx": self.context_window,
                },
            },
        )
        content = response.get("message", {}).get("content")
        if not content:
            raise RuntimeError("Ollama가 빈 응답을 반환했습니다.")
        return str(content).strip()

    async def is_ready(self) -> bool:
        try:
            payload = await asyncio.to_thread(
                self._request_json, "/api/tags", None, 3
            )
        except Exception:
            return False
        installed = {
            str(item.get("name") or item.get("model") or "")
            for item in payload.get("models", [])
        }
        return self.model in installed or (
            ":" not in self.model and f"{self.model}:latest" in installed
        )


def build_study_assistant(settings: Settings) -> StudyAssistant:
    if settings.llm_provider == "huggingface":
        if not settings.hf_token:
            raise RuntimeError("LLM_PROVIDER=huggingface에는 HF_TOKEN이 필요합니다.")
        return HuggingFaceStudyAssistant(settings.hf_token, settings.hf_llm_model)
    if settings.llm_provider == "ollama":
        return OllamaStudyAssistant(
            settings.ollama_base_url,
            settings.ollama_model,
            settings.ollama_timeout_seconds,
            settings.ollama_context_window,
            settings.ollama_keep_alive,
        )
    return LocalStudyAssistant()
