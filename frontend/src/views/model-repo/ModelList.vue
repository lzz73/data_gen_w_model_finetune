<template>
  <div class="page-container">
    <PageHeader title="模型列表">
      <el-input v-model="search" placeholder="搜索模型名称..." clearable style="width:260px" class="search-input">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-button type="primary" @click="loadModels">
        <el-icon><Refresh /></el-icon>刷新
      </el-button>
    </PageHeader>

    <div class="model-grid">
      <el-card v-for="model in paginatedModels" :key="model.path" class="model-card" shadow="hover">
        <template #header>
          <div class="model-header">
            <span class="model-name">{{ model.name }}</span>
            <el-tag type="success" size="small">已合并</el-tag>
          </div>
        </template>
        <el-descriptions :column="1" size="small">
          <el-descriptions-item label="路径">{{ model.path }}</el-descriptions-item>
          <el-descriptions-item label="大小">{{ model.size }}</el-descriptions-item>
          <el-descriptions-item label="修改时间">{{ model.modified }}</el-descriptions-item>
        </el-descriptions>
        <div class="model-actions">
          <el-button size="small" type="primary" @click="$router.push('/model-repo/verify')">验证</el-button>
        </div>
      </el-card>

      <div v-if="paginatedModels.length === 0 && !loading" class="empty-hint">
        <el-empty description="暂无已合并的模型">
          <el-button type="primary" @click="$router.push('/model-repo/export')">去导出模型</el-button>
        </el-empty>
      </div>
    </div>

    <div v-if="filteredModels.length > 10" style="text-align:center;margin-top:16px">
      <el-pagination background layout="prev, pager, next" :total="filteredModels.length" :page-size="10" v-model:current-page="page" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import PageHeader from '@/components/common/PageHeader.vue'
import { trainingApi } from '@/api/training'

interface MergedModel { name: string; path: string; size: string; modified: string }
const loading = ref(false)
const models = ref<MergedModel[]>([])
const search = ref('')
const page = ref(1)

const filteredModels = computed(() => {
  const q = search.value.toLowerCase()
  if (!q) return models.value
  return models.value.filter(m => m.name.toLowerCase().includes(q) || m.path.toLowerCase().includes(q))
})
const paginatedModels = computed(() => filteredModels.value.slice((page.value-1)*10, page.value*10))

const loadModels = async () => {
  loading.value = true
  try {
    models.value = await trainingApi.listMergedModels()
  } catch (e: any) {
    ElMessage.error('加载失败: ' + e.message)
  } finally { loading.value = false }
}

onMounted(loadModels)
</script>

<style lang="scss" scoped>
.model-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 16px; }
.model-card .model-header { display: flex; justify-content: space-between; align-items: center; .model-name { font-weight: 600; font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 240px; } }
.model-actions { margin-top: 12px; display: flex; gap: 8px; }
.empty-hint { grid-column: 1 / -1; }
.search-input { margin-right: 8px; }
</style>
