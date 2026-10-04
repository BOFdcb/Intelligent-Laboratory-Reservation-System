<template>
  <div class="chat-page">
    <div class="chat-card">
      <div class="chat-header">
        <span class="chat-title">AI 助手</span>
        <div class="header-actions">
          <el-radio-group v-model="chat.mode" size="small">
            <el-radio-button label="normal">普通对话</el-radio-button>
            <el-radio-button label="agent">智能预约</el-radio-button>
          </el-radio-group>
          <el-button size="small" text type="danger" @click="chat.clear()">清空对话</el-button>
        </div>
      </div>

      <div ref="messagesRef" class="messages-area">
        <div v-if="chat.messages.length === 0" class="empty-hint">
          <div class="hint-icon">🤖</div>
          <div class="hint-text">你好，我是智能助手，请发送消息开始对话</div>
        </div>

        <template v-for="msg in chat.messages" :key="msg.id">
          <div v-if="msg.role === 'user'" class="message-row user-row">
            <div class="bubble user-bubble">{{ msg.content }}</div>
          </div>
          <template v-else-if="msg.role === 'process'">
            <div class="process-node">
              <el-icon><Loading v-if="msg.isLoading" /></el-icon>
              <span class="process-label">{{ processLabel(msg.type) }}</span>
              <span class="process-content">{{ msg.content }}</span>
            </div>
          </template>
          <div v-else class="message-row ai-row">
            <div class="bubble ai-bubble">
              <div v-if="msg.content" v-html="renderMarkdown(msg.content)"></div>
              <span v-else class="typing">思考中<span class="dot">...</span></span>
            </div>
          </div>
        </template>
      </div>

      <div class="input-area">
        <el-input
          v-model="inputText"
          type="textarea"
          :rows="2"
          placeholder="请输入消息，回车发送"
          resize="none"
          :disabled="streaming"
          @keydown.enter.prevent="sendMessage"
        />
        <el-button type="primary" :disabled="streaming || !inputText.trim()" class="send-btn" @click="sendMessage">
          发送
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { auth } from '../store/auth'
import { chat } from '../store/chat'

const inputText = ref('')
const streaming = ref(false)
const messagesRef = ref(null)

function processLabel(type) {
  const map = {
    thinking: '思考',
    tool_call: '调用工具',
    tool_result: '工具结果',
  }
  return map[type] || type
}

function renderMarkdown(text) {
  const clean = text.replace(/<think>[\s\S]*?<\/think>/g, '')
  return clean.replace(/\n/g, '<br>')
}

function scrollToBottom() {
  nextTick(() => {
    const el = messagesRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || streaming.value) return

  chat.messages.push({ id: chat.nextId(), role: 'user', content: text })
  inputText.value = ''
  streaming.value = true
  scrollToBottom()

  const aiMsgId = chat.nextId()
  chat.messages.push({ id: aiMsgId, role: 'ai', content: '' })
  scrollToBottom()

  const endpoint = chat.mode === 'agent' ? '/api/chat/agent' : '/api/chat'
  try {
    const resp = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${auth.token}`,
      },
      body: JSON.stringify({ message: text, use_rag: true }),
    })

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed.startsWith('data: ')) continue
        const payload = trimmed.slice(6)
        if (!payload) continue
        try {
          const ev = JSON.parse(payload)
          handleEvent(ev, aiMsgId)
        } catch {
          // ignore malformed
        }
      }
    }
  } catch (err) {
    ElMessage.error('请求失败：' + (err.message || '网络错误'))
    const aiMsg = chat.messages.find((m) => m.id === aiMsgId)
    if (aiMsg) aiMsg.content = '请求失败，请稍后重试。'
  } finally {
    streaming.value = false
  }
}

function handleEvent(ev, aiMsgId) {
  if (ev.type === 'done') {
    return
  }
  if (ev.type === 'error') {
    const aiMsg = chat.messages.find((m) => m.id === aiMsgId)
    if (aiMsg) aiMsg.content = '错误：' + (ev.content || '未知错误')
    return
  }
  if (ev.type === 'answer') {
    const aiMsg = chat.messages.find((m) => m.id === aiMsgId)
    if (aiMsg) {
      aiMsg.content += ev.content || ''
      scrollToBottom()
    }
    return
  }
  if (['thinking', 'tool_call', 'tool_result'].includes(ev.type)) {
    const content = ev.content || ev.name || ev.result || JSON.stringify(ev)
    const existing = chat.messages.find((m) => m.role === 'process' && m.parentId === aiMsgId && m.type === ev.type && m.isLoading)
    if (existing) {
      existing.content = content
      existing.isLoading = false
    } else {
      chat.messages.push({
        id: chat.nextId(),
        role: 'process',
        type: ev.type,
        content,
        parentId: aiMsgId,
        isLoading: false,
      })
    }
    scrollToBottom()
  }
}
</script>

<style scoped>
.chat-page {
  height: calc(100vh - 100px);
}
.chat-card {
  background: #fff;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid #ebeef5;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.chat-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}
.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 18px;
  background: #f5f7fa;
}
.empty-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #909399;
}
.hint-icon {
  font-size: 48px;
  margin-bottom: 12px;
}
.hint-text {
  font-size: 14px;
}
.message-row {
  display: flex;
  margin-bottom: 14px;
}
.user-row {
  justify-content: flex-end;
}
.ai-row {
  justify-content: flex-start;
}
.bubble {
  max-width: 70%;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}
.user-bubble {
  background: #409eff;
  color: #fff;
  border-bottom-right-radius: 4px;
}
.ai-bubble {
  background: #fff;
  color: #303133;
  border: 1px solid #ebeef5;
  border-bottom-left-radius: 4px;
}
.typing {
  color: #909399;
}
.process-node {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 6px 0 6px 8px;
  font-size: 12px;
  color: #909399;
}
.process-label {
  background: #ecf5ff;
  color: #409eff;
  padding: 2px 8px;
  border-radius: 4px;
}
.process-content {
  color: #606266;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 60%;
}
.input-area {
  display: flex;
  gap: 10px;
  padding: 12px 18px;
  border-top: 1px solid #ebeef5;
  background: #fff;
}
.input-area :deep(.el-textarea__inner) {
  resize: none;
}
.send-btn {
  align-self: flex-end;
}
</style>
