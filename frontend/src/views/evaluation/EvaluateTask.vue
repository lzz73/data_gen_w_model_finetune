<template>
  <div class="page-container">
    <PageHeader title="评估任务">
      <el-button type="primary" @click="showCreateDialog = true">
        <el-icon><Plus /></el-icon>创建评估
      </el-button>
    </PageHeader>

    <div class="content-card">
      <el-table :data="evalTasks" stripe>
        <el-table-column prop="name" label="任务名称" />
        <el-table-column prop="model" label="评估模型" width="160" />
        <el-table-column prop="dataset" label="测试集" width="160" />
        <el-table-column prop="method" label="评估方式" width="120">
          <template #default="{ row }">
            <el-tag size="small">{{ row.method }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="score" label="综合得分" width="100">
          <template #default="{ row }">
            <el-text v-if="row.score" :type="row.score >= 80 ? 'success' : row.score >= 60 ? 'warning' : 'danger'" size="large" tag="b">
              {{ row.score }}
            </el-text>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === '已完成' ? 'success' : row.status === '评估中' ? 'primary' : 'info'" size="small">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="time" label="创建时间" width="180" />
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === '已完成'" link type="primary" size="small" @click="$router.push('/evaluation/report')">查看报告</el-button>
            <el-button v-if="row.status === '待评估'" link type="primary" size="small">启动</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 创建评估对话框 -->
    <el-dialog v-model="showCreateDialog" title="创建评估任务" width="550px">
      <el-form :model="evalForm" label-width="100px">
        <el-form-item label="任务名称">
          <el-input v-model="evalForm.name" placeholder="请输入任务名称" />
        </el-form-item>
        <el-form-item label="评估模型">
          <el-select v-model="evalForm.model" placeholder="选择已训练模型">
            <el-option label="电力SFT-Qwen2-7B-v3" value="power_sft_v3" />
            <el-option label="合同DPO-DeepSeek-7B-v2" value="contract_dpo_v2" />
          </el-select>
        </el-form-item>
        <el-form-item label="测试集">
          <el-select v-model="evalForm.dataset" placeholder="选择测试集">
            <el-option label="电力招标测试集 (78条)" value="power_test" />
            <el-option label="合同条款测试集 (29条)" value="contract_test" />
          </el-select>
        </el-form-item>
        <el-form-item label="评审模型">
          <el-select v-model="evalForm.judgeModel">
            <el-option label="Qwen2-7B-Instruct (本地)" value="qwen2-local" />
          </el-select>
        </el-form-item>
        <el-form-item label="人工复核">
          <el-switch v-model="evalForm.humanReview" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="showCreateDialog = false">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'

const showCreateDialog = ref(false)
const evalForm = reactive({ name: '', model: '', dataset: '', judgeModel: 'qwen2-local', humanReview: false })

const evalTasks = [
  { name: '电力SFT-v3评估', model: '电力SFT-Qwen2-7B-v3', dataset: '电力招标测试集', method: 'LLM评审', score: 82, status: '已完成', time: '2026-07-01 08:00' },
  { name: '合同DPO-v2评估', model: '合同DPO-DeepSeek-7B-v2', dataset: '合同条款测试集', method: 'LLM+人工', score: 75, status: '已完成', time: '2026-06-30 14:00' },
  { name: '财务SFT-v1评估', model: '财务SFT-Qwen2-7B-v1', dataset: '财务报表测试集', method: 'LLM评审', score: null, status: '评估中', time: '2026-06-29 10:00' },
  { name: '规章CPT-v1评估', model: '规章CPT-LLaMA3-8B-v1', dataset: '规章制度测试集', method: 'LLM评审', score: null, status: '待评估', time: '2026-06-28 16:00' },
]
</script>
