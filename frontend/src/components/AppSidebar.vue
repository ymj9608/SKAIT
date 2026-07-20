<script setup>
import { BookOpen, ChevronLeft, Clock3, MonitorPlay, Plus, Radio, Sparkles } from '@lucide/vue'

defineProps({
  sessions: { type: Array, default: () => [] },
  activeId: { type: String, default: '' },
  open: { type: Boolean, default: false },
})

const emit = defineEmits(['select', 'new', 'close'])

function formatDate(value) {
  const date = new Date(value)
  const today = new Date()
  if (date.toDateString() === today.toDateString()) return '오늘'
  return new Intl.DateTimeFormat('ko-KR', { month: 'short', day: 'numeric' }).format(date)
}
</script>

<template>
  <aside class="sidebar" :class="{ 'sidebar--open': open }">
    <div class="brand-row">
      <button class="brand" aria-label="Re:Class 홈">
        <span class="brand-mark"><BookOpen :size="20" /></span>
        <span>Re:<strong>Class</strong></span>
      </button>
      <button class="icon-button sidebar-close" aria-label="메뉴 닫기" @click="emit('close')">
        <ChevronLeft :size="20" />
      </button>
    </div>

    <button class="new-session-button" @click="emit('new')">
      <Plus :size="18" stroke-width="2.4" />
      새 학습 시작
    </button>

    <div class="sidebar-label">
      <span>최근 수업</span>
      <span>{{ sessions.length }}</span>
    </div>

    <nav class="session-list" aria-label="학습 세션 목록">
      <button
        v-for="session in sessions"
        :key="session.id"
        class="session-item"
        :class="{ 'session-item--active': session.id === activeId }"
        @click="emit('select', session.id)"
      >
        <span class="session-icon">
          <Radio v-if="session.status === 'recording'" :size="16" />
          <MonitorPlay v-else-if="session.source_type === 'youtube'" :size="16" />
          <Clock3 v-else :size="16" />
        </span>
        <span class="session-copy">
          <strong>{{ session.title }}</strong>
          <small>{{ formatDate(session.created_at) }} · {{ session.course_name }}</small>
        </span>
      </button>
      <div v-if="!sessions.length" class="sidebar-empty">
        <Sparkles :size="20" />
        첫 학습을 시작해 보세요.
      </div>
    </nav>

    <div class="sidebar-tip">
      <span class="tip-orbit"><Sparkles :size="17" /></span>
      <div>
        <strong>비전공자 모드</strong>
        <p>어려운 개념을 쉬운 말과 예시로 바꿔 드려요.</p>
      </div>
    </div>

    <div class="profile-row">
      <span class="avatar">SK</span>
      <span><strong>SKALA 학습자</strong><small>나의 학습 공간</small></span>
      <span class="online-dot" title="온라인" />
    </div>
  </aside>
  <button v-if="open" class="sidebar-backdrop" aria-label="메뉴 닫기" @click="emit('close')" />
</template>
