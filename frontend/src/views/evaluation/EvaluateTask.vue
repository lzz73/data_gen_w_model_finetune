<template>
  <div class="page-container">
    <PageHeader title="评估任务">
      <el-button type="primary" @click="showCreateDialog = true">
        <el-icon><Plus /></el-icon>创建评估
      </el-button>
    </PageHeader>

    <!-- 评估任务列表 -->
    <div class="content-card">
      <div class="card-title">评估任务列表</div>
      <el-table :data="evalTasks" stripe v-loading="loading">
        <el-table-column prop="name" label="任务名称" />
        <el-table-column label="模型" show-overflow-tooltip>
          <template #default="{ row }">{{ row.config?.base_model || row.model }}</template>
        </el-table-column>
        <el-table-column label="数据集">
          <template #default="{ row }">{{ row.config?.dataset }}</template>
        </el-table-column>
        <el-table-column label="指标" width="160">
          <template #default="{ row }">{{ row.config?.metrics || 'BLEU, ROUGE' }}</template>
        </el-table-column>
        <el-table-column prop="score" label="得分" width="100">
          <template #default="{ row }">
            <el-text v-if="row.score !== null && row.score !== undefined" type="danger" size="large" tag="b">{{ row.score }}</el-text>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="220">
          <template #default="{ row }">
            <div v-if="row.status === 'running'">
              <el-progress :percentage="row.progress || 0" :stroke-width="8" />
              <span v-if="row.eta" style="font-size:11px;color:#909399">预计 {{ row.eta }}</span>
            </div>
            <el-tooltip v-else-if="row.status === 'failed' && row.error" :content="row.error" placement="top">
              <el-tag type="danger" size="small">失败 <el-icon><Warning /></el-icon></el-tag>
            </el-tooltip>
            <el-tag v-else :type="row.status === 'completed' ? 'success' : 'info'" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170" />
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button v-if="row.status === 'completed'" link type="primary" size="small" @click="$router.push(`/evaluation/report?taskId=${row.task_id}`)">查看报告</el-button>
            <el-popconfirm title="确定删除此评估任务？" @confirm="deleteEval(row.task_id)">
              <template #reference>
                <el-button link type="danger" size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 创建评估对话框 -->
    <el-dialog v-model="showCreateDialog" title="创建评估任务" width="550px">
      <el-form :model="evalForm" label-width="100px">
        <el-divider content-position="left">模型 & 数据</el-divider>
        <el-form-item label="评估模型">
          <el-select v-model="evalForm.model" filterable placeholder="选择模型" style="width:100%">
            <el-option-group label="── 本地 ──">
              <el-option v-for="m in availableModels.local" :key="m.path" :label="m.name" :value="m.path" />
            </el-option-group>
            <el-option-group label="── 已合并 ──">
              <el-option v-for="m in availableModels.merged" :key="m.path" :label="m.name" :value="m.path" />
            </el-option-group>
          </el-select>
        </el-form-item>
        <el-form-item label="测试数据集">
          <el-select v-model="evalForm.dataset" placeholder="选择数据集" style="width:100%">
            <el-option v-for="ds in datasets" :key="ds.name" :label="`${ds.name} (${ds.samples}条)`" :value="ds.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="对话模板">
          <el-select v-model="evalForm.template" style="width:100%">
            <el-option label="qwen" value="qwen" />
            <el-option label="default" value="default" />
            <el-option label="llama3" value="llama3" />
            <el-option label="deepseek" value="deepseek" />
            <el-option label="chatglm3" value="chatglm3" />
            <el-option label="baichuan2" value="baichuan2" />
            <el-option label="mistral" value="mistral" />
          </el-select>
        </el-form-item>
        <el-form-item label="最大样本数">
          <el-input-number v-model="evalForm.max_samples" :min="10" :max="10000" :step="50" />
        </el-form-item>

        <el-divider content-position="left">生成参数</el-divider>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="批大小">
              <el-input-number v-model="evalForm.batch_size" :min="1" :max="16" size="small" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="Max Tokens">
              <el-input-number v-model="evalForm.max_tokens" :min="64" :max="4096" :step="64" size="small" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="Temperature">
          <el-slider v-model="evalForm.temperature" :min="0" :max="200" :step="5" show-input />
        </el-form-item>
        <el-form-item label="Top-p">
          <el-slider v-model="evalForm.topP" :min="0" :max="100" :step="5" show-input />
        </el-form-item>

        <el-divider content-position="left">LLM 评审（可选）</el-divider>
        <el-form-item label="启用LLM评审" style="white-space: nowrap;">
          <el-switch v-model="evalForm.use_judge" />
        </el-form-item>
        <template v-if="evalForm.use_judge">
          <el-form-item label="API 地址">
            <el-input v-model="evalForm.judge_api" placeholder="https://api.openai.com/v1" clearable />
          </el-form-item>
          <el-form-item label="API Key">
            <el-input v-model="evalForm.judge_key" type="password" show-password placeholder="sk-xxx" clearable />
          </el-form-item>
          <el-form-item label="评审模型">
            <el-input v-model="evalForm.judge_model" placeholder="gpt-4o-mini" clearable />
          </el-form-item>
        </template>

        <el-divider content-position="left">评估指标</el-divider>
        <el-form-item label="指标选择">
          <el-checkbox-group v-model="evalForm.metrics">
            <el-checkbox label="bleu" value="bleu">BLEU</el-checkbox>
            <el-checkbox label="rouge_1" value="rouge_1">ROUGE-1</el-checkbox>
            <el-checkbox label="rouge_2" value="rouge_2">ROUGE-2</el-checkbox>
            <el-checkbox label="rouge_l" value="rouge_l">ROUGE-L</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="createEval">创建并运行</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import PageHeader from '@/components/common/PageHeader.vue'
import { evaluationApi } from '@/api/evaluation'
import { trainingApi, type TrainingDatasetItem } from '@/api/training'

const loading = ref(false)
const creating = ref(false)
const showCreateDialog = ref(false)
const evalTasks = ref<any[]>([])
const datasets = ref<TrainingDatasetItem[]>([])
const availableModels = ref<{ local: any[]; merged: any[] }>({ local: [], merged: [] })

const evalForm = reactive({
  model: '',
  dataset: '',
  template: 'qwen',
  cutoff_len: 1024,
  batch_size: 8,
  metrics: ['bleu', 'rouge_1', 'rouge_2', 'rouge_l'],
  use_judge: false,
  judge_api: localStorage.getItem('eval_judge_api') || '',
  judge_key: localStorage.getItem('eval_judge_key') || '',
  judge_model: localStorage.getItem('eval_judge_model') || 'gpt-4o-mini',
  temperature: 20,
  topP: 90,
  max_tokens: 256,
  max_samples: 200,
})

const statusLabel = (s: string) => ({ pending: '排队中', running: '评估中', completed: '已完成', failed: '失败' } as any)[s] || s

const loadEvalTasks = async () => {
  try {
    evalTasks.value = await evaluationApi.listTasks()
  } catch (e) { console.error(e) }
}

const deleteEval = async (taskId: string) => {
  try {
    await evaluationApi.deleteTask(taskId)
    ElMessage.success('已删除')
    loadEvalTasks()
  } catch (e: any) { ElMessage.error(e.message) }
}

const createEval = async () => {
  if (!evalForm.model) { ElMessage.warning('请选择模型'); return }
  if (!evalForm.dataset) { ElMessage.warning('请选择数据集'); return }
  creating.value = true
  try {
    await evaluationApi.runEval(evalForm)
    ElMessage.success('评估任务已创建')
    showCreateDialog.value = false
    loadEvalTasks()
  } catch (e: any) { ElMessage.error(e.message) }
  finally { creating.value = false }
}

let pollTimer: any = null

// 评审配置自动保存
watch(() => evalForm.judge_api, v => { if (v) localStorage.setItem('eval_judge_api', v) })
watch(() => evalForm.judge_key, v => { if (v) localStorage.setItem('eval_judge_key', v) })
watch(() => evalForm.judge_model, v => { if (v) localStorage.setItem('eval_judge_model', v) })

onMounted(async () => {
  const modelsData = await trainingApi.listVerifyModels()
  if (modelsData) availableModels.value = modelsData
  datasets.value = await trainingApi.listTrainingDatasets()
  loadEvalTasks()
  // 仅当有运行中任务时才每5秒刷新
  pollTimer = setInterval(() => {
    if (evalTasks.value.some(t => t.status === 'running')) loadEvalTasks()
  }, 5000)
})
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
</script>
