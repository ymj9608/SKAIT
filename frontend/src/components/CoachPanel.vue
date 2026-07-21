<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  ArrowUp,
  BookCheck,
  Bot,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  MessageCircleQuestion,
  RotateCcw,
  Sparkles,
  X,
} from '@lucide/vue'
import { api } from '../services/api'
import { selectQuizItems } from '../utils/quiz'

const props = defineProps({
  session: { type: Object, default: null },
  llmReady: { type: Boolean, default: true },
})
const emit = defineEmits(['updated', 'error'])

const tab = ref('note')
const question = ref('')
const asking = ref(false)
const chatScroll = ref(null)
const messages = ref([])
const panelWidth = ref(390)
const resizingPanel = ref(false)
const quizOpen = ref(false)
const quizIndex = ref(0)
const quizSelected = ref('')
const quizChecked = ref(false)
const quizAnswers = ref({})

const PANEL_WIDTH_STORAGE_KEY = 'skait-coach-panel-width'
const MIN_PANEL_WIDTH = 320
const MAX_PANEL_WIDTH = 680

const material = computed(() => props.session?.material || {})
const learningItems = computed(() => {
  if (material.value.learning_items?.length) {
    return [...material.value.learning_items].reverse()
  }
  return [...(material.value.keywords || [])].reverse().map((keyword) => ({
    type: 'term',
    title: keyword,
    explanation: material.value.keyword_explanations?.[keyword] || '',
  }))
})
const termItems = computed(() => learningItems.value.filter((item) => item.type === 'term'))
const conceptItems = computed(() => learningItems.value.filter((item) => item.type === 'concept'))
const quizItems = computed(() => selectQuizItems(learningItems.value))
const activeQuizItem = computed(() => quizItems.value[quizIndex.value] || null)
const quizOptions = computed(() => {
  const item = activeQuizItem.value
  if (!item) return []
  const fallbackOptions = [
    '화면의 모양과 배치만 꾸미기 위한 시각적 규칙입니다.',
    '컴퓨터의 전원을 직접 제어하는 물리적인 장치입니다.',
    '인터넷 연결 속도를 나타내기 위해 사용하는 측정 단위입니다.',
  ]
  const distractors = quizItems.value
    .filter((candidate) => candidate.title !== item.title)
    .map((candidate) => candidate.explanation)
  const uniqueDistractors = [...new Set([...distractors, ...fallbackOptions])]
    .filter((option) => option !== item.explanation)
    .slice(0, 3)
  const options = [item.explanation, ...uniqueDistractors]
  const correctPosition = quizIndex.value % options.length
  options.splice(correctPosition, 0, options.shift())
  return options
})
const quizCorrect = computed(() => quizSelected.value === activeQuizItem.value?.explanation)

function quizItemKey(item) {
  return item ? `${item.type || 'item'}:${item.title}` : ''
}

function quizStorageKey(sessionId = props.session?.id) {
  return sessionId ? `skait-quiz-progress-${sessionId}` : ''
}

function saveQuizProgress() {
  const storageKey = quizStorageKey()
  if (!storageKey || !activeQuizItem.value) return
  localStorage.setItem(storageKey, JSON.stringify({
    currentItemKey: quizItemKey(activeQuizItem.value),
    answers: quizAnswers.value,
  }))
}

function restoreCurrentQuizAnswer() {
  const answer = quizAnswers.value[quizItemKey(activeQuizItem.value)]
  const selected = answer?.selected || ''
  quizSelected.value = quizOptions.value.includes(selected) ? selected : ''
  quizChecked.value = Boolean(answer?.checked && quizSelected.value)
}

function loadQuizProgress() {
  quizIndex.value = 0
  quizAnswers.value = {}
  const storageKey = quizStorageKey()
  if (!storageKey) return
  try {
    const progress = JSON.parse(localStorage.getItem(storageKey) || '{}')
    if (progress.answers && typeof progress.answers === 'object' && !Array.isArray(progress.answers)) {
      const validItemKeys = new Set(quizItems.value.map(quizItemKey))
      quizAnswers.value = Object.fromEntries(
        Object.entries(progress.answers).filter(([itemKey]) => validItemKeys.has(itemKey)),
      )
    }
    const savedIndex = quizItems.value.findIndex(
      (item) => quizItemKey(item) === progress.currentItemKey,
    )
    if (savedIndex >= 0) quizIndex.value = savedIndex
  } catch {
    localStorage.removeItem(storageKey)
  }
  restoreCurrentQuizAnswer()
}

function allowedPanelWidth(width) {
  const compactLayout = window.innerWidth <= 1180
  const sidebarWidth = compactLayout ? 228 : 268
  const lessonMinWidth = compactLayout ? 420 : 480
  const availableWidth = window.innerWidth - sidebarWidth - lessonMinWidth
  return Math.min(Math.max(width, MIN_PANEL_WIDTH), Math.max(MIN_PANEL_WIDTH, Math.min(MAX_PANEL_WIDTH, availableWidth)))
}

function savePanelWidth() {
  localStorage.setItem(PANEL_WIDTH_STORAGE_KEY, String(Math.round(panelWidth.value)))
}

function stopPanelResize() {
  if (!resizingPanel.value) return
  resizingPanel.value = false
  document.body.classList.remove('is-resizing-coach')
  window.removeEventListener('pointermove', resizePanel)
  window.removeEventListener('pointerup', stopPanelResize)
  window.removeEventListener('pointercancel', stopPanelResize)
  savePanelWidth()
}

let resizeStartX = 0
let resizeStartWidth = 0

function resizePanel(event) {
  panelWidth.value = allowedPanelWidth(resizeStartWidth + resizeStartX - event.clientX)
}

function startPanelResize(event) {
  if (window.innerWidth <= 920) return
  event.preventDefault()
  resizeStartX = event.clientX
  resizeStartWidth = panelWidth.value
  resizingPanel.value = true
  document.body.classList.add('is-resizing-coach')
  window.addEventListener('pointermove', resizePanel)
  window.addEventListener('pointerup', stopPanelResize)
  window.addEventListener('pointercancel', stopPanelResize)
}

function resetPanelWidth() {
  panelWidth.value = allowedPanelWidth(390)
  savePanelWidth()
}

function fitPanelWidth() {
  if (window.innerWidth > 920) panelWidth.value = allowedPanelWidth(panelWidth.value)
}

function timestamp(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0))
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}

function resetChat() {
  quizOpen.value = false
  quizIndex.value = 0
  quizSelected.value = ''
  quizChecked.value = false
  quizAnswers.value = {}
  messages.value = [
    {
      role: 'assistant',
      text: '안녕하세요! 수업 내용 중에서 이해가 안 된 부분을 물어보세요.',
      sources: [],
    },
  ]
}

watch(() => props.session?.id, resetChat, { immediate: true })

onMounted(() => {
  const savedWidth = Number(localStorage.getItem(PANEL_WIDTH_STORAGE_KEY))
  if (Number.isFinite(savedWidth) && savedWidth > 0) panelWidth.value = allowedPanelWidth(savedWidth)
  window.addEventListener('resize', fitPanelWidth)
})

onBeforeUnmount(() => {
  stopPanelResize()
  window.removeEventListener('resize', fitPanelWidth)
})

async function scrollToBottom() {
  await nextTick()
  if (chatScroll.value) chatScroll.value.scrollTop = chatScroll.value.scrollHeight
}

async function sendQuestion(prompt) {
  const text = (prompt || question.value).trim()
  if (!text || asking.value || !props.session) return
  if (!props.llmReady) {
    emit('error', '로컬 LLM이 준비되지 않았습니다. Ollama와 모델 상태를 확인해 주세요.')
    return
  }
  tab.value = 'chat'
  question.value = ''
  const history = messages.value
    .slice(1)
    .filter((message) => !message.failed)
    .slice(-12)
    .map((message) => ({
      role: message.role,
      content: [message.text, message.classContext, message.supplement]
        .filter(Boolean)
        .join('\n')
        .slice(0, 4000),
    }))
  const userMessage = { role: 'user', text }
  messages.value.push(userMessage)
  asking.value = true
  await scrollToBottom()
  try {
    const result = await api.chat(props.session.id, text, history)
    messages.value.push({
      role: 'assistant',
      text: result.answer,
      classContext: result.class_context,
      supplement: result.supplementary_explanation,
      knowledgeScope: result.knowledge_scope,
      sources: result.sources,
    })
  } catch (error) {
    userMessage.failed = true
    emit('error', error.message)
    messages.value.push({
      role: 'assistant',
      text: '답변을 만들지 못했어요. 잠시 후 다시 시도해 주세요.',
      sources: [],
      failed: true,
    })
  } finally {
    asking.value = false
    await scrollToBottom()
  }
}

function openQuiz() {
  if (!quizItems.value.length) {
    emit('error', '객관식 퀴즈를 만들 수 있는 용어나 중요 개념이 아직 없습니다.')
    return
  }
  loadQuizProgress()
  quizOpen.value = true
}

function closeQuiz() {
  saveQuizProgress()
  quizOpen.value = false
}

function showNextQuiz() {
  quizIndex.value = (quizIndex.value + 1) % quizItems.value.length
  restoreCurrentQuizAnswer()
  saveQuizProgress()
}

function showPreviousQuiz() {
  quizIndex.value = (quizIndex.value - 1 + quizItems.value.length) % quizItems.value.length
  restoreCurrentQuizAnswer()
  saveQuizProgress()
}

function retryQuiz() {
  delete quizAnswers.value[quizItemKey(activeQuizItem.value)]
  quizSelected.value = ''
  quizChecked.value = false
  saveQuizProgress()
}

function selectQuizOption(option) {
  if (quizChecked.value) return
  quizSelected.value = option
  quizAnswers.value[quizItemKey(activeQuizItem.value)] = {
    selected: option,
    checked: false,
  }
  saveQuizProgress()
}

function submitQuiz() {
  if (quizChecked.value) {
    showNextQuiz()
    return
  }
  if (quizSelected.value) {
    quizChecked.value = true
    quizAnswers.value[quizItemKey(activeQuizItem.value)] = {
      selected: quizSelected.value,
      checked: true,
    }
    saveQuizProgress()
  }
}

</script>

<template>
  <aside
    class="coach-panel"
    :class="{ 'coach-panel--resizing': resizingPanel }"
    :style="{ '--coach-panel-width': `${panelWidth}px` }"
  >
    <button
      type="button"
      class="coach-panel-resizer"
      aria-label="AI 노트 패널 너비 조절"
      title="드래그하여 AI 노트 너비 조절 · 더블 클릭하여 초기화"
      @pointerdown="startPanelResize"
      @dblclick="resetPanelWidth"
    />

    <div class="coach-tabs" role="tablist">
      <button :class="{ active: tab === 'note' }" @click="tab = 'note'">
        <BookCheck :size="16" /> AI 노트
      </button>
      <button :class="{ active: tab === 'chat' }" @click="tab = 'chat'">
        <MessageCircleQuestion :size="16" /> 질문하기
        <span v-if="messages.length > 1" class="message-count">{{ messages.length - 1 }}</span>
      </button>
    </div>

    <div v-if="tab === 'note'" class="note-scroll">
      <section v-if="quizItems.length" class="review-card">
        <div class="review-card-icon"><BookCheck :size="21" /></div>
        <div>
          <strong>3분 복습</strong>
          <p>오늘 배운 내용을 간단한 퀴즈로 복습해 볼까요?</p>
          <button @click="openQuiz">
            복습 시작 <ChevronRight :size="15" />
          </button>
        </div>
      </section>

      <section class="note-section learning-section learning-section--terms">
        <div class="section-heading">
          <span>
            <BookCheck :size="17" /> 알아둘 용어
            <small class="learning-item-count">{{ termItems.length }}</small>
          </span>
        </div>
        <div v-if="termItems.length" class="keyword-list">
          <div
            v-for="(item, index) in termItems"
            :key="`term-${item.title}-${index}`"
            class="keyword-item keyword-item--term"
          >
            <div class="learning-item-heading">
              <button
                :title="`${item.title} 더 자세히 질문하기`"
                @click="sendQuestion(`${item.title}를 비전공자도 이해하게 쉽게 설명해줘`)"
              >
                {{ item.title }}
              </button>
            </div>
            <p v-if="item.explanation">{{ item.explanation }}</p>
          </div>
        </div>
        <div v-else class="learning-empty">
          <strong>아직 감지된 용어가 없습니다.</strong>
          <p>새로운 전문 용어가 감지되면 최신 항목부터 이곳에 표시됩니다.</p>
        </div>
      </section>

      <section class="note-section learning-section learning-section--concepts">
        <div class="section-heading">
          <span>
            <Sparkles :size="17" /> 중요 개념
            <small class="learning-item-count learning-item-count--concept">{{ conceptItems.length }}</small>
          </span>
        </div>
        <div v-if="conceptItems.length" class="keyword-list">
          <div
            v-for="(item, index) in conceptItems"
            :key="`concept-${item.title}-${index}`"
            class="keyword-item keyword-item--concept"
          >
            <div class="learning-item-heading">
              <button
                :title="`${item.title} 더 자세히 질문하기`"
                @click="sendQuestion(`${item.title}를 비전공자도 이해하게 쉽게 설명해줘`)"
              >
                {{ item.title }}
              </button>
            </div>
            <p v-if="item.explanation">{{ item.explanation }}</p>
          </div>
        </div>
        <div v-else class="learning-empty">
          <strong>아직 감지된 중요 개념이 없습니다.</strong>
          <p>새로운 원리나 개념이 감지되면 최신 항목부터 이곳에 표시됩니다.</p>
        </div>
      </section>

    </div>

    <div v-else ref="chatScroll" class="chat-scroll">
      <div v-for="(message, index) in messages" :key="index" class="chat-message" :class="`chat-message--${message.role}`">
        <span v-if="message.role === 'assistant'" class="bot-avatar"><Bot :size="16" /></span>
        <div class="message-body">
          <div v-if="message.role === 'assistant' && (message.classContext || message.supplement)" class="scoped-answer">
            <p v-if="message.supplement || message.text !== message.classContext" class="answer-lead">{{ message.text }}</p>
            <section v-if="message.classContext" class="scope-card scope-card--class">
              <div class="scope-title">
                <BookCheck :size="14" />
                <strong>수업에서 확인한 내용</strong>
              </div>
              <p>{{ message.classContext }}</p>
            </section>
            <section v-if="message.supplement" class="scope-card scope-card--supplement">
              <div class="scope-title">
                <Sparkles :size="14" />
                <strong>AI 보충 설명</strong>
                <span>사전학습 지식</span>
              </div>
              <p>{{ message.supplement }}</p>
            </section>
          </div>
          <p v-else>{{ message.text }}</p>
          <div v-if="message.sources?.length" class="source-list">
            <span class="source-label"><CheckCircle2 :size="13" /> 수업 근거</span>
            <button v-for="source in message.sources" :key="source.segment_id" class="source-chip">
              <Clock3 :size="12" /> {{ timestamp(source.start_seconds) }}
              <span>{{ source.excerpt }}</span>
            </button>
          </div>
        </div>
      </div>
      <div v-if="asking" class="chat-message chat-message--assistant">
        <span class="bot-avatar"><Bot :size="16" /></span>
        <span class="typing"><i /><i /><i /></span>
      </div>
    </div>

    <div class="question-composer">
      <div v-if="tab === 'chat' && messages.length === 1" class="suggestions">
        <button :disabled="!llmReady" @click="sendQuestion('오늘 수업 핵심을 세 줄로 요약해줘')">3줄 요약</button>
        <button :disabled="!llmReady" @click="sendQuestion('가장 어려운 개념을 쉽게 설명해줘')">쉽게 설명</button>
        <button :disabled="!llmReady" @click="sendQuestion('실제 예시를 하나 들어줘')">예시 보기</button>
      </div>
      <form @submit.prevent="sendQuestion()">
        <textarea
          v-model="question"
          rows="1"
          :placeholder="llmReady ? '질문을 입력하세요…' : 'AI 튜터를 준비하는 중입니다…'"
          :disabled="!llmReady"
          @keydown.enter.exact.prevent="sendQuestion()"
        />
        <button type="submit" :disabled="!question.trim() || asking || !llmReady" aria-label="질문 보내기">
          <ArrowUp :size="18" stroke-width="2.5" />
        </button>
      </form>
      <small>수업 근거와 AI 사전학습 지식을 구분해 답변합니다.</small>
    </div>
  </aside>

  <Teleport to="body">
    <Transition name="quiz">
      <div v-if="quizOpen" class="quiz-backdrop" @click.self="closeQuiz">
        <form class="quiz-modal" @submit.prevent="submitQuiz" @keydown.esc="closeQuiz">
          <button type="button" class="modal-close" aria-label="퀴즈 닫기" @click="closeQuiz">
            <X :size="19" />
          </button>

          <div class="quiz-heading">
            <span class="quiz-icon"><BookCheck :size="21" /></span>
            <div>
              <small>3분 복습</small>
              <h2>수업 내용을 확인해 볼까요?</h2>
            </div>
            <div class="quiz-progress" aria-label="퀴즈 문제 이동">
              <button type="button" aria-label="이전 문제" title="이전 문제" :disabled="quizItems.length <= 1" @click="showPreviousQuiz">
                <ChevronLeft :size="15" />
              </button>
              <span>{{ quizIndex + 1 }} / {{ quizItems.length }}</span>
              <button type="button" aria-label="다음 문제" title="다음 문제" :disabled="quizItems.length <= 1" @click="showNextQuiz">
                <ChevronRight :size="15" />
              </button>
            </div>
          </div>

          <section class="quiz-question">
            <small>QUESTION</small>
            <p>“{{ activeQuizItem?.title }}”에 대한 설명으로 가장 알맞은 것은?</p>
          </section>

          <div class="quiz-options" role="radiogroup" aria-label="퀴즈 선택지">
            <button
              v-for="(option, index) in quizOptions"
              :key="option"
              type="button"
              class="quiz-option"
              :class="{
                'quiz-option--selected': quizSelected === option,
                'quiz-option--correct': quizChecked && option === activeQuizItem?.explanation,
                'quiz-option--wrong': quizChecked && quizSelected === option && !quizCorrect,
              }"
              :aria-checked="quizSelected === option"
              role="radio"
              @click="selectQuizOption(option)"
            >
              <span>{{ ['A', 'B', 'C', 'D'][index] }}</span>
              <p>{{ option }}</p>
              <CheckCircle2 v-if="quizChecked && option === activeQuizItem?.explanation" :size="17" />
            </button>
          </div>

          <p v-if="quizChecked" class="quiz-feedback" :class="{ 'quiz-feedback--correct': quizCorrect }">
            {{ quizCorrect ? '정답이에요! 개념을 잘 이해하고 있어요.' : '정답을 확인했어요. 설명을 한 번 더 읽어보세요.' }}
          </p>

          <div class="quiz-actions">
            <button type="button" class="quiz-cancel" @click="closeQuiz">취소</button>
            <button v-if="quizChecked" type="button" class="quiz-retry" @click="retryQuiz">
              <RotateCcw :size="14" /> 다시 풀기
            </button>
            <button v-if="!quizChecked || quizItems.length > 1" type="submit" class="quiz-submit" :disabled="!quizSelected">
              {{ quizChecked ? '다음 문제' : '정답 확인' }}
            </button>
          </div>
        </form>
      </div>
    </Transition>
  </Teleport>
</template>
