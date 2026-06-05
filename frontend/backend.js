window.ContinualAI = (function() {
  const API_BASE_URL = 'http://localhost:8000';
  let sessionId = localStorage.getItem('continual_ai_session') || generateSessionId();

  function generateSessionId() {
    const id = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    localStorage.setItem('continual_ai_session', id);
    return id;
  }

  async function getReply(userMessage, attachments = []) {
    try {
      const response = await fetch(API_BASE_URL + '/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage, session_id: sessionId })
      });

      if (!response.ok) {
        throw new Error(`Backend error: ${response.status}`);
      }

      const data = await response.json();
      console.log('[API Response]:', data);

      return data.answer || data.text || data.message || 'Không có phản hồi từ backend';
    } catch (error) {
      console.error('[API Error]:', error.message);
      return `❌ Lỗi kết nối backend: ${error.message}`;
    }
  }

  return {
    getAssistantReply: getReply,
    learnFromInteraction: (msg, reply) => console.log('[Learning]', msg, reply)
  };
})();