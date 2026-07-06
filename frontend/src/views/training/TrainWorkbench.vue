<template>
  <div class="page-container">
    <PageHeader title="训练工作台" />

    <!-- 步骤条 -->
    <div class="content-card">
      <el-steps :active="currentStep" finish-status="success" align-center>
        <el-step title="训练模式" />
        <el-step title="数据选择" />
        <el-step title="基座模型" />
        <el-step title="参数配置" />
        <el-step title="GPU选择" />
      </el-steps>
    </div>

    <!-- Step 1: 训练模式 -->
    <div v-if="currentStep === 0" class="content-card">
      <div class="card-title">选择训练模式</div>
      <el-radio-group v-model="trainConfig.mode" size="large">
        <el-radio-button value="sft">SFT 指令微调</el-radio-button>
        <el-radio-button value="dpo">DPO 偏好对齐</el-radio-button>
        <el-radio-button value="cpt">CPT 继续预训练</el-radio-button>
        <el-radio-button value="cot">思维链微调</el-radio-button>
      </el-radio-group>
      <div class="mode-info">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="模式说明">{{ modeDescriptions[trainConfig.mode] }}</el-descriptions-item>
        </el-descriptions>
      </div>
    </div>

    <!-- Step 2: 数据选择 -->
    <div v-if="currentStep === 1" class="content-card">
      <div class="card-title">选择数据版本</div>
      <el-form label-width="100px">
        <el-form-item label="数据集">
          <el-select v-model="trainConfig.dataset" placeholder="请选择数据集" style="width: 100%">
            <el-option
              v-for="d in availableDatasets"
              :key="d.id"
              :label="`${d.name} (${d.question_count || 0}条)`"
              :value="d.id"
            />
            <template #empty>
              <div style="padding: 10px; color: #909399;">暂无数据集，请先在数据治理中创建</div>
            </template>
          </el-select>
        </el-form-item>
        <el-form-item label="格式匹配">
          <el-tag type="success" size="small">✓ 数据格式与所选模式匹配</el-tag>
        </el-form-item>
      </el-form>
    </div>

    <!-- Step 3: 基座模型 -->
    <div v-if="currentStep === 2" class="content-card">
      <div class="card-title">选择基座模型</div>
      <el-radio-group v-model="trainConfig.baseModel">
        <el-card v-for="model in baseModels" :key="model.value" class="model-card" :class="{ selected: trainConfig.baseModel === model.value }" @click="trainConfig.baseModel = model.value">
          <div class="model-name">{{ model.label }}</div>
          <div class="model-info">{{ model.desc }}</div>
        </el-card>
      </el-radio-group>
    </div>

    <!-- Step 4: 参数配置 -->
    <div v-if="currentStep === 3" class="content-card">
      <div class="card-title">参数配置</div>
      <el-form :model="trainConfig" label-width="120px" size="small">
        <el-form-item label="参数预设">
          <el-radio-group v-model="trainConfig.preset">
            <el-radio-button value="quick">快速验证</el-radio-button>
            <el-radio-button value="standard">标准训练</el-radio-button>
            <el-radio-button value="high">高精度训练</el-radio-button>
            <el-radio-button value="custom">自定义</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="学习率">
              <el-input v-model="trainConfig.lr" :disabled="trainConfig.preset !== 'custom'" />
            </el-form-item>
            <el-form-item label="训练轮数">
              <el-input-number v-model="trainConfig.epochs" :min="1" :max="50" :disabled="trainConfig.preset !== 'custom'" />
            </el-form-item>
            <el-form-item label="批次大小">
              <el-input-number v-model="trainConfig.batchSize" :min="1" :max="128" :disabled="trainConfig.preset !== 'custom'" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="截断长度">
              <el-input-number v-model="trainConfig.maxLength" :min="128" :max="8192" :step="128" :disabled="trainConfig.preset !== 'custom'" />
            </el-form-item>
            <el-form-item label="LoRA Rank">
              <el-input-number v-model="trainConfig.loraRank" :min="4" :max="128" :disabled="trainConfig.preset !== 'custom'" />
            </el-form-item>
            <el-form-item label="LoRA Alpha">
              <el-input-number v-model="trainConfig.loraAlpha" :min="8" :max="256" :disabled="trainConfig.preset !== 'custom'" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </div>

    <!-- Step 5: GPU选择 -->
    <div v-if="currentStep === 4" class="content-card">
      <div class="card-title">GPU选择与硬件自检</div>
      <el-table :data="gpuList" stripe @row-click="selectGpu">
        <el-table-column type="selection" width="50" />
        <el-table-column prop="name" label="GPU" />
        <el-table-column prop="model" label="型号" width="160" />
        <el-table-column prop="totalMem" label="总显存" width="100" />
        <el-table-column label="已用显存" width="160">
          <template #default="{ row }">
            <el-progress :percentage="row.usedPercent" :color="row.usedPercent > 90 ? '#f56c6c' : row.usedPercent > 70 ? '#e6a23c' : '#67c23a'" :stroke-width="10" />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.usedPercent > 90 ? 'danger' : 'success'" size="small">
              {{ row.usedPercent > 90 ? '繁忙' : '可用' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
      <el-alert v-if="hardwareCheck" :type="hardwareCheck.type" :title="hardwareCheck.msg" show-icon :closable="false" style="margin-top: 16px" />
    </div>

    <!-- 操作按钮 -->
    <div class="step-actions">
      <el-button v-if="currentStep > 0" @click="currentStep--">上一步</el-button>
      <el-button v-if="currentStep < 4" type="primary" @click="currentStep++">下一步</el-button>
      <el-button v-if="currentStep === 4" type="success" @click="submitTask">
        <el-icon><VideoPlay /></el-icon>提交训练
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useProjectStore } from '@/stores/project'
import { datasetApi } from '@/api'
import PageHeader from '@/components/common/PageHeader.vue'
import { ElMessage } from 'element-plus'
import type { Dataset } from '@/types'

const projectStore = useProjectStore()
const currentStep = ref(0)
const availableDatasets = ref<Dataset[]>([])

const trainConfig = reactive({
  mode: 'sft',
  dataset: '',
  baseModel: 'qwen2-7b',
  preset: 'standard',
  lr: '2e-5',
  epochs: 3,
  batchSize: 8,
  maxLength: 2048,
  loraRank: 16,
  loraAlpha: 32,
  gpu: 'gpu-0',
})

const modeDescriptions: Record<string, string> = {
  sft: '指令微调：使用指令-回复对数据训练模型，适用于特定任务场景的模型定制',
  dpo: '偏好对齐：使用偏好对比数据训练模型，使模型输出更符合人类偏好',
  cpt: '继续预训练：使用领域语料继续预训练，注入领域知识',
  cot: '思维链微调：训练模型展示推理过程，提升复杂问题的推理能力',
}

const baseModels = [
  { value: 'qwen2-7b', label: 'Qwen2-7B', desc: '通义千问2代 7B参数，中文能力强' },
  { value: 'qwen2-14b', label: 'Qwen2-14B', desc: '通义千问2代 14B参数，效果更优' },
  { value: 'deepseek-7b', label: 'DeepSeek-7B', desc: 'DeepSeek 7B参数，代码能力强' },
  { value: 'llama3-8b', label: 'LLaMA3-8B', desc: 'Meta LLaMA3 8B参数，英文能力强' },
]

const gpuList = [
  { name: 'GPU-0', model: 'NVIDIA A100 80GB', totalMem: '80GB', usedPercent: 25 },
  { name: 'GPU-1', model: 'NVIDIA A100 80GB', totalMem: '80GB', usedPercent: 45 },
  { name: 'GPU-2', model: 'NVIDIA A100 40GB', totalMem: '40GB', usedPercent: 92 },
  { name: 'GPU-3', model: 'NVIDIA A100 40GB', totalMem: '40GB', usedPercent: 15 },
]

const hardwareCheck = computed(() => {
  const selected = gpuList.find(g => g.name === trainConfig.gpu)
  if (!selected) return null
  if (selected.usedPercent > 90) return { type: 'error' as const, msg: '显存不足：所选GPU可用显存不足，请更换GPU或降低参数' }
  if (selected.usedPercent > 70) return { type: 'warning' as const, msg: '显存预警：预估显存占用接近可用上限，建议降低批次大小或截断长度' }
  return { type: 'success' as const, msg: '硬件自检通过：显存充足，可以开始训练' }
})

const fetchDatasets = async () => {
  if (!projectStore.currentProjectId) return
  try {
    const res = await datasetApi.list(projectStore.currentProjectId)
    availableDatasets.value = Array.isArray(res) ? res : []
  } catch (e) {
    availableDatasets.value = []
  }
}

const selectGpu = (row: any) => { trainConfig.gpu = row.name }
const submitTask = () => { ElMessage.success('训练任务已提交') }

onMounted(() => {
  if (projectStore.currentProjectId) fetchDatasets()
})
</script>

<style lang="scss" scoped>
.mode-info {
  margin-top: 16px;
}

.model-card {
  margin-bottom: 12px;
  cursor: pointer;
  transition: border-color 0.3s;

  &.selected {
    border-color: #409eff;
  }

  .model-name {
    font-weight: 600;
    font-size: 15px;
    color: #303133;
  }

  .model-info {
    font-size: 12px;
    color: #909399;
    margin-top: 4px;
  }
}

.step-actions {
  margin-top: 20px;
  display: flex;
  justify-content: center;
  gap: 12px;
}
</style>
