<template>
  <div class="page-container">
    <PageHeader title="在线验证" />

    <el-row :gutter="16">
      <el-col :span="6">
        <div class="content-card">
          <div class="card-title">选择模型</div>
          <el-select v-model="selectedModel" filterable placeholder="选择本地或已合并模型" style="width:100%" @change="onModelChange">
            <el-option-group label="── 本地模型 ──">
              <el-option v-for="m in localModels" :key="m.path" :label="`📁 ${m.name}`" :value="m.path">
                <span>{{ m.name }}</span>
              </el-option>
            </el-option-group>
            <el-option-group label="── 已合并模型 ──">
              <el-option v-for="m in mergedModels" :key="m.path" :label="`🔗 ${m.name}`" :value="m.path">
                <span>{{ m.name }}</span>
              </el-option>
            </el-option-group>
          </el-select>

          <div v-if="selectedModel" style="margin-top:16px">
            <!-- 模型加载状态 -->
            <div style="margin-bottom:12px">
              <el-tag v-if="modelLoaded" type="success" size="small">已加载</el-tag>
              <el-tag v-else type="info" size="small">未加载</el-tag>
              <span v-if="modelLoaded && vramInfo" style="font-size:12px;color:#909399;margin-left:8px">显存: {{ vramInfo }}</span>
            </div>
            <el-form size="small">
              <el-form-item>
                <el-button v-if="!modelLoaded" type="success" size="small" :loading="loadingModel" @click="loadModel" style="width:100%">
                  加载模型
                </el-button>
                <el-button v-else type="warning" size="small" :loading="loadingModel" @click="unloadModel" style="width:100%">
                  卸载模型
                </el-button>
              </el-form-item>
            </el-form>

            <div class="param-title" style="margin-top:8px">生成参数</div>
            <el-form label-width="80px" size="small">
              <el-form-item label="Temperature">
                <el-slider v-model="temperature" :min="0" :max="200" :step="5" show-input style="width:calc(100% - 60px)" />
              </el-form-item>
              <el-form-item label="Top-p">
                <el-slider v-model="topP" :min="0" :max="100" :step="5" show-input style="width:calc(100% - 60px)" />
              </el-form-item>
              <el-form-item label="Max Tokens">
                <el-input-number v-model="maxTokens" :min="64" :max="4096" :step="64" style="width:100%" />
              </el-form-item>
              <el-form-item>
                <el-button size="small" type="danger" @click="clearChat" plain :disabled="!modelLoaded">清空对话</el-button>
              </el-form-item>
            </el-form>
          </div>

          <el-empty v-if="localModels.length === 0 && mergedModels.length === 0" description="无可用模型" />
        </div>
      </el-col>

      <el-col :span="18">
        <div class="content-card chat-card">
          <div v-if="!selectedModel" style="text-align:center;padding:60px;color:#909399">
            请从左侧选择一个模型开始验证
          </div>
          <div v-else-if="!modelLoaded" style="text-align:center;padding:60px;color:#909399">
            <p>模型已选择，请点击"加载模型"按钮</p>
          </div>
          <template v-else-if="modelLoaded">
            <div class="chat-messages" ref="messagesRef">
              <div v-for="(msg, i) in messages" :key="i" class="chat-msg" :class="msg.role">
                <div class="msg-avatar">
                  <el-avatar :size="32" :icon="msg.role === 'user' ? 'User' : 'Monitor'" />
                </div>
                <div class="msg-content">
                  <div class="msg-text">{{ msg.content }}</div>
                </div>
              </div>
              <div v-if="loading" class="chat-msg assistant">
                <div class="msg-avatar"><el-avatar :size="32" icon="Monitor" /></div>
                <div class="msg-content"><div class="msg-text typing">推理中...</div></div>
              </div>
            </div>
            <div class="chat-input">
              <el-input v-model="inputText" placeholder="输入问题进行验证..." @keyup.enter="sendMessage" :disabled="loading">
                <template #append>
                  <el-button :icon="Promotion" @click="sendMessage" :loading="loading" />
                </template>
              </el-input>
            </div>
          </template>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import PageHeader from '@/components/common/PageHeader.vue'
import { get, post } from '@/api/index'

interface ModelItem { name: string; path: string; size: string }
const localModels = ref<ModelItem[]>([])
const mergedModels = ref<ModelItem[]>([])

const selectedModel = ref('')
const inputText = ref('')
const loading = ref(false)
const loadingModel = ref(false)
const modelLoaded = ref(false)
const vramInfo = ref('')
const temperature = ref(0.7 * 100)
const topP = ref(0.9 * 100)
const maxTokens = ref(512)
const messagesRef = ref<HTMLDivElement>()
const messages = ref<{ role: 'user' | 'assistant'; content: string }[]>([])

const onModelChange = () => {
  modelLoaded.value = false
  vramInfo.value = ''
  messages.value = []
}

const loadModel = async () => {
  if (!selectedModel.value) return
  loadingModel.value = true
  try {
    const res = await post('/training/verify-load', { model_path: selectedModel.value, question: '' })
    if (res.code === 0) {
      modelLoaded.value = true
      vramInfo.value = res.data?.vram_used ? `${res.data.vram_used}G / ${res.data.vram_total}G` : ''
      ElMessage.success(res.message || '模型已加载')
      messages.value = [{ role: 'assistant', content: `模型已加载：${selectedModel.value}\n请输入问题进行验证。` }]
    } else {
      ElMessage.error(res.message || '加载失败')
    }
  } catch (e: any) { ElMessage.error(e.message) }
  finally { loadingModel.value = false }
}

const unloadModel = async () => {
  loadingModel.value = true
  try {
    const res = await post('/training/verify-unload', { model_path: selectedModel.value, question: '' })
    modelLoaded.value = false
    vramInfo.value = ''
    ElMessage.success(res.message || '已卸载')
  } catch (e: any) { ElMessage.error(e.message) }
  finally { loadingModel.value = false }
}

const clearChat = () => {
  messages.value = []
}

const buildHistory = () => {
  const history: { user: string; assistant: string }[] = []
  for (let i = 0; i < messages.value.length - 1; i += 2) {
    if (messages.value[i]?.role === 'user' && messages.value[i + 1]?.role === 'assistant') {
      history.push({ user: messages.value[i].content, assistant: messages.value[i + 1].content })
    }
  }
  return history
}

const sendMessage = async () => {
  if (!inputText.value.trim() || loading.value) return
  const question = inputText.value
  inputText.value = ''
  messages.value.push({ role: 'user', content: question })
  loading.value = true
  await nextTick()
  if (messagesRef.value) messagesRef.value.scrollTop = messagesRef.value.scrollHeight

  try {
    const res = await post<{ reply: string }>('/training/verify-chat', {
      model_path: selectedModel.value,
      question: question,
      history: buildHistory(),
      temperature: temperature.value / 100,
      top_p: topP.value / 100,
      max_tokens: maxTokens.value,
    })
    if (res.code === 0) {
      messages.value.push({ role: 'assistant', content: res.data.reply })
    } else {
      messages.value.push({ role: 'assistant', content: `推理失败: ${res.message || '未知错误'}` })
    }
  } catch (e: any) {
    messages.value.push({ role: 'assistant', content: `连接失败: ${e.message}` })
  } finally {
    loading.value = false
    nextTick(() => { if (messagesRef.value) messagesRef.value.scrollTop = messagesRef.value.scrollHeight })
  }
}

onMounted(async () => {
  try {
    const res = await get<{ local: ModelItem[]; merged: ModelItem[] }>('/training/verify-models')
    if (res.code === 0) {
      localModels.value = res.data.local || []
      mergedModels.value = res.data.merged || []
    }
  } catch (e) { console.error(e) }
})

onUnmounted(() => {
  if (modelLoaded.value && selectedModel.value) {
    post('/training/verify-unload', { model_path: selectedModel.value, question: '' }).catch(() => {})
  }
})
</script>

<style lang="scss" scoped>
.param-title { font-weight: 600; font-size: 14px; color: #303133; margin-bottom: 8px; }
.chat-card { display: flex; flex-direction: column; height: calc(100vh - 200px); padding: 0;
  .card-title { padding: 16px 20px; margin-bottom: 0; }
  .chat-messages { flex: 1; overflow-y: auto; padding: 16px 20px;
    .chat-msg { display: flex; gap: 12px; margin-bottom: 16px;
      &.user { flex-direction: row-reverse; .msg-text { background: #409eff; color: #fff; } }
      &.assistant .msg-text { background: #f4f4f5; color: #303133; }
      .msg-content { max-width: 70%; .msg-text { padding: 10px 14px; border-radius: 12px; font-size: 14px; line-height: 1.6; } }
    }
  }
  .chat-input { padding: 16px 20px; border-top: 1px solid #ebeef5; }
}
</style>
