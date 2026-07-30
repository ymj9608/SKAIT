<script setup>
import { onMounted, ref } from 'vue'
import {
  RotateCcw,
  Settings,
  TimerReset,
  Type,
  X,
} from '@lucide/vue'

defineProps({
  settings: { type: Object, required: true },
})

const emit = defineEmits(['cancel', 'close', 'reset-display', 'save', 'update'])
const modal = ref(null)

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
        <button type="button" class="settings-cancel-button" @click="emit('cancel')">
          취소
        </button>
        <button type="button" class="settings-save-button" @click="emit('save')">
          저장
        </button>
      </footer>
    </section>
  </div>
</template>
