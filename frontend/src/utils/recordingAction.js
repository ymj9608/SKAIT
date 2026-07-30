export function getRecordingActionLabel(session, isRecording) {
  if (isRecording) return '학습 중지'

  const hasStartedBefore = (
    session?.status === 'recording'
    || session?.status === 'completed'
    || Number(session?.duration_seconds || 0) > 0
  )
  return hasStartedBefore ? '학습 재개' : '학습 시작'
}
