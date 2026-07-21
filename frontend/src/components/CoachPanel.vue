<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  ArrowUp,
  BookCheck,
  Bot,
  CheckCircle2,
  ChevronRight,
  Clock3,
  MessageCircleQuestion,
  PanelRightClose,
  Sparkles,
} from '@lucide/vue'
import { api } from '../services/api'

const props = defineProps({
  session: { type: Object, default: null },
  llmReady: { type: Boolean, default: true },
})
const emit = defineEmits(['updated', 'error', 'toggle'])

const tab = ref('note')
const question = ref('')
const asking = ref(false)
const chatScroll = ref(null)
const messages = ref([])
const panelWidth = ref(390)
const resizingPanel = ref(false)

const PANEL_WIDTH_STORAGE_KEY = 'reclass-coach-panel-width'
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
    <header class="coach-header">
      <div class="coach-heading">
        <button class="coach-panel-toggle" aria-label="AI 도우미 숨기기" title="AI 도우미 숨기기" @click="emit('toggle')">
          <PanelRightClose :size="17" />
        </button>
        <div class="coach-title">
          <span class="ai-orb"><Sparkles :size="18" /></span>
          <div><strong>AI 도우미</strong><span>수업 전용 튜터</span></div>
        </div>
      </div>
    </header>

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
      <section class="note-section learning-section learning-section--terms">
        <div class="section-heading">
          <span>
            <BookCheck :size="17" /> 알아둘 용어
            <small class="learning-item-count">{{ termItems.length }}</small>
          </span>
          <small class="learning-sort-label">최신순</small>
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
          <small class="learning-sort-label">최신순</small>
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

      <section v-if="material.review_questions?.length" class="review-card">
        <div class="review-card-icon"><BookCheck :size="21" /></div>
        <div>
          <strong>3분 복습</strong>
          <p>오늘 배운 내용, 질문으로 확인해 볼까요?</p>
          <button @click="sendQuestion(material.review_questions[0])">
            첫 질문 풀기 <ChevronRight :size="15" />
          </button>
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
</template>
