<template>
  <div class="page-container">
    <PageHeader title="日志管理" />

    <div class="content-card">
      <div class="card-title">日志筛选</div>
      <el-form inline size="small">
        <el-form-item label="时间范围">
          <el-date-picker v-model="dateRange" type="datetimerange" range-separator="至" start-placeholder="开始时间" end-placeholder="结束时间" />
        </el-form-item>
        <el-form-item label="日志级别">
          <el-select v-model="logLevel" multiple placeholder="全部" style="width: 200px">
            <el-option label="INFO" value="info" />
            <el-option label="WARN" value="warn" />
            <el-option label="ERROR" value="error" />
          </el-select>
        </el-form-item>
        <el-form-item label="任务名称">
          <el-input v-model="taskName" placeholder="搜索任务名称" clearable />
        </el-form-item>
        <el-form-item>
          <el-button type="primary">查询</el-button>
          <el-button>重置</el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="content-card">
      <div class="card-title">日志列表</div>
      <el-table :data="logs" stripe>
        <el-table-column prop="time" label="时间" width="180" />
        <el-table-column prop="level" label="级别" width="80">
          <template #default="{ row }">
            <el-tag :type="row.level === 'ERROR' ? 'danger' : row.level === 'WARN' ? 'warning' : 'info'" size="small">
              {{ row.level }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="task" label="任务" width="200" />
        <el-table-column prop="message" label="日志内容" show-overflow-tooltip />
        <el-table-column label="操作" width="100">
          <template #default>
            <el-button link type="primary" size="small">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination">
        <el-pagination background layout="total, prev, pager, next" :total="156" :page-size="20" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'

const dateRange = ref(null)
const logLevel = ref([])
const taskName = ref('')

const logs = [
  { time: '2026-07-01 10:30:00', level: 'INFO', task: '电力SFT-v3', message: '训练任务启动，加载数据集 power_sft_v3' },
  { time: '2026-07-01 10:30:05', level: 'INFO', task: '电力SFT-v3', message: '基座模型 Qwen2-7B 加载完成' },
  { time: '2026-07-01 10:45:00', level: 'WARN', task: '电力SFT-v3', message: 'GPU-0 显存使用率达到 85%' },
  { time: '2026-06-30 14:20:00', level: 'INFO', task: '合同DPO-v2', message: '训练任务完成，最终Loss: 0.312' },
  { time: '2026-06-28 16:50:00', level: 'ERROR', task: '财务SFT-v1', message: 'CUDA out of memory，训练中断' },
  { time: '2026-06-28 16:50:01', level: 'ERROR', task: '财务SFT-v1', message: '建议降低批次大小或截断长度后重试' },
]
</script>

<style lang="scss" scoped>
.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
