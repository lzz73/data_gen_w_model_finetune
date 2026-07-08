<template>
  <div class="page-container">
    <PageHeader title="数据管理" />

    <!-- 双 Tab 切换 -->
    <div class="content-card">
      <el-tabs v-model="activeTab" type="border-card">
        <!-- Tab 1: 数据治理数据集 -->
        <el-tab-pane label="数据治理数据集" name="governance">
          <template #label>
            <span><el-icon><FolderOpened /></el-icon> 数据治理数据集</span>
          </template>

          <div v-if="!projectStore.currentProjectId" style="padding:20px;text-align:center;color:#909399">
            请先在左侧选择一个项目，才能查看该项目的数据集
          </div>

          <div v-else>
            <div style="margin-bottom:12px;display:flex;justify-content:space-between;align-items:center">
              <el-text type="info" size="small">
                来自当前项目的数据集，可导出为训练格式并注册到训练模块
              </el-text>
            </div>

            <el-table :data="governanceDatasets" stripe v-loading="govLoading">
              <el-table-column prop="name" label="数据集名称" min-width="160" />
              <el-table-column label="问答对数" width="100">
                <template #default="{ row }">{{ row.question_count ?? '-' }}</template>
              </el-table-column>
              <el-table-column prop="created_at" label="创建时间" width="180" />
              <el-table-column label="已注册训练" width="120">
                <template #default="{ row }">
                  <el-tag v-if="isRegisteredForTraining(row.name)" type="success" size="small">已注册</el-tag>
                  <el-tag v-else type="info" size="small">未注册</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="240" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="openExportDialog(row)">
                    导出并注册训练
                  </el-button>
                  <el-button link type="primary" size="small" @click="previewGovernanceDataset(row)">
                    查看详情
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <!-- Tab 2: 本地训练数据集 -->
        <el-tab-pane label="本地训练数据集" name="local">
          <template #label>
            <span><el-icon><Upload /></el-icon> 本地训练数据集</span>
          </template>

          <div style="margin-bottom:12px;display:flex;justify-content:space-between;align-items:center">
            <el-text type="info" size="small">
              直接上传 JSONL/JSON 文件供训练使用
            </el-text>
            <el-button type="primary" size="small" @click="showUploadDialog = true">
              <el-icon><Upload /></el-icon>上传数据集
            </el-button>
          </div>

          <el-table :data="trainingDatasets" stripe v-loading="localLoading">
            <el-table-column prop="name" label="数据集名称" min-width="160" />
            <el-table-column label="格式" width="100">
              <template #default="{ row }">
                <el-tag size="small">{{ (row.formatting || 'alpaca').toUpperCase() }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="samples" label="样本数" width="100" />
            <el-table-column label="文件大小" width="100">
              <template #default="{ row }">{{ formatSize(row.size) }}</template>
            </el-table-column>
            <el-table-column label="文件" width="180">
              <template #default="{ row }">
                <el-text size="small" type="info">{{ row.file_name }}</el-text>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="200" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="previewLocalDataset(row)">查看</el-button>
                <el-button link type="danger" size="small" @click="handleDeleteLocal(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 上传对话框 -->
    <el-dialog v-model="showUploadDialog" title="上传训练数据集" width="550px" @close="resetUpload">
      <el-form :model="uploadForm" label-width="100px">
        <el-form-item label="数据集名称" required>
          <el-input v-model="uploadForm.name" placeholder="如：电力招标SFT数据集" />
        </el-form-item>
        <el-form-item label="选择文件" required>
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            :on-change="onFileChange"
            :on-remove="onFileRemove"
            accept=".jsonl,.json,.txt"
            drag
          >
            <el-icon :size="40"><UploadFilled /></el-icon>
            <div>将文件拖到此处，或<em>点击上传</em></div>
            <template #tip>
              <div class="el-upload__tip">支持 .jsonl / .json / .txt 格式</div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showUploadDialog = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="handleUpload">上传</el-button>
      </template>
    </el-dialog>

    <!-- 导出并注册对话框 -->
    <el-dialog v-model="showExportDialog" title="导出并注册到训练模块" width="550px">
      <el-form :model="exportForm" label-width="120px">
        <el-form-item label="数据集名称">
          <el-input v-model="exportForm.datasetName" disabled />
        </el-form-item>
        <el-form-item label="训练注册名称" required>
          <el-input v-model="exportForm.trainName" placeholder="注册到训练模块的名称" />
        </el-form-item>
        <el-form-item label="数据格式">
          <el-select v-model="exportForm.dataFormat" style="width:100%">
            <el-option label="Alpaca (instruction/input/output)" value="alpaca" />
            <el-option label="ShareGPT (conversations)" value="sharegpt" />
            <el-option label="LLaMA Factory (同Alpaca)" value="llama_factory" />
          </el-select>
        </el-form-item>
        <el-form-item label="划分策略">
          <el-select v-model="exportForm.splitStrategy" style="width:100%">
            <el-option label="随机划分" value="random" />
            <el-option label="按文件划分" value="file" />
          </el-select>
        </el-form-item>
        <el-form-item label="训练集比例">
          <div class="ratio-row">
            <el-slider v-model="exportForm.trainRatioPercent" :min="50" :max="98" :step="1" class="ratio-slider" />
            <el-input v-model.number="exportForm.trainRatioPercent" type="number" :min="50" :max="98" class="ratio-input" />
            <span class="ratio-suffix">%</span>
          </div>
        </el-form-item>
        <el-form-item label="验证集比例">
          <div class="ratio-row">
            <el-slider v-model="exportForm.valRatioPercent" :min="1" :max="25" :step="1" class="ratio-slider" />
            <el-input v-model.number="exportForm.valRatioPercent" type="number" :min="1" :max="25" class="ratio-input" />
            <span class="ratio-suffix">%</span>
          </div>
        </el-form-item>
        <el-form-item label="测试集比例">
          <div class="ratio-row">
            <el-slider v-model="exportForm.testRatioPercent" :min="1" :max="25" :step="1" class="ratio-slider" />
            <el-input v-model.number="exportForm.testRatioPercent" type="number" :min="1" :max="25" class="ratio-input" />
            <span class="ratio-suffix">%</span>
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showExportDialog = false">取消</el-button>
        <el-button type="primary" :loading="exporting" @click="doExportAndRegister">导出并注册</el-button>
      </template>
    </el-dialog>

    <!-- 数据预览对话框 -->
    <el-dialog v-model="showPreviewDialog" title="数据预览" width="700px">
      <pre class="data-preview">{{ previewContent }}</pre>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { FolderOpened, Upload, UploadFilled } from '@element-plus/icons-vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { useProjectStore } from '@/stores/project'
import { datasetApi } from '@/api/index'
import { trainingApi, type TrainingDatasetItem } from '@/api/training'

const projectStore = useProjectStore()

// Tab 状态
const activeTab = ref('governance')

// ── 数据治理数据集 ──
const govLoading = ref(false)
const governanceDatasets = ref<any[]>([])

const loadGovernanceDatasets = async () => {
  const pid = projectStore.currentProjectId
  if (!pid) return
  govLoading.value = true
  try {
    const res = await datasetApi.list(pid)
    // datasetApi.list returns paginated: { items, total, ... }
    if (res && typeof res === 'object' && 'items' in res) {
      governanceDatasets.value = (res as any).items || []
    } else if (Array.isArray(res)) {
      governanceDatasets.value = res
    } else {
      governanceDatasets.value = []
    }
  } catch (e: any) {
    console.error('加载数据治理数据集失败:', e)
    governanceDatasets.value = []
  } finally {
    govLoading.value = false
  }
}

// ── 本地训练数据集 ──
const localLoading = ref(false)
const trainingDatasets = ref<TrainingDatasetItem[]>([])

const loadTrainingDatasets = async () => {
  localLoading.value = true
  try {
    trainingDatasets.value = await trainingApi.listTrainingDatasets()
  } catch (e: any) {
    console.error('加载训练数据集失败:', e)
    trainingDatasets.value = []
  } finally {
    localLoading.value = false
  }
}

/** 判断数据治理数据集是否已注册到训练模块 */
const isRegisteredForTraining = (name: string): boolean => {
  return trainingDatasets.value.some(d => d.name === name)
}

// ── 上传本地训练数据集 ──
const showUploadDialog = ref(false)
const uploading = ref(false)
const selectedFile = ref<File | null>(null)
const uploadForm = reactive({ name: '' })

const onFileChange = (file: any) => { selectedFile.value = file.raw }
const onFileRemove = () => { selectedFile.value = null }

const handleUpload = async () => {
  if (!uploadForm.name.trim()) {
    ElMessage.warning('请输入数据集名称')
    return
  }
  if (!selectedFile.value) {
    ElMessage.warning('请选择文件')
    return
  }
  uploading.value = true
  try {
    const res = await trainingApi.uploadTrainingDataset(selectedFile.value, uploadForm.name.trim())
    ElMessage.success(`上传成功，共 ${res.samples} 条样本`)
    showUploadDialog.value = false
    loadTrainingDatasets()
  } catch (e: any) {
    ElMessage.error('上传失败: ' + e.message)
  } finally {
    uploading.value = false
  }
}

const resetUpload = () => {
  uploadForm.name = ''
  selectedFile.value = null
}

// ── 导出数据治理数据集并注册到训练模块（服务端完成） ──
const showExportDialog = ref(false)
const exporting = ref(false)
const exportForm = reactive({
  datasetId: '',
  datasetName: '',
  trainName: '',
  dataFormat: 'alpaca',
  splitStrategy: 'random',
  trainRatioPercent: 90,
  valRatioPercent: 5,
  testRatioPercent: 5,
})

const openExportDialog = (row: any) => {
  exportForm.datasetId = row.id
  exportForm.datasetName = row.name
  exportForm.trainName = row.name
  showExportDialog.value = true
}

const doExportAndRegister = async () => {
  const pid = projectStore.currentProjectId
  if (!pid) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (!exportForm.trainName.trim()) {
    ElMessage.warning('请输入训练注册名称')
    return
  }

  exporting.value = true
  try {
    const res = await trainingApi.exportFromGovernance({
      project_id: pid,
      dataset_id: exportForm.datasetId,
      train_name: exportForm.trainName.trim(),
      data_format: exportForm.dataFormat,
      split_strategy: exportForm.splitStrategy,
      train_ratio: exportForm.trainRatioPercent / 100,
      val_ratio: exportForm.valRatioPercent / 100,
      test_ratio: exportForm.testRatioPercent / 100,
    })
    ElMessage.success(res.message || '导出注册成功')
    showExportDialog.value = false
    loadTrainingDatasets()
  } catch (e: any) {
    ElMessage.error('导出失败: ' + e.message)
  } finally {
    exporting.value = false
  }
}

// ── 预览 ──
const showPreviewDialog = ref(false)
const previewContent = ref('')

const previewLocalDataset = async (row: TrainingDatasetItem) => {
  try {
    const items = await trainingApi.previewTrainingDataset(row.name)
    previewContent.value = JSON.stringify(items || [], null, 2)
    showPreviewDialog.value = true
  } catch (e: any) {
    ElMessage.error('预览失败: ' + e.message)
  }
}

const previewGovernanceDataset = (row: any) => {
  ElMessage.info(`数据集 "${row.name}"：${row.question_count ?? '?'} 条问答对`)
}

// ── 删除 ──
const handleDeleteLocal = async (row: TrainingDatasetItem) => {
  try {
    await ElMessageBox.confirm(`确定删除训练数据集 "${row.name}"？`, '确认删除', { type: 'warning' })
    await trainingApi.deleteTrainingDataset(row.name)
    ElMessage.success('删除成功')
    loadTrainingDatasets()
  } catch (e: any) {
    if (e !== 'cancel' && e?.message) {
      ElMessage.error(e.message)
    }
  }
}

// ── 工具函数 ──
const formatSize = (bytes: number): string => {
  if (bytes > 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  if (bytes > 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}

// ── 初始化 ──
onMounted(() => {
  loadTrainingDatasets()
  if (projectStore.currentProjectId) {
    loadGovernanceDatasets()
  }
})

// 当项目切换时重新加载
watch(() => projectStore.currentProjectId, (newId) => {
  if (newId) loadGovernanceDatasets()
  else governanceDatasets.value = []
})
</script>

<style lang="scss" scoped>
.ratio-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;

  .ratio-slider {
    flex: 1;
  }

  .ratio-input {
    width: 70px;
    flex-shrink: 0;
  }

  .ratio-suffix {
    flex-shrink: 0;
    color: #606266;
    font-size: 14px;
  }
}

.data-preview {
  max-height: 400px;
  overflow: auto;
  background: #f5f7fa;
  padding: 12px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.6;
}
</style>
