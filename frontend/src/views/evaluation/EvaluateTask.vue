<template>
  <div class="page-container">
    <PageHeader title="评估任务">
      <el-button type="primary" @click="showCreateDialog = true" :disabled="!projectStore.hasProject">
        <el-icon><Plus /></el-icon>创建评估
      </el-button>
    </PageHeader>

    <EmptyState
      v-if="!projectStore.hasProject"
      description="请先在首页选择一个项目"
      action-text="前往首页"
      @action="$router.push('/')"
    />

    <div v-else class="content-card">
      <el-table :data="evalTasks" stripe v-loading="loadingTasks">
        <el-table-column prop="name" label="任务名称" />
        <el-table-column label="评估模型" width="160">
          <template #default="{ row }">
            {{ row.model_name || (row.eval_config?.model_name || '-') }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="taskStatusTag(row.status)" size="small">
              {{ taskStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="100">
          <template #default="{ row }">
            {{ row.progress || 0 }}%
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'completed'"
              link type="primary" size="small"
              @click="$router.push('/evaluation/report')"
            >
              查看报告
            </el-button>
            <el-button
              v-if="row.status === 'pending' || row.status === 'created'"
              link type="primary" size="small"
              :loading="startingTaskId === row.id"
              @click="handleStartTask(row)"
            >
              启动
            </el-button>
            <el-button
              v-if="row.status === 'running'"
              link type="warning" size="small"
              @click="handleStopTask(row)"
            >
              停止
            </el-button>
            <el-button
              link type="danger" size="small"
              @click="handleDeleteTask(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <EmptyState
        v-if="!loadingTasks && evalTasks.length === 0"
        description="暂无评估任务"
        action-text="创建评估"
        @action="showCreateDialog = true"
      />
    </div>

    <!-- 创建评估对话框 -->
    <el-dialog v-model="showCreateDialog" title="创建评估任务" width="550px">
      <el-form :model="evalForm" label-width="100px">
        <el-form-item label="任务名称">
          <el-input v-model="evalForm.name" placeholder="请输入任务名称" />
        </el-form-item>
        <el-form-item label="评审模型">
          <el-select v-model="evalForm.judge_model_id" placeholder="选择评审模型" style="width: 100%">
            <el-option
              v-for="m in chatModels"
              :key="m.id"
              :label="m.model_name"
              :value="m.id"
            />
            <template #empty>
              <div style="padding: 10px; color: #909399;">暂无可用模型</div>
            </template>
          </el-select>
        </el-form-item>
        <el-form-item label="测试数据集">
          <el-select v-model="evalForm.dataset_id" placeholder="选择数据集" style="width: 100%">
            <el-option
              v-for="d in datasets"
              :key="d.id"
              :label="`${d.name} (${d.question_count || 0}条)`"
              :value="d.id"
            />
            <template #empty>
              <div style="padding: 10px; color: #909399;">暂无数据集</div>
            </template>
          </el-select>
        </el-form-item>
        <el-form-item label="人工复核">
          <el-switch v-model="evalForm.human_review" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
import { useProjectStore } from '@/stores/project'
import { evalApi, modelApi, datasetApi } from '@/api'
import { formatDateTime } from '@/composables/useFormatters'
import { ElMessage } from 'element-plus'
import PageHeader from '@/components/common/PageHeader.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import type { Model, Dataset } from '@/types'

const projectStore = useProjectStore()
const loadingTasks = ref(false)
const creating = ref(false)
const startingTaskId = ref<string | null>(null)
const showCreateDialog = ref(false)
const evalTasks = ref<any[]>([])
const chatModels = ref<Model[]>([])
const datasets = ref<Dataset[]>([])

const evalForm = reactive({
  name: '',
  judge_model_id: '',
  dataset_id: '',
  human_review: false,
})

const fetchTasks = async () => {
  if (!projectStore.currentProjectId) return
  loadingTasks.value = true
  try {
    const res = await evalApi.listTasks(projectStore.currentProjectId)
    if (Array.isArray(res)) {
      evalTasks.value = res
    } else if (res && typeof res === 'object' && 'items' in res) {
      evalTasks.value = (res as any).items || []
    } else {
      evalTasks.value = []
    }
  } catch (e) {
    evalTasks.value = []
  } finally {
    loadingTasks.value = false
  }
}

const fetchModels = async () => {
  try {
    const res = await modelApi.list()
    const allModels = Array.isArray(res) ? res : []
    chatModels.value = allModels.filter((m: Model) => m.model_type === 'chat')
  } catch (e) {
    chatModels.value = []
  }
}

const fetchDatasets = async () => {
  if (!projectStore.currentProjectId) return
  try {
    const res = await datasetApi.list(projectStore.currentProjectId)
    datasets.value = Array.isArray(res) ? res : []
  } catch (e) {
    datasets.value = []
  }
}

const handleCreate = async () => {
  if (!projectStore.currentProjectId) return
  creating.value = true
  try {
    await evalApi.createTask(projectStore.currentProjectId, evalForm)
    ElMessage.success('评估任务创建成功')
    showCreateDialog.value = false
    await fetchTasks()
  } catch (error: any) {
    ElMessage.error(error?.message || '创建失败')
  } finally {
    creating.value = false
  }
}

const handleStartTask = async (row: any) => {
  if (!projectStore.currentProjectId) return
  startingTaskId.value = row.id
  try {
    await evalApi.startTask(projectStore.currentProjectId, row.id)
    ElMessage.info('评估任务已启动')
    await fetchTasks()
  } catch (error: any) {
    ElMessage.error(error?.message || '启动失败')
  } finally {
    startingTaskId.value = null
  }
}

const handleStopTask = async (row: any) => {
  if (!projectStore.currentProjectId) return
  try {
    await evalApi.stopTask(projectStore.currentProjectId, row.id)
    ElMessage.info('评估任务已停止')
    await fetchTasks()
  } catch (error: any) {
    ElMessage.error(error?.message || '停止失败')
  }
}

const handleDeleteTask = async (row: any) => {
  if (!projectStore.currentProjectId) return
  try {
    await evalApi.deleteTask(projectStore.currentProjectId, row.id)
    ElMessage.success('删除成功')
    await fetchTasks()
  } catch (error: any) {
    ElMessage.error(error?.message || '删除失败')
  }
}

const taskStatusTag = (status: string) => {
  const map: Record<string, string> = { completed: 'success', running: 'primary', pending: 'info', created: 'info', failed: 'danger' }
  return map[status] || 'info'
}

const taskStatusLabel = (status: string) => {
  const map: Record<string, string> = { completed: '已完成', running: '评估中', pending: '待评估', created: '待启动', failed: '失败' }
  return map[status] || status
}

watch(() => projectStore.currentProjectId, (newId) => {
  if (newId) {
    fetchTasks()
    fetchModels()
    fetchDatasets()
  }
})

onMounted(() => {
  if (projectStore.currentProjectId) {
    fetchTasks()
    fetchModels()
    fetchDatasets()
  }
})
</script>
