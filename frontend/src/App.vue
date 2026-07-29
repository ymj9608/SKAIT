<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import {
  CalendarDays,
  CircleStop,
  Cloud,
  FileText,
  LoaderCircle,
  Menu,
  MonitorPlay,
  MonitorUp,
  Radio,
  Sparkles,
  Trash2,
  X,
} from '@lucide/vue'
import AppSidebar from './components/AppSidebar.vue'
import CoachPanel from './components/CoachPanel.vue'
import TranscriptPanel from './components/TranscriptPanel.vue'
import { useRecorder } from './composables/useRecorder'
import { api } from './services/api'
import skaitLogo from './assets/brand/skait-logo.png'

const sessions = ref([])
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
const createModalOpen = ref(false)
const newTitle = ref('새 수업')
const newSourceType = ref('zoom')
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
  if (activeSession.value?.id === session.id) activeSession.value = session
  upsertSession(session)
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
      await api.uploadAudio(recordingSessionId.value, blob, startSeconds, endSeconds),
    )
  },
  async (elapsedSeconds) => finalizeRecording(elapsedSeconds),
)

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

const recordingActionLabel = computed(() => {
  if (recorder.isRecording.value) return '학습 종료'
  return '학습 시작'
})

const activeSessionIsBeingRecorded = computed(() => (
  Boolean(recordingSessionId.value && activeSession.value?.id === recordingSessionId.value)
))

async function loadApp() {
  loading.value = true
  loadFailed.value = false
  try {
    const [healthResult, sessionResult] = await Promise.all([api.health(), api.sessions()])
    health.value = healthResult
    sessions.value = sessionResult
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
  newReferenceFiles.value = []
  createModalOpen.value = true
  sidebarOpen.value = false
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
      }),
    )
  } catch (error) {
    await recorder.stop()
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
  await loadApp()
})

</script>

<template>
  <div class="app-shell" :class="{ 'app-shell--sidebar-collapsed': sidebarCollapsed }">
    <AppSidebar
      :sessions="sessions"
      :active-id="activeSession?.id"
      :open="sidebarOpen"
      @select="selectSession"
      @new="openCreateModal"
      @rename="renameSession"
      @delete="removeSession"
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
            <h1>{{ activeSession.title }}</h1>
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
