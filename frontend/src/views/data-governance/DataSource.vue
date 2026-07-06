<template>
  <div class="page-container">
    <PageHeader title="数据源接入">
      <el-button type="primary" @click="showUploadDialog = true">
        <el-icon><Plus /></el-icon>新增数据源
      </el-button>
    </PageHeader>

    <!-- 未选择项目提示 -->
    <EmptyState
      v-if="!projectStore.hasProject"
      description="请先在首页选择一个项目"
      action-text="前往首页"
      @action="$router.push('/')"
    />

    <!-- 文件列表 -->
    <div v-else class="content-card">
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
        <span class="card-title" style="margin-bottom: 0;">已接入数据源</span>
        <div style="display: flex; gap: 8px;">
          <el-button
            size="small"
            :disabled="selectedFileIds.length === 0"
            @click="handleBatchDelete"
          >
            <el-icon><Delete /></el-icon>
            批量删除（已选 {{ selectedFileIds.length }} 个）
          </el-button>
        </div>
      </div>
      <el-table
        ref="tableRef"
        :data="files"
        stripe
        v-loading="loading"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="45" />
        <el-table-column prop="filename" label="文件名" />
        <el-table-column prop="file_type" label="类型" width="120">
          <template #default="{ row }">
            <el-tag :type="fileTypeTag(row.file_type)" size="small">{{ row.file_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="大小" width="100">
          <template #default="{ row }">
            {{ row.size ? formatSize(row.size) : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.status === 'completed' ? 'success' : row.status === 'processing' ? 'warning' : row.status === 'failed' ? 'danger' : 'info'" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="接入时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 新增数据源对话框 -->
    <el-dialog v-model="showUploadDialog" title="新增数据源" width="700px" @close="resetUploadForm">
      <el-form :model="uploadForm" label-width="110px">
        <el-form-item label="接入方式">
          <el-radio-group v-model="uploadForm.source">
            <el-radio value="file">上传文件</el-radio>
            <el-radio value="database">连接数据库</el-radio>
            <el-radio value="crawler">网页抓取</el-radio>
            <el-radio value="manual">人工录入</el-radio>
          </el-radio-group>
        </el-form-item>

        <!-- ========= 上传文件 ========= -->
        <template v-if="uploadForm.source === 'file'">
          <el-form-item label="文件类型">
            <el-radio-group v-model="uploadForm.fileCategory">
              <el-radio value="structured">结构化（CSV/Excel）</el-radio>
              <el-radio value="unstructured">非结构化（PDF/Word）</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="文件上传">
            <el-upload
              ref="uploadRef"
              drag
              multiple
              :auto-upload="false"
              :accept="uploadForm.fileCategory === 'structured' ? '.csv,.xlsx,.xls' : '.pdf,.doc,.docx'"
              :on-change="handleFileChange"
              :on-remove="handleFileRemove"
            >
              <el-icon :size="40"><UploadFilled /></el-icon>
              <div>将文件拖到此处，或<em>点击上传</em></div>
            </el-upload>
          </el-form-item>
        </template>

        <!-- ========= 连接数据库 ========= -->
        <template v-if="uploadForm.source === 'database'">
          <el-form-item label="数据库类型">
            <el-select v-model="dbForm.dbType" style="width: 200px;">
              <el-option label="MySQL" value="mysql" />
              <el-option label="PostgreSQL" value="postgresql" />
              <el-option label="SQLite" value="sqlite" />
            </el-select>
          </el-form-item>
          <template v-if="dbForm.dbType !== 'sqlite'">
            <el-form-item label="主机地址">
              <el-input v-model="dbForm.host" placeholder="如：192.168.1.100" style="width: 240px;" />
            </el-form-item>
            <el-form-item label="端口">
              <el-input-number v-model="dbForm.port" :min="1" :max="65535" :placeholder="dbForm.dbType === 'mysql' ? 3306 : 5432" style="width: 160px;" />
            </el-form-item>
            <el-form-item label="用户名">
              <el-input v-model="dbForm.user" placeholder="数据库用户名" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="dbForm.password" type="password" placeholder="数据库密码" show-password />
            </el-form-item>
          </template>
          <el-form-item :label="dbForm.dbType === 'sqlite' ? '数据库路径' : '数据库名'">
            <el-input v-model="dbForm.database" :placeholder="dbForm.dbType === 'sqlite' ? '数据库文件路径' : '数据库名称'" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" plain :loading="dbConnecting" @click="connectDatabase">
              测试连接
            </el-button>
          </el-form-item>

          <!-- 表列表 -->
          <div v-if="dbTables.length > 0" style="margin: 0 0 16px 0;">
            <el-form-item label="选择表">
              <div style="width: 100%;">
                <el-text type="info" size="small" style="margin-bottom: 8px; display: block;">勾选要导入的表，支持多选</el-text>
                <el-table
                  :data="dbTables"
                  stripe
                  max-height="260"
                  @selection-change="handleDbTableSelect"
                  style="width: 100%;"
                >
                  <el-table-column type="selection" width="45" />
                  <el-table-column prop="name" label="表名" />
                  <el-table-column prop="row_count" label="行数" width="100" />
                  <el-table-column label="列数" width="80">
                    <template #default="{ row }">{{ row.columns?.length || 0 }}</template>
                  </el-table-column>
                </el-table>
              </div>
            </el-form-item>
            <el-alert v-if="selectedDbTables.length > 0" type="success" :closable="false" style="margin-bottom: 12px;">
              <template #title>已选择 {{ selectedDbTables.length }} 张表：{{ selectedDbTables.join('、') }}</template>
            </el-alert>
          </div>
        </template>

        <!-- ========= 网页抓取 ========= -->
        <template v-if="uploadForm.source === 'crawler'">
          <el-form-item label="起始 URL">
            <el-input v-model="crawlerForm.url" placeholder="https://www.runoob.com/python3/python3-tutorial.html" />
          </el-form-item>
          <el-form-item label="最大页数">
            <el-input-number v-model="crawlerForm.maxPages" :min="1" :max="50" style="width: 160px;" />
          </el-form-item>
          <el-form-item label="CSS 选择器">
            <el-input v-model="crawlerForm.cssSelector" placeholder="可选，如 .article-content" />
          </el-form-item>
          <el-form-item label="提取选项">
            <el-checkbox v-model="crawlerForm.extractTitle">提取标题</el-checkbox>
            <el-checkbox v-model="crawlerForm.extractContent">提取正文</el-checkbox>
            <el-checkbox v-model="crawlerForm.extractImages">提取图片链接</el-checkbox>
          </el-form-item>

          <!-- 抓取进度 -->
          <div v-if="crawlerTaskId" style="margin-bottom: 16px;">
            <el-form-item label="抓取进度">
              <div style="width: 100%;">
                <el-progress :percentage="crawlerProgress" :status="crawlerStatus === 'failed' ? 'exception' : crawlerStatus === 'completed' ? 'success' : undefined" />
                <div style="display: flex; justify-content: space-between; margin-top: 6px; font-size: 12px; color: #909399;">
                  <span>{{ crawlerStatusLabel }}</span>
                  <span>已获取 {{ crawlerPageCount }} 页</span>
                </div>
              </div>
            </el-form-item>
          </div>

          <el-form-item>
            <el-button type="primary" plain :loading="crawlerRunning" :disabled="!crawlerForm.url" @click="startCrawl">
              {{ crawlerTaskId ? '重新抓取' : '开始抓取' }}
            </el-button>
            <el-button
              v-if="crawlerTaskId && crawlerStatus === 'completed'"
              type="success"
              :loading="crawlerSaving"
              @click="saveCrawlResult"
            >
              保存到项目
            </el-button>
          </el-form-item>
        </template>

        <!-- ========= 人工录入 → 跳转引导 ========= -->
        <template v-if="uploadForm.source === 'manual'">
          <el-alert type="info" :closable="false" style="margin-bottom: 16px;">
            <template #title>人工生成已迁移到专属页面，支持批量导入文件、在线编辑和导出</template>
          </el-alert>
          <el-button type="primary" @click="$router.push('/data-governance/manual-generate')">
            <el-icon><Right /></el-icon>前往人工生成
          </el-button>
        </template>
      </el-form>

      <template #footer>
        <el-button @click="showUploadDialog = false">关闭</el-button>
        <el-button
          v-if="canConfirmUpload"
          type="primary"
          :loading="uploading"
          @click="handleUpload"
        >
          确认接入
        </el-button>
      </template>
    </el-dialog>

    <!-- 删除确认 -->
    <!-- 单个删除确认 -->
    <DeleteDialog
      v-if="!isBatchDelete"
      v-model:visible="showDeleteDialog"
      :item-name="deleteTarget?.filename"
      item-type="文件"
      :loading="deleteLoading"
      @confirm="confirmDelete"
    />

    <!-- 批量删除确认 -->
    <el-dialog v-model="showDeleteDialog" title="确认删除" width="400px" v-if="isBatchDelete">
      <p>确定要删除选中的 <strong>{{ selectedFileIds.length }}</strong> 个文件吗？此操作不可撤销。</p>
      <template #footer>
        <el-button @click="showDeleteDialog = false">取消</el-button>
        <el-button type="danger" :loading="deleteLoading" @click="confirmBatchDelete">确定删除</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { fileApi, databaseApi, crawlerApi } from '@/api'
import { formatSize, formatDateTime } from '@/composables/useFormatters'
import { ElMessage } from 'element-plus'
import { Delete, Right } from '@element-plus/icons-vue'
import PageHeader from '@/components/common/PageHeader.vue'
import DeleteDialog from '@/components/common/DeleteDialog.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import type { FileItem } from '@/types'
import type { UploadFile, ElTable } from 'element-plus'

const router = useRouter()
const projectStore = useProjectStore()

const loading = ref(false)
const files = ref<FileItem[]>([])
const showUploadDialog = ref(false)
const uploading = ref(false)
const showDeleteDialog = ref(false)
const deleteTarget = ref<FileItem | null>(null)
const deleteLoading = ref(false)
const fileList = ref<UploadFile[]>([])
const selectedFileIds = ref<string[]>([])
const selectedFiles = ref<FileItem[]>([])
const isBatchDelete = ref(false)
const tableRef = ref<InstanceType<typeof ElTable>>()
const uploadForm = reactive({
  source: 'file',
  fileCategory: 'structured',
  template: 'instruct',
})

// ==================== 数据库连接 ====================
const dbForm = reactive({
  dbType: 'mysql',
  host: '',
  port: undefined as number | undefined,
  user: '',
  password: '',
  database: '',
})
const dbConnecting = ref(false)
const dbTables = ref<any[]>([])
const selectedDbTables = ref<string[]>([])

const connectDatabase = async () => {
  dbConnecting.value = true
  dbTables.value = []
  selectedDbTables.value = []
  try {
    const res = await databaseApi.connect({
      db_type: dbForm.dbType,
      host: dbForm.host,
      port: dbForm.port,
      user: dbForm.user,
      password: dbForm.password,
      database: dbForm.database,
    }) as any
    if (res?.tables?.length) {
      dbTables.value = res.tables
      ElMessage.success(`连接成功，发现 ${res.tables.length} 张表`)
    } else {
      ElMessage.warning('连接成功，但未发现任何表')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '连接失败')
  } finally {
    dbConnecting.value = false
  }
}

const handleDbTableSelect = (selection: any[]) => {
  selectedDbTables.value = selection.map(row => row.name)
}

// ==================== 网页抓取 ====================
const crawlerForm = reactive({
  url: '',
  maxPages: 5,
  cssSelector: '',
  extractTitle: true,
  extractContent: true,
  extractImages: false,
})
const crawlerTaskId = ref('')
const crawlerStatus = ref('')
const crawlerProgress = ref(0)
const crawlerPageCount = ref(0)
const crawlerRunning = ref(false)
const crawlerSaving = ref(false)
let crawlerPollTimer: ReturnType<typeof setInterval> | null = null

const crawlerStatusLabel = computed(() => {
  const map: Record<string, string> = {
    pending: '等待中',
    running: '抓取中...',
    completed: '抓取完成',
    failed: '抓取失败',
  }
  return map[crawlerStatus.value] || crawlerStatus.value
})

const startCrawl = async () => {
  if (!crawlerForm.url) return
  crawlerRunning.value = true
  crawlerProgress.value = 0
  crawlerPageCount.value = 0
  crawlerStatus.value = ''
  try {
    const res = await crawlerApi.start({
      url: crawlerForm.url,
      max_pages: crawlerForm.maxPages,
      css_selector: crawlerForm.cssSelector || undefined,
      extract_title: crawlerForm.extractTitle,
      extract_content: crawlerForm.extractContent,
      extract_images: crawlerForm.extractImages,
      project_id: projectStore.currentProjectId || undefined,
    }) as any
    crawlerTaskId.value = res?.task_id || ''
    startCrawlerPolling()
    ElMessage.info('抓取任务已启动')
  } catch (e: any) {
    ElMessage.error(e?.message || '启动抓取失败')
    crawlerRunning.value = false
  }
}

const startCrawlerPolling = () => {
  stopCrawlerPolling()
  crawlerPollTimer = setInterval(async () => {
    if (!crawlerTaskId.value) return
    try {
      const res = await crawlerApi.getTask(crawlerTaskId.value) as any
      crawlerStatus.value = res?.status || ''
      crawlerProgress.value = res?.progress || 0
      crawlerPageCount.value = res?.pages?.length || 0

      if (res?.status === 'completed' || res?.status === 'failed') {
        stopCrawlerPolling()
        crawlerRunning.value = false
        if (res?.status === 'failed') {
          ElMessage.error('抓取失败: ' + (res?.error || '未知错误'))
        }
      }
    } catch {
      // continue polling
    }
  }, 2000)
}

const stopCrawlerPolling = () => {
  if (crawlerPollTimer) {
    clearInterval(crawlerPollTimer)
    crawlerPollTimer = null
  }
}

const saveCrawlResult = async () => {
  if (!projectStore.currentProjectId || !crawlerTaskId.value) return
  crawlerSaving.value = true
  try {
    const res = await crawlerApi.save(crawlerTaskId.value, projectStore.currentProjectId) as any
    ElMessage.success(`已保存 ${res?.count || 0} 个页面到项目`)
    showUploadDialog.value = false
    await fetchFiles()
    router.push('/data-governance/unstructured')
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    crawlerSaving.value = false
  }
}

// ==================== 文件上传 ====================
const canConfirmUpload = computed(() => {
  if (uploadForm.source === 'manual') return false
  if (uploadForm.source === 'database') return selectedDbTables.value.length > 0
  if (uploadForm.source === 'crawler') return false
  return fileList.value.length > 0
})

const handleFileChange = (_file: UploadFile, uploadFileList: UploadFile[]) => {
  fileList.value = uploadFileList
}

const handleFileRemove = (_file: UploadFile, uploadFileList: UploadFile[]) => {
  fileList.value = uploadFileList
}

const handleUpload = async () => {
  if (!projectStore.currentProjectId) {
    ElMessage.warning('请先选择项目')
    return
  }

  // 数据库导入
  if (uploadForm.source === 'database') {
    if (selectedDbTables.value.length === 0) {
      ElMessage.warning('请先选择要导入的表')
      return
    }
    uploading.value = true
    let successCount = 0
    let failCount = 0
    for (const tableName of selectedDbTables.value) {
      try {
        await databaseApi.importTable({
          db_type: dbForm.dbType,
          host: dbForm.host,
          port: dbForm.port,
          user: dbForm.user,
          password: dbForm.password,
          database: dbForm.database,
          table_name: tableName,
          project_id: projectStore.currentProjectId,
        })
        successCount++
      } catch (e: any) {
        console.error(`导入表 ${tableName} 失败:`, e)
        failCount++
      }
    }
    uploading.value = false
    if (failCount > 0) {
      ElMessage.warning(`导入完成：${successCount} 张表成功，${failCount} 张表失败`)
    } else {
      ElMessage.success(`成功导入 ${successCount} 张表`)
    }
    showUploadDialog.value = false
    await fetchFiles()
    router.push('/data-governance/structured')
    return
  }

  // 文件上传
  if (fileList.value.length === 0) {
    ElMessage.warning('请先选择文件')
    return
  }

  uploading.value = true
  showUploadDialog.value = false

  const uploadedExts: string[] = fileList.value.map(
    item => item.raw?.name?.split('.').pop()?.toLowerCase() || ''
  ).filter(Boolean)

  let successCount = 0
  let failCount = 0
  for (const item of fileList.value) {
    try {
      const formData = new FormData()
      formData.append('file', item.raw!)
      await fileApi.upload(projectStore.currentProjectId!, formData)
      successCount++
    } catch (error) {
      console.error('上传失败:', error)
      failCount++
    }
  }

  await fetchFiles()

  if (failCount > 0) {
    ElMessage.warning(`上传完成：${successCount} 个成功，${failCount} 个失败`)
  } else if (successCount > 0) {
    ElMessage.success(`成功上传 ${successCount} 个文件`)
  }
  uploading.value = false

  // Auto-redirect based on uploaded file types
  if (successCount > 0) {
    const structuredExts = ['xlsx', 'xls', 'csv']
    const unstructuredExts = ['pdf', 'docx', 'doc', 'txt', 'md', 'epub']

    if (uploadedExts.some(ext => unstructuredExts.includes(ext))) {
      router.push('/data-governance/unstructured')
    } else if (uploadedExts.some(ext => structuredExts.includes(ext))) {
      router.push('/data-governance/structured')
    }
  }
}

const resetUploadForm = () => {
  fileList.value = []
  uploadForm.source = 'file'
  uploadForm.fileCategory = 'structured'
  // 重置数据库表单
  dbTables.value = []
  selectedDbTables.value = []
  // 重置爬虫
  crawlerTaskId.value = ''
  crawlerStatus.value = ''
  crawlerProgress.value = 0
  crawlerPageCount.value = 0
  stopCrawlerPolling()
}

const handleSelectionChange = (selection: FileItem[]) => {
  selectedFiles.value = selection
  selectedFileIds.value = selection.map(f => f.id)
}

const handleDelete = (row: FileItem) => {
  deleteTarget.value = row
  isBatchDelete.value = false
  showDeleteDialog.value = true
}

const handleBatchDelete = () => {
  if (selectedFileIds.value.length === 0) return
  isBatchDelete.value = true
  showDeleteDialog.value = true
}

const confirmBatchDelete = async () => {
  if (!projectStore.currentProjectId) return
  deleteLoading.value = true
  let successCount = 0
  let failCount = 0
  for (const fileId of selectedFileIds.value) {
    try {
      await fileApi.delete(projectStore.currentProjectId, fileId)
      successCount++
    } catch {
      failCount++
    }
  }
  deleteLoading.value = false
  showDeleteDialog.value = false
  selectedFileIds.value = []
  selectedFiles.value = []
  await fetchFiles()
  if (failCount > 0) {
    ElMessage.warning(`删除完成：${successCount} 个成功，${failCount} 个失败`)
  } else {
    ElMessage.success(`已删除 ${successCount} 个文件`)
  }
}

const confirmDelete = async () => {
  if (!projectStore.currentProjectId || !deleteTarget.value) return
  deleteLoading.value = true
  try {
    await fileApi.delete(projectStore.currentProjectId, deleteTarget.value.id)
    ElMessage.success('删除成功')
    await fetchFiles()
    showDeleteDialog.value = false
  } catch (error: any) {
    ElMessage.error(error?.message || '删除失败')
  } finally {
    deleteLoading.value = false
  }
}

const fileTypeTag = (type: string) => {
  const map: Record<string, string> = {
    pdf: 'danger', docx: 'warning', doc: 'warning',
    xlsx: 'success', xls: 'success', csv: 'success',
    txt: 'info', md: 'info'
  }
  return map[type] || 'info'
}

const statusLabel = (status: string) => {
  const map: Record<string, string> = {
    pending: '待处理', processing: '处理中', completed: '已完成', failed: '失败'
  }
  return map[status] || status
}

const fetchFiles = async () => {
  if (!projectStore.currentProjectId) return
  loading.value = true
  try {
    const res = await fileApi.list(projectStore.currentProjectId)
    if (Array.isArray(res)) {
      files.value = res
    } else if (res && typeof res === 'object' && 'items' in res) {
      files.value = (res as any).items || []
    } else {
      files.value = []
    }
  } catch (e) {
    files.value = []
  } finally {
    loading.value = false
  }
}

watch(() => projectStore.currentProjectId, (newId) => {
  if (newId) fetchFiles()
})

onMounted(() => {
  if (projectStore.currentProjectId) fetchFiles()
})

onUnmounted(() => {
  stopCrawlerPolling()
})
</script>
