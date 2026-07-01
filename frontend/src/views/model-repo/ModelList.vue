<template>
  <div class="page-container">
    <PageHeader title="模型列表" />

    <div class="model-grid">
      <el-card v-for="model in models" :key="model.id" class="model-card" shadow="hover">
        <template #header>
          <div class="model-header">
            <span class="model-name">{{ model.name }}</span>
            <el-tag :type="model.status === '已注册' ? 'success' : model.status === '训练中' ? 'warning' : 'info'" size="small">
              {{ model.status }}
            </el-tag>
          </div>
        </template>
        <el-descriptions :column="1" size="small">
          <el-descriptions-item label="训练模式">{{ model.trainMode }}</el-descriptions-item>
          <el-descriptions-item label="基座模型">{{ model.baseModel }}</el-descriptions-item>
          <el-descriptions-item label="数据版本">{{ model.dataVersion }}</el-descriptions-item>
          <el-descriptions-item label="评估得分">
            <el-text :type="model.score >= 80 ? 'success' : 'warning'" tag="b">{{ model.score }}分</el-text>
          </el-descriptions-item>
          <el-descriptions-item label="关键超参">LR={{ model.lr }}, Rank={{ model.rank }}</el-descriptions-item>
          <el-descriptions-item label="注册时间">{{ model.time }}</el-descriptions-item>
        </el-descriptions>
        <div class="model-actions">
          <el-button size="small" type="primary" @click="$router.push('/model-repo/export')">导出</el-button>
          <el-button size="small" @click="$router.push('/model-repo/verify')">验证</el-button>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import PageHeader from '@/components/common/PageHeader.vue'

const models = [
  { id: 1, name: '电力SFT-Qwen2-7B-v3', trainMode: 'SFT', baseModel: 'Qwen2-7B', dataVersion: 'power_sft_v3', score: 82, lr: '2e-5', rank: 16, status: '已注册', time: '2026-07-01' },
  { id: 2, name: '合同DPO-DeepSeek-7B-v2', trainMode: 'DPO', baseModel: 'DeepSeek-7B', dataVersion: 'contract_dpo_v2', score: 75, lr: '1e-5', rank: 32, status: '已注册', time: '2026-06-30' },
  { id: 3, name: '规章CPT-LLaMA3-8B-v1', trainMode: 'CPT', baseModel: 'LLaMA3-8B', dataVersion: 'rules_cpt_v1', score: 68, lr: '5e-5', rank: 8, status: '已注册', time: '2026-06-29' },
  { id: 4, name: '财务SFT-Qwen2-7B-v1', trainMode: 'SFT', baseModel: 'Qwen2-7B', dataVersion: 'finance_sft_v1', score: 0, lr: '2e-5', rank: 16, status: '训练中', time: '2026-06-28' },
]
</script>

<style lang="scss" scoped>
.model-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}

.model-card {
  .model-header {
    display: flex;
    justify-content: space-between;
    align-items: center;

    .model-name {
      font-weight: 600;
      font-size: 15px;
      color: #303133;
    }
  }

  .model-actions {
    margin-top: 12px;
    display: flex;
    gap: 8px;
  }
}
</style>
