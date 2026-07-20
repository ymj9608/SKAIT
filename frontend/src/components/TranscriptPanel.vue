<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { Captions, Check, Plus, Search, Send, Waves } from '@lucide/vue'

const props = defineProps({
  segments: { type: Array, default: () => [] },
  recording: { type: Boolean, default: false },
  processing: { type: Boolean, default: false },
  appendText: { type: Function, required: true },
})

const query = ref('')
const manualText = ref('')
const adding = ref(false)
const submitting = ref(false)
const scrollArea = ref(null)

const filteredSegments = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  if (!keyword) return props.segments
  return props.segments.filter(
    (item) => item.text.toLowerCase().includes(keyword) || item.speaker.toLowerCase().includes(keyword),
  )
})

function timestamp(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0))
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}

async function submitText() {
  const text = manualText.value.trim()
  if (!text || submitting.value) return
  submitting.value = true
  try {
    const succeeded = await props.appendText(text)
    if (succeeded) {
      manualText.value = ''
      adding.value = false
    }
  } finally {
    submitting.value = false
  }
}

watch(
  () => props.segments.length,
  async () => {
    await nextTick()
    if (scrollArea.value) scrollArea.value.scrollTop = scrollArea.value.scrollHeight
  },
)
</script>

<template>
  <section class="transcript-card">
    <header class="panel-header">
      <div>
        <span class="eyebrow"><Captions :size="14" /> LIVE TRANSCRIPT</span>
        <h2>수업 전사</h2>
      </div>
      <div class="panel-actions">
        <label class="search-box">
          <Search :size="16" />
          <input v-model="query" type="search" placeholder="내용 검색" aria-label="전사 내용 검색" />
        </label>
        <button class="soft-icon-button" title="텍스트 직접 추가" @click="adding = !adding">
          <Plus :size="18" />
        </button>
      </div>
    </header>

    <form v-if="adding" class="manual-form" @submit.prevent="submitText">
      <div>
        <strong>전사 내용 직접 추가</strong>
        <span>모델이 놓친 내용을 보완할 수 있어요.</span>
      </div>
      <textarea v-model="manualText" rows="2" maxlength="20000" autofocus placeholder="교수님의 설명을 입력하세요…" />
      <button type="submit" class="send-square" :disabled="!manualText.trim() || submitting">
        <Send :size="17" />
      </button>
    </form>

    <div ref="scrollArea" class="transcript-scroll">
      <div v-if="!filteredSegments.length" class="empty-transcript">
        <span class="empty-wave"><Waves :size="30" /></span>
        <h3>{{ query ? '검색 결과가 없어요' : '아직 들려온 내용이 없어요' }}</h3>
        <p>{{ query ? '다른 단어로 검색해 보세요.' : '녹음을 시작하면 5초 무음 또는 최대 30초 단위로 수업 내용이 표시됩니다.' }}</p>
      </div>

      <article v-for="segment in filteredSegments" :key="segment.id" class="transcript-row">
        <time>{{ timestamp(segment.start_seconds) }}</time>
        <div class="speaker-avatar">교</div>
        <div class="transcript-content">
          <div class="speaker-line">
            <strong>{{ segment.speaker }}</strong>
            <span v-if="segment.confidence" class="confidence">
              <Check :size="12" /> {{ Math.round(segment.confidence * 100) }}%
            </span>
          </div>
          <p>{{ segment.text }}</p>
        </div>
      </article>

      <div v-if="recording || processing" class="listening-row">
        <span class="listening-bars"><i /><i /><i /><i /></span>
        <span>{{ processing ? '방금 들은 내용을 정리하고 있어요…' : '교수님의 설명을 듣고 있어요…' }}</span>
      </div>
    </div>

    <footer class="transcript-footer">
      <span><i class="live-indicator" :class="{ 'is-live': recording }" /> {{ recording ? '실시간 수신 중' : '녹음 대기' }}</span>
      <span>총 {{ segments.length }}개 구간</span>
    </footer>
  </section>
</template>
