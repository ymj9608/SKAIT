<script setup>
import { computed, onMounted, ref } from 'vue'
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
    value: 'qwen3.5:0.8b-q8_0',
    label: 'Qwen 3.5 0.8B · 실험용',
    detail: '약 1.0GB · 가장 가볍지만 전체 기능의 품질 저하가 큼',
  },
  {
    value: 'qwen3.5:2b-q4_K_M',
    label: 'Qwen 3.5 2B',
    detail: '약 1.9GB · 가볍지만 요약 품질이 낮을 수 있음',
  },
  {
    value: 'qwen3.5:4b-q4_K_M',
    label: 'Qwen 3.5 4B · 기본',
    detail: '약 3.4GB · 속도와 품질의 균형',
  },
  {
    value: 'qwen3.5:9b-q4_K_M',
    label: 'Qwen 3.5 9B · 품질 우선',
    detail: '약 6.6GB · 답변 품질 우선, 연산량과 발열 증가',
  },
]

const modelOptions = computed(() => {
  if (!props.settings.llmModel || qwenModels.some((item) => item.value === props.settings.llmModel)) {
    return qwenModels
  }
  return [
    {
      value: props.settings.llmModel,
      label: `${props.settings.llmModel} · 기존 모델`,
      detail: 'Qwen 3.5 모델을 선택하면 다시 선택할 수 없습니다.',
    },
    ...qwenModels,
  ]
})

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
            <h3>로컬 LLM 모델</h3>
          </div>
          <div
            class="llm-model-options"
            role="radiogroup"
            aria-label="로컬 LLM 모델"
            :aria-disabled="props.llmModelDisabled"
          >
            <button
              v-for="model in modelOptions"
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
            선택한 모델 하나를 전사 보정·요약·용어 탐지·퀴즈·질문 답변에 모두 사용합니다.
            기능을 바꿀 때 모델을 다시 불러오지 않습니다. 0.8B·2B는 저사양·실험용입니다.
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
