<template>
  <div class="page-container">
    <PageHeader title="实验记录" />

    <div class="content-card">
      <el-table :data="experiments" stripe>
        <el-table-column type="selection" width="50" />
        <el-table-column prop="name" label="实验名称" />
        <el-table-column prop="mode" label="训练模式" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ row.mode }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="baseModel" label="基座模型" width="140" />
        <el-table-column prop="dataVersion" label="数据版本" width="140" />
        <el-table-column prop="score" label="评估得分" width="100">
          <template #default="{ row }">
            <el-text :type="row.score >= 80 ? 'success' : 'warning'" tag="b">{{ row.score }}分</el-text>
          </template>
        </el-table-column>
        <el-table-column prop="duration" label="训练耗时" width="100" />
        <el-table-column prop="time" label="创建时间" width="180" />
        <el-table-column prop="tags" label="标签" width="150">
          <template #default="{ row }">
            <el-tag v-for="tag in row.tags" :key="tag" size="small" type="info" style="margin-right: 4px">{{ tag }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default>
            <el-button link type="primary" size="small">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import PageHeader from '@/components/common/PageHeader.vue'

const experiments = [
  { name: '电力SFT-v3', mode: 'SFT', baseModel: 'Qwen2-7B', dataVersion: 'power_sft_v3', score: 82, duration: '3h 20m', time: '2026-07-01 10:00', tags: ['最佳', '生产'] },
  { name: '电力SFT-v2', mode: 'SFT', baseModel: 'Qwen2-7B', dataVersion: 'power_sft_v2', score: 75, duration: '3h 15m', time: '2026-06-28 09:00', tags: ['基线'] },
  { name: '合同DPO-v2', mode: 'DPO', baseModel: 'DeepSeek-7B', dataVersion: 'contract_dpo_v2', score: 75, duration: '4h 10m', time: '2026-06-30 14:00', tags: ['偏好对齐'] },
  { name: '规章CPT-v1', mode: 'CPT', baseModel: 'LLaMA3-8B', dataVersion: 'rules_cpt_v1', score: 68, duration: '6h 30m', time: '2026-06-29 09:00', tags: ['预训练'] },
  { name: '电力SFT-v1', mode: 'SFT', baseModel: 'Qwen2-7B', dataVersion: 'power_sft_v1', score: 62, duration: '2h 50m', time: '2026-06-25 10:00', tags: ['初版'] },
]
</script>
