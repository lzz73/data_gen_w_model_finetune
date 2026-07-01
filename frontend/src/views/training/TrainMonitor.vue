<template>
  <div class="page-container">
    <PageHeader title="训练监控" />

    <!-- 训练概览 -->
    <div class="stat-row">
      <StatCard icon="Timer" label="训练进度" value="68%" color="#409eff" />
      <StatCard icon="TrendCharts" label="当前Loss" value="0.342" color="#67c23a" :trend="-15" />
      <StatCard icon="Monitor" label="GPU占用" value="76%" color="#e6a23c" />
      <StatCard icon="Clock" label="预计剩余" value="2h 15m" color="#909399" />
    </div>

    <el-row :gutter="16">
      <!-- Loss曲线 -->
      <el-col :span="16">
        <div class="content-card">
          <div class="card-title">Loss曲线</div>
          <LossChart />
        </div>
      </el-col>

      <!-- GPU监控 -->
      <el-col :span="8">
        <div class="content-card">
          <div class="card-title">GPU状态</div>
          <div v-for="gpu in gpuStatus" :key="gpu.name" class="gpu-item">
            <div class="gpu-header">
              <span class="gpu-name">{{ gpu.name }}</span>
              <span class="gpu-mem">{{ gpu.usedMem }} / {{ gpu.totalMem }}</span>
            </div>
            <el-progress :percentage="gpu.usedPercent" :color="gpu.usedPercent > 90 ? '#f56c6c' : '#409eff'" :stroke-width="12" />
            <div class="gpu-detail">
              <span>温度: {{ gpu.temp }}°C</span>
              <span>功耗: {{ gpu.power }}W</span>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 训练日志 -->
    <div class="content-card">
      <div class="card-title">训练日志</div>
      <div class="log-container">
        <div v-for="(log, i) in logs" :key="i" class="log-line" :class="log.type">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-msg">{{ log.msg }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import PageHeader from '@/components/common/PageHeader.vue'
import StatCard from '@/components/common/StatCard.vue'
import LossChart from '@/components/charts/LossChart.vue'

const gpuStatus = [
  { name: 'GPU-0 (A100 80GB)', totalMem: '80GB', usedMem: '61GB', usedPercent: 76, temp: 68, power: 285 },
  { name: 'GPU-1 (A100 80GB)', totalMem: '80GB', usedMem: '58GB', usedPercent: 72, temp: 65, power: 270 },
]

const logs = [
  { time: '10:30:00', msg: '[INFO] 训练任务启动: 电力文档SFT微调-v3', type: 'info' },
  { time: '10:30:05', msg: '[INFO] 加载数据集: power_sft_v3 (1200 samples)', type: 'info' },
  { time: '10:30:12', msg: '[INFO] 加载基座模型: Qwen2-7B', type: 'info' },
  { time: '10:30:45', msg: '[INFO] LoRA adapter 初始化完成, Rank=16, Alpha=32', type: 'info' },
  { time: '10:31:00', msg: '[INFO] Step 10/500, Loss: 1.856, LR: 2e-5', type: 'info' },
  { time: '10:35:00', msg: '[INFO] Step 50/500, Loss: 1.234, LR: 2e-5', type: 'info' },
  { time: '10:40:00', msg: '[INFO] Step 100/500, Loss: 0.876, LR: 1.8e-5', type: 'info' },
  { time: '10:45:00', msg: '[WARN] GPU-0 显存使用率达到 85%', type: 'warn' },
  { time: '10:50:00', msg: '[INFO] Step 200/500, Loss: 0.523, LR: 1.5e-5', type: 'info' },
  { time: '10:55:00', msg: '[INFO] Step 300/500, Loss: 0.412, LR: 1.2e-5', type: 'info' },
  { time: '11:00:00', msg: '[INFO] Step 340/500, Loss: 0.342, LR: 1.0e-5', type: 'info' },
]
</script>

<style lang="scss" scoped>
.gpu-item {
  margin-bottom: 16px;

  .gpu-header {
    display: flex;
    justify-content: space-between;
    margin-bottom: 6px;

    .gpu-name { font-size: 13px; color: #303133; font-weight: 500; }
    .gpu-mem { font-size: 12px; color: #909399; }
  }

  .gpu-detail {
    display: flex;
    gap: 16px;
    margin-top: 4px;
    font-size: 12px;
    color: #909399;
  }
}

.log-container {
  max-height: 300px;
  overflow-y: auto;
  background: #1e1e1e;
  border-radius: 6px;
  padding: 12px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;

  .log-line {
    padding: 2px 0;
    display: flex;
    gap: 12px;

    .log-time { color: #6a9955; flex-shrink: 0; }
    .log-msg { color: #d4d4d4; }

    &.warn .log-msg { color: #e6a23c; }
    &.error .log-msg { color: #f56c6c; }
  }
}
</style>
