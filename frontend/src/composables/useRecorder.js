import { computed, onBeforeUnmount, ref } from 'vue'

// Whisper가 기본적으로 처리하는 30초 창은 계속 말할 때의 최대 길이로 유지합니다.
// 그 전에 5초 동안 소리가 없으면 현재 구간을 먼저 전송하고 다음 발화를 기다립니다.
const MAX_CHUNK_MILLISECONDS = 30_000
const SILENCE_MILLISECONDS = 5_000
const VAD_POLL_MILLISECONDS = 50
const SPEECH_START_RMS = 0.015
const SPEECH_CONTINUE_RMS = 0.008

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
  let vadInterval = null
  let audioContext = null
  let analyser = null
  let analyserSource = null
  let analyserSamples = null
  let voiceActivityDetectionEnabled = false
  let lastSoundAt = null
  let stopCurrentChunk = null
  let markCurrentChunkSound = null
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

  function stopVoiceActivityDetection() {
    clearInterval(vadInterval)
    vadInterval = null
    analyserSource?.disconnect()
    analyser?.disconnect()
    analyserSource = null
    analyser = null
    analyserSamples = null
    voiceActivityDetectionEnabled = false
    lastSoundAt = null
    if (audioContext && audioContext.state !== 'closed') {
      void audioContext.close()
    }
    audioContext = null
  }

  function releaseTracks() {
    stopVoiceActivityDetection()
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

  function currentRms() {
    if (!analyser || !analyserSamples) return 0
    analyser.getFloatTimeDomainData(analyserSamples)
    let sumOfSquares = 0
    for (const sample of analyserSamples) {
      sumOfSquares += sample * sample
    }
    return Math.sqrt(sumOfSquares / analyserSamples.length)
  }

  function beginChunk() {
    if (!isRecording.value || !audioStream?.active || recorder) return

    const chunks = []
    const chunkStartedAt = elapsed.value
    const mimeType = supportedMimeType()
    const currentRecorder = new MediaRecorder(
      audioStream,
      mimeType ? { mimeType } : undefined,
    )
    // AudioContext를 지원하지 않는 브라우저의 30초 고정 폴백에서는
    // 분석 결과가 없으므로 기존처럼 모든 조각을 전송합니다.
    let chunkHasSound = !voiceActivityDetectionEnabled
    let stopReason = 'manual'
    let currentChunkTimeout = null

    recorder = currentRecorder
    const markChunkSound = () => {
      chunkHasSound = true
    }
    const requestChunkStop = (reason) => {
      if (currentRecorder.state !== 'recording') return
      stopReason = reason
      currentRecorder.stop()
    }
    markCurrentChunkSound = markChunkSound
    stopCurrentChunk = requestChunkStop

    currentRecorder.ondataavailable = (event) => {
      if (event.data.size) chunks.push(event.data)
    }
    currentRecorder.onerror = (event) => {
      error.value = event.error?.message || '오디오 녹음 중 오류가 발생했습니다.'
    }
    currentRecorder.onstop = async () => {
      const chunkEndedAt = elapsed.value
      clearTimeout(currentChunkTimeout)
      if (chunkTimeout === currentChunkTimeout) chunkTimeout = null
      if (recorder === currentRecorder) recorder = null
      if (stopCurrentChunk === requestChunkStop) stopCurrentChunk = null
      if (markCurrentChunkSound === markChunkSound) markCurrentChunkSound = null

      // 최대 길이로 자른 경우에는 짧은 침묵 중일 수도 있으므로 바로 다음
      // 조각을 열어 둡니다. 5초 무음으로 끝난 경우에는 새 소리를 기다립니다.
      if (
        stopReason === 'max-duration' &&
        isRecording.value &&
        audioStream?.active
      ) {
        beginChunk()
      }

      // 무음만 들어 있던 조각은 Whisper로 보내지 않습니다.
      if (chunks.length && chunkHasSound) {
        pendingUploads += 1
        isProcessing.value = true
        try {
          const upload = uploadQueue.then(() =>
            onChunk(
              new Blob(chunks, { type: mimeType || 'audio/webm' }),
              chunkStartedAt,
              Math.max(chunkStartedAt, chunkEndedAt),
            ),
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
    currentRecorder.start()
    currentChunkTimeout = window.setTimeout(() => {
      requestChunkStop('max-duration')
    }, MAX_CHUNK_MILLISECONDS)
    chunkTimeout = currentChunkTimeout
  }

  async function startVoiceActivityDetection() {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext
    if (!AudioContextClass) return false

    audioContext = new AudioContextClass()
    analyser = audioContext.createAnalyser()
    analyser.fftSize = 2048
    analyser.smoothingTimeConstant = 0.2
    analyserSamples = new Float32Array(analyser.fftSize)
    analyserSource = audioContext.createMediaStreamSource(audioStream)
    analyserSource.connect(analyser)
    await audioContext.resume()
    voiceActivityDetectionEnabled = true

    vadInterval = window.setInterval(() => {
      if (!isRecording.value || !audioStream?.active) return

      const now = performance.now()
      const rms = currentRms()
      const chunkIsRecording = recorder?.state === 'recording'
      const threshold = chunkIsRecording ? SPEECH_CONTINUE_RMS : SPEECH_START_RMS

      if (rms >= threshold) {
        lastSoundAt = now
        if (!chunkIsRecording) beginChunk()
        markCurrentChunkSound?.()
        return
      }

      if (
        chunkIsRecording &&
        lastSoundAt !== null &&
        now - lastSoundAt >= SILENCE_MILLISECONDS
      ) {
        stopCurrentChunk?.('silence')
      }
    }, VAD_POLL_MILLISECONDS)

    return true
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
    lastSoundAt = null

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

    // 분석 API가 없는 오래된 브라우저에서는 기존 30초 고정 녹음으로
    // 안전하게 폴백합니다.
    const vadReady = await startVoiceActivityDetection()
    if (!vadReady) beginChunk()
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
    stopVoiceActivityDetection()
    stopPromise = new Promise((resolve) => {
      stopResolver = resolve
    })
    if (recorder?.state === 'recording') {
      stopCurrentChunk?.('manual')
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
