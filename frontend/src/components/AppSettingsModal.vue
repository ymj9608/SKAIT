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
  llmModelDisabled: { type: Boolean, default: false },
  saving: { type: Boolean, default: false },
})

const emit = defineEmits(['cancel', 'close', 'reset-display', 'save', 'update'])
const modal = ref(null)
const qwenModels = [
  {
    value: 'qwen3:4b-instruct-2507-q4_K_M',
    label: 'Qwen 3 4B Instruct · 기본',
    detail: '약 2.5GB · 지시 이행과 구조화된 응답에 최적화',
  },
  {
    value: 'qwen3:8b-q4_K_M',
    label: 'Qwen 3 8B · 균형',
    detail: '약 5.2GB · 더 높은 품질, 연산량과 발열 증가',
  },
  {
    value: 'qwen3.5:9b-q4_K_M',
    label: 'Qwen 3.5 9B · 품질 우선',
    detail: '약 6.6GB · 최고 품질, 가장 많은 메모리와 연산량 사용',
  },
]

function updateSetting(key, value) {
  if (key === 'llmModel' && props.llmModelDisabled) return
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
  <div class="settings-backdrop">
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
            <h3>로컬 LLM 모델</h3>
          </div>
          <div
            class="llm-model-options"
            role="radiogroup"
            aria-label="로컬 LLM 모델"
            :aria-disabled="props.llmModelDisabled"
          >
            <button
              v-for="model in qwenModels"
              :key="model.value"
              type="button"
              role="radio"
              :aria-checked="settings.llmModel === model.value"
              :class="{ active: settings.llmModel === model.value }"
              :disabled="props.llmModelDisabled"
              @click="updateSetting('llmModel', model.value)"
            >
              <strong>{{ model.label }}</strong>
              <span>{{ model.detail }}</span>
            </button>
          </div>
          <p class="llm-model-help">
            <template v-if="props.llmModelDisabled">
              학습 또는 AI 작업 진행 중에는 모델을 변경할 수 없습니다. 작업이 끝난 뒤 변경해 주세요.
            </template>
            <template v-else>
            모델에 따라 GPU, CPU 연산량이 다르고, 성능이 떨어질 수 있습니다.
            </template>
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
