<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import {
  ChevronLeft,
  EllipsisVertical,
  PanelLeft,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
} from '@lucide/vue'
import skaitLogo from '../assets/brand/skait-logo.png'
import skaitWordmark from '../assets/brand/skait-wordmark.png'

defineProps({
  sessions: { type: Array, default: () => [] },
  activeId: { type: String, default: '' },
  open: { type: Boolean, default: false },
})

const emit = defineEmits(['select', 'new', 'close', 'collapse', 'rename', 'delete'])
const activeMenuId = ref('')

function formatDate(value) {
  const date = new Date(value)
  return new Intl.DateTimeFormat('ko-KR', { month: 'short', day: 'numeric' }).format(date)
}

function selectSession(id) {
  activeMenuId.value = ''
  emit('select', id)
}

function toggleMenu(id) {
  activeMenuId.value = activeMenuId.value === id ? '' : id
}

function renameSession(session) {
  const title = window.prompt('수업 제목을 입력해 주세요.', session.title)?.trim()
  activeMenuId.value = ''
  if (title && title !== session.title) emit('rename', { id: session.id, title })
}

function deleteSession(session) {
  activeMenuId.value = ''
  if (window.confirm(`“${session.title}” 수업을 삭제할까요?`)) emit('delete', session.id)
}

function closeMenu() {
  activeMenuId.value = ''
}

onMounted(() => document.addEventListener('click', closeMenu))
onBeforeUnmount(() => document.removeEventListener('click', closeMenu))
</script>

<template>
  <aside class="sidebar" :class="{ 'sidebar--open': open }">
    <div class="brand-row">
      <button class="brand" aria-label="SKAIT 홈">
        <img class="brand-logo" :src="skaitLogo" alt="" />
        <img class="brand-wordmark" :src="skaitWordmark" alt="SKAIT" />
      </button>
      <div class="sidebar-header-actions">
        <button class="icon-button sidebar-collapse" aria-label="사이드바 닫기" data-tooltip="사이드바 닫기" @click="emit('collapse')">
          <PanelLeft :size="20" stroke-width="1.8" />
        </button>
        <button class="icon-button sidebar-close" aria-label="메뉴 닫기" @click="emit('close')">
          <ChevronLeft :size="20" />
        </button>
      </div>
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
      <div
        v-for="session in sessions"
        :key="session.id"
        class="session-entry"
        :class="{ 'session-entry--active': session.id === activeId }"
      >
        <button class="session-item" @click="selectSession(session.id)">
          <strong>{{ session.title }}</strong>
          <time :datetime="session.created_at">{{ formatDate(session.created_at) }}</time>
        </button>
        <button
          class="session-menu-button"
          :aria-label="`${session.title} 메뉴`"
          :aria-expanded="activeMenuId === session.id"
          @click.stop="toggleMenu(session.id)"
        >
          <EllipsisVertical :size="17" />
        </button>
        <div v-if="activeMenuId === session.id" class="session-menu" @click.stop>
          <button @click="renameSession(session)"><Pencil :size="14" /> 제목 수정</button>
          <button class="session-menu-delete" @click="deleteSession(session)"><Trash2 :size="14" /> 삭제</button>
        </div>
      </div>
      <div v-if="!sessions.length" class="sidebar-empty">
        <Sparkles :size="20" />
        첫 학습을 시작해 보세요.
      </div>
    </nav>
  </aside>
  <button v-if="open" class="sidebar-backdrop" aria-label="메뉴 닫기" @click="emit('close')" />
</template>
