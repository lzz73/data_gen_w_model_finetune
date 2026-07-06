<template>
  <div class="page-container">
    <PageHeader title="数据质量校验">
      <el-button
        type="primary"
        :loading="validating"
        @click="runValidation"
        :disabled="!projectStore.hasProject || !selectedBatchId"
      >
        <el-icon><CircleCheck /></el-icon>
        {{ validating ? '校验中...' : '执行校验' }}
      </el-button>
    </PageHeader>

    <EmptyState
      v-if="!projectStore.hasProject"
      description="请先在首页选择一个项目"
      action-text="前往首页"
      @action="$router.push('/')"
    />

    <template v-else>
      <!-- 选择批次 -->
      <div class="content-card">
        <div class="card-title" style="display: flex; align-items: center; justify-content: space-between;">
          <span>选择校验批次</span>
          <div style="display: flex; gap: 8px; align-items: center;">
            <el-select
              v-model="selectedBatchId"
              placeholder="请选择批次"
              size="small"
              style="width: 280px;"
              :loading="loadingBatches"
              @change="onBatchChange"
            >
              <el-option
                v-for="b in batches"
                :key="b.batch_id"
                :label="`${b.label} · ${b.total_count}条 · ${formatTime(b.created_at)}`"
                :value="b.batch_id"
              />
            </el-select>
            <el-button
              v-if="selectedBatchId"
              size="small"
              type="danger"
              plain
              @click="handleDeleteSelectedBatch"
            >
              删除批次
            </el-button>
          </div>
        </div>
        <el-alert
          type="info"
          :closable="false"
          style="margin-bottom: 12px;"
        >
          <template #title>
            每次问答对生成或人工录入会创建一个批次，校验时需要选择对应的批次。如果看不到批次，请先生成问答对或录入数据。
          </template>
        </el-alert>

        <!-- 选中批次的信息摘要 -->
        <div v-if="selectedBatchInfo" class="batch-summary">
          <el-tag size="small" :type="batchTagType(selectedBatchInfo.source)">{{ selectedBatchInfo.label }}</el-tag>
          <span class="batch-summary-item">问答对 <strong>{{ selectedBatchInfo.total_count }}</strong></span>
          <span class="batch-summary-item">成功 <strong style="color: #67c23a;">{{ selectedBatchInfo.completed_count }}</strong></span>
          <span class="batch-summary-item">失败 <strong style="color: #f56c6c;">{{ selectedBatchInfo.failed_count }}</strong></span>
          <el-tag v-if="selectedBatchInfo.task_status === 'completed'" type="success" size="small">已校验</el-tag>
          <el-tag v-else-if="selectedBatchInfo.task_status === 'running'" type="warning" size="small">校验中</el-tag>
          <el-tag v-else-if="selectedBatchInfo.task_status === 'failed'" type="danger" size="small">失败</el-tag>
        </div>

        <el-empty
          v-if="!loadingBatches && batches.length === 0"
          description="暂无问答对批次，请先在问答生成页面生成问答对，或在数据源接入页面人工录入"
          :image-size="80"
        >
          <el-button type="primary" size="small" @click="$router.push('/data-governance/qa-generate')">
            前往生成
          </el-button>
        </el-empty>
      </div>

      <!-- 语义校验提示 -->
      <div class="content-card" style="margin-top: 16px;">
        <div class="card-title" style="display: flex; align-items: center; justify-content: space-between;">
          <span>校验能力</span>
        </div>
        <div class="validation-capabilities">
          <div class="capability-item">
            <el-icon :size="18" color="#67c23a"><CircleCheck /></el-icon>
            <div>
              <div class="capability-name">基础校验</div>
              <div class="capability-desc">检查答案是否存在且长度足够（≥20字）</div>
            </div>
          </div>
          <div class="capability-item">
            <el-icon :size="18" color="#67c23a"><CircleCheck /></el-icon>
            <div>
              <div class="capability-name">格式校验</div>
              <div class="capability-desc">检测乱码、截断、未闭合括号/引号、重复文本等格式异常</div>
            </div>
          </div>
          <div class="capability-item">
            <template v-if="hasEmbeddingModel">
              <el-icon :size="18" color="#67c23a"><CircleCheck /></el-icon>
            </template>
            <template v-else>
              <el-icon :size="18" color="#e6a23c"><Warning /></el-icon>
            </template>
            <div>
              <div class="capability-name">
                语义校验
                <el-tag v-if="!hasEmbeddingModel" type="warning" size="small" style="margin-left: 6px;">未启用</el-tag>
                <el-tag v-else type="success" size="small" style="margin-left: 6px;">已启用</el-tag>
              </div>
              <div class="capability-desc">
                <template v-if="hasEmbeddingModel">
                  使用 Embedding 模型（{{ embeddingModelName }}）计算答案与原切片的语义相似度，相似度 &lt; 0.5 判定为疑似幻觉
                </template>
                <template v-else>
                  语义校验需要配置 Embedding 模型，用于计算答案与原文的语义相似度，检测"幻觉"（答案与原文不相关）。
                  <el-link type="primary" @click="$router.push('/data-governance/model-config')" style="font-size: 12px;">
                    前往配置 Embedding 模型 →
                  </el-link>
                </template>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 校验进度 -->
      <div v-if="validating" class="content-card" style="margin-top: 16px;">
        <el-progress :percentage="progress" :status="progress === 100 ? 'success' : ''" />
        <div style="margin-top: 8px; font-size: 13px; color: #909399;">
          正在执行三层质量校验（基础校验 → 语义校验 → 格式校验）...
        </div>
      </div>

      <!-- 校验统计 -->
      <div v-if="questions.length > 0" class="stat-row" style="margin-top: 16px;">
        <StatCard icon="Document" label="总问答对" :value="stats.total" color="#409eff" />
        <StatCard icon="CircleCheck" label="通过" :value="stats.passed" color="#67c23a" />
        <StatCard icon="Warning" label="疑似幻觉" :value="stats.hallucination" color="#e6a23c" />
        <StatCard icon="DocumentDelete" label="格式异常" :value="stats.formatError" color="#f5a623" />
        <StatCard icon="CircleClose" label="失败" :value="stats.failed" color="#f56c6c" />
      </div>

      <!-- 校验结果列表 -->
      <div v-if="questions.length > 0" class="content-card" style="margin-top: 16px;">
        <div class="card-title" style="display: flex; align-items: center; justify-content: space-between;">
          <span>校验结果</span>
          <el-input
            v-model="searchKeyword"
            placeholder="搜索问答内容..."
            size="small"
            style="width: 200px;"
            clearable
          />
        </div>
        <div class="qa-validate-list" v-loading="loadingQa">
          <div
            v-for="(row, i) in filteredQuestions"
            :key="row.id || i"
            class="qa-validate-item"
          >
            <div class="qa-validate-header">
              <div style="display: flex; align-items: center; gap: 8px;">
                <el-tag size="small" type="primary">Q{{ i + 1 }}</el-tag>
                <el-tag
                  size="small"
                  :type="basicCheck(row) === '通过' ? 'success' : 'danger'"
                >
                  基础: {{ basicCheck(row) }}
                </el-tag>
                <el-tag
                  v-if="row.quality_score != null"
                  size="small"
                  :type="row.quality_score < 0.5 ? 'warning' : 'success'"
                >
                  语义: {{ row.quality_score < 0.5 ? '疑似幻觉' : '通过' }}
                </el-tag>
                <el-tag v-else size="small" type="info">语义: 未校验</el-tag>
                <el-tag
                  size="small"
                  :type="formatCheck(row) === '通过' ? 'success' : 'danger'"
                >
                  格式: {{ formatCheck(row) }}
                </el-tag>
              </div>
              <el-button
                v-if="row.answer_status === 'failed' || (row.quality_score != null && row.quality_score < 0.5)"
                link type="primary" size="small"
                :loading="regeneratingId === row.id"
                @click="handleRegenerate(row)"
              >
                重新生成
              </el-button>
            </div>
            <div class="qa-validate-question">{{ row.content }}</div>
            <div class="qa-validate-answer">
              <span class="qa-answer-label">答：</span>{{ row.answer || '（无答案）' }}
            </div>
            <div v-if="row.answer_error" class="qa-validate-error">
              <el-icon :size="12" color="#f56c6c"><WarningFilled /></el-icon>
              {{ row.answer_error }}
            </div>
          </div>
          <el-empty v-if="filteredQuestions.length === 0 && questions.length > 0" description="没有匹配的结果" :image-size="60" />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useProjectStore } from '@/stores/project'
import { questionApi } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { WarningFilled, Warning } from '@element-plus/icons-vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatCard from '@/components/common/StatCard.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import type { Question } from '@/types'

const projectStore = useProjectStore()

// 批次相关
const loadingBatches = ref(false)
const batches = ref<any[]>([])
const selectedBatchId = ref<string | null>(null)

// Embedding 模型状态
const hasEmbeddingModel = ref(false)
const embeddingModelName = ref('')

// 校验相关
const loadingQa = ref(false)
const validating = ref(false)
const progress = ref(0)
const questions = ref<Question[]>([])
const regeneratingId = ref<string | null>(null)
const searchKeyword = ref('')
let pollTimer: ReturnType<typeof setInterval> | null = null

// 统计
const stats = computed(() => {
  const total = questions.value.length
  const hallucination = questions.value.filter(q =>
    q.quality_score != null && q.quality_score < 0.5
  ).length
  const formatError = questions.value.filter(q =>
    q.answer_error && q.answer_error.includes('格式异常')
  ).length
  const failed = questions.value.filter(q =>
    q.answer_status === 'failed' && !(q.quality_score != null && q.quality_score < 0.5) && !(q.answer_error && q.answer_error.includes('格式异常'))
  ).length
  const passed = total - hallucination - formatError - failed
  return { total, passed, hallucination, formatError, failed }
})

// 过滤
const filteredQuestions = computed(() => {
  if (!searchKeyword.value.trim()) return questions.value
  const keyword = searchKeyword.value.trim().toLowerCase()
  return questions.value.filter(q =>
    q.content?.toLowerCase().includes(keyword) ||
    q.answer?.toLowerCase().includes(keyword)
  )
})

// 校验判断
const basicCheck = (row: Question) => {
  const minLen = (row.source || '').includes('structured') ? 2 : 20
  if (!row.answer || row.answer.length < minLen) return '失败'
  return '通过'
}

const formatCheck = (row: Question) => {
  if (row.answer_error && row.answer_error.includes('格式异常')) return '异常'
  return '通过'
}

// 批次标签颜色
const batchTagType = (source: string) => {
  const map: Record<string, string> = {
    manual: 'info',
    structured_template: '',
    structured_llm: 'warning',
    generated_qa: 'success',
  }
  return map[source] || 'info'
}

// 当前选中批次的详情
const selectedBatchInfo = computed(() => {
  if (!selectedBatchId.value) return null
  return batches.value.find(b => b.batch_id === selectedBatchId.value) || null
})

// 下拉选择批次
const onBatchChange = (batchId: string) => {
  selectedBatchId.value = batchId
}

// 删除当前选中批次
const handleDeleteSelectedBatch = async () => {
  if (!selectedBatchId.value || !selectedBatchInfo.value) return
  const info = selectedBatchInfo.value
  try {
    await ElMessageBox.confirm(
      `确定删除此批次？该批次下的 ${info.total_count} 条问答对将被永久删除。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
    if (!projectStore.currentProjectId) return
    await questionApi.deleteBatch(projectStore.currentProjectId, selectedBatchId.value)
    ElMessage.success('批次已删除')
    selectedBatchId.value = null
    questions.value = []
    await fetchBatches()
  } catch {
    // 用户取消
  }
}

// 格式化时间
const formatTime = (t: string | null) => {
  if (!t) return ''
  // 尝试解析 ISO 格式
  try {
    const d = new Date(t)
    if (isNaN(d.getTime())) return t.slice(0, 19)
    const month = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    const hour = String(d.getHours()).padStart(2, '0')
    const min = String(d.getMinutes()).padStart(2, '0')
    return `${month}-${day} ${hour}:${min}`
  } catch {
    return t.slice(0, 16)
  }
}

// 获取批次列表
const fetchBatches = async () => {
  if (!projectStore.currentProjectId) return
  loadingBatches.value = true
  try {
    const res = await questionApi.listBatches(projectStore.currentProjectId)
    const data = (res as any)?.batches || res || []
    batches.value = Array.isArray(data) ? data : []
  } catch {
    batches.value = []
  } finally {
    loadingBatches.value = false
  }
}

// 检查 Embedding 模型
const checkEmbedding = async () => {
  if (!projectStore.currentProjectId) return
  try {
    const res = await questionApi.checkEmbeddingModel(projectStore.currentProjectId)
    hasEmbeddingModel.value = (res as any)?.has_embedding ?? false
    embeddingModelName.value = (res as any)?.model_name || ''
  } catch {
    hasEmbeddingModel.value = false
    embeddingModelName.value = ''
  }
}

// 获取批次问答对
const fetchQuestions = async () => {
  if (!projectStore.currentProjectId || !selectedBatchId.value) return
  loadingQa.value = true
  try {
    const res = await questionApi.list(projectStore.currentProjectId, {
      batch_id: selectedBatchId.value,
      page_size: 100,
    })
    if (Array.isArray(res)) {
      questions.value = res
    } else if (res && typeof res === 'object' && 'items' in res) {
      questions.value = (res as any).items || []
    } else {
      questions.value = []
    }
  } catch {
    questions.value = []
  } finally {
    loadingQa.value = false
  }
}

// 执行校验
const runValidation = async () => {
  if (!projectStore.currentProjectId || !selectedBatchId.value) return
  validating.value = true
  progress.value = 0
  try {
    await questionApi.validate(projectStore.currentProjectId, {
      batch_id: selectedBatchId.value,
    })
    ElMessage.info('质量校验已启动')
    startPolling()
  } catch (error: any) {
    ElMessage.error(error?.message || '启动校验失败')
    validating.value = false
  }
}

// 轮询校验进度
const startPolling = () => {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    if (!projectStore.currentProjectId) return
    try {
      const task = await questionApi.latestQATask(projectStore.currentProjectId)
      if (task && typeof task === 'object') {
        const t = task as any
        progress.value = t.progress || 0
        if (t.status === 'completed' || t.status === 'failed') {
          stopPolling()
          validating.value = false
          if (t.status === 'completed') {
            ElMessage.success('质量校验完成')
          } else {
            ElMessage.error('质量校验失败')
          }
          await fetchQuestions()
        }
      }
    } catch {
      // continue polling
    }
  }, 3000)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// 重新生成答案
const handleRegenerate = async (row: Question) => {
  if (!projectStore.currentProjectId) return
  regeneratingId.value = row.id
  try {
    const res = await questionApi.regenerate(projectStore.currentProjectId, row.id)
    const data = (res as any)?.data || res
    row.answer = data.answer || row.answer
    row.answer_status = data.answer_status || row.answer_status
    row.answer_error = data.answer_error || null
    ElMessage.success('答案重新生成完成')
  } catch (error: any) {
    ElMessage.error(error?.message || '重新生成失败')
  } finally {
    regeneratingId.value = null
  }
}

// 监听批次选择变化 → 加载问答对
watch(selectedBatchId, (newId) => {
  if (newId) {
    fetchQuestions()
  } else {
    questions.value = []
  }
})

watch(() => projectStore.currentProjectId, (newId) => {
  if (newId) {
    selectedBatchId.value = null
    questions.value = []
    fetchBatches()
    checkEmbedding()
  }
})

onMounted(() => {
  if (projectStore.currentProjectId) {
    fetchBatches()
    checkEmbedding()
  }
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style lang="scss" scoped>
.batch-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: #f5f7fa;
  border-radius: 8px;
  font-size: 13px;
  color: #606266;

  .batch-summary-item {
    color: #909399;

    strong {
      color: #303133;
    }
  }
}

.validation-capabilities {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.capability-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  background: #fafbfc;
  transition: background 0.2s;

  &:hover {
    background: #f0f5ff;
  }
}

.capability-name {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 2px;
}

.capability-desc {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

.qa-validate-list {
  max-height: 600px;
  overflow-y: auto;
  padding-top: 4px;
}

.qa-validate-item {
  margin-bottom: 12px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 14px;
  transition: box-shadow 0.2s;

  &:hover {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  }
}

.qa-validate-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.qa-validate-question {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  line-height: 1.6;
  margin-bottom: 8px;
  padding: 8px 10px;
  background: #f0f5ff;
  border-radius: 6px;
  border-left: 3px solid #409eff;
}

.qa-validate-answer {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
  padding: 8px 10px;
  background: #f5f7fa;
  border-radius: 6px;

  .qa-answer-label {
    font-weight: 500;
    color: #303133;
  }
}

.qa-validate-error {
  margin-top: 8px;
  font-size: 12px;
  color: #f56c6c;
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
