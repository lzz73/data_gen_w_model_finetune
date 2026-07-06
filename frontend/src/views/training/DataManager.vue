<template>
  <div class="page-container">
    <PageHeader title="数据管理">
      <el-button type="primary" @click="showUploadDialog = true" :disabled="!projectStore.hasProject">
        <el-icon><Upload /></el-icon>上传数据集
      </el-button>
    </PageHeader>

    <EmptyState
      v-if="!projectStore.hasProject"
      description="请先在首页选择一个项目"
      action-text="前往首页"
      @action="$router.push('/')"
    />

    <!-- 数据集列表 -->
    <div v-else class="content-card">
      <div class="card-title">数据集列表</div>
      <el-table :data="datasets" stripe v-loading="loading">
        <el-table-column prop="name" label="数据集名称" />
        <el-table-column prop="dataset_type" label="类型" width="80">
          <template #default="{ row }">
            <el-tag size="small">{{ row.dataset_type || 'qa' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="question_count" label="样本数" width="80" />
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <EmptyState
        v-if="!loading && datasets.length === 0"
        description="暂无数据集"
      />
    </div>

    <!-- 上传对话框 -->
    <el-dialog v-model="showUploadDialog" title="上传数据集" width="500px" @close="fileList = []">
      <el-upload
        drag
        :auto-upload="false"
        accept=".jsonl"
        :on-change="handleFileChange"
        :on-remove="handleFileRemove"
      >
        <el-icon :size="40"><UploadFilled /></el-icon>
        <div>将JSONL文件拖到此处，或<em>点击上传</em></div>
      </el-upload>
      <template #footer>
        <el-button @click="showUploadDialog = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="handleUpload">上传并校验</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useProjectStore } from '@/stores/project'
import { fileApi, datasetApi } from '@/api'
import { formatDateTime } from '@/composables/useFormatters'
import { ElMessage } from 'element-plus'
import PageHeader from '@/components/common/PageHeader.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import type { Dataset } from '@/types'
import type { UploadFile } from 'element-plus'

const projectStore = useProjectStore()
const loading = ref(false)
const uploading = ref(false)
const showUploadDialog = ref(false)
const datasets = ref<Dataset[]>([])
const fileList = ref<UploadFile[]>([])

const fetchDatasets = async () => {
  if (!projectStore.currentProjectId) return
  loading.value = true
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
    loading.value = false
  }
}

const handleFileChange = (_file: UploadFile, list: UploadFile[]) => {
  fileList.value = list
}

const handleFileRemove = (_file: UploadFile, list: UploadFile[]) => {
  fileList.value = list
}

const handleUpload = async () => {
  if (!projectStore.currentProjectId) return
  if (fileList.value.length === 0) {
    ElMessage.warning('请先选择文件')
    return
  }
  uploading.value = true
  showUploadDialog.value = false
  try {
    for (const item of fileList.value) {
      const formData = new FormData()
      formData.append('file', item.raw!)
      await fileApi.upload(projectStore.currentProjectId!, formData)
    }
    ElMessage.success('上传成功')
    await fetchDatasets()
  } catch (error: any) {
    ElMessage.error(error?.message || '上传失败')
  } finally {
    uploading.value = false
  }
}

const handleDelete = async (row: Dataset) => {
  if (!projectStore.currentProjectId) return
  try {
    await datasetApi.delete(projectStore.currentProjectId, row.id)
    ElMessage.success('删除成功')
    await fetchDatasets()
  } catch (error: any) {
    ElMessage.error(error?.message || '删除失败')
  }
}

watch(() => projectStore.currentProjectId, (newId) => {
  if (newId) fetchDatasets()
})

onMounted(() => {
  if (projectStore.currentProjectId) fetchDatasets()
})
</script>
