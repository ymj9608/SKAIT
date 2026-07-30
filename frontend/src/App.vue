<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  CalendarDays,
  CircleStop,
  Cloud,
  FileText,
  Folder,
  LoaderCircle,
  Menu,
  MonitorPlay,
  MonitorUp,
  Plus,
  Radio,
  Sparkles,
  Trash2,
  X,
} from '@lucide/vue'
import AppSettingsModal from './components/AppSettingsModal.vue'
import AppSidebar from './components/AppSidebar.vue'
import CoachPanel from './components/CoachPanel.vue'
import TranscriptPanel from './components/TranscriptPanel.vue'
import { useRecorder } from './composables/useRecorder'
import { api } from './services/api'
import {
  loadAppSettings,
  resetAppSettings,
  saveAppSettings,
} from './utils/appSettings'
import { getRecordingActionLabel } from './utils/recordingAction'
import { mergeSessionResponse } from './utils/sessionState'
import skaitLogo from './assets/brand/skait-logo.png'

const sessions = ref([])
const categories = ref([])
const activeSession = ref(null)
const health = ref({
  stt_ready: false,
  llm_ready: false,
  stt_provider: '...',
  llm_provider: '...',
  stt_model: null,
  llm_model: null,
  summary_batch_seconds: 120,
})
const loading = ref(true)
const loadFailed = ref(false)
const sidebarOpen = ref(false)
const sidebarCollapsed = ref(false)
const settingsModalOpen = ref(false)
const appSettings = ref(loadAppSettings())
const settingsDraft = ref({ ...appSettings.value })
const createModalOpen = ref(false)
const newTitle = ref('새 수업')
const newSourceType = ref('zoom')
const newCategoryId = ref('')
const newCategoryName = ref('')
const newCategoryParentId = ref('')
const newCategoryInputOpen = ref(false)
const creatingCategory = ref(false)
const newReferenceFiles = ref([])
const referenceInput = ref(null)
const transcriptPanel = ref(null)
const uploadingReference = ref(false)
const deletingReferenceId = ref('')
const isFinalizing = ref(false)
const toast = ref(null)
let toastTimer = null
const recordingSessionId = ref(null)
let finalizationPromise = null
const RECORDING_HEALTH_INTERVAL_MILLISECONDS = 2_000
const RECORDING_HEALTH_TIMEOUT_MILLISECONDS = 1_500
const RECORDING_HEALTH_FAILURE_LIMIT = 2
const CLIENT_RECONNECT_MILLISECONDS = 2_000

function upsertSession(session) {
  const index = sessions.value.findIndex((item) => item.id === session.id)
  if (index >= 0) sessions.value.splice(index, 1, session)
  else sessions.value.unshift(session)
}

function replaceSession(session) {
  activeSession.value = session
  upsertSession(session)
}

function updateSessionInBackground(session) {
  const mergedSession = mergeSessionResponse(session, activeSession.value)
  if (activeSession.value?.id === mergedSession.id) activeSession.value = mergedSession
  upsertSession(mergedSession)
}

function showToast(message, type = 'error') {
  toast.value = { message, type }
  clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => (toast.value = null), 5000)
}

function focusSummarySource(source) {
  transcriptPanel.value?.focusSource(source)
}

const recorder = useRecorder(
  async (blob, startSeconds, endSeconds) => {
    if (!recordingSessionId.value) return
    updateSessionInBackground(
      await api.uploadAudio(
        recordingSessionId.value,
        blob,
        startSeconds,
        endSeconds,
        appSettings.value.summaryBatchSeconds,
      ),
    )
  },
  async (elapsedSeconds) => finalizeRecording(elapsedSeconds),
)

let recordingHealthTimer = null
let recordingHealthCheckRunning = false
let recordingHealthFailures = 0
let recordingHealthGeneration = 0
let recordingHealthController = null
let clientSocket = null
let clientReconnectTimer = null
let clientPageClosing = false

function stopClientConnection() {
  clientPageClosing = true
  window.clearTimeout(clientReconnectTimer)
  clientReconnectTimer = null
  const socket = clientSocket
  clientSocket = null
  if (
    socket
    && socket.readyState !== WebSocket.CLOSING
    && socket.readyState !== WebSocket.CLOSED
  ) {
    socket.close(1000, 'SKAIT page closed')
  }
}

function startClientConnection() {
  if (
    clientPageClosing
    || clientSocket?.readyState === WebSocket.OPEN
    || clientSocket?.readyState === WebSocket.CONNECTING
  ) return

  const socket = api.clientConnection()
  clientSocket = socket
  socket.addEventListener('close', () => {
    if (clientSocket === socket) clientSocket = null
    if (clientPageClosing) return
    window.clearTimeout(clientReconnectTimer)
    clientReconnectTimer = window.setTimeout(
      startClientConnection,
      CLIENT_RECONNECT_MILLISECONDS,
    )
  })
  socket.addEventListener('error', () => socket.close())
}

function handlePageHide() {
  recorder.abort()
  recordingSessionId.value = null
  stopClientConnection()
}

function handlePageShow() {
  clientPageClosing = false
  startClientConnection()
}

function stopRecordingHealthMonitor() {
  recordingHealthGeneration += 1
  recordingHealthController?.abort()
  recordingHealthController = null
  window.clearInterval(recordingHealthTimer)
  recordingHealthTimer = null
  recordingHealthCheckRunning = false
  recordingHealthFailures = 0
}

async function checkRecordingServerConnection() {
  if (!recorder.isRecording.value || recordingHealthCheckRunning) return
  const monitorGeneration = recordingHealthGeneration
  recordingHealthCheckRunning = true
  const controller = new AbortController()
  recordingHealthController = controller
  const timeout = window.setTimeout(
    () => controller.abort(),
    RECORDING_HEALTH_TIMEOUT_MILLISECONDS,
  )
  try {
    await api.health({ signal: controller.signal })
    if (monitorGeneration !== recordingHealthGeneration) return
    recordingHealthFailures = 0
  } catch {
    if (
      monitorGeneration !== recordingHealthGeneration
      || !recorder.isRecording.value
    ) return
    recordingHealthFailures += 1
    if (recordingHealthFailures < RECORDING_HEALTH_FAILURE_LIMIT) return

    const interruptedSessionId = recordingSessionId.value
    const interruptedDuration = recorder.elapsed.value
    recorder.abort()
    recordingSessionId.value = null
    if (activeSession.value?.id === interruptedSessionId) {
      const interruptedSession = {
        ...activeSession.value,
        status: 'recording',
        duration_seconds: Math.max(
          Number(activeSession.value.duration_seconds || 0),
          interruptedDuration,
        ),
      }
      activeSession.value = interruptedSession
      upsertSession(interruptedSession)
    }
    showToast('서버 연결이 종료되어 녹음과 화면 공유를 중지했습니다. 서버를 다시 실행한 뒤 학습을 재개해 주세요.')
  } finally {
    window.clearTimeout(timeout)
    if (recordingHealthController === controller) {
      recordingHealthController = null
    }
    if (monitorGeneration === recordingHealthGeneration) {
      recordingHealthCheckRunning = false
    }
  }
}

function startRecordingHealthMonitor() {
  stopRecordingHealthMonitor()
  recordingHealthTimer = window.setInterval(
    checkRecordingServerConnection,
    RECORDING_HEALTH_INTERVAL_MILLISECONDS,
  )
}

watch(recorder.isRecording, (isRecording) => {
  if (isRecording) startRecordingHealthMonitor()
  else stopRecordingHealthMonitor()
})

watch(recorder.error, (message) => {
  if (message) showToast(message)
})

const sessionDate = computed(() => {
  if (!activeSession.value) return ''
  return new Intl.DateTimeFormat('ko-KR', {
    month: 'long',
    day: 'numeric',
    weekday: 'short',
  }).format(new Date(activeSession.value.created_at))
})

const defaultCategory = computed(() => (
  categories.value.find((category) => category.is_default)
  || categories.value[0]
  || null
))

const activeCategoryName = computed(() => (
  categoryPath(activeSession.value?.category_id)
  || defaultCategory.value?.name
  || '내 수업'
))

const categoryOptions = computed(() => categories.value.map((category) => ({
  ...category,
  path: categoryPath(category.id),
})))

function categoryPath(categoryId) {
  if (!categoryId) return ''
  const byId = new Map(categories.value.map((category) => [category.id, category]))
  const parts = []
  const visited = new Set()
  let category = byId.get(categoryId)
  while (category && !visited.has(category.id)) {
    visited.add(category.id)
    parts.unshift(category.name)
    category = category.parent_id ? byId.get(category.parent_id) : null
  }
  return parts.join(' / ')
}

const recordingActionLabel = computed(() => (
  getRecordingActionLabel(activeSession.value, recorder.isRecording.value)
))

const activeSessionIsBeingRecorded = computed(() => (
  Boolean(recordingSessionId.value && activeSession.value?.id === recordingSessionId.value)
))

const previewSettings = computed(() => (
  settingsModalOpen.value ? settingsDraft.value : appSettings.value
))

const appShellStyle = computed(() => ({
  '--user-title-font-size': `${previewSettings.value.fontSize}pt`,
}))

watch(
  previewSettings,
  (value) => {
    document.documentElement.style.setProperty(
      '--user-title-font-size',
      `${value.fontSize}pt`,
    )
  },
  { deep: true, immediate: true },
)

function openSettingsModal() {
  settingsDraft.value = { ...appSettings.value }
  settingsModalOpen.value = true
  sidebarOpen.value = false
}

function updateSettingsDraft({ key, value }) {
  settingsDraft.value = {
    ...settingsDraft.value,
    [key]: value,
  }
}

function resetSettingsDraft() {
  settingsDraft.value = resetAppSettings()
}

function cancelSettings() {
  settingsDraft.value = { ...appSettings.value }
  settingsModalOpen.value = false
}

function saveSettings() {
  appSettings.value = saveAppSettings(settingsDraft.value)
  settingsDraft.value = { ...appSettings.value }
  settingsModalOpen.value = false
}

async function loadApp() {
  loading.value = true
  loadFailed.value = false
  try {
    const [healthResult, sessionResult, categoryResult] = await Promise.all([
      api.health(),
      api.sessions(),
      api.categories(),
    ])
    health.value = healthResult
    sessions.value = sessionResult
    categories.value = categoryResult
    activeSession.value = sessions.value[0] || null
  } catch (error) {
    loadFailed.value = true
    showToast(`백엔드에 연결할 수 없습니다. ${error.message}`)
  } finally {
    loading.value = false
  }
}

async function selectSession(id) {
  const local = sessions.value.find((item) => item.id === id)
  if (local) activeSession.value = local
  sidebarOpen.value = false
  try {
    updateSessionInBackground(await api.session(id))
  } catch (error) {
    showToast(error.message)
  }
}

async function renameSession({ id, title }) {
  try {
    updateSessionInBackground(await api.updateSession(id, { title }))
    showToast('수업 제목을 수정했습니다.', 'success')
  } catch (error) {
    showToast(error.message)
  }
}

async function moveSession({ id, categoryId, sortOrder }) {
  try {
    updateSessionInBackground(await api.updateSession(id, {
      category_id: categoryId,
      sort_order: sortOrder,
    }))
    const categoryName = categories.value.find((category) => category.id === categoryId)?.name
    showToast(`“${categoryName || defaultCategory.value?.name || '내 수업'}” 레포지토리로 옮겼습니다.`, 'success')
  } catch (error) {
    showToast(error.message)
  }
}

async function createCategory({ name, parentId = null, sessionId = '' }) {
  try {
    const category = await api.createCategory({ name, parent_id: parentId })
    categories.value.push(category)
    if (sessionId) {
      updateSessionInBackground(await api.updateSession(sessionId, { category_id: category.id }))
      showToast(`“${category.name}” 레포지토리를 만들고 수업을 옮겼습니다.`, 'success')
    } else {
      showToast(`“${category.name}” 레포지토리를 만들었습니다.`, 'success')
    }
    return category
  } catch (error) {
    showToast(error.message)
    return null
  }
}

async function renameCategory({ id, name }) {
  try {
    const category = await api.updateCategory(id, { name })
    const index = categories.value.findIndex((item) => item.id === id)
    if (index >= 0) categories.value.splice(index, 1, category)
    showToast('레포지토리 이름을 변경했습니다.', 'success')
  } catch (error) {
    showToast(error.message)
  }
}

async function moveCategory({ id, parentId, sortOrder }) {
  try {
    const previousCategory = categories.value.find((item) => item.id === id)
    const category = await api.updateCategory(id, {
      parent_id: parentId,
      sort_order: sortOrder,
    })
    const index = categories.value.findIndex((item) => item.id === id)
    if (index >= 0) categories.value.splice(index, 1, category)
    const destinationName = parentId ? categoryPath(parentId) : ''
    showToast(
      (previousCategory?.parent_id || null) === (parentId || null)
        ? '레포지토리 순서를 변경했습니다.'
        : destinationName
          ? `레포지토리를 “${destinationName}” 아래로 옮겼습니다.`
          : '독립 레포지토리로 옮겼습니다.',
      'success',
    )
  } catch (error) {
    showToast(error.message)
  }
}

async function removeCategory(id) {
  try {
    const removedCategory = categories.value.find((category) => category.id === id)
    await api.deleteCategory(id)
    const destinationId = (
      removedCategory?.parent_id
      || defaultCategory.value?.id
      || ''
    )
    categories.value = categories.value
      .filter((category) => category.id !== id)
      .map((category) => (
        category.parent_id === id
          ? { ...category, parent_id: removedCategory?.parent_id || null }
          : category
      ))
    sessions.value = sessions.value.map((session) => (
      session.category_id === id
        ? {
            ...session,
            category_id: destinationId,
            session_revision: (session.session_revision || 0) + 1,
          }
        : session
    ))
    if (activeSession.value?.category_id === id) {
      activeSession.value = {
        ...activeSession.value,
        category_id: destinationId,
        session_revision: (activeSession.value.session_revision || 0) + 1,
      }
    }
    const destinationName = categoryPath(destinationId) || '내 수업'
    showToast(`레포지토리를 삭제하고 수업은 “${destinationName}”으로 옮겼습니다.`, 'success')
  } catch (error) {
    showToast(error.message)
  }
}

async function removeSession(id) {
  if (recordingSessionId.value === id) {
    showToast('녹음 중인 수업은 학습을 종료한 뒤 삭제해 주세요.', 'info')
    return
  }
  try {
    await api.deleteSession(id)
    const wasActive = activeSession.value?.id === id
    sessions.value = sessions.value.filter((session) => session.id !== id)
    if (wasActive) activeSession.value = sessions.value[0] || null
    showToast('수업을 삭제했습니다.', 'success')
  } catch (error) {
    showToast(error.message)
  }
}

function openCreateModal() {
  newTitle.value = '새 수업'
  newSourceType.value = 'zoom'
  newCategoryId.value = defaultCategory.value?.id || ''
  newCategoryName.value = ''
  newCategoryParentId.value = ''
  newCategoryInputOpen.value = false
  newReferenceFiles.value = []
  createModalOpen.value = true
  sidebarOpen.value = false
}

function toggleNewCategoryInput() {
  newCategoryInputOpen.value = !newCategoryInputOpen.value
  if (newCategoryInputOpen.value) newCategoryParentId.value = newCategoryId.value
}

async function createCategoryFromModal() {
  const name = newCategoryName.value.trim()
  if (!name || creatingCategory.value) return
  creatingCategory.value = true
  const category = await createCategory({
    name,
    parentId: newCategoryParentId.value || null,
  })
  if (category) {
    newCategoryId.value = category.id
    newCategoryName.value = ''
    newCategoryInputOpen.value = false
  }
  creatingCategory.value = false
}

function chooseNewSource(sourceType) {
  newSourceType.value = sourceType
}

function referenceFilesFromEvent(event) {
  const files = [...(event.target.files || [])]
  event.target.value = ''
  if (!files.length) return []
  if (files.length > 20) {
    showToast('PDF 참고 자료는 최대 20개까지 선택할 수 있습니다.')
    return []
  }
  if (files.some((file) => !file.name.toLowerCase().endsWith('.pdf'))) {
    showToast('PDF 파일만 선택할 수 있습니다.')
    return []
  }
  return files
}

function chooseNewReference(event) {
  newReferenceFiles.value = referenceFilesFromEvent(event)
}

async function uploadActiveReference(event) {
  const files = referenceFilesFromEvent(event)
  if (!files.length || !activeSession.value || uploadingReference.value) return
  if ((activeSession.value.references?.length || 0) + files.length > 20) {
    showToast('PDF 참고 자료는 수업당 최대 20개까지 연결할 수 있습니다.')
    return
  }
  if (activeSessionIsBeingRecorded.value) {
    showToast('녹음 중인 수업의 PDF는 학습을 종료한 뒤 변경해 주세요.', 'info')
    return
  }
  const sessionId = activeSession.value.id
  uploadingReference.value = true
  try {
    updateSessionInBackground(await api.uploadReferences(sessionId, files))
    showToast(`PDF 참고 자료 ${files.length}개를 연결하고 AI 노트를 갱신했습니다.`, 'success')
  } catch (error) {
    showToast(error.message)
  } finally {
    uploadingReference.value = false
  }
}

function refreshMaterialInBackground(sessionId) {
  api.refreshSummary(sessionId).then((session) => {
    const index = sessions.value.findIndex((item) => item.id === session.id)
    if (index >= 0) sessions.value.splice(index, 1, session)
    if (activeSession.value?.id === session.id) {
      activeSession.value = session
      showToast('AI 노트까지 업데이트했습니다.', 'success')
    }
  }).catch((error) => {
    showToast(`변경 내용은 저장했지만 AI 노트를 갱신하지 못했습니다. ${error.message}`)
  })
}

async function deleteActiveReference(reference) {
  if (!activeSession.value || !reference || deletingReferenceId.value) return
  if (activeSessionIsBeingRecorded.value) {
    showToast('녹음 중인 수업의 PDF는 학습을 종료한 뒤 변경해 주세요.', 'info')
    return
  }
  if (!window.confirm(`“${reference.name}” PDF 참고 자료를 삭제할까요?`)) return
  const sessionId = activeSession.value.id
  deletingReferenceId.value = reference.id
  try {
    updateSessionInBackground(await api.deleteReferenceDocument(sessionId, reference.id))
    showToast('PDF 참고 자료를 삭제했습니다. AI 노트를 갱신하고 있습니다.', 'success')
    refreshMaterialInBackground(sessionId)
  } catch (error) {
    showToast(error.message)
  } finally {
    deletingReferenceId.value = ''
  }
}

async function createSession() {
  if (!newTitle.value.trim()) return
  try {
    let referenceUploadFailed = false
    let referenceConnected = false
    let session = await api.createSession({
      title: newTitle.value.trim(),
      category_id: newCategoryId.value || defaultCategory.value?.id,
      course_name: newSourceType.value === 'youtube' ? 'YouTube' : 'Zoom',
      source_type: newSourceType.value,
    })
    replaceSession(session)
    if (newReferenceFiles.value.length) {
      try {
        session = await api.uploadReferences(session.id, newReferenceFiles.value)
        replaceSession(session)
        referenceConnected = true
      } catch (error) {
        referenceUploadFailed = true
        showToast(`수업은 만들었지만 PDF를 연결하지 못했습니다. ${error.message}`)
      }
    }
    newReferenceFiles.value = []
    createModalOpen.value = false
    if (!referenceUploadFailed) {
      showToast(
        referenceConnected ? '새 학습 세션과 PDF 참고 자료를 연결했습니다.' : '새 학습 세션을 만들었습니다.',
        'success',
      )
    }
  } catch (error) {
    showToast(error.message)
  }
}

async function finalizeRecording(elapsedSeconds) {
  if (finalizationPromise) return finalizationPromise
  const sessionId = recordingSessionId.value
  if (!sessionId) return undefined

  isFinalizing.value = true
  finalizationPromise = (async () => {
    try {
      const session = await api.updateStatus(sessionId, {
        status: 'completed',
        duration_seconds: elapsedSeconds,
        summary_batch_seconds: appSettings.value.summaryBatchSeconds,
      })
      updateSessionInBackground(session)
      showToast('실시간 변환과 최종 AI 노트 정리가 완료되었습니다.', 'success')
      return session
    } catch (error) {
      showToast(error.message)
      return undefined
    } finally {
      recordingSessionId.value = null
      isFinalizing.value = false
    }
  })()

  try {
    return await finalizationPromise
  } finally {
    finalizationPromise = null
  }
}

async function toggleRecording() {
  if (!activeSession.value) return
  if (recorder.isRecording.value) {
    const elapsedSeconds = recorder.elapsed.value
    await recorder.stop()
    await finalizeRecording(elapsedSeconds)
    return
  }

  if (!health.value.stt_ready) {
    showToast('로컬 STT가 아직 준비되지 않았습니다. 모델 상태를 확인해 주세요.')
    return
  }

  try {
    const sessionId = activeSession.value.id
    const initialDuration = activeSession.value.duration_seconds || 0
    recordingSessionId.value = sessionId
    await recorder.start('screen', initialDuration)
    updateSessionInBackground(
      await api.updateStatus(sessionId, {
        status: 'recording',
        duration_seconds: initialDuration,
        summary_batch_seconds: appSettings.value.summaryBatchSeconds,
      }),
    )
  } catch (error) {
    recorder.abort()
    recordingSessionId.value = null
    showToast(error.message)
  }
}

async function appendSummaryNote(text) {
  if (!activeSession.value) return false
  const sessionId = activeSession.value.id
  try {
    updateSessionInBackground(await api.addSummaryNote(sessionId, text))
    showToast('요약을 추가했습니다.', 'success')
    return true
  } catch (error) {
    showToast(error.message)
    return false
  }
}

async function updateSummaries(payload) {
  if (!activeSession.value) return false
  const sessionId = activeSession.value.id
  try {
    updateSessionInBackground(await api.updateSummaries(sessionId, payload))
    showToast('수업 요약 변경 사항을 저장했습니다.', 'success')
    return true
  } catch (error) {
    showToast(error.message)
    return false
  }
}

onMounted(async () => {
  clientPageClosing = false
  window.addEventListener('pagehide', handlePageHide)
  window.addEventListener('pageshow', handlePageShow)
  startClientConnection()
  await loadApp()
})

onBeforeUnmount(() => {
  window.removeEventListener('pagehide', handlePageHide)
  window.removeEventListener('pageshow', handlePageShow)
  stopRecordingHealthMonitor()
  stopClientConnection()
})

</script>

<template>
  <div
    class="app-shell"
    :class="{ 'app-shell--sidebar-collapsed': sidebarCollapsed }"
    :style="appShellStyle"
  >
    <AppSidebar
      :sessions="sessions"
      :categories="categories"
      :active-id="activeSession?.id"
      :open="sidebarOpen"
      @select="selectSession"
      @new="openCreateModal"
      @rename="renameSession"
      @delete="removeSession"
      @move="moveSession"
      @move-category="moveCategory"
      @create-category="createCategory"
      @rename-category="renameCategory"
      @delete-category="removeCategory"
      @settings="openSettingsModal"
      @close="sidebarOpen = false"
      @collapse="sidebarCollapsed = true"
    />

    <main class="workspace">
      <header class="topbar">
        <div class="topbar-left">
          <button
            v-if="sidebarCollapsed"
            class="sidebar-reopen"
            aria-label="사이드바 열기"
            data-tooltip="사이드바 열기"
            @click="sidebarCollapsed = false"
          >
            <img class="sidebar-reopen-logo" :src="skaitLogo" alt="" />
          </button>
          <button class="mobile-menu" aria-label="수업 목록 열기" @click="sidebarOpen = true">
            <Menu :size="21" />
          </button>
        </div>

        <div class="recording-toolbar">
          <div class="record-time" :class="{ live: recorder.isRecording.value }">
            <span><i /> {{ recorder.isRecording.value ? 'REC' : 'READY' }}</span>
            <strong>{{ recorder.elapsedLabel.value }}</strong>
          </div>
          <button
            class="record-button"
            :class="{ 'record-button--stop': recorder.isRecording.value }"
            :disabled="!activeSession || isFinalizing || (!recorder.isRecording.value && (recorder.isProcessing.value || !health.stt_ready))"
            @click="toggleRecording"
          >
            <CircleStop v-if="recorder.isRecording.value" :size="18" fill="currentColor" />
            <Radio v-else :size="18" />
            <span>{{ recordingActionLabel }}</span>
          </button>
        </div>
      </header>

      <div v-if="activeSession" class="content-grid">
        <section class="lesson-column">
          <div class="lesson-heading">
            <div class="lesson-title-block">
              <p class="lesson-category"><Folder :size="13" /> {{ activeCategoryName }}</p>
              <h1>{{ activeSession.title }}</h1>
            </div>
            <div class="lesson-heading-meta">
              <p class="lesson-date"><CalendarDays :size="14" /> {{ sessionDate }}</p>
              <div class="reference-controls">
                <button
                  class="reference-button"
                  :title="activeSession.references?.length >= 20 ? 'PDF 참고 자료는 최대 20개까지 연결할 수 있습니다.' : 'PDF 참고 자료 추가'"
                  :disabled="uploadingReference || deletingReferenceId || activeSession.references?.length >= 20 || activeSessionIsBeingRecorded"
                  @click="referenceInput?.click()"
                >
                  <FileText :size="14" />
                  {{ uploadingReference ? '처리 중…' : 'PDF 추가' }}
                </button>
                <details v-if="activeSession.references?.length" class="reference-list-menu">
                  <summary>
                    <FileText :size="14" /> 자료 {{ activeSession.references.length }}개
                  </summary>
                  <div class="reference-list-popover">
                    <div v-for="reference in activeSession.references" :key="reference.id" class="reference-list-item">
                      <span :title="reference.name">{{ reference.name }}</span>
                      <button
                        type="button"
                        :title="`${reference.name} 삭제`"
                        :aria-label="`${reference.name} 삭제`"
                        :disabled="uploadingReference || deletingReferenceId || activeSessionIsBeingRecorded"
                        @click.prevent="deleteActiveReference(reference)"
                      >
                        <LoaderCircle v-if="deletingReferenceId === reference.id" class="spin" :size="13" />
                        <Trash2 v-else :size="13" />
                      </button>
                    </div>
                  </div>
                </details>
              </div>
              <input ref="referenceInput" class="reference-file-input" type="file" accept="application/pdf,.pdf" multiple @change="uploadActiveReference" />
            </div>
          </div>

          <TranscriptPanel
            ref="transcriptPanel"
            :summary-cards="activeSession.material?.summary_cards || []"
            :summary-notes="activeSession.material?.summary_notes || []"
            :append-note="appendSummaryNote"
            :update-summaries="updateSummaries"
          />
        </section>

        <CoachPanel
          :session="activeSession"
          :llm-ready="health.llm_ready"
          @updated="updateSessionInBackground"
          @error="showToast"
          @source-selected="focusSummarySource"
        />
      </div>

      <div v-else-if="!loading" class="connection-empty">
        <template v-if="loadFailed">
          <span><Cloud :size="34" /></span>
          <h1>학습 서버를 기다리고 있어요</h1>
          <p>FastAPI 서버를 실행한 뒤 다시 연결해 주세요.</p>
          <button @click="loadApp">다시 연결</button>
        </template>
        <template v-else>
          <span><Sparkles :size="34" /></span>
          <h1>아직 수업이 없어요</h1>
          <p>새 학습을 시작하면 이곳에 수업 요약이 표시됩니다.</p>
          <button @click="openCreateModal">새 학습 시작</button>
        </template>
      </div>
    </main>

    <div v-if="loading" class="loading-screen">
      <span class="loading-mark"><Sparkles :size="25" /></span>
      <strong>수업 공간을 준비하고 있어요</strong>
      <LoaderCircle class="spin" :size="20" />
    </div>

    <Teleport to="body">
      <AppSettingsModal
        v-if="settingsModalOpen"
        :settings="settingsDraft"
        @cancel="cancelSettings"
        @close="cancelSettings"
        @reset-display="resetSettingsDraft"
        @save="saveSettings"
        @update="updateSettingsDraft"
      />

      <div v-if="createModalOpen" class="modal-backdrop" @click.self="createModalOpen = false">
        <form class="create-modal" @submit.prevent="createSession">
          <button type="button" class="modal-close" aria-label="닫기" @click="createModalOpen = false"><X :size="20" /></button>
          <div class="source-choice" role="group" aria-label="수업 소스 선택">
            <button type="button" :class="{ active: newSourceType === 'zoom' }" @click="chooseNewSource('zoom')">
              <MonitorUp :size="17" /> Zoom
            </button>
            <button type="button" :class="{ active: newSourceType === 'youtube' }" @click="chooseNewSource('youtube')">
              <MonitorPlay :size="17" /> YouTube
            </button>
          </div>
          <label>
            <span>수업 제목</span>
            <input v-model="newTitle" maxlength="100" autofocus placeholder="예: Spring Security 기초" />
          </label>
          <div class="category-select-label">
            <span>레포지토리</span>
            <div class="category-picker-row">
              <select v-model="newCategoryId" aria-label="레포지토리 선택" required>
                <option v-for="category in categoryOptions" :key="category.id" :value="category.id">{{ category.path }}</option>
              </select>
              <button type="button" class="new-category-inline-toggle" @click="toggleNewCategoryInput">
                <Plus :size="15" /> 새 레포지토리
              </button>
            </div>
            <div v-if="newCategoryInputOpen" class="new-category-inline">
              <select v-model="newCategoryParentId" aria-label="새 레포지토리의 상위 레포지토리">
                <option value="">독립 레포지토리로 만들기</option>
                <option v-for="category in categoryOptions" :key="category.id" :value="category.id">
                  {{ category.path }} 아래에 만들기
                </option>
              </select>
              <input v-model="newCategoryName" maxlength="40" placeholder="예: 백엔드 개발" @keydown.enter.prevent="createCategoryFromModal" />
              <button type="button" :disabled="!newCategoryName.trim() || creatingCategory" @click="createCategoryFromModal">
                {{ creatingCategory ? '만드는 중…' : '만들기' }}
              </button>
            </div>
          </div>
          <label class="pdf-upload-label">
            <span>참고 자료 PDF <small>여러 개 선택 가능 · 선택 사항</small></span>
            <input class="pdf-file-input" type="file" accept="application/pdf,.pdf" multiple @change="chooseNewReference" />
            <span class="pdf-upload-control">
              <FileText :size="17" />
              <strong :title="newReferenceFiles.map((file) => file.name).join(', ')">
                {{ newReferenceFiles.length ? `PDF ${newReferenceFiles.length}개 선택됨` : 'PDF 파일 선택' }}
              </strong>
            </span>
            <small>PDF를 첨부하면 모든 자료의 전문 용어를 참고해 녹음된 수업 내용을 요약합니다.</small>
          </label>
          <button class="modal-submit" type="submit" :disabled="!newTitle.trim()">
            학습 공간 만들기
          </button>
        </form>
      </div>

      <Transition name="toast">
        <div v-if="toast" class="toast-message" :class="`toast-message--${toast.type}`">
          <i />
          <span>{{ toast.message }}</span>
          <button aria-label="알림 닫기" @click="toast = null"><X :size="16" /></button>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
