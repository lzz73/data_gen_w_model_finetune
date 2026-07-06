<template>
  <div class="page-container">
    <PageHeader title="硬件仪表盘" />

    <div class="stat-row">
      <StatCard icon="Cpu" label="GPU总数" :value="4" color="#409eff" />
      <StatCard icon="Monitor" label="平均占用率" value="45%" color="#67c23a" />
      <StatCard icon="Timer" label="运行中任务" :value="2" color="#e6a23c" />
      <StatCard icon="CircleCheck" label="空闲GPU" :value="2" color="#909399" />
    </div>

    <div class="gpu-grid">
      <el-card v-for="gpu in gpuList" :key="gpu.name" class="gpu-card" shadow="hover">
        <div class="gpu-header">
          <span class="gpu-name">{{ gpu.name }}</span>
          <el-tag :type="gpu.status === '运行中' ? 'warning' : 'success'" size="small">{{ gpu.status }}</el-tag>
        </div>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="型号">{{ gpu.model }}</el-descriptions-item>
          <el-descriptions-item label="显存">{{ gpu.usedMem }} / {{ gpu.totalMem }}</el-descriptions-item>
          <el-descriptions-item label="显存占用">
            <el-progress :percentage="gpu.usedPercent" :color="gpu.usedPercent > 90 ? '#f56c6c' : gpu.usedPercent > 70 ? '#e6a23c' : '#67c23a'" :stroke-width="14" />
          </el-descriptions-item>
          <el-descriptions-item label="温度">{{ gpu.temp }}°C</el-descriptions-item>
          <el-descriptions-item label="功耗">{{ gpu.power }}W</el-descriptions-item>
          <el-descriptions-item v-if="gpu.task" label="当前任务">{{ gpu.task }}</el-descriptions-item>
        </el-descriptions>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import PageHeader from '@/components/common/PageHeader.vue'
import StatCard from '@/components/common/StatCard.vue'

const gpuList = [
  { name: 'GPU-0', model: 'NVIDIA A100 80GB', totalMem: '80GB', usedMem: '61GB', usedPercent: 76, temp: 68, power: 285, status: '运行中', task: '电力SFT-v3' },
  { name: 'GPU-1', model: 'NVIDIA A100 80GB', totalMem: '80GB', usedMem: '58GB', usedPercent: 72, temp: 65, power: 270, status: '运行中', task: '财务SFT-v1' },
  { name: 'GPU-2', model: 'NVIDIA A100 40GB', totalMem: '40GB', usedMem: '2GB', usedPercent: 5, temp: 35, power: 75, status: '空闲', task: '' },
  { name: 'GPU-3', model: 'NVIDIA A100 40GB', totalMem: '40GB', usedMem: '6GB', usedPercent: 15, temp: 38, power: 90, status: '空闲', task: '' },
]
</script>

<style lang="scss" scoped>
.gpu-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.gpu-card {
  .gpu-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;

    .gpu-name {
      font-weight: 600;
      font-size: 16px;
      color: #303133;
    }
  }
}
</style>
