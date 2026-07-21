<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  CalendarDays,
  CircleStop,
  Cloud,
  HardDrive,
  LoaderCircle,
  Menu,
  MonitorPlay,
  MonitorUp,
  PanelRightOpen,
  Radio,
  Sparkles,
  X,
} from '@lucide/vue'
import AppSidebar from './components/AppSidebar.vue'
import CoachPanel from './components/CoachPanel.vue'
import TranscriptPanel from './components/TranscriptPanel.vue'
import { useRecorder } from './composables/useRecorder'
import { api } from './services/api'

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
const coachOpen = ref(true)
const createModalOpen = ref(false)
const newTitle = ref('')
const newSourceType = ref('zoom')
const isFinalizing = ref(false)
const toast = ref(null)
let toastTimer = null
let healthTimer = null
let recordingSessionId = null
let finalizationPromise = null

function replaceSession(session) {
  activeSession.value = session
  const index = sessions.value.findIndex((item) => item.id === session.id)
  if (index >= 0) sessions.value.splice(index, 1, session)
  else sessions.value.unshift(session)
}

function showToast(message, type = 'error') {
  toast.value = { message, type }
  clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => (toast.value = null), 5000)
}

const recorder = useRecorder(
  async (blob, startSeconds, endSeconds) => {
    if (!recordingSessionId) return
    replaceSession(await api.uploadAudio(recordingSessionId, blob, startSeconds, endSeconds))
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

const isYoutubeSession = computed(() => activeSession.value?.source_type === 'youtube')
const recordingActionLabel = computed(() => {
  if (recorder.isRecording.value) return '변환 종료'
  return isYoutubeSession.value ? 'YouTube 듣기' : '수업 녹음'
})

const providerLabel = computed(() => {
  const names = {
    demo: 'Demo STT',
    huggingface: 'Hugging Face',
    faster_whisper: 'Local Whisper',
    mlx_whisper: 'MLX Whisper',
  }
  return names[health.value.stt_provider] || health.value.stt_provider
})

async function refreshHealth() {
  try {
    health.value = await api.health()
  } catch {
    health.value = { ...health.value, stt_ready: false, llm_ready: false }
  }
}

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
  if (recorder.isRecording.value || recorder.isProcessing.value || isFinalizing.value) {
    showToast('현재 음성 구간 저장과 요약을 마친 뒤 다른 수업으로 이동해 주세요.', 'info')
    return
  }
  const local = sessions.value.find((item) => item.id === id)
  if (local) activeSession.value = local
  sidebarOpen.value = false
  try {
    activeSession.value = await api.session(id)
  } catch (error) {
    showToast(error.message)
  }
}

async function renameSession({ id, title }) {
  if (
    activeSession.value?.id === id
    && (recorder.isRecording.value || recorder.isProcessing.value || isFinalizing.value)
  ) {
    showToast('현재 수업 처리를 마친 뒤 제목을 수정해 주세요.', 'info')
    return
  }
  try {
    replaceSession(await api.updateSession(id, { title }))
    showToast('수업 제목을 수정했습니다.', 'success')
  } catch (error) {
    showToast(error.message)
  }
}

async function removeSession(id) {
  if (
    recordingSessionId === id
    || (
      activeSession.value?.id === id
      && (recorder.isRecording.value || recorder.isProcessing.value || isFinalizing.value)
    )
  ) {
    showToast('현재 처리 중인 수업은 삭제할 수 없습니다.', 'info')
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
  if (recorder.isRecording.value || recorder.isProcessing.value || isFinalizing.value) {
    showToast('현재 음성 구간 저장과 요약을 마친 뒤 새 학습을 시작해 주세요.', 'info')
    return
  }
  newTitle.value = `새 수업 · ${new Intl.DateTimeFormat('ko-KR', { month: 'short', day: 'numeric' }).format(new Date())}`
  newSourceType.value = 'zoom'
  createModalOpen.value = true
  sidebarOpen.value = false
}

function chooseNewSource(sourceType) {
  newSourceType.value = sourceType
}

async function createSession() {
  if (!newTitle.value.trim()) return
  try {
    const session = await api.createSession({
      title: newTitle.value.trim(),
      course_name: newSourceType.value === 'youtube' ? 'YouTube' : 'Zoom',
      source_type: newSourceType.value,
    })
    replaceSession(session)
    createModalOpen.value = false
    showToast('새 학습 세션을 만들었습니다.', 'success')
  } catch (error) {
    showToast(error.message)
  }
}

async function finalizeRecording(elapsedSeconds) {
  if (finalizationPromise) return finalizationPromise
  const sessionId = recordingSessionId
  if (!sessionId) return undefined

  isFinalizing.value = true
  finalizationPromise = (async () => {
    try {
      const session = await api.updateStatus(sessionId, {
        status: 'completed',
        duration_seconds: elapsedSeconds,
      })
      replaceSession(session)
      showToast('실시간 변환과 최종 AI 노트 정리가 완료되었습니다.', 'success')
      return session
    } catch (error) {
      showToast(error.message)
      return undefined
    } finally {
      recordingSessionId = null
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
    recordingSessionId = activeSession.value.id
    await recorder.start('screen', activeSession.value.duration_seconds || 0)
    replaceSession(
      await api.updateStatus(activeSession.value.id, {
        status: 'recording',
        duration_seconds: activeSession.value.duration_seconds || 0,
      }),
    )
  } catch (error) {
    await recorder.stop()
    recordingSessionId = null
    showToast(error.message)
  }
}

async function appendSummaryNote(text) {
  if (!activeSession.value) return false
  try {
    replaceSession(await api.addSummaryNote(activeSession.value.id, text))
    showToast('필기를 저장했습니다.', 'success')
    return true
  } catch (error) {
    showToast(error.message)
    return false
  }
}

onMounted(async () => {
  await loadApp()
  healthTimer = window.setInterval(refreshHealth, 30_000)
})

onBeforeUnmount(() => {
  clearInterval(healthTimer)
})

</script>

<template>
  <div class="app-shell">
    <AppSidebar
      :sessions="sessions"
      :active-id="activeSession?.id"
      :open="sidebarOpen"
      @select="selectSession"
      @new="openCreateModal"
      @rename="renameSession"
      @delete="removeSession"
      @close="sidebarOpen = false"
    />

    <main class="workspace">
      <header class="topbar">
        <div class="topbar-left">
          <button class="mobile-menu" aria-label="수업 목록 열기" @click="sidebarOpen = true">
            <Menu :size="21" />
          </button>
        </div>

        <div class="recording-toolbar">
          <div class="model-status" :title="`STT: ${health.stt_model || providerLabel}`">
            <HardDrive :size="15" />
            <span>{{ providerLabel }}</span>
            <i :class="{ off: !health.stt_ready }" />
          </div>
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

      <div v-if="activeSession" class="content-grid" :class="{ 'content-grid--coach-closed': !coachOpen }">
        <section class="lesson-column">
          <div class="lesson-heading">
            <h1>{{ activeSession.title }}</h1>
            <p class="lesson-date"><CalendarDays :size="14" /> {{ sessionDate }}</p>
          </div>

          <TranscriptPanel
            :summary-cards="activeSession.material?.summary_cards || []"
            :summary-notes="activeSession.material?.summary_notes || []"
            :append-note="appendSummaryNote"
          />
        </section>

        <button
          v-if="!coachOpen"
          class="coach-reopen"
          aria-label="AI 도우미 펼치기"
          title="AI 도우미 펼치기"
          @click="coachOpen = true"
        >
          <PanelRightOpen :size="17" />
        </button>

        <CoachPanel
          v-show="coachOpen"
          :session="activeSession"
          :llm-ready="health.llm_ready"
          @toggle="coachOpen = false"
          @updated="replaceSession"
          @error="showToast"
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
          <p>새 학습을 시작하면 이곳에 수업 내용이 표시됩니다.</p>
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
