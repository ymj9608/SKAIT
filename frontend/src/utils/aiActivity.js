export function isLlmModelLocked({
  recordingSessionId = '',
  recorderProcessing = false,
  appAiRequestCount = 0,
  coachAiBusy = false,
} = {}) {
  return Boolean(
    recordingSessionId
    || recorderProcessing
    || appAiRequestCount > 0
    || coachAiBusy,
  )
}
