<template>
  <div class="page-container">
    <!-- 统计卡片 -->
    <div class="stat-row">
      <StatCard icon="FolderOpened" label="数据集" :value="stats.dataset_count" color="#409eff" />
      <StatCard icon="Cpu" label="训练中" :value="stats.training_running" color="#67c23a" />
      <StatCard icon="Box" label="已完成" :value="stats.training_completed" color="#e6a23c" />
      <StatCard icon="Monitor" label="GPU利用率" :value="stats.gpu_utilization + '%'" color="#f56c6c" />
    </div>

    <el-row :gutter="16">
      <!-- 最近任务 -->
      <el-col :span="16">
        <div class="content-card">
          <div class="card-title">最近任务</div>
          <el-table :data="stats.recent_tasks" stripe v-loading="loading">
            <el-table-column prop="name" label="任务名称" />
            <el-table-column prop="type" label="类型" width="120">
              <template #default="{ row }">
                <el-tag :type="row.type === 'SFT' ? 'primary' : row.type === 'DPO' ? 'success' : 'warning'" size="small">
                  {{ row.type }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="model" label="基座模型" width="200">
              <template #default="{ row }">
                <el-text size="small" truncated>{{ row.model }}</el-text>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="time" label="创建时间" width="180" />
          </el-table>
          <div v-if="stats.recent_tasks.length === 0 && !loading" style="text-align:center;color:#909399;padding:20px">
            暂无训练任务，前往<el-link type="primary" @click="$router.push('/training/workbench')">训练工作台</el-link>创建
          </div>
        </div>
      </el-col>

      <!-- 快捷入口 -->
      <el-col :span="8">
        <div class="content-card">
          <div class="card-title">快捷入口</div>
          <div class="quick-links">
            <div class="quick-link" @click="$router.push('/data-governance/source')">
              <el-icon :size="28" color="#409eff"><Upload /></el-icon>
              <span>数据接入</span>
            </div>
            <div class="quick-link" @click="$router.push('/training/workbench')">
              <el-icon :size="28" color="#67c23a"><Cpu /></el-icon>
              <span>创建训练</span>
            </div>
            <div class="quick-link" @click="$router.push('/evaluation/task')">
              <el-icon :size="28" color="#e6a23c"><DataLine /></el-icon>
              <span>模型评估</span>
            </div>
            <div class="quick-link" @click="$router.push('/model-repo/list')">
              <el-icon :size="28" color="#f56c6c"><Box /></el-icon>
              <span>模型仓库</span>
            </div>
            <div class="quick-link" @click="$router.push('/experiment/list')">
              <el-icon :size="28" color="#909399"><TrendCharts /></el-icon>
              <span>实验记录</span>
            </div>
            <div class="quick-link" @click="$router.push('/system/gpu')">
              <el-icon :size="28" color="#9b59b6"><Monitor /></el-icon>
              <span>GPU监控</span>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import StatCard from '@/components/common/StatCard.vue'
import { fetchDashboard } from '@/api/training'

const loading = ref(true)

const stats = reactive({
  dataset_count: 0,
  training_running: 0,
  training_completed: 0,
  gpu_utilization: 0,
  recent_tasks: [] as any[],
})

const statusType = (status: string) => {
  const map: Record<string, string> = { '训练中': 'primary', '已完成': 'success', '失败': 'danger', '排队中': 'warning', '已取消': 'info' }
  return map[status] || 'info'
}

const loadDashboard = async () => {
  loading.value = true
  try {
    const res = await fetchDashboard()
    if (res.code === 0) {
      Object.assign(stats, res.data)
    }
  } catch (e) {
    console.error('加载仪表盘失败', e)
  } finally {
    loading.value = false
  }
}

onMounted(loadDashboard)
</script>

<style lang="scss" scoped>
.quick-links {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  .quick-link {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    padding: 20px 10px;
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.3s;
    &:hover { background: #f5f7fa; }
    span { font-size: 13px; color: #606266; }
  }
}
</style>
