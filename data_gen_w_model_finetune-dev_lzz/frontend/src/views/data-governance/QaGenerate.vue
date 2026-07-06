<template>
  <div class="page-container">
    <PageHeader title="问答对生成">
      <el-button type="primary" @click="startGenerate">
        <el-icon><VideoPlay /></el-icon>开始生成
      </el-button>
    </PageHeader>

    <!-- 生成模式选择 -->
    <div class="content-card">
      <div class="card-title">生成模式</div>
      <el-radio-group v-model="generateMode" size="large">
        <el-radio-button value="local">局部模式</el-radio-button>
        <el-radio-button value="enhanced">领域增强模式</el-radio-button>
        <el-radio-button value="fulltext">全文模式</el-radio-button>
        <el-radio-button value="all">组合模式(All)</el-radio-button>
      </el-radio-group>
      <div class="mode-desc">
        <el-text type="info" size="small">{{ modeDescriptions[generateMode] }}</el-text>
      </div>
    </div>

    <!-- 高级参数 -->
    <div class="content-card">
      <div class="card-title">高级参数</div>
      <el-form :model="params" label-width="120px" size="small" inline>
        <el-form-item label="生成模型">
          <el-select v-model="params.model" style="width: 200px">
            <el-option label="Qwen2-7B-Instruct" value="qwen2-7b" />
            <el-option label="DeepSeek-7B-Chat" value="deepseek-7b" />
          </el-select>
        </el-form-item>
        <el-form-item label="Temperature">
          <el-slider v-model="params.temperature" :min="0" :max="100" :step="5" style="width: 150px" />
        </el-form-item>
        <el-form-item label="并发数">
          <el-input-number v-model="params.concurrency" :min="1" :max="10" />
        </el-form-item>
        <el-form-item label="上下文窗口">
          <el-input-number v-model="params.contextWindow" :min="1" :max="10" />
        </el-form-item>
      </el-form>
    </div>

    <!-- 生成进度 -->
    <div v-if="generating" class="content-card">
      <div class="card-title">生成进度</div>
      <el-progress :percentage="progress" :status="progress === 100 ? 'success' : ''" />
      <div class="progress-info">
        <span>已生成 {{ generatedCount }} 条问答对</span>
        <span>失败 {{ failedCount }} 条</span>
        <span>跳过低质量切片 {{ skippedCount }} 个</span>
      </div>
    </div>

    <!-- 问答对列表 -->
    <div class="content-card">
      <div class="card-title">生成结果（共 {{ qaList.length }} 条）</div>
      <el-table :data="qaList" stripe max-height="500">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="qa-expand">
              <p><strong>问题：</strong>{{ row.question }}</p>
              <p><strong>答案：</strong>{{ row.answer }}</p>
              <p><strong>来源切片：</strong>{{ row.chunk }}</p>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="question" label="问题" show-overflow-tooltip />
        <el-table-column prop="answer" label="答案" show-overflow-tooltip />
        <el-table-column prop="source" label="来源" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ row.source }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === '成功' ? 'success' : row.status === '失败' ? 'danger' : 'warning'" size="small">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'

const generateMode = ref('local')
const generating = ref(false)
const progress = ref(0)
const generatedCount = ref(0)
const failedCount = ref(2)
const skippedCount = ref(3)

const modeDescriptions: Record<string, string> = {
  local: '仅基于当前文本切片生成事实型问答，答案直接引用切片原文',
  enhanced: '引入前后相邻切片作为上下文增强信息，降低语义片面性',
  fulltext: '以文档全文作为上下文生成摘要型、推理型问答',
  all: '同时生成三种来源的问答对',
}

const params = reactive({
  model: 'qwen2-7b',
  temperature: 70,
  concurrency: 5,
  contextWindow: 2,
})

const qaList = ref([
  { id: 1, question: '电力采购招标的方式有哪些？', answer: '电力采购招标分为公开招标和邀请招标两种方式。公开招标是以招标公告方式邀请不特定组织投标；邀请招标是以投标邀请书方式邀请特定组织投标。', source: '局部', status: '成功', chunk: '切片#3' },
  { id: 2, question: '招标文件应包含哪些内容？', answer: '招标文件应包括技术要求、资格审查标准、投标报价要求和评标标准等实质性要求，以及拟签订合同的主要条款。', source: '局部', status: '成功', chunk: '切片#4' },
  { id: 3, question: '合同金额的审批流程是什么？', answer: '合同金额需经部门负责人初审，财务部复核，最终由分管领导审批。金额超过100万的需提交总经理办公会审议。', source: '增强', status: '成功', chunk: '切片#7' },
  { id: 4, question: '该文档的核心内容是什么？', answer: '该文档主要规定了公司电力采购招标的管理办法，涵盖招标方式、招标文件编制、评标流程及合同签订等关键环节。', source: '全文', status: '成功', chunk: '全文摘要' },
  { id: 5, question: '安全生产的基本要求？', answer: '', source: '局部', status: '失败', chunk: '切片#12' },
])

const startGenerate = () => {
  generating.value = true
  progress.value = 0
  const timer = setInterval(() => {
    progress.value += 10
    generatedCount.value = Math.floor(progress.value / 10) * 12
    if (progress.value >= 100) {
      clearInterval(timer)
      generating.value = false
    }
  }, 500)
}
</script>

<style lang="scss" scoped>
.mode-desc {
  margin-top: 8px;
}

.progress-info {
  margin-top: 12px;
  display: flex;
  gap: 24px;
  font-size: 13px;
  color: #909399;
}

.qa-expand {
  padding: 12px 20px;
  line-height: 1.8;

  p {
    margin-bottom: 8px;
  }
}
</style>
