<script setup>
import { onMounted, ref } from 'vue'
import {
  Cpu,
  RotateCcw,
  Settings,
  TimerReset,
  Type,
  X,
} from '@lucide/vue'

const props = defineProps({
  settings: { type: Object, required: true },
  llmProvider: { type: String, default: '' },
  saving: { type: Boolean, default: false },
})

const emit = defineEmits(['cancel', 'close', 'reset-display', 'save', 'update'])
const modal = ref(null)
const performanceModes = [
  {
    value: 'eco',
    label: '절전',
    detail: '2K · 응답 직후 해제 · 1개씩 처리',
  },
  {
    value: 'balanced',
    label: '균형',
    detail: '4K · 2분 유지 · 1개씩 처리',
  },
  {
    value: 'performance',
    label: '성능 우선',
    detail: '8K 컨텍스트 · 15분간 메모리 유지',
  },
]

function updateSetting(key, value) {
  emit('update', { key, value })
}

function updateSummaryBatchSeconds(event) {
  const seconds = Math.round(Number(event.target.value))
  const normalized = Number.isFinite(seconds)
    ? Math.min(300, Math.max(60, seconds))
    : 120
  event.target.value = String(normalized)
  updateSetting('summaryBatchSeconds', normalized)
}

onMounted(() => modal.value?.focus())
</script>

<template>
  <div class="settings-backdrop" @click.self="emit('close')">
    <section
      ref="modal"
      class="settings-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-modal-title"
      tabindex="-1"
      @keydown.esc="emit('close')"
    >
      <header class="settings-modal-header">
        <span class="settings-modal-icon"><Settings :size="21" /></span>
        <div>
          <h2 id="settings-modal-title">설정</h2>
        </div>
        <button type="button" class="settings-close" aria-label="설정 닫기" @click="emit('close')">
          <X :size="20" />
        </button>
      </header>

      <div class="settings-sections">
        <section class="settings-section">
          <div class="settings-section-heading">
            <Type :size="18" />
            <h3>글자 크기 <span>(8pt ~ 14pt)</span></h3>
          </div>
          <div class="font-size-slider">
            <span aria-hidden="true">가</span>
            <input
              type="range"
              min="8"
              max="14"
              step="1"
              :value="settings.fontSize"
              aria-label="글자 크기"
              :aria-valuetext="`${settings.fontSize}포인트`"
              @input="updateSetting('fontSize', Number($event.target.value))"
            />
            <strong aria-hidden="true">가</strong>
            <output>{{ settings.fontSize }}pt</output>
          </div>
        </section>

        <section v-if="props.llmProvider === 'ollama'" class="settings-section">
          <div class="settings-section-heading">
            <Cpu :size="18" />
            <h3>로컬 LLM 자원 사용량</h3>
          </div>
          <div class="llm-performance-options" role="radiogroup" aria-label="로컬 LLM 자원 사용량">
            <button
              v-for="mode in performanceModes"
              :key="mode.value"
              type="button"
              role="radio"
              :aria-checked="settings.llmPerformanceMode === mode.value"
              :class="{ active: settings.llmPerformanceMode === mode.value }"
              @click="updateSetting('llmPerformanceMode', mode.value)"
            >
              <strong>{{ mode.label }}</strong>
              <span>{{ mode.detail }}</span>
            </button>
          </div>
          <p class="llm-performance-help">
            절전 모드는 발열과 대기 RAM을 줄이는 대신 응답이 느려지거나 긴 자료의 품질이 낮아질 수 있습니다.
            모델 실행 중에는 모델 자체 메모리가 필요합니다.
          </p>
        </section>

        <section class="settings-section">
          <div class="settings-section-heading">
            <TimerReset :size="18" />
            <h3>수업 요약 생성 주기 <span>(60초 ~ 300초)</span></h3>
          </div>
          <label class="summary-interval-control">
            <input
              type="number"
              min="60"
              max="300"
              step="1"
              :value="settings.summaryBatchSeconds"
              aria-label="수업 요약 생성 주기"
              @change="updateSummaryBatchSeconds"
              @keydown.enter.prevent="updateSummaryBatchSeconds"
            />
            <span>초</span>
          </label>
        </section>

        <section class="settings-reset-section">
          <strong>설정 초기화</strong>
          <button type="button" @click="emit('reset-display')">
            <RotateCcw :size="15" /> 초기화
          </button>
        </section>
      </div>

      <footer class="settings-modal-actions">
        <button type="button" class="settings-cancel-button" :disabled="saving" @click="emit('cancel')">
          취소
        </button>
        <button type="button" class="settings-save-button" :disabled="saving" @click="emit('save')">
          {{ saving ? '적용 중…' : '저장' }}
        </button>
      </footer>
    </section>
  </div>
</template>
