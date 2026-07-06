<template>
  <div class="page-container">
    <!-- 统计卡片 -->
    <div class="stat-row">
      <StatCard icon="FolderOpened" label="文件数" :value="stats.file_count" color="#409eff" />
      <StatCard icon="Document" label="文本分块" :value="stats.chunk_count" color="#67c23a" />
      <StatCard icon="ChatDotRound" label="问答对" :value="stats.question_count" color="#e6a23c" />
      <StatCard icon="DataLine" label="数据集" :value="stats.dataset_count" color="#f56c6c" />
    </div>

    <el-row :gutter="16">
      <!-- 项目列表 -->
      <el-col :span="16">
        <div class="content-card">
          <div class="card-header">
            <span class="card-title">项目列表</span>
            <el-button type="primary" size="small" @click="showCreateDialog = true">
              <el-icon><Plus /></el-icon> 创建项目
            </el-button>
          </div>
          <el-table
            :data="projectStore.projects"
            stripe
            v-loading="projectStore.loading"
            highlight-current-row
            :row-class-name="rowClassName"
            @row-click="handleSelectProject"
            style="cursor: pointer;"
          >
            <el-table-column prop="name" label="项目名称">
              <template #default="{ row }">
                <div style="display: flex; align-items: center; gap: 6px;">
                  <el-icon v-if="projectStore.currentProjectId === row.id" color="#409eff" :size="16"><CircleCheckFilled /></el-icon>
                  <span :style="{ fontWeight: projectStore.currentProjectId === row.id ? '600' : 'normal' }">{{ row.name }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="描述" show-overflow-tooltip />
            <el-table-column label="创建时间" width="180">
              <template #default="{ row }">
                {{ formatDateTime(row.created_at) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button
                  type="danger"
                  size="small"
                  link
                  @click.stop="handleDeleteProject(row)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- 空状态 -->
          <EmptyState
            v-if="!projectStore.loading && projectStore.projects.length === 0"
            description="暂无项目，创建一个开始吧"
            action-text="创建项目"
            @action="showCreateDialog = true"
          />
        </div>
      </el-col>

      <!-- 右侧面板 -->
      <el-col :span="8">
        <!-- 当前项目信息卡片 -->
        <div v-if="projectStore.currentProject" class="content-card current-project-card">
          <div class="current-project-header">
            <el-icon :size="20" color="#409eff"><FolderOpened /></el-icon>
            <span class="current-project-title">当前项目</span>
          </div>
          <h3 class="current-project-name">{{ projectStore.currentProject.name }}</h3>
          <p class="current-project-desc">{{ projectStore.currentProject.description || '暂无描述' }}</p>

          <!-- 项目数据概览 -->
          <div class="project-stats-grid">
            <div class="project-stat">
              <span class="stat-value">{{ stats.file_count }}</span>
              <span class="stat-label">文件</span>
            </div>
            <div class="project-stat">
              <span class="stat-value">{{ stats.chunk_count }}</span>
              <span class="stat-label">分块</span>
            </div>
            <div class="project-stat">
              <span class="stat-value">{{ stats.question_count }}</span>
              <span class="stat-label">问答</span>
            </div>
            <div class="project-stat">
              <span class="stat-value">{{ stats.dataset_count }}</span>
              <span class="stat-label">数据集</span>
            </div>
          </div>

          <!-- 快速操作 -->
          <div class="project-actions">
            <el-button type="primary" size="small" @click="$router.push('/data-governance/source')">
              <el-icon><Upload /></el-icon> 上传文件
            </el-button>
            <el-button size="small" @click="$router.push('/data-governance/unstructured')">
              <el-icon><Scissor /></el-icon> 切片处理
            </el-button>
            <el-button size="small" @click="$router.push('/data-governance/qa-generate')">
              <el-icon><ChatDotRound /></el-icon> 生成问答
            </el-button>
          </div>
        </div>

        <!-- 未选择项目提示 -->
        <div v-else class="content-card no-project-card">
          <el-icon :size="48" color="#c0c4cc"><FolderOpened /></el-icon>
          <h3>选择或创建项目</h3>
          <p>点击左侧项目列表中的项目进入工作区</p>
          <el-button type="primary" size="small" @click="showCreateDialog = true">
            <el-icon><Plus /></el-icon> 创建新项目
          </el-button>
        </div>

        <!-- 快捷入口 -->
        <div class="content-card" style="margin-top: 16px;">
          <div class="card-title">快捷入口</div>
          <div class="quick-links">
            <div class="quick-link" @click="$router.push('/data-governance/source')">
              <el-icon :size="24" color="#409eff"><Upload /></el-icon>
              <span>数据接入</span>
            </div>
            <div class="quick-link" @click="$router.push('/training/workbench')">
              <el-icon :size="24" color="#67c23a"><Cpu /></el-icon>
              <span>创建训练</span>
            </div>
            <div class="quick-link" @click="$router.push('/evaluation/task')">
              <el-icon :size="24" color="#e6a23c"><DataLine /></el-icon>
              <span>模型评估</span>
            </div>
            <div class="quick-link" @click="$router.push('/model-repo/list')">
              <el-icon :size="24" color="#f56c6c"><Box /></el-icon>
              <span>模型配置</span>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 创建项目对话框 -->
    <CreateProjectDialog
      v-model:visible="showCreateDialog"
      @created="handleProjectCreated"
    />

    <!-- 删除确认对话框 -->
    <DeleteDialog
      v-model:visible="showDeleteDialog"
      :item-name="deleteTarget?.name"
      item-type="项目"
      :loading="deleteLoading"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { projectApi } from '@/api'
import { formatDateTime } from '@/composables/useFormatters'
import { ElMessage } from 'element-plus'
import StatCard from '@/components/common/StatCard.vue'
import CreateProjectDialog from '@/components/common/CreateProjectDialog.vue'
import DeleteDialog from '@/components/common/DeleteDialog.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import { Plus } from '@element-plus/icons-vue'
import type { Project } from '@/types'

const router = useRouter()
const projectStore = useProjectStore()

const showCreateDialog = ref(false)
const showDeleteDialog = ref(false)
const deleteTarget = ref<Project | null>(null)
const deleteLoading = ref(false)

const stats = computed(() => projectStore.currentStats || {
  file_count: 0, chunk_count: 0, question_count: 0, dataset_count: 0, eval_count: 0
})

const rowClassName = ({ row }: { row: Project }) => {
  return projectStore.currentProjectId === row.id ? 'current-project-row' : ''
}

onMounted(async () => {
  try {
    await projectStore.fetchProjects()
  } catch (e: any) {
    ElMessage.error('加载项目列表失败: ' + (e?.message || '未知错误'))
  }
})

const handleSelectProject = async (row: Project) => {
  await projectStore.setCurrentProject(row.id)
  ElMessage.success(`已进入项目：${row.name}`)
  router.push('/data-governance/source')
}

const handleProjectCreated = async (id: string) => {
  await projectStore.fetchProjects()
  if (id) {
    await projectStore.setCurrentProject(id)
    router.push('/data-governance/source')
  }
}

const handleDeleteProject = (row: Project) => {
  deleteTarget.value = row
  showDeleteDialog.value = true
}

const confirmDelete = async () => {
  if (!deleteTarget.value) return
  deleteLoading.value = true
  try {
    await projectApi.delete(deleteTarget.value.id)
    ElMessage.success('删除成功')
    if (projectStore.currentProjectId === deleteTarget.value.id) {
      projectStore.clearCurrentProject()
    }
    await projectStore.fetchProjects()
    showDeleteDialog.value = false
  } catch (error: any) {
    ElMessage.error(error?.message || '删除失败')
  } finally {
    deleteLoading.value = false
  }
}
</script>

<style lang="scss" scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;

  .card-title {
    margin-bottom: 0;
  }
}

.current-project-card {
  border-left: 3px solid #409eff;

  .current-project-header {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 12px;

    .current-project-title {
      font-size: 13px;
      color: #409eff;
      font-weight: 500;
    }
  }

  .current-project-name {
    margin: 0 0 6px 0;
    font-size: 18px;
    color: #303133;
  }

  .current-project-desc {
    color: #909399;
    font-size: 13px;
    margin: 0 0 12px 0;
  }

  .project-stats-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    margin-top: 16px;
    padding: 12px;
    background: #f5f7fa;
    border-radius: 8px;

    .project-stat {
      display: flex;
      flex-direction: column;
      align-items: center;

      .stat-value {
        font-size: 20px;
        font-weight: 600;
        color: #303133;
      }

      .stat-label {
        font-size: 12px;
        color: #909399;
      }
    }
  }

  .project-actions {
    margin-top: 16px;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
}

.no-project-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 32px 20px;
  text-align: center;

  h3 {
    margin: 12px 0 4px 0;
    font-size: 15px;
    color: #606266;
  }

  p {
    color: #909399;
    font-size: 13px;
    margin: 0 0 16px 0;
  }
}

.quick-links {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;

  .quick-link {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    padding: 16px 10px;
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.3s;

    &:hover {
      background: #f5f7fa;
    }

    span {
      font-size: 13px;
      color: #606266;
    }
  }
}

:deep(.current-project-row) {
  background-color: #ecf5ff !important;
  td {
    border-left: 2px solid #409eff;
  }
}
</style>
