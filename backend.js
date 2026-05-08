// Continual AI - API layer (giả lập backend, có thể thay bằng fetch thật)
window.ContinualAI = (function() {
  // Bộ nhớ học tăng cường (continual learning simulation)
  let knowledgeBase = new Map();
  
  // Khởi tạo kiến thức cơ bản
  function initKnowledge() {
    knowledgeBase.set('thời tiết', '🌤️ Hiện tại Hà Nội 26°C, không mưa. Dự báo chiều mát dịu.');
    knowledgeBase.set('cảm ơn', '🙏 Rất vui được giúp bạn! Học thêm điều mới mỗi ngày.');
    knowledgeBase.set('giới thiệu', '✨ Tôi là trợ lý Continual AI, ghi nhớ ngữ cảnh và học hỏi không ngừng.');
    knowledgeBase.set('học liên tục', '🧠 Continual Learning = EWC + Replay Buffer. Tôi cập nhật tri thức mà không quên cũ.');
    knowledgeBase.set('đặt lịch', '📆 Vâng, bạn muốn đặt lịch họp hay sự kiện? Cho tôi biết thời gian.');
    knowledgeBase.set('ai tạo ra bạn', '⚡ Continual AI được phát triển với công nghệ học tăng cường.');
    knowledgeBase.set('continual', '🧠 Học liên tục giúp tôi thích nghi với dữ liệu mới mà vẫn giữ kiến thức cũ.');
  }
  
  // Học từ hội thoại mới (lưu vào bộ nhớ)
  function learnFromConversation(userMessage, assistantReply) {
    const lowerMsg = userMessage.toLowerCase();
    // Nếu câu hỏi mới chưa có trong knowledgeBase, học thêm (mô phỏng)
    let found = false;
    for (let key of knowledgeBase.keys()) {
      if (lowerMsg.includes(key)) {
        found = true;
        break;
      }
    }
    if (!found && userMessage.trim().length > 5) {
      // Học pattern mới (lưu ý: demo chỉ lưu tạm, không ghi đè)
      const newKey = userMessage.slice(0, 20).toLowerCase();
      if (!knowledgeBase.has(newKey)) {
        knowledgeBase.set(newKey, `🤖 (Đã học) "${userMessage.substring(0,40)}..." – Cảm ơn bạn, tôi sẽ ghi nhớ chủ đề này.`);
        console.log('[Continual Learning] Đã học mẫu hội thoại mới:', newKey);
      }
    }
  }
  
  // Sinh phản hồi dựa trên tin nhắn và file đính kèm
  function getReply(userMessage, attachments = []) {
    const lower = userMessage.toLowerCase();
    let reply = '';
    
    // Tìm kiếm trong knowledgeBase
    for (let [key, value] of knowledgeBase.entries()) {
      if (lower.includes(key)) {
        reply = value;
        break;
      }
    }
    
    // Nếu không có, trả lời mặc định + gợi ý
    if (!reply) {
      reply = `🤖 Cảm ơn bạn đã chia sẻ: "${userMessage.substring(0, 60)}". Tôi đã ghi nhận và học thêm mẫu hội thoại mới. Hỏi tôi về thời tiết, lịch trình hoặc continual learning nhé!`;
    }
    
    // Nếu có file đính kèm, thông báo nhận diện
    if (attachments.length > 0) {
      const fileNames = attachments.map(f => f.name).join(', ');
      reply += `\n\n📎 Đã nhận ${attachments.length} tệp đính kèm: ${fileNames}. Tôi có thể hỗ trợ phân tích nếu cần.`;
    }
    
    // Học từ hội thoại hiện tại
    learnFromConversation(userMessage, reply);
    
    return reply;
  }
  
  // Khởi tạo
  initKnowledge();
  
  // Public API
  return {
    getAssistantReply: getReply,
    learnFromInteraction: learnFromConversation
  };
})();