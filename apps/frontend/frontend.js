// frontend.js - quản lý hội thoại, memory profile (đã xóa Color)
(function () {
  let conversations = [];
  let activeConversationId = null;
  let isSending = false;

  // DOM elements
  const historyContainer = document.getElementById('historyList');
  const messageThread = document.getElementById('messageThread');
  const chatInput = document.getElementById('chatInput');
  const sendBtn = document.getElementById('sendMessageBtn');
  const newChatBtn = document.getElementById('newChatBtn');
  const menuToggle = document.getElementById('menuToggle');
  const sidebar = document.getElementById('historySidebar');
  const themeToggle = document.getElementById('themeToggle');
  const themeIcon = themeToggle ? themeToggle.querySelector('i') : null;
  const startBtn = document.getElementById('startChatBtn');
  const welcomeScreen = document.getElementById('welcomeScreen');
  const memoryProfileBtn = document.getElementById('memoryProfileBtn');
  const memoryModal = document.getElementById('memoryModal');
  const closeMemoryModal = document.getElementById('closeMemoryModal');

  // Memory modal fields (không có màu)
  const memBudgetSpan = document.getElementById('memBudget');
  const memCategorySpan = document.getElementById('memCategory');
  const memPrioritiesSpan = document.getElementById('memPriorities');
  const memDislikesSpan = document.getElementById('memDislikes');
  const enableMemoryExtractionChk = document.getElementById('enableMemoryExtraction');
  const enableConversationalContextChk = document.getElementById('enableConversationalContext');
  const enableProductContextChk = document.getElementById('enableProductContext');

  async function updateMemoryModalFromBackend() {
    try {
      const profile = await window.ContinualAI.getCustomerProfile();
      if (profile) {
        if (memBudgetSpan) memBudgetSpan.innerText = profile.budget || '—';
        if (memCategorySpan) memCategorySpan.innerText = profile.preferred_category || '—';
        if (memPrioritiesSpan) memPrioritiesSpan.innerText = profile.priorities || '—';
        if (memDislikesSpan) memDislikesSpan.innerText = profile.dislikes || '—';
      } else {
        if (memBudgetSpan) memBudgetSpan.innerText = '—';
        if (memCategorySpan) memCategorySpan.innerText = '—';
        if (memPrioritiesSpan) memPrioritiesSpan.innerText = '—';
        if (memDislikesSpan) memDislikesSpan.innerText = '—';
      }
    } catch (e) {
      console.warn('Failed to load customer profile', e);
    }
  }

  async function syncExperimentFlags() {
    const flags = {
      enable_memory: enableMemoryExtractionChk ? enableMemoryExtractionChk.checked : true,
      enable_recent_context: enableConversationalContextChk ? enableConversationalContextChk.checked : true,
      enable_product_context: enableProductContextChk ? enableProductContextChk.checked : true
    };
    await window.ContinualAI.updateExperimentFlags(flags);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/[&<>]/g, function(m) {
      if (m === '&') return '&amp;';
      if (m === '<') return '&lt;';
      if (m === '>') return '&gt;';
      return m;
    });
  }

  function markdownToHtml(text) {
    if (!text) return '';
    let html = escapeHtml(text);
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
    html = html.replace(/\n/g, '<br>');
    return html;
  }

  function scrollToBottom() {
    if (!messageThread) return;
    setTimeout(() => { messageThread.scrollTop = messageThread.scrollHeight; }, 50);
  }

  function setLoading(isLoading) {
    if (!sendBtn) return;
    sendBtn.disabled = isLoading;
    sendBtn.innerHTML = isLoading ? '<i class="fas fa-spinner fa-spin"></i>' : '<i class="fas fa-arrow-up"></i>';
    if (!isLoading && chatInput) chatInput.focus();
  }

  function normalizeReply(rawReply) {
    if (typeof rawReply === 'string') return rawReply;
    if (rawReply && typeof rawReply === 'object') {
      return rawReply.answer || rawReply.text || rawReply.message || JSON.stringify(rawReply);
    }
    return String(rawReply || '');
  }

  function renderMessage(msg) {
    const wrapper = document.createElement('div');
    wrapper.className = `message-wrapper ${msg.sender}`;
    const avatar = document.createElement('div');
    avatar.className = 'avatar-mini';
    avatar.innerHTML = msg.sender === 'user' ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';
    const bubble = document.createElement('div');
    bubble.className = 'bubble-minimal';
    
    if (msg.text && msg.text.trim()) {
      const textDiv = document.createElement('div');
      textDiv.className = 'message-text';
      if (msg.sender === 'assistant') {
        textDiv.innerHTML = markdownToHtml(msg.text);
        const links = textDiv.querySelectorAll('a');
        links.forEach(link => link.style.color = 'var(--accent)');
      } else {
        textDiv.textContent = msg.text;
      }
      bubble.appendChild(textDiv);
    }
    
    const footer = document.createElement('div');
    footer.className = 'bubble-footer';
    const timeSpan = document.createElement('span');
    timeSpan.textContent = msg.timestamp || new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
    footer.appendChild(timeSpan);
    bubble.appendChild(footer);
    wrapper.appendChild(avatar);
    wrapper.appendChild(bubble);
    return wrapper;
  }

  function renderMessages(conversation) {
    if (!conversation || !messageThread) return;
    messageThread.innerHTML = '';
    conversation.messages.forEach(msg => { messageThread.appendChild(renderMessage(msg)); });
    scrollToBottom();
    updateMemoryModalFromBackend();
  }

  function renderHistoryList() {
    if (!historyContainer) return;
    historyContainer.innerHTML = '';
    conversations.forEach(conv => {
      const div = document.createElement('div');
      div.className = `history-item ${activeConversationId === conv.id ? 'active' : ''}`;
      div.innerHTML = `
        <div class="history-icon"><i class="fas fa-comment-dots"></i></div>
        <div class="history-info">
          <div class="history-title">${escapeHtml(conv.title)}</div>
          <div class="history-meta">
            <span>${new Date(conv.updatedAt).toLocaleTimeString('vi-VN', { hour:'2-digit', minute:'2-digit' })}</span>
            <span class="learning-tag-small"><i class="fas fa-database"></i> ${conv.messages.length} tin</span>
          </div>
        </div>
        <button class="delete-conv-btn"><i class="fas fa-trash-alt"></i></button>
      `;
      const deleteBtn = div.querySelector('.delete-conv-btn');
      if (deleteBtn) deleteBtn.addEventListener('click', (e) => { e.stopPropagation(); deleteConversation(conv.id); });
      div.addEventListener('click', () => { if (activeConversationId === conv.id) return; activeConversationId = conv.id; renderHistoryList(); renderMessages(conv); });
      historyContainer.appendChild(div);
    });
  }

  function deleteConversation(convId) {
    const idx = conversations.findIndex(c => c.id === convId);
    if (idx === -1) return;
    conversations.splice(idx, 1);
    if (conversations.length === 0) createNewConversation(true);
    else if (activeConversationId === convId) activeConversationId = conversations[0].id;
    renderHistoryList();
    const current = conversations.find(c => c.id === activeConversationId);
    if (current) renderMessages(current);
  }

  function createNewConversation(skipRender = false) {
    const newId = Date.now() + '-' + Math.random().toString(36).slice(2,8);
    const welcomeMsg = 'Xin chào! Tôi là trợ lý AI. Hãy hỏi tôi về sản phẩm, tôi sẽ ghi nhớ sở thích của bạn 🌟';
    const newConv = {
      id: newId,
      title: `Cuộc trò chuyện ${conversations.length+1}`,
      messages: [{ text: welcomeMsg, sender: 'assistant', timestamp: new Date().toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'}) }],
      updatedAt: Date.now()
    };
    conversations.unshift(newConv);
    activeConversationId = newId;
    if (!skipRender) { renderHistoryList(); renderMessages(newConv); }
    return newConv;
  }

  async function sendMessageToActive(userText) {
    if (isSending || !userText.trim()) return;
    const conv = conversations.find(c => c.id === activeConversationId);
    if (!conv) return;
    isSending = true;
    setLoading(true);
    
    const userMsg = {
      text: userText.trim(),
      sender: 'user',
      timestamp: new Date().toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'})
    };
    conv.messages.push(userMsg);
    conv.updatedAt = Date.now();
    if (conv.messages.filter(m => m.sender === 'user').length === 1 && userText.trim()) {
      conv.title = userText.length > 28 ? userText.slice(0,25)+'...' : userText;
    }
    renderMessages(conv);
    renderHistoryList();
    
    const typingDiv = document.createElement('div');
    typingDiv.className = 'typing-indicator';
    typingDiv.id = 'tempTyping';
    typingDiv.innerHTML = `<div class="avatar-mini"><i class="fas fa-robot"></i></div><div class="typing-dots"><span></span><span></span><span></span></div>`;
    if (messageThread) { messageThread.appendChild(typingDiv); scrollToBottom(); }
    
    try {
      const rawReply = await window.ContinualAI.getAssistantReply(userText);
      const replyText = normalizeReply(rawReply);
      const assistantMsg = {
        text: replyText,
        sender: 'assistant',
        timestamp: new Date().toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'})
      };
      conv.messages.push(assistantMsg);
      conv.updatedAt = Date.now();
      document.getElementById('tempTyping')?.remove();
      renderMessages(conv);
      renderHistoryList();
      await updateMemoryModalFromBackend();
    } catch (error) {
      console.error(error);
      const errorMsg = { text: `❌ Lỗi: ${error.message}`, sender: 'assistant', timestamp: new Date().toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'}) };
      conv.messages.push(errorMsg);
      document.getElementById('tempTyping')?.remove();
      renderMessages(conv);
    } finally { isSending = false; setLoading(false); }
  }

  function handleSend() {
    if (isSending) return;
    const text = chatInput ? chatInput.value.trim() : '';
    if (!text) return;
    if (chatInput) chatInput.value = '';
    sendMessageToActive(text);
  }

  async function initApp() {
    const initId = Date.now() + '-init';
    const welcomeOnly = 'Chào mừng bạn! Tôi là trợ lý AI. Hãy thử hỏi về laptop, điện thoại, ngân sách (ví dụ: "tôi cần laptop khoảng 20 triệu, chơi game") 🚀';
    conversations = [{
      id: initId,
      title: 'Trò chuyện đầu tiên',
      messages: [{ text: welcomeOnly, sender: 'assistant', timestamp: new Date().toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'}) }],
      updatedAt: Date.now()
    }];
    activeConversationId = initId;
    renderHistoryList();
    renderMessages(conversations[0]);
    await updateMemoryModalFromBackend();
    await syncExperimentFlags();
    if (enableMemoryExtractionChk) enableMemoryExtractionChk.addEventListener('change', syncExperimentFlags);
    if (enableConversationalContextChk) enableConversationalContextChk.addEventListener('change', syncExperimentFlags);
    if (enableProductContextChk) enableProductContextChk.addEventListener('change', syncExperimentFlags);
  }

  // Event listeners
  if (menuToggle && sidebar) menuToggle.addEventListener('click', () => sidebar.classList.toggle('collapsed'));
  if (newChatBtn) newChatBtn.addEventListener('click', () => createNewConversation());
  if (sendBtn) sendBtn.addEventListener('click', handleSend);
  if (chatInput) chatInput.addEventListener('keypress', (e) => { if (e.key === 'Enter' && !isSending) { e.preventDefault(); handleSend(); } });
  if (themeToggle && themeIcon) {
    if (localStorage.getItem('theme') === 'light') { document.body.classList.add('light-mode'); themeIcon.classList.replace('fa-sun','fa-moon'); }
    themeToggle.addEventListener('click', () => { document.body.classList.toggle('light-mode'); const isLight = document.body.classList.contains('light-mode'); themeIcon.classList.toggle('fa-sun',!isLight); themeIcon.classList.toggle('fa-moon',isLight); localStorage.setItem('theme', isLight ? 'light' : 'dark'); });
  }
  if (startBtn && welcomeScreen) startBtn.addEventListener('click', () => welcomeScreen.classList.add('hidden'));

  if (memoryProfileBtn && memoryModal) {
    memoryProfileBtn.addEventListener('click', () => {
      memoryModal.classList.remove('hidden');
      updateMemoryModalFromBackend();
    });
  }
  if (closeMemoryModal) closeMemoryModal.addEventListener('click', () => memoryModal.classList.add('hidden'));
  memoryModal?.addEventListener('click', (e) => { if (e.target === memoryModal) memoryModal.classList.add('hidden'); });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initApp);
  else initApp();
})();