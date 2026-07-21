<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import {
  BookCheck,
  ChevronDown,
  Clock3,
  ListChecks,
  Plus,
  Search,
  Sparkles,
  Waves,
} from '@lucide/vue'

const props = defineProps({
  summaryCards: { type: Array, default: () => [] },
  summaryNotes: { type: Array, default: () => [] },
  appendNote: { type: Function, required: true },
})

const query = ref('')
const noteText = ref('')
const adding = ref(false)
const submitting = ref(false)
const scrollArea = ref(null)

const feedItems = computed(() => [
  ...props.summaryCards.map((card) => ({
    id: card.id,
    type: 'summary',
    createdAt: card.generated_at,
    card,
  })),
  ...props.summaryNotes.map((note) => ({
    id: note.id,
    type: 'note',
    createdAt: note.created_at,
    note,
  })),
].sort((left, right) => new Date(left.createdAt) - new Date(right.createdAt)))

const filteredItems = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  if (!keyword) return feedItems.value
  return feedItems.value.filter((item) => {
    if (item.type === 'note') return item.note.text.toLowerCase().includes(keyword)
    return item.card.topics?.some((topic) =>
      [topic.title, topic.summary, ...(topic.key_points || [])]
        .join(' ')
        .toLowerCase()
        .includes(keyword),
    )
  })
})

function koreaTime(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date)
}

function cardTitle(card) {
  return card.topics?.map((topic) => topic.title).join(' · ') || '수업 요약'
}

function cardPreview(card) {
  return card.topics?.map((topic) => topic.summary).join(' ') || ''
}

async function submitNote() {
  const text = noteText.value.trim()
  if (!text || submitting.value) return
  submitting.value = true
  try {
    const succeeded = await props.appendNote(text)
    if (succeeded) {
      noteText.value = ''
      adding.value = false
    }
  } finally {
    submitting.value = false
  }
}

function cancelAdding() {
  noteText.value = ''
  adding.value = false
}

watch(
  () => feedItems.value.length,
  async () => {
    await nextTick()
    if (scrollArea.value) scrollArea.value.scrollTop = scrollArea.value.scrollHeight
  },
)
</script>

<template>
  <section class="transcript-card summary-feed">
    <header class="panel-header">
      <h2>수업 요약</h2>
      <div class="panel-actions">
        <label class="search-box">
          <Search :size="16" />
          <input v-model="query" type="search" placeholder="요약·필기 검색" aria-label="수업 요약과 필기 검색" />
        </label>
        <button class="soft-icon-button" title="내 필기 추가" aria-label="내 필기 추가" @click="adding = true">
          <Plus :size="18" />
        </button>
      </div>
    </header>

    <form v-if="adding" class="manual-form" @submit.prevent="submitNote">
      <div class="manual-form-copy">
        <strong>내 필기</strong>
        <span>기억하고 싶은 내용을 자유롭게 적어 보세요.</span>
      </div>
      <textarea v-model="noteText" rows="2" maxlength="20000" autofocus placeholder="내가 정리하고 싶은 내용을 입력하세요…" />
      <div class="manual-form-actions">
        <button type="button" class="form-button form-button--secondary" @click="cancelAdding">취소</button>
        <button type="submit" class="form-button form-button--primary" :disabled="!noteText.trim() || submitting">
          <Plus :size="14" /> 저장
        </button>
      </div>
    </form>

    <div ref="scrollArea" class="transcript-scroll summary-card-list">
      <div v-if="!filteredItems.length" class="empty-transcript">
        <span class="empty-wave"><Waves :size="30" /></span>
        <h3>{{ query ? '검색 결과가 없어요' : '요약 내용이 여기 표시돼요' }}</h3>
        <p v-if="query">다른 단어로 검색해 보세요.</p>
      </div>

      <article
        v-for="item in filteredItems"
        :key="`${item.type}-${item.id}`"
        class="feed-message"
        :class="`feed-message--${item.type}`"
      >
        <div v-if="item.type === 'summary'" class="feed-sender">
          <span class="feed-avatar">교</span>
          <strong>교수님</strong>
          <time><Clock3 :size="11" /> {{ koreaTime(item.createdAt) }}</time>
        </div>
        <div v-else class="feed-sender feed-sender--me">
          <time><Clock3 :size="11" /> {{ koreaTime(item.createdAt) }}</time>
          <strong>나</strong>
          <span class="feed-avatar feed-avatar--me">나</span>
        </div>

        <details v-if="item.type === 'summary'" class="summary-card">
          <summary>
            <span class="summary-card-icon"><Sparkles :size="18" /></span>
            <span class="summary-card-heading">
              <span class="summary-card-meta"><em>{{ item.card.topics?.length || 0 }}개 주제</em></span>
              <strong>{{ cardTitle(item.card) }}</strong>
              <span class="summary-card-preview">{{ cardPreview(item.card) }}</span>
            </span>
            <span class="summary-card-toggle">
              펼쳐보기 <ChevronDown :size="16" />
            </span>
          </summary>

          <div class="summary-card-body">
            <section
              v-for="(topic, topicIndex) in item.card.topics"
              :key="`${item.card.id}-${topic.title}`"
              class="summary-topic"
            >
              <div class="summary-topic-heading">
                <span>{{ String(topicIndex + 1).padStart(2, '0') }}</span>
                <h3>{{ topic.title }}</h3>
              </div>
              <p>{{ topic.summary }}</p>
              <div v-if="topic.key_points?.length" class="summary-key-points">
                <strong><ListChecks :size="14" /> Key Points</strong>
                <ul>
                  <li v-for="point in topic.key_points" :key="point">{{ point }}</li>
                </ul>
              </div>
            </section>
            <div class="summary-grounding-note">
              <BookCheck :size="14" /> 수업 발언만 근거로 생성된 요약입니다.
            </div>
          </div>
        </details>

        <div v-else class="personal-note-bubble">
          <p>{{ item.note.text }}</p>
        </div>
      </article>
    </div>
  </section>
</template>
