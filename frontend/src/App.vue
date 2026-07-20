<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  AudioLines,
  CalendarDays,
  ChevronDown,
  CircleStop,
  Cloud,
  ExternalLink,
  HardDrive,
  LoaderCircle,
  Menu,
  Mic,
  MonitorPlay,
  MonitorUp,
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
})
const loading = ref(true)
const sidebarOpen = ref(false)
const createModalOpen = ref(false)
const newTitle = ref('')
const newCourse = ref('SKALA Zoom 수업')
const newSourceType = ref('zoom')
const newSourceUrl = ref('')
const captureSource = ref('screen')
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
  async (blob, startSeconds) => {
    if (!recordingSessionId) return
    replaceSession(await api.uploadAudio(recordingSessionId, blob, startSeconds))
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

const llmProviderLabel = computed(() => {
  const names = { local: '로컬 추출식', huggingface: 'Hugging Face', ollama: 'Ollama' }
  return names[health.value.llm_provider] || health.value.llm_provider
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
  try {
    const [healthResult, sessionResult] = await Promise.all([api.health(), api.sessions()])
    health.value = healthResult
    sessions.value = sessionResult
    if (sessions.value.length) {
      activeSession.value = sessions.value[0]
    } else {
      const demo = await api.createDemo()
      sessions.value = [demo]
      activeSession.value = demo
    }
  } catch (error) {
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

function openCreateModal() {
  if (recorder.isRecording.value || recorder.isProcessing.value || isFinalizing.value) {
    showToast('현재 음성 구간 저장과 요약을 마친 뒤 새 학습을 시작해 주세요.', 'info')
    return
  }
  newTitle.value = `새 수업 · ${new Intl.DateTimeFormat('ko-KR', { month: 'short', day: 'numeric' }).format(new Date())}`
  newCourse.value = 'SKALA Zoom 수업'
  newSourceType.value = 'zoom'
  newSourceUrl.value = ''
  createModalOpen.value = true
  sidebarOpen.value = false
}

function chooseNewSource(sourceType) {
  newSourceType.value = sourceType
  const dateLabel = new Intl.DateTimeFormat('ko-KR', { month: 'short', day: 'numeric' }).format(new Date())
  if (sourceType === 'youtube') {
    newTitle.value = `YouTube 강의 · ${dateLabel}`
    newCourse.value = 'YouTube 강의 테스트'
  } else {
    newTitle.value = `새 수업 · ${dateLabel}`
    newCourse.value = 'SKALA Zoom 수업'
  }
}

function normalizeYoutubeUrl(value) {
  try {
    const url = new URL(value.trim())
    const allowedHosts = new Set([
      'youtube.com',
      'www.youtube.com',
      'm.youtube.com',
      'music.youtube.com',
      'youtu.be',
    ])
    if (url.protocol !== 'https:' || !allowedHosts.has(url.hostname.toLowerCase())) return null
    return url.href
  } catch {
    return null
  }
}

async function createSession() {
  if (!newTitle.value.trim()) return
  const youtubeUrl = newSourceType.value === 'youtube' ? normalizeYoutubeUrl(newSourceUrl.value) : null
  if (newSourceType.value === 'youtube' && !youtubeUrl) {
    showToast('https://youtube.com 또는 https://youtu.be 형식의 영상 주소를 입력해 주세요.')
    return
  }
  try {
    const session = await api.createSession({
      title: newTitle.value.trim(),
      course_name: newCourse.value.trim() || 'SKALA Zoom 수업',
      source_type: newSourceType.value,
      source_url: youtubeUrl,
    })
    replaceSession(session)
    captureSource.value = 'screen'
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
    await recorder.start(captureSource.value, activeSession.value.duration_seconds || 0)
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

async function appendText(text) {
  if (!activeSession.value) return false
  try {
    replaceSession(
      await api.appendTranscript(activeSession.value.id, {
        text,
        speaker: '교수님',
        start_seconds: recorder.isRecording.value
          ? recorder.elapsed.value
          : activeSession.value.duration_seconds,
      }),
    )
    showToast('전사 내용과 AI 노트를 업데이트했습니다.', 'success')
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

watch(
  () => activeSession.value?.source_type,
  (sourceType) => {
    if (sourceType === 'youtube') captureSource.value = 'screen'
  },
)
</script>

<template>
  <div class="app-shell">
    <AppSidebar
      :sessions="sessions"
      :active-id="activeSession?.id"
      :open="sidebarOpen"
      @select="selectSession"
      @new="openCreateModal"
      @close="sidebarOpen = false"
    />

    <main class="workspace">
      <header class="topbar">
        <div class="topbar-left">
          <button class="mobile-menu" aria-label="수업 목록 열기" @click="sidebarOpen = true">
            <Menu :size="21" />
          </button>
          <div class="course-path">
            <span>MY CLASS</span>
            <strong>{{ activeSession?.course_name || '학습 공간' }}</strong>
          </div>
        </div>

        <div class="recording-toolbar">
          <div class="model-status" :title="`STT: ${health.stt_model || providerLabel}`">
            <HardDrive :size="15" />
            <span>{{ providerLabel }}</span>
            <i :class="{ off: !health.stt_ready }" />
          </div>
          <label class="source-select" :class="{ disabled: recorder.isRecording.value || isYoutubeSession }">
            <MonitorPlay v-if="isYoutubeSession" :size="16" />
            <MonitorUp v-else-if="captureSource === 'screen'" :size="16" />
            <Mic v-else :size="16" />
            <select v-model="captureSource" :disabled="recorder.isRecording.value || isYoutubeSession">
              <option value="screen">{{ isYoutubeSession ? 'YouTube 탭 오디오' : 'Zoom 탭 오디오' }}</option>
              <option v-if="!isYoutubeSession" value="microphone">마이크</option>
            </select>
            <ChevronDown :size="14" />
          </label>
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
            <div>
              <div class="lesson-meta">
                <span class="class-badge" :class="{ 'class-badge--youtube': isYoutubeSession }">
                  {{ isYoutubeSession ? 'YOUTUBE LIVE' : 'LIVE CLASS' }}
                </span>
                <span><CalendarDays :size="14" /> {{ sessionDate }}</span>
                <span><AudioLines :size="14" /> {{ activeSession.segments.length }}개 음성 구간</span>
              </div>
              <h1>{{ activeSession.title }}</h1>
              <p>{{ isYoutubeSession ? '영상은 내려받지 않고, 재생되는 탭 음성만 실시간으로 정리합니다.' : '듣는 동안 핵심은 AI가 정리할게요. 지금은 교수님의 설명에 집중하세요.' }}</p>
            </div>
            <div class="focus-mark" aria-hidden="true">
              <span><Sparkles :size="21" /></span>
              <small>FOCUS<br />MODE</small>
            </div>
          </div>

          <div v-if="captureSource === 'screen' && !recorder.isRecording.value" class="audio-guide" :class="{ 'audio-guide--youtube': isYoutubeSession }">
            <MonitorPlay v-if="isYoutubeSession" :size="18" />
            <MonitorUp v-else :size="17" />
            <span v-if="isYoutubeSession">
              <strong>① 강의 열기·광고 넘기기 → ② YouTube 듣기 → ③ 해당 Chrome 탭 선택 → ④ 탭 오디오 공유 켜기 → ⑤ 영상 재생</strong>
              <small>최대 30초 음성 조각은 5초 무음 또는 길이 제한에 도달하면 STT 후 폐기되고, 텍스트·요약만 로컬 DB에 저장됩니다.</small>
            </span>
            <span v-else>녹음 버튼을 누른 뒤 Zoom이 열린 <strong>브라우저 탭</strong>을 선택하고, “탭 오디오 공유”를 켜 주세요.</span>
            <a v-if="isYoutubeSession && activeSession.source_url" :href="activeSession.source_url" target="_blank" rel="noopener noreferrer">
              강의 열기 <ExternalLink :size="13" />
            </a>
            <button v-else @click="captureSource = 'microphone'">마이크로 듣기</button>
          </div>

          <TranscriptPanel
            :segments="activeSession.segments"
            :recording="recorder.isRecording.value"
            :processing="recorder.isProcessing.value"
            :append-text="appendText"
          />
        </section>

        <CoachPanel
          :session="activeSession"
          :llm-ready="health.llm_ready"
          :llm-provider="llmProviderLabel"
          :llm-model="health.llm_model"
          @updated="replaceSession"
          @error="showToast"
        />
      </div>

      <div v-else-if="!loading" class="connection-empty">
        <span><Cloud :size="34" /></span>
        <h1>학습 서버를 기다리고 있어요</h1>
        <p>FastAPI 서버를 실행한 뒤 다시 연결해 주세요.</p>
        <button @click="loadApp">다시 연결</button>
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
          <span class="modal-icon"><MonitorPlay v-if="newSourceType === 'youtube'" :size="22" /><Sparkles v-else :size="22" /></span>
          <p class="modal-kicker">NEW STUDY SESSION</p>
          <h2>어떤 수업을 들을까요?</h2>
          <p class="modal-description">Zoom 수업 또는 YouTube 실시간 테스트 중 학습 방식을 선택하세요.</p>
          <div class="source-choice" role="group" aria-label="수업 소스 선택">
            <button type="button" :class="{ active: newSourceType === 'zoom' }" @click="chooseNewSource('zoom')">
              <MonitorUp :size="17" /><span><strong>Zoom / 마이크</strong><small>실시간 수업 듣기</small></span>
            </button>
            <button type="button" :class="{ active: newSourceType === 'youtube' }" @click="chooseNewSource('youtube')">
              <MonitorPlay :size="17" /><span><strong>YouTube</strong><small>탭 오디오 테스트</small></span>
            </button>
          </div>
          <label>
            <span>수업 제목</span>
            <input v-model="newTitle" maxlength="100" autofocus placeholder="예: Spring Security 기초" />
          </label>
          <label>
            <span>과정명</span>
            <input v-model="newCourse" maxlength="100" placeholder="예: SKALA 백엔드" />
          </label>
          <label v-if="newSourceType === 'youtube'">
            <span>YouTube 영상 주소</span>
            <input v-model="newSourceUrl" type="url" maxlength="2048" required placeholder="https://youtu.be/..." />
          </label>
          <p v-if="newSourceType === 'youtube'" class="youtube-privacy-note">서버가 영상을 다운로드하거나 URL에 접속하지 않습니다. Chrome에서 사용자가 공유한 탭의 재생 음성만 처리합니다.</p>
          <button class="modal-submit" type="submit" :disabled="!newTitle.trim() || (newSourceType === 'youtube' && !newSourceUrl.trim())">
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
