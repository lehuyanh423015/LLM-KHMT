window.ContinualAI = (function() {
  const API_BASE_URL = 'http://localhost:8000';
  let sessionId = localStorage.getItem('continual_ai_session') || generateSessionId();

  function generateSessionId() {
    const id = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    localStorage.setItem('continual_ai_session', id);
    return id;
  }

  async function getAssistantReply(userMessage) {
    try {
      const response = await fetch(API_BASE_URL + '/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage, session_id: sessionId })
      });
      if (!response.ok) throw new Error(`Backend error: ${response.status}`);
      const data = await response.json();
      let answer = data.answer || data.text || data.message || 'Không có phản hồi từ backend';
      answer = viConvert(answer);
      return answer;
    } catch (error) {
      console.error('[API Error]:', error.message);
      return `❌ Lỗi kết nối backend: ${error.message}`;
    }
  }

  async function getCustomerProfile() {
    try {
      const response = await fetch(`${API_BASE_URL}/customer-profile/${sessionId}`);
      if (!response.ok) return null;
      const data = await response.json();
      if (data.budget) data.budget = viConvert(data.budget);
      if (data.preferred_category) data.preferred_category = viConvert(data.preferred_category);
      if (data.priorities) data.priorities = viConvert(data.priorities);
      if (data.dislikes) data.dislikes = viConvert(data.dislikes);
      return data;
    } catch (error) {
      console.error('[Get Profile Error]', error);
      return null;
    }
  }

  async function updateExperimentFlags(flags) {
    try {
      const response = await fetch(`${API_BASE_URL}/config/experiment`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(flags)
      });
      if (!response.ok) throw new Error('Failed to update experiment');
      return await response.json();
    } catch (error) {
      console.error('[Experiment Error]', error);
      return null;
    }
  }

  // Hàm chuyển đổi văn bản không dấu -> có dấu (đã xóa màu sắc, thêm pin yếu, sạc chậm...)
  function viConvert(str) {
    if (!str) return str;
    let s = str;
    const map = {
      // Giá cả, ngân sách
      'trieu': 'triệu', 'tr': 'triệu', 'duoi': 'dưới', 'tren': 'trên',
      'khoang': 'khoảng', 'tam': 'tầm', 'toi da': 'tối đa', 'toi thieu': 'tối thiểu',
      'tu': 'từ', 'den': 'đến', 'ngan sach': 'ngân sách', 'muc dich': 'mục đích',
      // Ưu tiên, sở thích
      'uu tien': 'ưu tiên', 'khong thich': 'không thích', 'choi game': 'chơi game',
      'pin trau': 'pin trâu', 'man hinh dep': 'màn hình đẹp', 'hieu nang': 'hiệu năng',
      'camera': 'camera', 'laptop': 'laptop', 'dien thoai': 'điện thoại',
      'may tinh': 'máy tính', 'san pham': 'sản phẩm', 'gia re': 'giá rẻ',
      'gia tot': 'giá tốt', 'phu hop': 'phù hợp', 'nhe': 'nhẹ', 'mong': 'mỏng',
      'manh': 'mạnh', 'ben': 'bền', 'de dung': 'dễ dùng',
      // Pin, sạc, nhiệt độ, cấu hình
      'pin yeu': 'pin yếu', 'pin yếu': 'pin yếu',
      'sac cham': 'sạc chậm', 'sạc chậm': 'sạc chậm',
      'man hinh kem': 'màn hình kém', 'cpu cham': 'CPU chậm',
      'gpu yeu': 'GPU yếu', 'nhiet do cao': 'nhiệt độ cao',
      'tan nhiet kem': 'tản nhiệt kém', 'man hinh nho': 'màn hình nhỏ',
      'pin nhanh het': 'pin nhanh hết', 'sac lau': 'sạc lâu',
      'ram it': 'RAM ít', 'bo nho it': 'bộ nhớ ít'
    };
    for (let [key, val] of Object.entries(map)) {
      s = s.replace(new RegExp('\\b' + key + '\\b', 'gi'), val);
    }
    // Xử lý khoảng giá
    s = s.replace(/tu\s+(\d+)\s+den\s+(\d+)\s+triệu/gi, 'từ $1 đến $2 triệu');
    return s;
  }

  return {
    getAssistantReply,
    getCustomerProfile,
    updateExperimentFlags,
    getSessionId: () => sessionId
  };
})();