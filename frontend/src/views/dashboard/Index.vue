<template>
  <div class="page-container">
    <!-- 统计卡片 -->
    <div class="stat-row">
      <StatCard icon="FolderOpened" label="数据集" :value="12" color="#409eff" :trend="8" />
      <StatCard icon="Cpu" label="训练任务" :value="5" color="#67c23a" :trend="20" />
      <StatCard icon="Box" label="模型数量" :value="8" color="#e6a23c" :trend="-5" />
      <StatCard icon="Monitor" label="GPU利用率" value="73%" color="#f56c6c" :trend="12" />
    </div>

    <el-row :gutter="16">
      <!-- 最近任务 -->
      <el-col :span="16">
        <div class="content-card">
          <div class="card-title">最近任务</div>
          <el-table :data="recentTasks" stripe>
            <el-table-column prop="name" label="任务名称" />
            <el-table-column prop="type" label="类型" width="120">
              <template #default="{ row }">
                <el-tag :type="row.type === 'SFT' ? 'primary' : row.type === 'DPO' ? 'success' : 'warning'" size="small">
                  {{ row.type }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="model" label="基座模型" width="160" />
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="time" label="创建时间" width="180" />
          </el-table>
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
import StatCard from '@/components/common/StatCard.vue'

const recentTasks = [
  { name: '电力文档SFT微调-v3', type: 'SFT', model: 'Qwen2-7B', status: '训练中', time: '2026-07-01 10:30' },
  { name: '合同条款DPO对齐-v2', type: 'DPO', model: 'DeepSeek-7B', status: '已完成', time: '2026-06-30 14:20' },
  { name: '招标文件CPT预训练-v1', type: 'CPT', model: 'LLaMA3-8B', status: '已完成', time: '2026-06-29 09:15' },
  { name: '财务报表SFT微调-v1', type: 'SFT', model: 'Qwen2-7B', status: '失败', time: '2026-06-28 16:45' },
  { name: '规章制度SFT微调-v2', type: 'SFT', model: 'Qwen2-14B', status: '待评估', time: '2026-06-27 11:00' },
]

const statusType = (status: string) => {
  const map: Record<string, string> = { '训练中': 'primary', '已完成': 'success', '失败': 'danger', '待评估': 'warning' }
  return map[status] || 'info'
}
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

    &:hover {
      background: #f5f7fa;
    }

    span {
      font-size: 13px;
      color: #606266;
    }
  }
}
</style>
