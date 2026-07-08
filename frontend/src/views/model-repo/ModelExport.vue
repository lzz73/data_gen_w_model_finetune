<template>
  <div class="page-container">
    <PageHeader title="模型导出" />

    <el-row :gutter="16">
      <el-col :span="16">
        <div class="content-card">
          <div class="card-title">LoRA 模型列表（未合并）</div>
          <el-table :data="loraModels" stripe v-loading="loading" highlight-current-row @current-change="selectTask">
            <el-table-column type="index" width="50" />
            <el-table-column prop="name" label="任务名称" min-width="180" />
            <el-table-column label="基座模型" show-overflow-tooltip>
              <template #default="{ row }">{{ row.config?.base_model || row.model }}</template>
            </el-table-column>
            <el-table-column label="LoRA Rank" width="90">
              <template #default="{ row }">{{ row.config?.lora_rank || '--' }}</template>
            </el-table-column>
            <el-table-column label="最新 Checkpoint" width="140">
              <template #default="{ row }">{{ row.latest_ckpt || '--' }}</template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag v-if="row.is_merged" type="success" size="small">已导出</el-tag>
                <el-tag v-else type="warning" size="small">待导出</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="合并路径" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">
                <span v-if="row.merged_path">{{ row.merged_path }}</span>
                <span v-else style="color:#909399">--</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>

      <el-col :span="8">
        <div class="content-card" v-if="selected">
          <div class="card-title">导出配置</div>
          <el-form label-width="120px" size="small">
            <el-form-item label="导出路径">
              <el-input v-model="exportPath" :placeholder="defaultExportPath" :disabled="exporting || selected?.is_merged" />
            </el-form-item>
            <el-form-item label="分片大小 (GB)">
              <el-input-number v-model="exportSize" :min="1" :max="50" :disabled="exporting || selected?.is_merged" />
            </el-form-item>
            <el-form-item v-if="!exporting && !exportDone">
              <el-button type="primary" :disabled="selected?.is_merged" @click="doExport">
                <el-icon><Download /></el-icon>合并导出
              </el-button>
            </el-form-item>
          </el-form>

          <!-- 进度条 / 结果 -->
          <div v-if="exporting || exportDone" style="margin-top:12px">
            <el-progress
              v-if="!exportDone"
              :percentage="exportProgress"
              :stroke-width="16"
            />
            <p style="margin-top:8px;color:#909399;font-size:13px">{{ exportMsg }}</p>
            <el-alert v-if="exportDone" type="success" :closable="false" title="导出完成!" style="margin-top:8px">
              模型已保存至 {{ exportResultDir }}
            </el-alert>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import PageHeader from '@/components/common/PageHeader.vue'
import { trainingApi } from '@/api/training'

const loading = ref(false)
const loraModels = ref<any[]>([])
const selected = ref<any>(null)
const exporting = ref(false)
const exportDone = ref(false)
const exportMsg = ref('')
const exportProgress = ref(0)
const exportResultDir = ref('')
const exportSize = ref(5)
const exportPath = ref('')

const defaultExportPath = computed(() =>
  selected.value ? `output/merged/${selected.value.task_id}` : ''
)

let pollTimer: any = null

const selectTask = (row: any) => {
  selected.value = row
  exportPath.value = ''
  exportMsg.value = ''
  exportDone.value = false
  exportProgress.value = 0
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

const doExport = async () => {
  if (!selected.value) { ElMessage.warning('请先选择一个 LoRA 模型'); return }
  if (selected.value.is_merged) { ElMessage.warning('该任务已导出，不能重复导出'); return }
  exporting.value = true; exportDone.value = false; exportProgress.value = 10
  try {
    const data = await trainingApi.exportModel({
      task_id: selected.value.task_id,
      export_dir: exportPath.value || defaultExportPath.value,
      export_size: exportSize.value,
    })
    if (data?.job_id) {
      exportResultDir.value = data.export_dir
      // 轮询进度
      pollTimer = setInterval(async () => {
        try {
          const job = await trainingApi.getExportStatus(data.job_id)
          if (job) {
            exportProgress.value = job.progress
            exportMsg.value = job.msg
            if (job.status === 'done') {
              exportProgress.value = 100
              exportDone.value = true
              exporting.value = false
              clearInterval(pollTimer!)
              loadLoraModels()
            } else if (job.status === 'error') {
              exportMsg.value = '导出失败: ' + job.msg
              exporting.value = false
              clearInterval(pollTimer!)
            }
          }
        } catch {}
      }, 1000)
    } else {
      exporting.value = false
      exportMsg.value = '启动失败'
    }
  } catch (e: any) {
    exporting.value = false; exportMsg.value = e.message
  }
}

const loadLoraModels = async () => {
  loading.value = true
  try {
    loraModels.value = await trainingApi.listLoraModels()
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

onMounted(loadLoraModels)
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
</script>
