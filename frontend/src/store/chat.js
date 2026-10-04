import { reactive, watch } from 'vue'
import { auth } from './auth'

// AI 助手对话的全局状态：
// - 组件销毁（切换路由）不丢失，因为状态挂在全局 store 上
// - 用 localStorage 持久化，重新登录后依然能看到历史对话
// - 按用户名隔离不同账号的聊天记录
// - 最多保留最近 5 次对话（5 轮问答），更早的自动丢弃

const MAX_ROUNDS = 5

function storageKey() {
  const name = auth.user?.username || 'guest'
  return `chat_history_${name}`
}

function loadState() {
  try {
    return JSON.parse(localStorage.getItem(storageKey()) || 'null')
  } catch {
    return null
  }
}

function trimRounds(messages) {
  // 一轮 = 一条 user 消息 + 其后的 ai/process 消息
  const userIdx = messages
    .map((m, i) => (m.role === 'user' ? i : -1))
    .filter((i) => i >= 0)
  if (userIdx.length <= MAX_ROUNDS) return messages
  return messages.slice(userIdx[userIdx.length - MAX_ROUNDS])
}

const saved = loadState()

export const chat = reactive({
  mode: saved?.mode || 'normal',
  messages: saved?.messages || [],
  msgIdCounter: saved?.msgIdCounter || 0,

  nextId() {
    return ++this.msgIdCounter
  },

  save() {
    const trimmed = trimRounds(this.messages)
    if (trimmed.length !== this.messages.length) {
      this.messages.splice(0, this.messages.length, ...trimmed)
    }
    localStorage.setItem(
      storageKey(),
      JSON.stringify({
        mode: this.mode,
        messages: this.messages,
        msgIdCounter: this.msgIdCounter,
      })
    )
  },

  clear() {
    this.messages = []
    this.save()
  },
})

// 内容变化时自动持久化（并裁剪到最近 5 轮）
watch(() => [chat.mode, chat.messages], () => chat.save(), { deep: true })

// 切换登录账号时，加载对应账号的聊天记录
watch(
  () => auth.user?.username,
  () => {
    const s = loadState()
    chat.mode = s?.mode || 'normal'
    chat.messages = s?.messages || []
    chat.msgIdCounter = s?.msgIdCounter || 0
  }
)
