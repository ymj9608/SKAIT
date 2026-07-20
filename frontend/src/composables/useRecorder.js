import { computed, onBeforeUnmount, ref } from 'vue'

// Whisper가 기본적으로 처리하는 30초 창에 맞춰 호출 오버헤드를 줄입니다.
const CHUNK_MILLISECONDS = 30_000

function supportedMimeType() {
  if (typeof MediaRecorder === 'undefined') return ''
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || ''
}

export function useRecorder(onChunk, onCaptureEnded) {
  const isRecording = ref(false)
  const isProcessing = ref(false)
  const elapsed = ref(0)
  const error = ref('')
  const source = ref('screen')

  let captureStream = null
  let audioStream = null
  let recorder = null
  let chunkTimeout = null
  let clockInterval = null
  let startedAt = 0
  let baseSeconds = 0
  let stopResolver = null
  let stopPromise = null
  let pendingUploads = 0
  let uploadQueue = Promise.resolve()
  let captureEndedHandled = false

  const elapsedLabel = computed(() => {
    const total = Math.max(0, Math.floor(elapsed.value))
    const hours = String(Math.floor(total / 3600)).padStart(2, '0')
    const minutes = String(Math.floor((total % 3600) / 60)).padStart(2, '0')
    const seconds = String(total % 60).padStart(2, '0')
    return `${hours}:${minutes}:${seconds}`
  })

  function releaseTracks() {
    captureStream?.getTracks().forEach((track) => track.stop())
    if (audioStream !== captureStream) {
      audioStream?.getTracks().forEach((track) => track.stop())
    }
    captureStream = null
    audioStream = null
  }

  function finishIfIdle() {
    if (!isRecording.value && pendingUploads === 0 && recorder?.state !== 'recording') {
      releaseTracks()
      stopResolver?.()
      stopResolver = null
      stopPromise = null
    }
  }

  function beginChunk() {
    if (!isRecording.value || !audioStream?.active) return

    const chunks = []
    const chunkStartedAt = elapsed.value
    const mimeType = supportedMimeType()
    recorder = new MediaRecorder(audioStream, mimeType ? { mimeType } : undefined)
    recorder.ondataavailable = (event) => {
      if (event.data.size) chunks.push(event.data)
    }
    recorder.onerror = (event) => {
      error.value = event.error?.message || '오디오 녹음 중 오류가 발생했습니다.'
    }
    recorder.onstop = async () => {
      clearTimeout(chunkTimeout)
      if (isRecording.value && audioStream?.active) beginChunk()
      if (chunks.length) {
        pendingUploads += 1
        isProcessing.value = true
        try {
          const upload = uploadQueue.then(() =>
            onChunk(new Blob(chunks, { type: mimeType || 'audio/webm' }), chunkStartedAt),
          )
          uploadQueue = upload.catch(() => undefined)
          await upload
        } catch (chunkError) {
          error.value = chunkError.message || '음성 구간을 전송하지 못했습니다.'
        } finally {
          pendingUploads -= 1
          isProcessing.value = pendingUploads > 0
        }
      }
      finishIfIdle()
    }
    recorder.start()
    chunkTimeout = window.setTimeout(() => {
      if (recorder?.state === 'recording') recorder.stop()
    }, CHUNK_MILLISECONDS)
  }

  async function start(selectedSource = 'screen', initialSeconds = 0) {
    if (!navigator.mediaDevices || typeof MediaRecorder === 'undefined') {
      throw new Error('이 브라우저는 오디오 녹음을 지원하지 않습니다. 최신 Chrome을 사용해 주세요.')
    }
    error.value = ''
    source.value = selectedSource
    baseSeconds = initialSeconds
    captureEndedHandled = false
    pendingUploads = 0
    uploadQueue = Promise.resolve()
    stopPromise = null
    stopResolver = null

    if (selectedSource === 'screen') {
      captureStream = await navigator.mediaDevices.getDisplayMedia({
        video: { displaySurface: 'browser' },
        audio: true,
        selfBrowserSurface: 'exclude',
        monitorTypeSurfaces: 'exclude',
        surfaceSwitching: 'include',
      })
      const audioTracks = captureStream.getAudioTracks()
      if (!audioTracks.length) {
        releaseTracks()
        throw new Error('공유한 화면에 오디오가 없습니다. 공유 창에서 “탭 오디오 공유”를 켜 주세요.')
      }
      const videoTrack = captureStream.getVideoTracks()[0]
      const displaySurface = videoTrack?.getSettings?.().displaySurface
      if (displaySurface && displaySurface !== 'browser') {
        releaseTracks()
        throw new Error('전체 화면이나 창이 아닌 강의가 재생되는 Chrome 탭을 선택해 주세요.')
      }
      audioStream = new MediaStream(audioTracks)
      videoTrack?.addEventListener('ended', () => {
        if (captureEndedHandled || !isRecording.value) return
        captureEndedHandled = true
        const endedAt = elapsed.value
        void stop()
          .then(() => onCaptureEnded?.(endedAt))
          .catch((captureError) => {
            error.value = captureError.message || '수업 종료 처리를 완료하지 못했습니다.'
          })
      })
    } else {
      captureStream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      })
      audioStream = captureStream
    }

    startedAt = Date.now()
    elapsed.value = baseSeconds
    isRecording.value = true
    clockInterval = window.setInterval(() => {
      elapsed.value = baseSeconds + (Date.now() - startedAt) / 1000
    }, 250)
    beginChunk()
  }

  function stop() {
    if (stopPromise) return stopPromise
    if (!isRecording.value && !captureStream) return Promise.resolve()
    if (isRecording.value) {
      elapsed.value = baseSeconds + (Date.now() - startedAt) / 1000
    }
    isRecording.value = false
    clearInterval(clockInterval)
    clearTimeout(chunkTimeout)
    stopPromise = new Promise((resolve) => {
      stopResolver = resolve
    })
    if (recorder?.state === 'recording') {
      recorder.stop()
    } else {
      queueMicrotask(finishIfIdle)
    }
    return stopPromise
  }

  onBeforeUnmount(stop)

  return {
    isRecording,
    isProcessing,
    elapsed,
    elapsedLabel,
    error,
    source,
    start,
    stop,
  }
}
