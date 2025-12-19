class ChatApp {
    constructor() {
        this.messagesContainer = document.getElementById('messages-container');
        this.messageInput = document.getElementById('message-input');
        this.sendBtn = document.getElementById('send-btn');
        this.newChatBtn = document.getElementById('new-chat-btn');
        this.sessionIdDisplay = document.getElementById('session-id');
        this.connectionStatus = document.getElementById('connection-status');
        this.toolModal = document.getElementById('tool-modal');
        this.toolModalBody = document.getElementById('tool-modal-body');
        this.chatHistoryList = document.getElementById('chat-history-list');

        this.ws = null;
        this.sessionId = null;
        this.isConnected = false;
        this.currentAssistantMessage = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.welcomeMessageRemoved = false;

        this.bindEvents();
        this.loadChatHistory();
        this.connect();
    }

    bindEvents() {
        this.sendBtn.addEventListener('click', () => this.sendMessage());

        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        this.messageInput.addEventListener('input', () => {
            this.messageInput.style.height = 'auto';
            this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 150) + 'px';
        });

        this.newChatBtn.addEventListener('click', () => this.startNewChat());

        this.toolModal.addEventListener('click', (e) => {
            if (e.target === this.toolModal) {
                this.hideToolModal();
            }
        });
    }

    generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    connect() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            return;
        }

        this.updateConnectionStatus('connecting');
        this.sessionId = this.sessionId || this.generateUUID();
        this.sessionIdDisplay.textContent = this.sessionId.substring(0, 8) + '...';

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/session/${this.sessionId}`;

        try {
            this.ws = new WebSocket(wsUrl);
            this.ws.onopen = () => this.onWebSocketOpen();
            this.ws.onclose = () => this.onWebSocketClose();
            this.ws.onerror = (error) => this.onWebSocketError(error);
            this.ws.onmessage = (event) => this.onWebSocketMessage(event);
        } catch (error) {
            console.error('WebSocket connection error:', error);
            this.updateConnectionStatus('disconnected');
        }
    }

    onWebSocketOpen() {
        console.log('WebSocket connected');
        this.isConnected = true;
        this.reconnectAttempts = 0;
        this.updateConnectionStatus('connected');
        this.enableInput();
        this.startHeartbeat();
    }

    onWebSocketClose() {
        console.log('WebSocket disconnected');
        this.isConnected = false;
        this.updateConnectionStatus('disconnected');
        this.disableInput();
        this.stopHeartbeat();

        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
            console.log(`Reconnecting in ${delay}ms... (attempt ${this.reconnectAttempts})`);
            setTimeout(() => this.connect(), delay);
        }
    }

    onWebSocketError(error) {
        console.error('WebSocket error:', error);
    }

    onWebSocketMessage(event) {
        try {
            const data = JSON.parse(event.data);

            switch (data.type) {
                case 'system':
                    this.handleSystemMessage(data);
                    break;
                case 'ai_token':
                    this.handleAIToken(data);
                    break;
                case 'ai_complete':
                    this.handleAIComplete(data);
                    break;
                case 'tool_call':
                    this.handleToolCall(data);
                    break;
                case 'tool_result':
                    this.handleToolResult(data);
                    break;
                case 'error':
                    this.handleError(data);
                    break;
                case 'pong':
                    break;
                default:
                    console.log('Unknown message type:', data.type);
            }
        } catch (error) {
            console.error('Error parsing message:', error);
        }
    }

    handleSystemMessage(data) {
        this.addMessage('system', data.content);
    }

    handleAIToken(data) {
        if (!this.currentAssistantMessage) {
            this.removeWelcomeMessage();
            this.currentAssistantMessage = this.createAssistantMessage();
        }

        const contentEl = this.currentAssistantMessage.querySelector('.message-text');
        if (contentEl) {
            const typingIndicator = contentEl.querySelector('.typing-indicator');
            if (typingIndicator) {
                typingIndicator.remove();
            }

            let token = data.token;
            if (!contentEl.textContent) {
                token = token.trimStart();
            }

            contentEl.textContent += token;
            this.scrollToBottom();
        }
    }

    handleAIComplete(data) {
        console.log('AI Complete:', data);

        if (this.currentAssistantMessage) {
            const contentEl = this.currentAssistantMessage.querySelector('.message-text');
            if (contentEl) {
                const typingIndicator = contentEl.querySelector('.typing-indicator');
                if (typingIndicator) {
                    typingIndicator.remove();
                }

                if (!contentEl.textContent.trim() && data.content) {
                    contentEl.textContent = data.content;
                }
            }
        } else if (data.content) {
            this.removeWelcomeMessage();
            this.addMessage('assistant', data.content);
        }

        this.currentAssistantMessage = null;
        this.enableInput();
        this.scrollToBottom();
    }

    handleToolCall(data) {
        if (this.currentAssistantMessage) {
            const toolInfo = document.createElement('div');
            toolInfo.className = 'tool-call-info';
            toolInfo.innerHTML = `
                <span>Using tool: </span>
                <span class="tool-name">${data.tool_name}</span>
            `;
            this.currentAssistantMessage.querySelector('.message-content').appendChild(toolInfo);
        }

        this.showToolModal(data.tool_name, data.tool_input);
    }

    handleToolResult(data) {
        setTimeout(() => this.hideToolModal(), 500);
    }

    handleError(data) {
        console.log('Error received:', data);

        if (this.currentAssistantMessage) {
            this.currentAssistantMessage.remove();
        }

        this.removeWelcomeMessage();
        const errorMsg = data.message || data.content || 'An error occurred';
        this.addMessage('error', errorMsg);

        this.currentAssistantMessage = null;
        this.enableInput();
        this.scrollToBottom();
    }

    sendMessage() {
        const content = this.messageInput.value.trim();
        if (!content || !this.isConnected) return;

        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';

        this.removeWelcomeMessage();
        this.addMessage('user', content);

        this.ws.send(JSON.stringify({
            type: 'user_input',
            content: content
        }));

        this.disableInput();
        this.currentAssistantMessage = this.createAssistantMessage(true);
    }

    addMessage(type, content) {
        const messageEl = document.createElement('div');
        messageEl.className = `message ${type}`;

        if (type === 'user') {
            messageEl.innerHTML = `
                <div class="message-avatar">U</div>
                <div class="message-content">
                    <p class="message-text">${this.escapeHtml(content)}</p>
                </div>
            `;
        } else if (type === 'assistant') {
            messageEl.innerHTML = `
                <div class="message-avatar">AI</div>
                <div class="message-content">
                    <p class="message-text">${this.escapeHtml(content)}</p>
                </div>
            `;
        } else if (type === 'system') {
            messageEl.innerHTML = `
                <div class="message-content">
                    <p class="message-text">${this.escapeHtml(content)}</p>
                </div>
            `;
        } else if (type === 'error') {
            messageEl.className = 'message system';
            messageEl.style.borderColor = 'rgba(239, 68, 68, 0.3)';
            messageEl.style.background = 'rgba(239, 68, 68, 0.1)';
            messageEl.innerHTML = `
                <div class="message-content">
                    <p class="message-text">Error: ${this.escapeHtml(content)}</p>
                </div>
            `;
        }

        this.messagesContainer.appendChild(messageEl);
        this.scrollToBottom();

        return messageEl;
    }

    createAssistantMessage(showTyping = false) {
        const messageEl = document.createElement('div');
        messageEl.className = 'message assistant';

        const typingHtml = showTyping ? `
            <span class="typing-indicator">
                <span></span><span></span><span></span>
            </span>
        ` : '';

        messageEl.innerHTML = `
            <div class="message-avatar">AI</div>
            <div class="message-content">
                <p class="message-text">${typingHtml}</p>
            </div>
        `;

        this.messagesContainer.appendChild(messageEl);
        this.scrollToBottom();

        return messageEl;
    }

    removeWelcomeMessage() {
        if (this.welcomeMessageRemoved) return;

        const welcomeEl = this.messagesContainer.querySelector('.welcome-message');
        if (welcomeEl) {
            welcomeEl.remove();
            this.welcomeMessageRemoved = true;
        }
    }

    startNewChat() {
        if (this.ws) {
            this.ws.close();
        }

        this.sessionId = null;
        this.currentAssistantMessage = null;
        this.welcomeMessageRemoved = false;

        this.messagesContainer.innerHTML = '';

        setTimeout(() => this.connect(), 100);
        this.loadChatHistory();
    }

    async loadChatHistory() {
        try {
            const response = await fetch('/api/sessions?limit=15');
            const data = await response.json();

            if (data.sessions && data.sessions.length > 0) {
                this.renderChatHistory(data.sessions);
            } else {
                this.chatHistoryList.innerHTML = '<div class="no-history">No previous chats</div>';
            }
        } catch (error) {
            console.error('Failed to load chat history:', error);
            this.chatHistoryList.innerHTML = '<div class="no-history">Failed to load history</div>';
        }
    }

    renderChatHistory(sessions) {
        this.chatHistoryList.innerHTML = sessions.map(session => {
            const date = new Date(session.start_time);
            const timeStr = date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            const displayName = session.name || session.summary || 'Chat session';
            const shortName = displayName.length > 30 ? displayName.substring(0, 30) + '...' : displayName;

            return `
                <button class="chat-history-item" data-session-id="${session.id}">
                    <span class="chat-summary">${this.escapeHtml(shortName)}</span>
                    <span class="chat-time">${timeStr}</span>
                </button>
            `;
        }).join('');

        this.chatHistoryList.querySelectorAll('.chat-history-item').forEach(item => {
            item.addEventListener('click', () => {
                const sessionId = item.dataset.sessionId;
                this.loadSession(sessionId);
            });
        });
    }

    async loadSession(sessionId) {
        try {
            if (this.ws) {
                this.ws.close();
            }

            this.messagesContainer.innerHTML = '';
            this.currentAssistantMessage = null;
            this.welcomeMessageRemoved = true;

            const response = await fetch(`/api/sessions/${sessionId}/messages`);
            const data = await response.json();

            if (data.messages && data.messages.length > 0) {
                data.messages.forEach(msg => {
                    if (msg.event_type === 'user_message') {
                        this.addMessage('user', msg.content);
                    } else if (msg.event_type === 'ai_response') {
                        this.addMessage('assistant', msg.content);
                    }
                });
            } else {
                this.messagesContainer.innerHTML = '<div class="no-history" style="text-align: center; padding: 2rem;">No messages in this session</div>';
            }

            this.sessionId = sessionId;
            this.sessionIdDisplay.textContent = sessionId.substring(0, 8) + '...';

            this.chatHistoryList.querySelectorAll('.chat-history-item').forEach(item => {
                item.classList.toggle('active', item.dataset.sessionId === sessionId);
            });

            this.reconnectAttempts = 0;
            this.connect();

            this.scrollToBottom();
        } catch (error) {
            console.error('Failed to load session:', error);
        }
    }

    showToolModal(toolName, toolInput) {
        this.toolModalBody.innerHTML = `
            <p><strong>Tool:</strong> ${toolName}</p>
            <p><strong>Input:</strong></p>
            <pre>${JSON.stringify(toolInput, null, 2)}</pre>
        `;
        this.toolModal.classList.add('active');
    }

    hideToolModal() {
        this.toolModal.classList.remove('active');
    }

    updateConnectionStatus(status) {
        const statusDot = this.connectionStatus.querySelector('.status-dot');
        const statusText = this.connectionStatus.querySelector('span:last-child');

        statusDot.className = 'status-dot ' + status;

        switch (status) {
            case 'connected':
                statusText.textContent = 'Connected';
                break;
            case 'connecting':
                statusText.textContent = 'Connecting...';
                break;
            case 'disconnected':
                statusText.textContent = 'Disconnected';
                break;
        }
    }

    enableInput() {
        this.messageInput.disabled = false;
        this.sendBtn.disabled = false;
        this.messageInput.focus();
    }

    disableInput() {
        this.messageInput.disabled = true;
        this.sendBtn.disabled = true;
    }

    scrollToBottom() {
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    startHeartbeat() {
        this.heartbeatInterval = setInterval(() => {
            if (this.isConnected && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: 'ping' }));
            }
        }, 30000);
    }

    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.chatApp = new ChatApp();
});
