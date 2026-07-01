<template>
  <div class="page-container">
    <PageHeader title="在线验证" />

    <el-row :gutter="16">
      <!-- 模型选择 -->
      <el-col :span="6">
        <div class="content-card">
          <div class="card-title">选择模型</div>
          <el-select v-model="selectedModel" placeholder="选择模型" style="width: 100%">
            <el-option label="电力SFT-Qwen2-7B-v3" value="power_sft_v3" />
            <el-option label="合同DPO-DeepSeek-7B-v2" value="contract_dpo_v2" />
            <el-option label="规章CPT-LLaMA3-8B-v1" value="rules_cpt_v1" />
          </el-select>
          <el-descriptions :column="1" size="small" border style="margin-top: 12px">
            <el-descriptions-item label="训练模式">SFT</el-descriptions-item>
            <el-descriptions-item label="基座模型">Qwen2-7B</el-descriptions-item>
            <el-descriptions-item label="评估得分">82分</el-descriptions-item>
          </el-descriptions>
        </div>
      </el-col>

      <!-- 对话区域 -->
      <el-col :span="18">
        <div class="content-card chat-card">
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
              <div class="msg-content">
                <div class="msg-text typing">思考中<span class="dot">...</span></div>
              </div>
            </div>
          </div>
          <div class="chat-input">
            <el-input v-model="inputText" placeholder="输入问题进行验证..." @keyup.enter="sendMessage" :disabled="loading">
              <template #append>
                <el-button :icon="Promotion" @click="sendMessage" :loading="loading" />
              </template>
            </el-input>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { Promotion } from '@element-plus/icons-vue'
import PageHeader from '@/components/common/PageHeader.vue'

const selectedModel = ref('power_sft_v3')
const inputText = ref('')
const loading = ref(false)
const messagesRef = ref<HTMLDivElement>()

const messages = ref([
  { role: 'assistant' as const, content: '您好！我是电力SFT-Qwen2-7B-v3模型，请输入问题进行验证。' },
])

const mockReplies: Record<string, string> = {
  '电力采购招标的方式有哪些？': '电力采购招标分为公开招标和邀请招标两种方式。公开招标是以招标公告方式邀请不特定组织投标；邀请招标是以投标邀请书方式邀请特定组织投标。',
  '合同审批流程是什么？': '合同审批流程包括：部门负责人初审 → 财务部复核 → 分管领导审批。金额超过100万的需提交总经理办公会审议。',
}

const sendMessage = async () => {
  if (!inputText.value.trim() || loading.value) return
  messages.value.push({ role: 'user', content: inputText.value })
  const question = inputText.value
  inputText.value = ''
  loading.value = true

  await nextTick()
  messagesRef.value!.scrollTop = messagesRef.value!.scrollHeight

  setTimeout(() => {
    const reply = mockReplies[question] || `针对您的问题"${question}"，基于训练数据，该模型可以给出相关领域的专业回答。此为模拟验证环境，实际回答将由模型实时生成。`
    messages.value.push({ role: 'assistant', content: reply })
    loading.value = false
    nextTick(() => { messagesRef.value!.scrollTop = messagesRef.value!.scrollHeight })
  }, 1500)
}
</script>

<style lang="scss" scoped>
.chat-card {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 200px);
  padding: 0;

  .card-title {
    padding: 16px 20px;
    margin-bottom: 0;
  }

  .chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 16px 20px;

    .chat-msg {
      display: flex;
      gap: 12px;
      margin-bottom: 16px;

      &.user {
        flex-direction: row-reverse;

        .msg-content {
          .msg-text {
            background: #409eff;
            color: #fff;
          }
        }
      }

      &.assistant {
        .msg-content {
          .msg-text {
            background: #f4f4f5;
            color: #303133;
          }
        }
      }

      .msg-content {
        max-width: 70%;

        .msg-text {
          padding: 10px 14px;
          border-radius: 12px;
          font-size: 14px;
          line-height: 1.6;

          &.typing {
            .dot {
              animation: blink 1s infinite;
            }
          }
        }
      }
    }
  }

  .chat-input {
    padding: 16px 20px;
    border-top: 1px solid #ebeef5;
  }
}

@keyframes blink {
  0%, 100% { opacity: 0.2; }
  50% { opacity: 1; }
}
</style>
