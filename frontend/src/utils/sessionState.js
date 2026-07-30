export function preserveNewerChatHistory(incomingSession, currentSession) {
  if (!incomingSession || incomingSession.id !== currentSession?.id) return incomingSession

  const incomingMessages = Array.isArray(incomingSession.chat_messages)
    ? incomingSession.chat_messages
    : []
  const currentMessages = Array.isArray(currentSession.chat_messages)
    ? currentSession.chat_messages
    : []

  // 대화는 삭제 없이 추가만 되므로 더 짧은 목록은 늦게 도착한 과거 응답입니다.
  if (incomingMessages.length >= currentMessages.length) return incomingSession
  return {
    ...incomingSession,
    chat_messages: currentMessages,
  }
}

export function mergeSessionResponse(incomingSession, currentSession) {
  if (!incomingSession || incomingSession.id !== currentSession?.id) return incomingSession

  const incomingRevision = Number(incomingSession.session_revision || 0)
  const currentRevision = Number(currentSession.session_revision || 0)
  if (incomingRevision < currentRevision) return currentSession

  return preserveNewerChatHistory(incomingSession, currentSession)
}
