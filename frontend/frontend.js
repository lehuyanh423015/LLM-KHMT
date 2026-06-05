// frontend.js - chat history + render text only (hiển thị đẹp)
(function () {
  let conversations = [];
  let activeConversationId = null;
  let isSending = false;
  let attachedFiles = [];
  let currentMode = 'fast';

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
  const attachBtn = document.getElementById('attachBtn');
  const fileInput = document.getElementById('fileInput');
  const attachmentPreview = document.getElementById('attachmentPreview');
  const modeSelect = document.getElementById('modeSelect');

  // ========== NOTIFICATION ==========
  function showNotification(title, message, type = 'info') {
    let container = document.getElementById('notificationContainer');
    if (!container) {
      container = document.createElement('div');
      container.id = 'notificationContainer';
      container.className = 'notification-container';
      document.body.appendChild(container);
    }
    const notifDiv = document.createElement('div');
    notifDiv.className = `notification notification-${type}`;
    let iconSvg = type === 'success' ? '<svg stroke="currentColor" viewBox="0 0 24 24" fill="none"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" stroke-width="2"/></svg>' : '<svg stroke="currentColor" viewBox="0 0 24 24" fill="none"><path d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke-width="2"/></svg>';
    notifDiv.innerHTML = `<div class="notification-content">${iconSvg}<div><strong>${escapeHtml(title)}</strong><br>${escapeHtml(message)}</div></div>`;
    container.appendChild(notifDiv);
    setTimeout(() => { notifDiv.style.opacity = '0'; notifDiv.style.transform = 'translateX(100%)'; notifDiv.style.transition = 'all 0.3s ease'; setTimeout(() => notifDiv.remove(), 300); }, 4000);
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

  // Cải thiện markdown: link, đậm, xuống dòng
  function markdownToHtml(text) {
    if (!text) return '';
    let html = escapeHtml(text);
    
    // **bold**
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // URL -> link clickable
    html = html.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
    
    // Dấu đầu dòng • hoặc -
    html = html.replace(/^[•\-]\s+/gm, '• ');
    html = html.replace(/(?:^|(\n))•\s+/g, '$1• ');
    
    // Xuống dòng
    html = html.replace(/\n/g, '<br>');
    
    return html;
  }

  function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  }

  function readFileAsDataURL(file) {
    return new Promise((resolve) => {
      if (file.type && file.type.startsWith('image/')) {
        const reader = new FileReader();
        reader.onload = (e) => resolve({ name: file.name, size: file.size, type: file.type, dataURL: e.target.result });
        reader.readAsDataURL(file);
      } else {
        resolve({ name: file.name, size: file.size, type: file.type, dataURL: null });
      }
    });
  }

  function updateAttachmentPreview() {
    if (!attachmentPreview) return;
    attachmentPreview.innerHTML = '';
    attachedFiles.forEach((file, idx) => {
      const container = document.createElement('div');
      container.className = 'attach-thumbnail';
      const leftDiv = document.createElement('div');
      const isImage = file.type && file.type.startsWith('image/');
      if (isImage) {
        const img = document.createElement('img');
        const url = URL.createObjectURL(file);
        img.src = url;
        img.onload = () => URL.revokeObjectURL(url);
        leftDiv.appendChild(img);
      } else {
        const iconDiv = document.createElement('div');
        iconDiv.className = 'file-icon';
        iconDiv.innerHTML = '📄';
        leftDiv.appendChild(iconDiv);
      }
      const infoDiv = document.createElement('div');
      infoDiv.className = 'attach-info';
      const nameDiv = document.createElement('div');
      nameDiv.className = 'attach-name';
      nameDiv.textContent = file.name.length > 22 ? file.name.slice(0,20)+'...' : file.name;
      const sizeDiv = document.createElement('div');
      sizeDiv.className = 'attach-size';
      sizeDiv.textContent = formatFileSize(file.size);
      infoDiv.appendChild(nameDiv);
      infoDiv.appendChild(sizeDiv);
      const removeBtn = document.createElement('span');
      removeBtn.innerHTML = '❌';
      removeBtn.style.cursor = 'pointer';
      removeBtn.addEventListener('click', () => { attachedFiles.splice(idx,1); updateAttachmentPreview(); });
      container.appendChild(leftDiv);
      container.appendChild(infoDiv);
      container.appendChild(removeBtn);
      attachmentPreview.appendChild(container);
    });
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
    if (rawReply && typeof rawReply === 'object') return rawReply.answer || rawReply.text || rawReply.message || '';
    return String(rawReply || '');
  }

  // ========== MODE ==========
  async function fetchCurrentMode() {
    try {
      const response = await fetch('http://localhost:8000/config/mode', { method: 'GET', headers: { 'Content-Type': 'application/json' } });
      if (response.ok) { const data = await response.json(); currentMode = data.mode || 'fast'; }
      else currentMode = 'fast';
    } catch (error) { console.warn('Cannot fetch mode, using fast', error); currentMode = 'fast'; }
    updateModeUI();
  }

  async function setMode(mode) {
    if (!modeSelect) return;
    modeSelect.classList.add('loading');
    try {
      const response = await fetch('http://localhost:8000/config/mode', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode: mode }) });
      if (response.ok) { const data = await response.json(); currentMode = data.mode || mode; updateModeUI(); showNotification('Chế độ', `Đã chuyển sang ${currentMode === 'fast' ? 'Fast (Nhanh)' : 'Quality (Chất lượng cao)'}`, 'success'); }
      else throw new Error(`HTTP ${response.status}`);
    } catch (error) { console.error(error); showNotification('Lỗi', 'Không thể thay đổi chế độ', 'error'); updateModeUI(); }
    finally { modeSelect.classList.remove('loading'); }
  }

  function updateModeUI() { if (modeSelect) modeSelect.value = currentMode; }
  function onModeChange() { const newMode = modeSelect.value; if (newMode !== currentMode) setMode(newMode); }

  // ========== RENDER ==========
  function renderMessage(msg) {
    const wrapper = document.createElement('div');
    wrapper.className = `message-wrapper ${msg.sender}`;
    const avatar = document.createElement('div');
    avatar.className = 'avatar-mini';
    avatar.innerHTML = msg.sender === 'user' ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';
    const bubble = document.createElement('div');
    bubble.className = 'bubble-minimal';
    
    if (msg.attachments && msg.attachments.length) {
      const attachDiv = document.createElement('div');
      attachDiv.className = 'message-attachments';
      msg.attachments.forEach(att => {
        const item = document.createElement('div');
        item.className = 'attach-item';
        if (att.type && att.type.startsWith('image/') && att.dataURL) {
          const img = document.createElement('img');
          img.src = att.dataURL;
          item.appendChild(img);
        } else {
          const iconDiv = document.createElement('div');
          iconDiv.className = 'file-icon';
          iconDiv.innerHTML = '<i class="fas fa-file-alt"></i>';
          item.appendChild(iconDiv);
        }
        const infoDiv = document.createElement('div');
        infoDiv.className = 'attach-info';
        const nameDiv = document.createElement('div');
        nameDiv.className = 'attach-name';
        nameDiv.textContent = att.name.length > 20 ? att.name.slice(0,18)+'...' : att.name;
        const sizeDiv = document.createElement('div');
        sizeDiv.className = 'attach-size';
        sizeDiv.textContent = formatFileSize(att.size);
        infoDiv.appendChild(nameDiv);
        infoDiv.appendChild(sizeDiv);
        item.appendChild(infoDiv);
        attachDiv.appendChild(item);
      });
      bubble.appendChild(attachDiv);
    }
    
    if (msg.text && msg.text.trim()) {
      const textDiv = document.createElement('div');
      textDiv.className = 'message-text';
      if (msg.sender === 'assistant') {
        textDiv.innerHTML = markdownToHtml(msg.text);
        // Style cho link
        const links = textDiv.querySelectorAll('a');
        links.forEach(link => {
          link.style.color = 'var(--accent)';
          link.style.textDecoration = 'underline';
        });
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
    conversation.messages.forEach((msg) => { messageThread.appendChild(renderMessage(msg)); });
    scrollToBottom();
  }

  // ========== LỊCH SỬ ==========
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
    const welcomeMsg = 'Xin chào! Tôi là trợ lý AI. Hãy hỏi tôi bất cứ điều gì nhé 🌟';
    const newConv = {
      id: newId,
      title: `Cuộc trò chuyện ${conversations.length+1}`,
      messages: [{ text: welcomeMsg, sender: 'assistant', timestamp: new Date().toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'}), attachments: [] }],
      updatedAt: Date.now()
    };
    conversations.unshift(newConv);
    activeConversationId = newId;
    if (!skipRender) { renderHistoryList(); renderMessages(newConv); }
    return newConv;
  }

  // ========== GỬI TIN ==========
  async function sendMessageToActive(userText, files = []) {
    if (isSending || (!userText.trim() && files.length === 0)) return;
    const conv = conversations.find(c => c.id === activeConversationId);
    if (!conv) return;
    isSending = true;
    setLoading(true);
    const attachments = [];
    for (const file of files) { attachments.push(await readFileAsDataURL(file)); }
    const userMsg = {
      text: userText.trim(),
      sender: 'user',
      timestamp: new Date().toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'}),
      attachments
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
    setTimeout(async () => {
      try {
        const rawReply = await window.ContinualAI.getAssistantReply(userText || 'có đính kèm file', attachments);
        const replyText = normalizeReply(rawReply);
        const assistantMsg = {
          text: replyText,
          sender: 'assistant',
          timestamp: new Date().toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'}),
          attachments: []
        };
        conv.messages.push(assistantMsg);
        conv.updatedAt = Date.now();
        document.getElementById('tempTyping')?.remove();
        renderMessages(conv);
        renderHistoryList();
      } catch (error) {
        console.error(error);
        const errorMsg = { text: `❌ Lỗi: ${error.message}`, sender: 'assistant', timestamp: new Date().toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'}), attachments: [] };
        conv.messages.push(errorMsg);
        document.getElementById('tempTyping')?.remove();
        renderMessages(conv);
      } finally { isSending = false; setLoading(false); }
    }, 250);
  }

  function handleSend() {
    if (isSending) return;
    const text = chatInput ? chatInput.value.trim() : '';
    const filesToSend = [...attachedFiles];
    if (!text && filesToSend.length === 0) return;
    if (chatInput) chatInput.value = '';
    attachedFiles = [];
    updateAttachmentPreview();
    sendMessageToActive(text, filesToSend);
  }

  // ========== INIT ==========
  function initApp() {
    const initId = Date.now() + '-init';
    const welcomeOnly = 'Chào mừng bạn! Tôi là trợ lý AI. Hãy thử hỏi về điện thoại, laptop hoặc sản phẩm bạn quan tâm nhé 🚀';
    conversations = [{
      id: initId,
      title: 'Trò chuyện đầu tiên',
      messages: [{ text: welcomeOnly, sender: 'assistant', timestamp: new Date().toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'}), attachments: [] }],
      updatedAt: Date.now()
    }];
    activeConversationId = initId;
    renderHistoryList();
    renderMessages(conversations[0]);
    fetchCurrentMode();
  }

  // ========== SỰ KIỆN ==========
  if (attachBtn && fileInput) {
    attachBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => { if (e.target.files) for (const file of e.target.files) attachedFiles.push(file); updateAttachmentPreview(); fileInput.value = ''; });
  }
  if (menuToggle && sidebar) menuToggle.addEventListener('click', () => sidebar.classList.toggle('collapsed'));
  if (newChatBtn) newChatBtn.addEventListener('click', () => createNewConversation());
  if (sendBtn) sendBtn.addEventListener('click', handleSend);
  if (chatInput) chatInput.addEventListener('keypress', (e) => { if (e.key === 'Enter' && !isSending) { e.preventDefault(); handleSend(); } });
  if (themeToggle && themeIcon) {
    if (localStorage.getItem('theme') === 'light') { document.body.classList.add('light-mode'); themeIcon.classList.replace('fa-sun','fa-moon'); }
    themeToggle.addEventListener('click', () => { document.body.classList.toggle('light-mode'); const isLight = document.body.classList.contains('light-mode'); themeIcon.classList.toggle('fa-sun',!isLight); themeIcon.classList.toggle('fa-moon',isLight); localStorage.setItem('theme', isLight ? 'light' : 'dark'); });
  }
  if (modeSelect) modeSelect.addEventListener('change', onModeChange);
  if (startBtn && welcomeScreen) startBtn.addEventListener('click', () => welcomeScreen.classList.add('hidden'));
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initApp);
  else initApp();
})();