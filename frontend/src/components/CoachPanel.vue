<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import {
  ArrowUp,
  BookCheck,
  Bot,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Lightbulb,
  ListChecks,
  MessageCircleQuestion,
  RefreshCw,
  Sparkles,
} from '@lucide/vue'
import { api } from '../services/api'

const props = defineProps({
  session: { type: Object, default: null },
  llmReady: { type: Boolean, default: true },
  llmProvider: { type: String, default: 'AI' },
  llmModel: { type: String, default: '' },
})
const emit = defineEmits(['updated', 'error'])

const tab = ref('note')
const question = ref('')
const asking = ref(false)
const refreshing = ref(false)
const chatScroll = ref(null)
const messages = ref([])

const material = computed(() => props.session?.material || {})

function timestamp(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0))
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}

function resetChat() {
  messages.value = [
    {
      role: 'assistant',
      text: '안녕하세요! 방금 수업에서 이해가 안 된 부분을 물어보세요. 전사 내용에서 근거를 찾아 쉽게 설명해 드릴게요.',
      sources: [],
    },
  ]
}

watch(() => props.session?.id, resetChat, { immediate: true })

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
  messages.value.push({ role: 'user', text })
  asking.value = true
  await scrollToBottom()
  try {
    const result = await api.chat(props.session.id, text)
    messages.value.push({
      role: 'assistant',
      text: result.answer,
      classContext: result.class_context,
      supplement: result.supplementary_explanation,
      knowledgeScope: result.knowledge_scope,
      sources: result.sources,
    })
  } catch (error) {
    emit('error', error.message)
    messages.value.push({ role: 'assistant', text: '답변을 만들지 못했어요. 잠시 후 다시 시도해 주세요.', sources: [] })
  } finally {
    asking.value = false
    await scrollToBottom()
  }
}

async function refresh() {
  if (!props.session || refreshing.value) return
  if (!props.llmReady) {
    emit('error', '로컬 LLM이 준비되지 않았습니다.')
    return
  }
  refreshing.value = true
  try {
    emit('updated', await api.refreshSummary(props.session.id))
  } catch (error) {
    emit('error', error.message)
  } finally {
    refreshing.value = false
  }
}
</script>

<template>
  <aside class="coach-panel">
    <header class="coach-header">
      <div class="coach-title">
        <span class="ai-orb"><Sparkles :size="18" /></span>
        <div><strong>AI Study Coach</strong><span>수업 전용 튜터 · {{ llmProvider }}</span></div>
      </div>
      <span class="ready-badge" :class="{ 'ready-badge--off': !llmReady }" :title="llmModel || llmProvider">
        <i /> {{ llmReady ? '준비됨' : '설정 필요' }}
      </span>
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
      <section class="summary-block">
        <div class="section-heading">
          <span><Lightbulb :size="17" /> 한눈에 보는 핵심</span>
          <button title="AI 노트 새로고침" :disabled="refreshing || !llmReady" @click="refresh">
            <RefreshCw :size="15" :class="{ spin: refreshing }" />
          </button>
        </div>
        <p>{{ material.summary }}</p>
      </section>

      <section class="note-section">
        <div class="section-heading"><span><ListChecks :size="17" /> 핵심 포인트</span></div>
        <ol v-if="material.key_points?.length" class="key-point-list">
          <li v-for="(point, index) in material.key_points" :key="point">
            <span>{{ String(index + 1).padStart(2, '0') }}</span>
            <p>{{ point }}</p>
          </li>
        </ol>
        <p v-else class="muted-copy">전사가 쌓이면 핵심 포인트가 만들어집니다.</p>
      </section>

      <section v-if="material.keywords?.length" class="note-section">
        <div class="section-heading"><span><Sparkles :size="17" /> 오늘의 키워드</span></div>
        <div class="keyword-list">
          <button v-for="keyword in material.keywords" :key="keyword" @click="sendQuestion(`${keyword}를 비전공자도 이해하게 쉽게 설명해줘`)" >
            # {{ keyword }}
          </button>
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
          :placeholder="llmReady ? '수업 내용에 대해 무엇이든 물어보세요…' : 'Ollama 모델을 준비하는 중입니다…'"
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
