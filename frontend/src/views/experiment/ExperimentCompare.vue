<template>
  <div class="page-container">
    <PageHeader title="多实验对比" />

    <div class="content-card">
      <div class="card-title">选择实验</div>
      <el-select v-model="selectedExperiments" multiple placeholder="选择2-3个实验进行对比" style="width: 100%; max-width: 600px">
        <el-option label="电力SFT-v3 (82分)" value="v3" />
        <el-option label="电力SFT-v2 (75分)" value="v2" />
        <el-option label="电力SFT-v1 (62分)" value="v1" />
      </el-select>
    </div>

    <div v-if="selectedExperiments.length >= 2" class="content-card">
      <div class="card-title">超参数对比</div>
      <el-table :data="paramCompare" stripe border>
        <el-table-column prop="param" label="参数" width="140" />
        <el-table-column v-for="exp in selectedExperiments" :key="exp" :label="expLabel(exp)" width="160">
          <template #default="{ row }">
            <el-text :type="row[exp + '_highlight'] ? 'danger' : ''">{{ row[exp] }}</el-text>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div v-if="selectedExperiments.length >= 2" class="content-card">
      <div class="card-title">评估指标对比</div>
      <el-table :data="metricCompare" stripe border>
        <el-table-column prop="metric" label="指标" width="160" />
        <el-table-column v-for="exp in selectedExperiments" :key="exp" :label="expLabel(exp)">
          <template #default="{ row }">
            <el-text :type="row[exp] >= 80 ? 'success' : row[exp] >= 60 ? 'warning' : 'danger'" tag="b">{{ row[exp] }}%</el-text>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div v-if="selectedExperiments.length >= 2" class="content-card">
      <div class="card-title">错误分类变化</div>
      <el-table :data="errorCompare" stripe border>
        <el-table-column prop="type" label="错误类型" width="120" />
        <el-table-column v-for="exp in selectedExperiments" :key="exp" :label="expLabel(exp)">
          <template #default="{ row }">
            {{ row[exp] }}条
          </template>
        </el-table-column>
      </el-table>
      <el-alert type="success" :closable="false" show-icon style="margin-top: 12px">
        <template #title>本轮相比上轮：混淆错误下降60%，不完整错误下降25%</template>
      </el-alert>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'

const selectedExperiments = ref(['v3', 'v2'])

const expLabel = (exp: string) => {
  const map: Record<string, string> = { v3: '电力SFT-v3', v2: '电力SFT-v2', v1: '电力SFT-v1' }
  return map[exp] || exp
}

const paramCompare = [
  { param: '学习率', v3: '2e-5', v2: '3e-5', v1: '5e-5', v3_highlight: false, v2_highlight: false, v1_highlight: true },
  { param: '训练轮数', v3: '3', v2: '5', v1: '3', v3_highlight: false, v2_highlight: true, v1_highlight: false },
  { param: '批次大小', v3: '8', v2: '4', v1: '8', v3_highlight: false, v2_highlight: true, v1_highlight: false },
  { param: 'LoRA Rank', v3: '16', v2: '8', v1: '8', v3_highlight: true, v2_highlight: false, v1_highlight: false },
  { param: '截断长度', v3: '2048', v2: '1024', v1: '1024', v3_highlight: true, v2_highlight: false, v1_highlight: false },
]

const metricCompare = [
  { metric: '综合得分', v3: 82, v2: 75, v1: 62 },
  { metric: '核心事实正确性', v3: 85, v2: 78, v1: 65 },
  { metric: '信息完整性', v3: 72, v2: 68, v1: 55 },
  { metric: '无幻觉', v3: 90, v2: 82, v1: 70 },
  { metric: '格式合规性', v3: 78, v2: 72, v1: 58 },
]

const errorCompare = [
  { type: '混淆', v3: 8, v2: 20, v1: 35 },
  { type: '不完整', v3: 6, v2: 8, v1: 15 },
  { type: '幻觉', v3: 4, v2: 6, v1: 10 },
  { type: '格式偏差', v3: 3, v2: 5, v1: 8 },
  { type: '其他', v3: 1, v2: 2, v1: 5 },
]
</script>
