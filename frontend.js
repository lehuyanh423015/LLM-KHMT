// frontend.js (đã sửa spinner)
(function() {
  let conversations = [];
  let activeConversationId = null;
  let isSending = false;
  let attachedFiles = [];

  const historyContainer = document.getElementById('historyList');
  const messageThread = document.getElementById('messageThread');
  const chatInput = document.getElementById('chatInput');
  const sendBtn = document.getElementById('sendMessageBtn');
  const newChatBtn = document.getElementById('newChatBtn');
  const menuToggle = document.getElementById('menuToggle');
  const sidebar = document.getElementById('historySidebar');
  const themeToggle = document.getElementById('themeToggle');
  const themeIcon = themeToggle.querySelector('i');
  const startBtn = document.getElementById('startChatBtn');
  const welcomeScreen = document.getElementById('welcomeScreen');
  const attachBtn = document.getElementById('attachBtn');
  const fileInput = document.getElementById('fileInput');
  const attachmentPreview = document.getElementById('attachmentPreview');

  function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  }

  function readFileAsDataURL(file) {
    return new Promise((resolve) => {
      if (file.type.startsWith('image/')) {
        const reader = new FileReader();
        reader.onload = (e) => resolve({
          name: file.name,
          size: file.size,
          type: file.type,
          dataURL: e.target.result
        });
        reader.readAsDataURL(file);
      } else {
        resolve({
          name: file.name,
          size: file.size,
          type: file.type,
          dataURL: null
        });
      }
    });
  }

  function updateAttachmentPreview() {
    attachmentPreview.innerHTML = '';
    attachedFiles.forEach((file, idx) => {
      const container = document.createElement('div');
      container.className = 'attach-thumbnail';
      const isImage = file.type.startsWith('image/');
      const leftDiv = document.createElement('div');
      if (isImage) {
        const img = document.createElement('img');
        const url = URL.createObjectURL(file);
        img.src = url;
        img.onload = () => URL.revokeObjectURL(url);
        leftDiv.appendChild(img);
      } else {
        const iconDiv = document.createElement('div');
        iconDiv.className = 'file-icon';
        iconDiv.innerHTML = '<i class="fas fa-file-alt"></i>';
        leftDiv.appendChild(iconDiv);
      }
      const infoDiv = document.createElement('div');
      infoDiv.className = 'attach-info';
      const nameSpan = document.createElement('div');
      nameSpan.className = 'attach-name';
      nameSpan.textContent = file.name.length > 22 ? file.name.slice(0, 20)+'...' : file.name;
      const sizeSpan = document.createElement('div');
      sizeSpan.className = 'attach-size';
      sizeSpan.textContent = formatFileSize(file.size);
      infoDiv.appendChild(nameSpan);
      infoDiv.appendChild(sizeSpan);
      const removeBtn = document.createElement('i');
      removeBtn.className = 'fas fa-times-circle remove-attach';
      removeBtn.addEventListener('click', () => {
        attachedFiles.splice(idx, 1);
        updateAttachmentPreview();
      });
      container.appendChild(leftDiv);
      container.appendChild(infoDiv);
      container.appendChild(removeBtn);
      attachmentPreview.appendChild(container);
    });
  }

  function renderMessage(msg, isFirstAssistant = false) {
    const wrapper = document.createElement('div');
    wrapper.className = `message-wrapper ${msg.sender}`;
    const avatar = document.createElement('div');
    avatar.className = 'avatar-mini';
    avatar.innerHTML = msg.sender === 'user' ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';
    const bubble = document.createElement('div');
    bubble.className = 'bubble-minimal';
    
    if (msg.attachments && msg.attachments.length > 0) {
      const attachDiv = document.createElement('div');
      attachDiv.className = 'message-attachments';
      msg.attachments.forEach(att => {
        const item = document.createElement('div');
        item.className = 'attach-item';
        if (att.type.startsWith('image/') && att.dataURL) {
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
        const nameSpan = document.createElement('div');
        nameSpan.className = 'attach-name';
        nameSpan.textContent = att.name.length > 20 ? att.name.slice(0, 18)+'...' : att.name;
        const sizeSpan = document.createElement('div');
        sizeSpan.className = 'attach-size';
        sizeSpan.textContent = formatFileSize(att.size);
        infoDiv.appendChild(nameSpan);
        infoDiv.appendChild(sizeSpan);
        item.appendChild(infoDiv);
        attachDiv.appendChild(item);
      });
      bubble.appendChild(attachDiv);
    }
    
    if (msg.text && msg.text.trim()) {
      const textDiv = document.createElement('div');
      textDiv.className = 'message-text';
      textDiv.textContent = msg.text;
      bubble.appendChild(textDiv);
    }
    
    const footer = document.createElement('div');
    footer.className = 'bubble-footer';
    const timeSpan = document.createElement('span');
    timeSpan.textContent = msg.timestamp || new Date().toLocaleTimeString('vi-VN', {hour:'2-digit', minute:'2-digit'});
    footer.appendChild(timeSpan);
    if(msg.sender === 'assistant' && !isFirstAssistant) {
      const badge = document.createElement('span');
      badge.className = 'learning-badge';
      badge.innerHTML = '<i class="fas fa-graduation-cap"></i> vừa học';
      footer.appendChild(badge);
    }
    bubble.appendChild(footer);
    wrapper.appendChild(avatar);
    wrapper.appendChild(bubble);
    return wrapper;
  }

  function renderMessages(conversation) {
    if(!conversation) return;
    messageThread.innerHTML = '';
    conversation.messages.forEach((msg, idx) => {
      const isFirstAssistant = (idx === 0 && msg.sender === 'assistant');
      const msgEl = renderMessage(msg, isFirstAssistant);
      messageThread.appendChild(msgEl);
    });
    messageThread.scrollTop = messageThread.scrollHeight;
  }

  function renderHistoryList() {
    historyContainer.innerHTML = '';
    conversations.forEach(conv => {
      const div = document.createElement('div');
      div.className = `history-item ${activeConversationId === conv.id ? 'active' : ''}`;
      const iconDiv = document.createElement('div');
      iconDiv.className = 'history-icon';
      iconDiv.innerHTML = '<i class="fas fa-comment-dots"></i>';
      const infoDiv = document.createElement('div');
      infoDiv.className = 'history-info';
      const titleSpan = document.createElement('div');
      titleSpan.className = 'history-title';
      titleSpan.textContent = conv.title;
      const metaDiv = document.createElement('div');
      metaDiv.className = 'history-meta';
      const timeSpan = document.createElement('span');
      const date = new Date(conv.updatedAt);
      timeSpan.textContent = `${date.getHours().toString().padStart(2,'0')}:${date.getMinutes().toString().padStart(2,'0')}`;
      const tagSpan = document.createElement('span');
      tagSpan.className = 'learning-tag-small';
      tagSpan.innerHTML = `<i class="fas fa-database"></i> ${conv.messages.length} tin`;
      metaDiv.appendChild(timeSpan);
      metaDiv.appendChild(tagSpan);
      infoDiv.appendChild(titleSpan);
      infoDiv.appendChild(metaDiv);
      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'delete-conv-btn';
      deleteBtn.innerHTML = '<i class="fas fa-trash-alt"></i>';
      deleteBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        deleteConversation(conv.id);
      });
      div.appendChild(iconDiv);
      div.appendChild(infoDiv);
      div.appendChild(deleteBtn);
      div.addEventListener('click', () => {
        if(activeConversationId === conv.id) return;
        activeConversationId = conv.id;
        renderHistoryList();
        const activeConv = conversations.find(c => c.id === activeConversationId);
        if(activeConv) renderMessages(activeConv);
      });
      historyContainer.appendChild(div);
    });
  }

  function deleteConversation(convId) {
    const idx = conversations.findIndex(c => c.id === convId);
    if(idx === -1) return;
    conversations.splice(idx, 1);
    if(conversations.length === 0) {
      createNewConversation(true);
    } else if(activeConversationId === convId) {
      activeConversationId = conversations[0].id;
    }
    renderHistoryList();
    const current = conversations.find(c => c.id === activeConversationId);
    if(current) renderMessages(current);
  }

  function createNewConversation(skipRender = false) {
    const newId = Date.now() + '-' + Math.random().toString(36);
    const welcomeMsg = "Xin chào! Tôi là trợ lý AI học liên tục. Hãy hỏi tôi bất cứ điều gì về thời tiết, kiến thức, hoặc công nghệ Continual Learning nhé 🌟";
    const newConv = {
      id: newId,
      title: `Cuộc trò chuyện ${conversations.length + 1}`,
      messages: [{ text: welcomeMsg, sender: 'assistant', timestamp: new Date().toLocaleTimeString('vi-VN', {hour:'2-digit', minute:'2-digit'}), attachments: [] }],
      updatedAt: Date.now()
    };
    conversations.unshift(newConv);
    activeConversationId = newId;
    if(!skipRender) {
      renderHistoryList();
      renderMessages(newConv);
    }
    return newConv;
  }

  async function sendMessageToActive(userText, files = []) {
    if(isSending || (!userText.trim() && files.length === 0)) return;
    const conv = conversations.find(c => c.id === activeConversationId);
    if(!conv) return;
    isSending = true;
    sendBtn.disabled = true;
    sendBtn.classList.add('loading');
    sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; // ĐÃ SỬA: thêm fa-spin
    
    const attachments = [];
    for (let file of files) {
      const att = await readFileAsDataURL(file);
      attachments.push(att);
    }
    
    const userMsg = {
      text: userText.trim(),
      sender: 'user',
      timestamp: new Date().toLocaleTimeString('vi-VN', {hour:'2-digit', minute:'2-digit'}),
      attachments: attachments
    };
    conv.messages.push(userMsg);
    conv.updatedAt = Date.now();
    if(conv.messages.filter(m => m.sender === 'user').length === 1 && userText.trim()) {
      let shortTitle = userText.length > 28 ? userText.slice(0,25)+'...' : userText;
      conv.title = shortTitle;
    }
    renderMessages(conv);
    renderHistoryList();
    
    const typingDiv = document.createElement('div');
    typingDiv.className = 'typing-indicator';
    typingDiv.id = 'tempTyping';
    typingDiv.innerHTML = `<div class="avatar-mini"><i class="fas fa-robot"></i></div><div class="typing-dots"><span></span><span></span><span></span></div>`;
    messageThread.appendChild(typingDiv);
    messageThread.scrollTop = messageThread.scrollHeight;
    
    setTimeout(async () => {
      const replyText = window.ContinualAI.getAssistantReply(userText || "có đính kèm file", attachments);
      const assistantMsg = {
        text: replyText,
        sender: 'assistant',
        timestamp: new Date().toLocaleTimeString('vi-VN', {hour:'2-digit', minute:'2-digit'}),
        attachments: []
      };
      conv.messages.push(assistantMsg);
      conv.updatedAt = Date.now();
      document.getElementById('tempTyping')?.remove();
      renderMessages(conv);
      renderHistoryList();
      isSending = false;
      sendBtn.disabled = false;
      sendBtn.classList.remove('loading');
      sendBtn.innerHTML = '<i class="fas fa-arrow-up"></i>';
      chatInput.focus();
    }, 800);
  }

  function handleSend() {
    if(isSending) return;
    const text = chatInput.value.trim();
    const filesToSend = [...attachedFiles];
    if(!text && filesToSend.length === 0) return;
    chatInput.value = '';
    attachedFiles = [];
    updateAttachmentPreview();
    sendMessageToActive(text, filesToSend);
  }

  function initApp() {
    const initId = Date.now() + '-init';
    const welcomeOnly = "Chào mừng bạn! Tôi là trợ lý Continual AI. Tôi học hỏi liên tục từ hội thoại. Hãy thử hỏi tôi về thời tiết, lịch trình, hoặc 'học liên tục' nhé 🚀";
    conversations = [{
      id: initId,
      title: "Trò chuyện đầu tiên",
      messages: [{ text: welcomeOnly, sender: 'assistant', timestamp: new Date().toLocaleTimeString('vi-VN', {hour:'2-digit', minute:'2-digit'}), attachments: [] }],
      updatedAt: Date.now()
    }];
    activeConversationId = initId;
    renderHistoryList();
    renderMessages(conversations[0]);
  }

  attachBtn.addEventListener('click', () => { fileInput.click(); });
  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) {
      for (let file of e.target.files) attachedFiles.push(file);
      updateAttachmentPreview();
    }
    fileInput.value = '';
  });
  menuToggle.addEventListener('click', () => sidebar.classList.toggle('collapsed'));
  newChatBtn.addEventListener('click', () => { createNewConversation(); });
  sendBtn.addEventListener('click', handleSend);
  chatInput.addEventListener('keypress', (e) => { if(e.key === 'Enter' && !isSending) handleSend(); });
  
  if(localStorage.getItem('theme') === 'light') {
    document.body.classList.add('light-mode');
    themeIcon.classList.replace('fa-sun', 'fa-moon');
  }
  themeToggle.addEventListener('click', () => {
    document.body.classList.toggle('light-mode');
    const isLight = document.body.classList.contains('light-mode');
    themeIcon.classList.toggle('fa-sun', !isLight);
    themeIcon.classList.toggle('fa-moon', isLight);
    localStorage.setItem('theme', isLight ? 'light' : 'dark');
  });
  
  startBtn.addEventListener('click', () => welcomeScreen.classList.add('hidden'));
  initApp();
})();