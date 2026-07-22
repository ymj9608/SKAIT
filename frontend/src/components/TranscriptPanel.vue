<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import {
  BookCheck,
  ChevronDown,
  Clock3,
  ListChecks,
  Pencil,
  Plus,
  Save,
  Search,
  Sparkles,
  Trash2,
  Waves,
} from '@lucide/vue'
import { findSummaryCardForSource } from '../utils/summaryEvidence'

const props = defineProps({
  summaryCards: { type: Array, default: () => [] },
  summaryNotes: { type: Array, default: () => [] },
  appendNote: { type: Function, required: true },
  updateSummaries: { type: Function, required: true },
})

const query = ref('')
const manualText = ref('')
const adding = ref(false)
const submitting = ref(false)
const summaryEditing = ref(false)
const summaryDrafts = ref({ cards: {}, notes: {} })
const deletedSummaryCardIds = ref([])
const deletedSummaryNoteIds = ref([])
const summaryEditSubmitting = ref(false)
const scrollArea = ref(null)
const highlightedCardId = ref(null)
let highlightTimer = null

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
].sort((left, right) => new Date(right.createdAt) - new Date(left.createdAt)))

const filteredItems = computed(() => {
  const deletedCardIds = new Set(deletedSummaryCardIds.value)
  const deletedNoteIds = new Set(deletedSummaryNoteIds.value)
  const visibleItems = summaryEditing.value
    ? feedItems.value.filter((item) => (
      item.type === 'summary'
        ? !deletedCardIds.has(item.id)
        : !deletedNoteIds.has(item.id)
    ))
    : feedItems.value
  const keyword = query.value.trim().toLowerCase()
  if (!keyword) return visibleItems
  return visibleItems.filter((item) => {
    if (item.type === 'note') return item.note.text.toLowerCase().includes(keyword)
    return item.card.topics?.some((topic) =>
      [topic.title, topic.summary, ...(topic.key_points || [])]
        .join(' ')
        .toLowerCase()
        .includes(keyword),
    )
  })
})

function keyPointsFromText(text) {
  return text
    .split('\n')
    .map((point) => point.trim())
    .filter(Boolean)
}

function summaryCardPayload(card) {
  const draft = summaryDrafts.value.cards[card.id]
  return {
    id: card.id,
    topics: draft.topics.map((topic) => ({
      title: topic.title.trim(),
      summary: topic.summary.trim(),
      key_points: keyPointsFromText(topic.keyPointsText),
    })),
  }
}

const pendingSummaryCards = computed(() => props.summaryCards
  .filter((card) => (
    summaryDrafts.value.cards[card.id]
    && !deletedSummaryCardIds.value.includes(card.id)
  ))
  .map((card) => summaryCardPayload(card))
  .filter((update) => {
    const card = props.summaryCards.find((item) => item.id === update.id)
    const original = {
      id: card.id,
      topics: card.topics.map((topic) => ({
        title: topic.title.trim(),
        summary: topic.summary.trim(),
        key_points: (topic.key_points || []).map((point) => point.trim()).filter(Boolean),
      })),
    }
    return JSON.stringify(update) !== JSON.stringify(original)
  }))

const pendingSummaryNotes = computed(() => props.summaryNotes
  .filter((note) => (
    summaryDrafts.value.notes[note.id] !== undefined
    && !deletedSummaryNoteIds.value.includes(note.id)
  ))
  .map((note) => ({ id: note.id, text: summaryDrafts.value.notes[note.id].trim() }))
  .filter((update) => {
    const note = props.summaryNotes.find((item) => item.id === update.id)
    return update.text !== note.text
  }))

const hasInvalidSummaryEdit = computed(() => {
  const cardsInvalid = props.summaryCards
    .filter((card) => !deletedSummaryCardIds.value.includes(card.id))
    .some((card) => {
      const draft = summaryDrafts.value.cards[card.id]
      return !draft || draft.topics.some((topic) => (
        !topic.title.trim()
        || !topic.summary.trim()
        || keyPointsFromText(topic.keyPointsText).length > 5
      ))
    })
  const notesInvalid = props.summaryNotes
    .filter((note) => !deletedSummaryNoteIds.value.includes(note.id))
    .some((note) => !(summaryDrafts.value.notes[note.id] ?? '').trim())
  return cardsInvalid || notesInvalid
})

const pendingDeletionCount = computed(() => (
  deletedSummaryCardIds.value.length + deletedSummaryNoteIds.value.length
))

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

async function submitManual() {
  const text = manualText.value.trim()
  if (!text || submitting.value) return
  submitting.value = true
  try {
    const succeeded = await props.appendNote(text)
    if (succeeded) {
      manualText.value = ''
      adding.value = false
    }
  } finally {
    submitting.value = false
  }
}

function cancelAdding() {
  manualText.value = ''
  adding.value = false
}

function summaryCardDraft(card) {
  return {
    topics: card.topics.map((topic) => ({
      title: topic.title,
      summary: topic.summary,
      keyPointsText: (topic.key_points || []).join('\n'),
    })),
  }
}

function syncNewSummaryDrafts() {
  if (!summaryEditing.value) return
  const cards = { ...summaryDrafts.value.cards }
  const notes = { ...summaryDrafts.value.notes }
  for (const card of props.summaryCards) {
    if (!cards[card.id]) cards[card.id] = summaryCardDraft(card)
  }
  for (const note of props.summaryNotes) {
    if (notes[note.id] === undefined) notes[note.id] = note.text
  }
  summaryDrafts.value = { cards, notes }
}

function startSummaryEditing() {
  cancelAdding()
  deletedSummaryCardIds.value = []
  deletedSummaryNoteIds.value = []
  summaryDrafts.value = {
    cards: Object.fromEntries(props.summaryCards.map((card) => [
      card.id,
      summaryCardDraft(card),
    ])),
    notes: Object.fromEntries(props.summaryNotes.map((note) => [note.id, note.text])),
  }
  summaryEditing.value = true
}

function cancelSummaryEditing() {
  summaryEditing.value = false
  summaryDrafts.value = { cards: {}, notes: {} }
  deletedSummaryCardIds.value = []
  deletedSummaryNoteIds.value = []
}

function deleteSummaryItem(item) {
  if (item.type === 'summary') {
    if (!deletedSummaryCardIds.value.includes(item.id)) {
      deletedSummaryCardIds.value = [...deletedSummaryCardIds.value, item.id]
    }
    return
  }
  if (!deletedSummaryNoteIds.value.includes(item.id)) {
    deletedSummaryNoteIds.value = [...deletedSummaryNoteIds.value, item.id]
  }
}

async function submitSummaryEdits() {
  if (summaryEditSubmitting.value || hasInvalidSummaryEdit.value) return
  const payload = {
    cards: pendingSummaryCards.value,
    notes: pendingSummaryNotes.value,
    deleted_card_ids: deletedSummaryCardIds.value,
    deleted_note_ids: deletedSummaryNoteIds.value,
  }
  if (!payload.cards.length && !payload.notes.length && !pendingDeletionCount.value) {
    cancelSummaryEditing()
    return
  }
  summaryEditSubmitting.value = true
  try {
    const succeeded = await props.updateSummaries(payload)
    if (succeeded) cancelSummaryEditing()
  } finally {
    summaryEditSubmitting.value = false
  }
}

async function focusSource(source) {
  const card = findSummaryCardForSource(props.summaryCards, source)
  if (!card) return false

  query.value = ''
  await nextTick()

  const cardElement = [...(scrollArea.value?.querySelectorAll('[data-summary-card-id]') || [])]
    .find((element) => element.dataset.summaryCardId === card.id)
  if (!cardElement) return false

  cardElement.open = true
  highlightedCardId.value = null
  await nextTick()
  highlightedCardId.value = card.id
  cardElement.scrollIntoView({
    behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
    block: 'center',
  })

  window.clearTimeout(highlightTimer)
  highlightTimer = window.setTimeout(() => {
    if (highlightedCardId.value === card.id) highlightedCardId.value = null
  }, 1400)
  return true
}

defineExpose({ focusSource })

onBeforeUnmount(() => window.clearTimeout(highlightTimer))

watch(
  () => feedItems.value.length,
  async () => {
    await nextTick()
    if (scrollArea.value) scrollArea.value.scrollTop = 0
  },
)

watch(
  [() => props.summaryCards, () => props.summaryNotes],
  syncNewSummaryDrafts,
)
</script>

<template>
  <section
    class="transcript-card summary-feed"
    :class="{ 'transcript-card--editing': summaryEditing }"
  >
    <header class="panel-header">
      <h2>수업 요약</h2>

      <div class="panel-actions">
        <button
          v-if="!summaryEditing"
          type="button"
          class="panel-edit-button"
          :disabled="!feedItems.length"
          @click="startSummaryEditing"
        >
          <Pencil :size="14" /> 편집
        </button>
        <template v-else>
          <button
            type="button"
            class="panel-edit-cancel"
            :disabled="summaryEditSubmitting"
            @click="cancelSummaryEditing"
          >
            취소
          </button>
          <button
            type="button"
            class="panel-edit-button panel-edit-button--active"
            :disabled="summaryEditSubmitting || hasInvalidSummaryEdit"
            @click="submitSummaryEdits"
          >
            <Save :size="14" /> {{ summaryEditSubmitting ? '저장 중' : '저장' }}
          </button>
        </template>
        <label class="search-box">
          <Search :size="16" />
          <input
            v-model="query"
            type="search"
            placeholder="요약 검색"
            aria-label="수업 요약 검색"
          />
        </label>
        <button
          v-if="!summaryEditing"
          class="soft-icon-button"
          title="요약 직접 추가"
          aria-label="요약 직접 추가"
          @click="adding = true"
        >
          <Plus :size="18" />
        </button>
      </div>
    </header>

    <form v-if="adding" class="manual-form" @submit.prevent="submitManual">
      <div class="manual-form-copy">
        <strong>요약 직접 추가</strong>
      </div>
      <textarea
        v-model="manualText"
        rows="2"
        maxlength="20000"
        autofocus
        placeholder="요약 내용을 입력하세요…"
      />
      <div class="manual-form-actions">
        <button type="button" class="form-button form-button--secondary" @click="cancelAdding">취소</button>
        <button type="submit" class="form-button form-button--primary" :disabled="!manualText.trim() || submitting">
          <Plus :size="14" /> 저장
        </button>
      </div>
    </form>

    <div
      ref="scrollArea"
      class="transcript-scroll summary-card-list"
      :class="{ 'transcript-scroll--empty': !filteredItems.length }"
    >
      <div v-if="!filteredItems.length" class="empty-transcript">
          <span class="empty-wave"><Waves :size="30" /></span>
          <h3>{{ query
            ? '검색 결과가 없어요'
            : (summaryEditing && pendingDeletionCount ? '삭제할 요약을 저장해 주세요' : '요약 내용이 여기 표시돼요')
          }}</h3>
          <p v-if="query">다른 단어로 검색해 보세요.</p>
          <p v-else-if="summaryEditing && pendingDeletionCount">취소하면 삭제 선택을 되돌릴 수 있어요.</p>
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

          <details
            v-if="item.type === 'summary'"
            class="summary-card"
            :class="{
              'summary-card--editing': summaryEditing,
              'summary-card--evidence': highlightedCardId === item.card.id,
            }"
            :data-summary-card-id="item.card.id"
            :open="summaryEditing ? true : undefined"
          >
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
              <div v-if="summaryEditing" class="summary-delete-row">
                <button type="button" @click="deleteSummaryItem(item)">
                  <Trash2 :size="14" /> 이 요약 삭제
                </button>
              </div>
              <section
                v-for="(topic, topicIndex) in summaryEditing
                  ? summaryDrafts.cards[item.card.id].topics
                  : item.card.topics"
                :key="`${item.card.id}-${topicIndex}`"
                class="summary-topic"
              >
                <div v-if="summaryEditing" class="summary-topic-edit-fields">
                  <label>
                    <span>주제 제목</span>
                    <input
                      v-model="topic.title"
                      maxlength="100"
                      :aria-label="`${topicIndex + 1}번째 요약 주제 제목`"
                      @keydown.esc="cancelSummaryEditing"
                    />
                  </label>
                  <label>
                    <span>요약 내용</span>
                    <textarea
                      v-model="topic.summary"
                      rows="4"
                      maxlength="800"
                      :aria-label="`${topicIndex + 1}번째 요약 내용`"
                      @keydown.esc="cancelSummaryEditing"
                    />
                  </label>
                  <label>
                    <span>핵심 포인트 <small>한 줄에 하나, 최대 5개</small></span>
                    <textarea
                      v-model="topic.keyPointsText"
                      rows="4"
                      maxlength="2500"
                      :aria-label="`${topicIndex + 1}번째 핵심 포인트`"
                      @keydown.esc="cancelSummaryEditing"
                    />
                  </label>
                </div>
                <template v-else>
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
                </template>
              </section>
              <div class="summary-grounding-note">
                <BookCheck :size="14" /> AI가 생성한 요약이며 직접 수정할 수 있습니다.
              </div>
            </div>
          </details>

          <div v-else class="personal-note-bubble">
            <template v-if="summaryEditing">
              <div class="summary-delete-row summary-delete-row--note">
                <button type="button" @click="deleteSummaryItem(item)">
                  <Trash2 :size="14" /> 이 요약 삭제
                </button>
              </div>
              <textarea
                v-model="summaryDrafts.notes[item.note.id]"
                class="summary-note-edit-textarea"
                rows="4"
                maxlength="20000"
                aria-label="직접 추가한 요약 편집"
                @keydown.esc="cancelSummaryEditing"
              />
            </template>
            <p v-else>{{ item.note.text }}</p>
          </div>
        </article>
    </div>
  </section>
</template>
