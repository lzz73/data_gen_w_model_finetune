<template>
  <div class="page-container">
    <PageHeader title="数据管理">
      <el-button type="primary" @click="showUploadDialog = true">
        <el-icon><Upload /></el-icon>上传数据集
      </el-button>
    </PageHeader>

    <!-- 数据集列表 -->
    <div class="content-card">
      <div class="card-title">数据集列表</div>
      <el-table :data="datasets" stripe v-loading="loading">
        <el-table-column prop="name" label="数据集名称" />
        <el-table-column prop="format" label="格式" width="80">
          <template #default="{ row }"><el-tag size="small">{{ row.format.toUpperCase() }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="samples" label="样本数" width="100" />
        <el-table-column prop="version" label="版本" width="80" />
        <el-table-column label="校验状态" width="140">
          <template #default="{ row }">
            <el-popover
              v-if="row.validation && row.validation.success === false"
              placement="top" :width="320" trigger="hover"
            >
              <template #reference>
                <el-tag type="danger" size="small" style="cursor:pointer">
                  {{ row.validation.blocking_count }}项未通过
                </el-tag>
              </template>
              <div v-for="(e, i) in row.validation.errors" :key="i" style="margin-bottom:6px;font-size:13px">
                <b style="color:#f56c6c">[{{ e.code }}]</b>
                {{ e.message }}
                <span v-if="e.row" style="color:#909399">(第{{ e.row }}行)</span>
              </div>
            </el-popover>
            <el-tag v-else-if="row.validation?.success === true" type="success" size="small">通过</el-tag>
            <el-tag v-else type="info" size="small">未校验</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="警告" width="100">
          <template #default="{ row }">
            <el-popover
              v-if="row.validation?.warning_count > 0"
              placement="top" :width="320" trigger="hover"
            >
              <template #reference>
                <el-text type="warning" size="small" style="cursor:pointer">{{ row.validation.warning_count }}条警告</el-text>
              </template>
              <div v-for="(w, i) in row.validation.warnings" :key="i" style="margin-bottom:4px;font-size:13px;color:#e6a23c">
                [{{ w.code }}] {{ w.message }}
              </div>
            </el-popover>
            <el-text v-else type="success" size="small">无</el-text>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="previewData(row)">查看</el-button>
            <el-button link type="primary" size="small" @click="showVersions(row.name)">版本</el-button>
            <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 上传对话框 -->
    <el-dialog v-model="showUploadDialog" title="上传数据集" width="550px" @close="resetUpload">
      <el-form :model="uploadForm" label-width="100px">
        <el-form-item label="数据集名称" required>
          <el-input v-model="uploadForm.name" placeholder="如：电力招标SFT数据集" />
        </el-form-item>
        <el-form-item label="数据格式">
          <el-radio-group v-model="uploadForm.format">
            <el-radio value="jsonl">JSONL（每行一个JSON对象）</el-radio>
            <el-radio value="json">JSON</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="必填字段">
          <el-input v-model="uploadForm.requiredFields" placeholder="逗号分隔，如：instruction,output" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="uploadForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="选择文件" required>
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            :on-change="onFileChange"
            :on-remove="onFileRemove"
            accept=".jsonl,.json"
            drag
          >
            <el-icon :size="40"><UploadFilled /></el-icon>
            <div>将文件拖到此处，或<em>点击上传</em></div>
          </el-upload>
        </el-form-item>
      </el-form>

      <!-- 校验结果 -->
      <div v-if="validateResults.length > 0" style="margin-top:12px">
        <el-alert
          v-for="(r, i) in validateResults"
          :key="i"
          :title="`[${r.code}] ${r.message}`"
          :type="r.level === 'blocking' ? 'error' : 'warning'"
          :closable="false"
          style="margin-bottom:4px"
        />
      </div>

      <template #footer>
        <el-button @click="showUploadDialog = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="handleUpload">上传并校验</el-button>
      </template>
    </el-dialog>

    <!-- 数据预览对话框 -->
    <el-dialog v-model="showPreviewDialog" title="数据预览" width="700px">
      <pre class="data-preview">{{ previewContent }}</pre>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageHeader from '@/components/common/PageHeader.vue'
import { fetchDatasets, uploadDataset, fetchDatasetData, deleteVersion } from '@/api/datasets'
import type { DatasetItem, ValidationResult } from '@/api/datasets'

const loading = ref(false)
const uploading = ref(false)
const datasets = ref<DatasetItem[]>([])
const showUploadDialog = ref(false)
const showPreviewDialog = ref(false)
const previewContent = ref('')
const validateResults = ref<ValidationResult[]>([])
const selectedFile = ref<File | null>(null)

const uploadForm = reactive({
  name: '',
  format: 'jsonl',
  requiredFields: 'instruction,output',
  description: '',
})

const loadDatasets = async () => {
  loading.value = true
  try {
    const res = await fetchDatasets()
    if (res.code === 0) {
      datasets.value = res.data
    }
  } catch (e: any) {
    console.error('加载数据集失败:', e)
  } finally {
    loading.value = false
  }
}

const onFileChange = (file: any) => {
  selectedFile.value = file.raw
}

const onFileRemove = () => {
  selectedFile.value = null
}

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
    const res = await uploadDataset(
      selectedFile.value,
      uploadForm.name,
      uploadForm.format,
      uploadForm.description,
      uploadForm.requiredFields,
    )
    if (res.code === 0) {
      ElMessage.success(res.data.message || '上传成功')
      showUploadDialog.value = false
      loadDatasets()
    } else {
      validateResults.value = res.data?.validation_results || []
      ElMessage.error(res.data?.message || '上传失败')
    }
  } catch (e: any) {
    ElMessage.error('上传失败: ' + e.message)
  } finally {
    uploading.value = false
  }
}

const resetUpload = () => {
  uploadForm.name = ''
  uploadForm.requiredFields = 'instruction,output'
  uploadForm.description = ''
  selectedFile.value = null
  validateResults.value = []
}

const previewData = async (row: DatasetItem) => {
  try {
    const res = await fetchDatasetData(row.name)
    if (res.code === 0) {
      const data = res.data || []
      previewContent.value = JSON.stringify(data.slice(0, 20), null, 2)
      showPreviewDialog.value = true
    }
  } catch (e) {
    ElMessage.error('加载数据失败')
  }
}

const showVersions = (name: string) => {
  ElMessage.info(`数据集 "${name}" 的版本列表（功能待扩展）`)
}

const handleDelete = async (row: DatasetItem) => {
  try {
    await ElMessageBox.confirm(`确定删除数据集 "${row.name}"？`, '确认删除', { type: 'warning' })
    const res = await deleteVersion(row.version_id)
    if (res.code === 0) {
      ElMessage.success('删除成功')
      loadDatasets()
    } else {
      ElMessage.error(res.message || '删除失败')
    }
  } catch {
    // 取消
  }
}

onMounted(() => {
  loadDatasets()
})
</script>

<style lang="scss" scoped>
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
