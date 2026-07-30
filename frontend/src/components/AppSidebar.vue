<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  BookOpen,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  EllipsisVertical,
  Folder,
  FolderOpen,
  FolderPlus,
  GripVertical,
  PanelLeft,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
  X,
} from '@lucide/vue'
import skaitLogo from '../assets/brand/skait-logo.png'
import skaitWordmark from '../assets/brand/skait-wordmark.png'
import {
  buildVisibleCategoryGroups,
  compareSessionOrder,
} from '../utils/categoryTree'

const props = defineProps({
  sessions: { type: Array, default: () => [] },
  categories: { type: Array, default: () => [] },
  activeId: { type: String, default: '' },
  open: { type: Boolean, default: false },
})

const emit = defineEmits([
  'select',
  'new',
  'close',
  'collapse',
  'rename',
  'delete',
  'move',
  'create-category',
  'rename-category',
  'delete-category',
])
const activeMenuId = ref('')
const activeCategoryMenuId = ref('')
const collapsedGroupIds = ref(new Set())
const categoryEditor = ref(null)
const draggedSessionId = ref('')
const dropTargetCategoryId = ref('')
const sessionDropTarget = ref(null)

const categoryById = computed(() => new Map(
  props.categories.map((category) => [category.id, category]),
))

const categoryOptions = computed(() => props.categories.map((category) => ({
  ...category,
  path: categoryPath(category.id),
})))

const visibleCategoryGroups = computed(() => buildVisibleCategoryGroups(
  props.categories,
  props.sessions,
  props.activeId,
  collapsedGroupIds.value,
))

const rootSessions = computed(() => {
  return props.sessions.filter((session) => (
    normalizedCategoryId(session) === null
  )).sort(compareSessionOrder)
})

function selectSession(id) {
  closeMenu()
  emit('select', id)
}

function toggleSessionMenu(id) {
  activeCategoryMenuId.value = ''
  activeMenuId.value = activeMenuId.value === id ? '' : id
}

function toggleCategoryMenu(id) {
  activeMenuId.value = ''
  activeCategoryMenuId.value = activeCategoryMenuId.value === id ? '' : id
}

function toggleGroup(id) {
  const next = new Set(collapsedGroupIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  collapsedGroupIds.value = next
}

function groupIsOpen(id) {
  return !collapsedGroupIds.value.has(id)
}

function categoryPath(categoryId) {
  const parts = []
  const visited = new Set()
  let category = categoryById.value.get(categoryId)
  while (category && !visited.has(category.id)) {
    visited.add(category.id)
    parts.unshift(category.name)
    category = category.parent_id ? categoryById.value.get(category.parent_id) : null
  }
  return parts.join(' / ')
}

function renameSession(session) {
  const title = window.prompt('수업 제목을 입력해 주세요.', session.title)?.trim()
  closeMenu()
  if (title && title !== session.title) emit('rename', { id: session.id, title })
}

function deleteSession(session) {
  closeMenu()
  if (window.confirm(`“${session.title}” 수업을 삭제할까요?`)) emit('delete', session.id)
}

function moveSession(sessionId, categoryId, sortOrder) {
  closeMenu()
  emit('move', { id: sessionId, categoryId, sortOrder })
}

function startSessionDrag(event, sessionId) {
  draggedSessionId.value = sessionId
  dropTargetCategoryId.value = ''
  sessionDropTarget.value = null
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', sessionId)
}

function dragOverCategory(categoryId) {
  if (!draggedSessionId.value) return
  dropTargetCategoryId.value = categoryId || 'root'
  sessionDropTarget.value = null
  if (categoryId && collapsedGroupIds.value.has(categoryId)) {
    const next = new Set(collapsedGroupIds.value)
    next.delete(categoryId)
    collapsedGroupIds.value = next
  }
}

function leaveCategoryDropTarget(event, categoryId) {
  const currentTarget = event.currentTarget
  if (currentTarget.contains(event.relatedTarget)) return
  const targetId = categoryId || 'root'
  if (dropTargetCategoryId.value === targetId) dropTargetCategoryId.value = ''
}

function dropSession(event, categoryId) {
  const sessionId = draggedSessionId.value || event.dataTransfer.getData('text/plain')
  const session = props.sessions.find((item) => item.id === sessionId)
  if (session) moveSession(sessionId, categoryId, nextSortOrder(categoryId))
  endSessionDrag()
}

function sessionsInCategory(categoryId) {
  return props.sessions
    .filter((session) => normalizedCategoryId(session) === categoryId)
    .sort(compareSessionOrder)
}

function normalizedCategoryId(session) {
  return session.category_id && categoryById.value.has(session.category_id)
    ? session.category_id
    : null
}

function sessionSortOrder(session) {
  const sortOrder = Number(session?.sort_order)
  return Number.isFinite(sortOrder) ? sortOrder : 0
}

function nextSortOrder(categoryId) {
  const siblings = sessionsInCategory(categoryId)
  if (!siblings.length) return 0
  return sessionSortOrder(siblings.at(-1)) + 1
}

function dragOverSession(event, session) {
  if (!draggedSessionId.value || draggedSessionId.value === session.id) return
  const bounds = event.currentTarget.getBoundingClientRect()
  const position = event.clientY < bounds.top + bounds.height / 2 ? 'before' : 'after'
  sessionDropTarget.value = { id: session.id, position }
  dropTargetCategoryId.value = ''
}

function leaveSessionDropTarget(event, sessionId) {
  if (event.currentTarget.contains(event.relatedTarget)) return
  if (sessionDropTarget.value?.id === sessionId) sessionDropTarget.value = null
}

function dropSessionBeside(event, targetSession) {
  const sessionId = draggedSessionId.value || event.dataTransfer.getData('text/plain')
  if (!sessionId || sessionId === targetSession.id) {
    endSessionDrag()
    return
  }
  const categoryId = normalizedCategoryId(targetSession)
  const siblings = sessionsInCategory(categoryId).filter((session) => session.id !== sessionId)
  let insertionIndex = siblings.findIndex((session) => session.id === targetSession.id)
  if (insertionIndex < 0) {
    endSessionDrag()
    return
  }
  if (sessionDropTarget.value?.position === 'after') insertionIndex += 1

  const previous = siblings[insertionIndex - 1]
  const next = siblings[insertionIndex]
  let sortOrder = 0
  if (previous && next) sortOrder = (sessionSortOrder(previous) + sessionSortOrder(next)) / 2
  else if (previous) sortOrder = sessionSortOrder(previous) + 1
  else if (next) sortOrder = sessionSortOrder(next) - 1

  moveSession(sessionId, categoryId, sortOrder)
  endSessionDrag()
}

function endSessionDrag() {
  draggedSessionId.value = ''
  dropTargetCategoryId.value = ''
  sessionDropTarget.value = null
}

function openCategoryEditor({ mode = 'create', category = null, parentId = '', sessionId = '' } = {}) {
  closeMenu()
  categoryEditor.value = {
    mode,
    id: category?.id || '',
    name: category?.name || '',
    parentId: parentId || category?.parent_id || '',
    sessionId,
  }
}

function renameCategory(category) {
  openCategoryEditor({ mode: 'rename', category })
}

function deleteCategory(category) {
  openCategoryEditor({ mode: 'delete', category })
}

function submitCategoryEditor() {
  const editor = categoryEditor.value
  if (!editor) return
  if (editor.mode === 'delete') {
    emit('delete-category', editor.id)
    categoryEditor.value = null
    return
  }
  const name = editor.name.trim()
  if (!name) return
  if (editor.mode === 'rename') emit('rename-category', { id: editor.id, name })
  else {
    emit('create-category', {
      name,
      parentId: editor.parentId || null,
      sessionId: editor.sessionId,
    })
  }
  categoryEditor.value = null
}

function closeMenu() {
  activeMenuId.value = ''
  activeCategoryMenuId.value = ''
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

    <div
      class="sidebar-label"
      :class="{ 'sidebar-label--drop-target': dropTargetCategoryId === 'root' }"
      @dragenter.prevent="dragOverCategory(null)"
      @dragover.prevent="dragOverCategory(null)"
      @dragleave="leaveCategoryDropTarget($event, null)"
      @drop.prevent="dropSession($event, null)"
    >
      <span>내 학습</span>
      <div class="sidebar-label-actions">
        <button aria-label="새 학습 시작" data-tooltip="새 학습 시작" @click="emit('new')">
          <span class="new-study-icon">
            <BookOpen :size="18" stroke-width="1.9" />
            <Plus class="new-study-icon-plus" :size="9" stroke-width="2.8" />
          </span>
        </button>
        <button aria-label="카테고리 만들기" data-tooltip="카테고리 만들기" @click.stop="openCategoryEditor()">
          <FolderPlus :size="17" stroke-width="1.9" />
        </button>
      </div>
    </div>

    <nav class="session-list category-tree" aria-label="카테고리별 학습 세션 목록">
      <section
        v-for="group in visibleCategoryGroups"
        :key="group.id"
        class="category-group"
        :style="{ '--category-indent': `${group.depth * 14}px` }"
      >
        <div
          class="category-row"
          :class="{
            'category-row--active': group.containsActiveSession,
            'category-row--drop-target': dropTargetCategoryId === group.id,
          }"
          @dragenter.prevent="dragOverCategory(group.id)"
          @dragover.prevent="dragOverCategory(group.id)"
          @dragleave="leaveCategoryDropTarget($event, group.id)"
          @drop.prevent="dropSession($event, group.id)"
        >
          <button class="category-toggle" :aria-expanded="groupIsOpen(group.id)" @click="toggleGroup(group.id)">
            <ChevronDown v-if="groupIsOpen(group.id)" :size="14" />
            <ChevronRight v-else :size="14" />
            <FolderOpen v-if="groupIsOpen(group.id)" :size="16" />
            <Folder v-else :size="16" />
            <strong>{{ group.name }}</strong>
          </button>
          <button
            class="category-menu-button"
            :aria-label="`${group.name} 카테고리 메뉴`"
            :aria-expanded="activeCategoryMenuId === group.id"
            @click.stop="toggleCategoryMenu(group.id)"
          >
            <EllipsisVertical :size="16" />
          </button>
          <div v-if="activeCategoryMenuId === group.id" class="session-menu category-menu" @click.stop>
            <button @click="openCategoryEditor({ parentId: group.id })"><FolderPlus :size="14" /> 하위 카테고리</button>
            <button @click="renameCategory(group)"><Pencil :size="14" /> 이름 변경</button>
            <button class="session-menu-delete" @click="deleteCategory(group)"><Trash2 :size="14" /> 카테고리 삭제</button>
          </div>
        </div>

        <div v-if="groupIsOpen(group.id)" class="category-children">
          <div
            v-for="session in group.sessions"
            :key="session.id"
            class="session-entry"
            :class="{
              'session-entry--active': session.id === activeId,
              'session-entry--dragging': session.id === draggedSessionId,
              'session-entry--drop-before': sessionDropTarget?.id === session.id && sessionDropTarget.position === 'before',
              'session-entry--drop-after': sessionDropTarget?.id === session.id && sessionDropTarget.position === 'after',
            }"
            :draggable="true"
            @dragstart="startSessionDrag($event, session.id)"
            @dragend="endSessionDrag"
            @dragenter.prevent.stop="dragOverSession($event, session)"
            @dragover.prevent.stop="dragOverSession($event, session)"
            @dragleave.stop="leaveSessionDropTarget($event, session.id)"
            @drop.prevent.stop="dropSessionBeside($event, session)"
          >
            <button class="session-item" :title="session.title" @click="selectSession(session.id)">
              <GripVertical class="session-drag-handle" :size="13" title="드래그해서 순서 또는 폴더 이동" />
              <strong>{{ session.title }}</strong>
            </button>
            <button
              class="session-menu-button"
              :aria-label="`${session.title} 메뉴`"
              :aria-expanded="activeMenuId === session.id"
              @click.stop="toggleSessionMenu(session.id)"
            >
              <EllipsisVertical :size="17" />
            </button>
            <div v-if="activeMenuId === session.id" class="session-menu" @click.stop>
              <button @click="renameSession(session)"><Pencil :size="14" /> 제목 수정</button>
              <button class="session-menu-delete" @click="deleteSession(session)"><Trash2 :size="14" /> 삭제</button>
            </div>
          </div>
          <p v-if="!group.sessions.length" class="category-empty">아직 수업이 없습니다.</p>
        </div>
      </section>

      <div
        v-for="session in rootSessions"
        :key="session.id"
        class="session-entry session-entry--root"
        :class="{
          'session-entry--active': session.id === activeId,
          'session-entry--dragging': session.id === draggedSessionId,
          'session-entry--drop-before': sessionDropTarget?.id === session.id && sessionDropTarget.position === 'before',
          'session-entry--drop-after': sessionDropTarget?.id === session.id && sessionDropTarget.position === 'after',
        }"
        :draggable="true"
        @dragstart="startSessionDrag($event, session.id)"
        @dragend="endSessionDrag"
        @dragenter.prevent.stop="dragOverSession($event, session)"
        @dragover.prevent.stop="dragOverSession($event, session)"
        @dragleave.stop="leaveSessionDropTarget($event, session.id)"
        @drop.prevent.stop="dropSessionBeside($event, session)"
      >
        <button class="session-item" :title="session.title" @click="selectSession(session.id)">
          <GripVertical class="session-drag-handle" :size="13" title="드래그해서 순서 또는 폴더 이동" />
          <strong>{{ session.title }}</strong>
        </button>
        <button
          class="session-menu-button"
          :aria-label="`${session.title} 메뉴`"
          :aria-expanded="activeMenuId === session.id"
          @click.stop="toggleSessionMenu(session.id)"
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

  <Teleport to="body">
    <div
      v-if="categoryEditor"
      class="category-editor-backdrop"
      @click.self="categoryEditor = null"
      @keydown.esc="categoryEditor = null"
    >
      <form class="category-editor-modal" @submit.prevent="submitCategoryEditor">
        <button type="button" class="category-editor-close" aria-label="닫기" @click="categoryEditor = null">
          <X :size="18" />
        </button>
        <span class="category-editor-icon">
          <Trash2 v-if="categoryEditor.mode === 'delete'" :size="21" />
          <FolderPlus v-else :size="21" />
        </span>
        <h2>
          {{ categoryEditor.mode === 'rename'
            ? '카테고리 이름 변경'
            : categoryEditor.mode === 'delete'
              ? '카테고리 삭제'
              : categoryEditor.parentId
                ? '하위 카테고리 만들기'
                : '카테고리 만들기' }}
        </h2>
        <template v-if="categoryEditor.mode === 'delete'">
          <p class="category-editor-description">
            “{{ categoryEditor.name }}” 카테고리를 삭제할까요? 이 카테고리의 수업은
            ‘{{ categoryEditor.parentId ? categoryPath(categoryEditor.parentId) : '최상위' }}’로 이동하고,
            하위 카테고리는 한 단계 위로 이동합니다.
          </p>
        </template>
        <template v-else>
          <label>
            <span>카테고리 이름</span>
            <input v-model="categoryEditor.name" maxlength="40" autofocus placeholder="예: 백엔드 개발" />
          </label>
          <label v-if="categoryEditor.mode === 'create'">
            <span>상위 카테고리</span>
            <select v-model="categoryEditor.parentId">
              <option value="">최상위</option>
              <option v-for="category in categoryOptions" :key="category.id" :value="category.id">
                {{ category.path }}
              </option>
            </select>
          </label>
        </template>
        <div class="category-editor-actions">
          <button type="button" class="category-editor-cancel" @click="categoryEditor = null">취소</button>
          <button
            type="submit"
            class="category-editor-submit"
            :class="{ 'category-editor-submit--delete': categoryEditor.mode === 'delete' }"
            :disabled="categoryEditor.mode !== 'delete' && !categoryEditor.name.trim()"
          >
            {{ categoryEditor.mode === 'delete' ? '삭제' : categoryEditor.mode === 'rename' ? '변경' : '만들기' }}
          </button>
        </div>
      </form>
    </div>
  </Teleport>
</template>
