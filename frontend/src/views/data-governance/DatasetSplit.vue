<template>
  <div class="page-container">
    <PageHeader title="数据集划分">
      <el-button type="primary" @click="exportDataset" :disabled="!projectStore.hasProject || exporting">
        <el-icon><Download /></el-icon>导出数据集
      </el-button>
    </PageHeader>

    <EmptyState
      v-if="!projectStore.hasProject"
      description="请先在首页选择一个项目"
      action-text="前往首页"
      @action="$router.push('/')"
    />

    <el-row v-else :gutter="16">
      <!-- 划分配置 -->
      <el-col :span="12">
        <div class="content-card">
          <div class="card-title">划分配置</div>
          <el-form :model="splitConfig" label-width="120px">
            <el-form-item label="选择批次">
              <el-select
                v-model="splitConfig.batchId"
                placeholder="选择要划分的问答批次"
                style="width: 100%;"
                @change="onBatchSelect"
              >
                <el-option
                  v-for="b in batches"
                  :key="b.batch_id"
                  :label="`${b.label} · ${b.total_count}条 · ${formatBatchTime(b.created_at)}`"
                  :value="b.batch_id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="数据集名称">
              <el-input v-model="splitConfig.name" placeholder="选择批次后自动填充，也可自定义" />
            </el-form-item>
            <el-form-item label="划分方式">
              <el-radio-group v-model="splitConfig.strategy">
                <el-radio value="random">随机划分</el-radio>
                <el-radio value="file">按文件划分</el-radio>
              </el-radio-group>
              <div style="margin-top: 4px; color: #909399; font-size: 12px;">
                {{ splitConfig.strategy === 'random'
                  ? '所有问答对混在一起随机分配，同一个文件的问答可能分散到不同集合'
                  : '同一个文件的问答对全部归到同一个集合，避免模型"见过"训练数据又考到它'
                }}
              </div>
            </el-form-item>
            <el-form-item label="随机种子">
              <el-input-number v-model="splitConfig.seed" :min="1" :max="9999" />
              <span style="margin-left: 8px; color: #909399; font-size: 12px;">相同种子可复现划分结果</span>
            </el-form-item>
            <el-form-item label="文件格式" style="margin-bottom: 24px;">
              <el-radio-group v-model="splitConfig.fileFormat">
                <el-radio value="jsonl">JSONL</el-radio>
                <el-radio value="json">JSON</el-radio>
                <el-radio value="excel">Excel</el-radio>
              </el-radio-group>
              <div style="color: #909399; font-size: 12px; margin-top: 4px; min-height: 32px;">
                <template v-if="splitConfig.fileFormat === 'jsonl'">每行一条问答对，训练框架常用格式</template>
                <template v-else-if="splitConfig.fileFormat === 'json'">JSON 数组格式，方便查看和二次处理</template>
                <template v-else-if="splitConfig.fileFormat === 'excel'">Excel 表格格式，方便人工审阅编辑</template>
              </div>
            </el-form-item>
            <el-form-item label="数据格式" style="margin-bottom: 36px;">
              <el-radio-group v-model="splitConfig.dataFormat" style="display: inline-flex; gap: 8px;">
                <el-radio value="alpaca" style="display: inline-flex; align-items: flex-start;">
                  <div>
                    <div>Alpaca</div>
                    <div :style="{ color: '#909399', fontSize: '12px', lineHeight: '1.3', marginTop: '2px', visibility: splitConfig.dataFormat === 'alpaca' ? 'visible' : 'hidden', whiteSpace: 'normal', maxWidth: '100px' }">instruction/input/output 三字段格式，最通用</div>
                  </div>
                </el-radio>
                <el-radio value="sharegpt" style="display: inline-flex; align-items: flex-start;">
                  <div>
                    <div>ShareGPT</div>
                    <div :style="{ color: '#909399', fontSize: '12px', lineHeight: '1.3', marginTop: '2px', visibility: splitConfig.dataFormat === 'sharegpt' ? 'visible' : 'hidden', whiteSpace: 'normal', maxWidth: '100px' }">conversations 对话格式，多轮对话场景</div>
                  </div>
                </el-radio>
                <el-radio value="llama_factory" style="display: inline-flex; align-items: flex-start;">
                  <div>
                    <div>LLaMA Factory</div>
                    <div :style="{ color: '#909399', fontSize: '12px', lineHeight: '1.3', marginTop: '2px', visibility: splitConfig.dataFormat === 'llama_factory' ? 'visible' : 'hidden', whiteSpace: 'normal', maxWidth: '100px' }">与 Alpaca 格式相同，LLaMA Factory 专用</div>
                  </div>
                </el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="训练集比例">
              <el-slider v-model="splitConfig.trainRatio" :min="50" :max="98" :step="1" show-input />
              <div style="color: #909399; font-size: 12px; margin-top: 2px;">用于模型学习的主要数据</div>
            </el-form-item>
            <el-form-item label="验证集比例">
              <el-slider v-model="splitConfig.valRatio" :min="1" :max="25" :step="1" show-input />
              <div style="color: #909399; font-size: 12px; margin-top: 2px;">训练过程中监控模型效果，防止过拟合</div>
            </el-form-item>
            <el-form-item label="测试集比例">
              <el-slider v-model="splitConfig.testRatio" :min="1" :max="25" :step="1" show-input />
              <div style="color: #909399; font-size: 12px; margin-top: 2px;">训练结束后评估模型最终表现</div>
            </el-form-item>
            <el-form-item>
              <el-alert
                :type="totalRatio === 100 ? 'success' : 'error'"
                :title="`比例总和：${totalRatio}%${totalRatio !== 100 ? '（需等于100%）' : ''}`"
                :closable="false"
                show-icon
              />
            </el-form-item>
          </el-form>
        </div>
      </el-col>

      <!-- 划分预览 -->
      <el-col :span="12">
        <div class="content-card">
          <div class="card-title">划分预览</div>
          <div class="split-preview">
            <div class="split-bar">
              <div class="split-segment train" :style="{ width: splitConfig.trainRatio + '%' }">
                训练集 {{ splitConfig.trainRatio }}%
              </div>
              <div class="split-segment val" :style="{ width: splitConfig.valRatio + '%' }">
                验证 {{ splitConfig.valRatio }}%
              </div>
              <div class="split-segment test" :style="{ width: splitConfig.testRatio + '%' }">
                测试 {{ splitConfig.testRatio }}%
              </div>
            </div>
            <el-descriptions :column="1" border size="small" style="margin-top: 16px">
              <el-descriptions-item label="总样本数">{{ totalQuestions }}</el-descriptions-item>
              <el-descriptions-item label="训练集">{{ Math.floor(totalQuestions * splitConfig.trainRatio / 100) }} 条</el-descriptions-item>
              <el-descriptions-item label="验证集">{{ Math.floor(totalQuestions * splitConfig.valRatio / 100) }} 条</el-descriptions-item>
              <el-descriptions-item label="测试集">{{ totalQuestions - Math.floor(totalQuestions * splitConfig.trainRatio / 100) - Math.floor(totalQuestions * splitConfig.valRatio / 100) }} 条</el-descriptions-item>
            </el-descriptions>
          </div>
        </div>

        <!-- 已创建的数据集 -->
        <div class="content-card">
          <div class="card-title" style="display: flex; align-items: center; justify-content: space-between;">
            <span>已有数据集</span>
            <el-button
              type="danger"
              plain
              size="small"
              :disabled="selectedDatasetIds.length === 0"
              @click="handleBatchDelete"
            >
              批量删除（已选 {{ selectedDatasetIds.length }} 个）
            </el-button>
          </div>
          <el-table
            :data="datasets"
            stripe
            v-loading="loadingDatasets"
            @selection-change="handleDatasetSelectionChange"
          >
            <el-table-column type="selection" width="45" />
            <el-table-column prop="name" label="数据集名称" />
            <el-table-column prop="dataset_type" label="类型" width="100" />
            <el-table-column prop="question_count" label="样本数" width="80" />
            <el-table-column label="创建时间" width="180">
              <template #default="{ row }">
                {{ formatDateTime(row.created_at) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="handleExport(row)">导出</el-button>
                <el-button link type="danger" size="small" @click="handleDeleteDataset(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <EmptyState
            v-if="!loadingDatasets && datasets.length === 0"
            description="暂无数据集"
          />
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, onMounted, watch } from 'vue'
import { useProjectStore } from '@/stores/project'
import { questionApi, datasetApi } from '@/api'
import axios from 'axios'
import { formatDateTime } from '@/composables/useFormatters'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageHeader from '@/components/common/PageHeader.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import type { Dataset } from '@/types'

const projectStore = useProjectStore()

const exporting = ref(false)
const loadingDatasets = ref(false)
const totalQuestions = ref(0)
const datasets = ref<Dataset[]>([])
const selectedDatasetIds = ref<string[]>([])
const batches = ref<any[]>([])

const splitConfig = reactive({
  batchId: '',
  name: '',
  strategy: 'random',
  fileFormat: 'jsonl',
  dataFormat: 'alpaca',
  seed: 42,
  trainRatio: 90,
  valRatio: 5,
  testRatio: 5,
})

const totalRatio = computed(() => splitConfig.trainRatio + splitConfig.valRatio + splitConfig.testRatio)

const formatBatchTime = (dateStr: string | null | undefined) => {
  if (!dateStr) return ''
  try {
    const d = new Date(dateStr)
    const month = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    const hour = String(d.getHours()).padStart(2, '0')
    const min = String(d.getMinutes()).padStart(2, '0')
    return `${month}-${day} ${hour}:${min}`
  } catch {
    return ''
  }
}

const onBatchSelect = (batchId: string) => {
  const batch = batches.value.find(b => b.batch_id === batchId)
  if (batch) {
    splitConfig.name = batch.label || batch.name || `数据集_${formatBatchTime(batch.created_at)}`
    totalQuestions.value = batch.total_count || 0
  }
}

const fetchBatches = async () => {
  if (!projectStore.currentProjectId) return
  try {
    const res = await questionApi.listBatches(projectStore.currentProjectId)
    const data = (res as any)?.batches || res || []
    batches.value = Array.isArray(data) ? data : []
  } catch {
    batches.value = []
  }
}

const fetchQuestionCount = async () => {
  if (!projectStore.currentProjectId) return
  try {
    const res = await questionApi.list(projectStore.currentProjectId, { page: 1, page_size: 1 })
    if (res && typeof res === 'object' && 'total' in res) {
      totalQuestions.value = (res as any).total || 0
    }
  } catch (e) {
    totalQuestions.value = 0
  }
}

const fetchDatasets = async () => {
  if (!projectStore.currentProjectId) return
  loadingDatasets.value = true
  try {
    const res = await datasetApi.list(projectStore.currentProjectId)
    if (Array.isArray(res)) {
      datasets.value = res
    } else if (res && typeof res === 'object' && 'items' in res) {
      datasets.value = (res as any).items || []
    } else {
      datasets.value = []
    }
  } catch (e) {
    datasets.value = []
  } finally {
    loadingDatasets.value = false
  }
}

const exportDataset = async () => {
  if (!projectStore.currentProjectId) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (totalRatio.value !== 100) {
    ElMessage.error('比例总和必须等于100%')
    return
  }
  if (!splitConfig.name) {
    ElMessage.error('请先选择批次或输入数据集名称')
    return
  }
  if (!splitConfig.batchId) {
    ElMessage.error('请先选择要划分的问答批次')
    return
  }
  if (totalQuestions.value < 100) {
    ElMessage.warning('样本数不足100条，建议调整比例或关闭测试集划分')
  }

  exporting.value = true
  try {
    const createRes = await datasetApi.create(projectStore.currentProjectId, {
      name: splitConfig.name,
      description: `${splitConfig.strategy === 'random' ? '随机划分' : '按文件划分'}，种子${splitConfig.seed}`,
      dataset_type: 'qa',
      extra_data: {
        batch_id: splitConfig.batchId,
        split_strategy: splitConfig.strategy,
        seed: splitConfig.seed,
        train_ratio: splitConfig.trainRatio / 100,
        val_ratio: splitConfig.valRatio / 100,
        test_ratio: splitConfig.testRatio / 100,
      },
    })

    const datasetId = (createRes as any)?.id
    if (datasetId) {
      // 用原生 axios 直接请求文件流，绕过拦截器的 JSON 解析
      const apiBaseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'
      const res = await axios.post(
        `${apiBaseURL}/projects/${projectStore.currentProjectId}/datasets/${datasetId}/export`,
        {
          file_format: splitConfig.fileFormat,
          data_format: splitConfig.dataFormat,
          batch_id: splitConfig.batchId,
          split_strategy: splitConfig.strategy,
          seed: splitConfig.seed,
          train_ratio: splitConfig.trainRatio / 100,
          val_ratio: splitConfig.valRatio / 100,
          test_ratio: splitConfig.testRatio / 100,
        },
        { responseType: 'blob' }
      )

      const blob = res.data as Blob
      // 检测后端返回的是否为错误 JSON（而非文件流）
      if (blob.type && blob.type.includes('json')) {
        const text = await blob.text()
        const json = JSON.parse(text)
        throw new Error(json.message || '导出失败')
      }

      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `${splitConfig.name}.zip`)
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    }

    ElMessage.success('数据集导出成功')
    await fetchDatasets()
  } catch (error: any) {
    ElMessage.error(error?.message || '导出失败')
  } finally {
    exporting.value = false
  }
}

const handleExport = async (row: Dataset) => {
  if (!projectStore.currentProjectId) return
  try {
    const apiBaseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'
    const res = await axios.post(
      `${apiBaseURL}/projects/${projectStore.currentProjectId}/datasets/${row.id}/export`,
      { file_format: splitConfig.fileFormat, data_format: splitConfig.dataFormat },
      { responseType: 'blob' }
    )
    const blob = res.data as Blob
    // 检测后端返回的是否为错误 JSON
    if (blob.type && blob.type.includes('json')) {
      const text = await blob.text()
      const json = JSON.parse(text)
      throw new Error(json.message || '导出失败')
    }
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `${row.name}.zip`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (error: any) {
    ElMessage.error(error?.message || '导出失败')
  }
}

const handleDeleteDataset = async (row: Dataset) => {
  if (!projectStore.currentProjectId) return
  try {
    await ElMessageBox.confirm(`确定删除数据集「${row.name}」？此操作不可恢复。`, '删除确认', {
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch { return }
  try {
    await datasetApi.delete(projectStore.currentProjectId, row.id)
    ElMessage.success('删除成功')
    await fetchDatasets()
  } catch (error: any) {
    ElMessage.error(error?.message || '删除失败')
  }
}

const handleDatasetSelectionChange = (selection: Dataset[]) => {
  selectedDatasetIds.value = selection.map(d => d.id)
}

const handleBatchDelete = async () => {
  if (!projectStore.currentProjectId || selectedDatasetIds.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${selectedDatasetIds.value.length} 个数据集？此操作不可恢复。`,
      '批量删除确认',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch { return }
  try {
    await datasetApi.batchDelete(projectStore.currentProjectId, selectedDatasetIds.value)
    ElMessage.success(`已删除 ${selectedDatasetIds.value.length} 个数据集`)
    selectedDatasetIds.value = []
    await fetchDatasets()
  } catch (error: any) {
    ElMessage.error(error?.message || '批量删除失败')
  }
}

watch(() => projectStore.currentProjectId, (newId) => {
  if (newId) {
    fetchBatches()
    fetchQuestionCount()
    fetchDatasets()
  }
})

onMounted(() => {
  if (projectStore.currentProjectId) {
    fetchBatches()
    fetchQuestionCount()
    fetchDatasets()
  }
})
</script>

<style lang="scss" scoped>
.split-bar {
  display: flex;
  height: 36px;
  border-radius: 6px;
  overflow: hidden;

  .split-segment {
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fff;
    font-size: 12px;
    font-weight: 500;
    transition: width 0.3s;

    &.train { background: #409eff; }
    &.val { background: #67c23a; }
    &.test { background: #e6a23c; }
  }
}
</style>
