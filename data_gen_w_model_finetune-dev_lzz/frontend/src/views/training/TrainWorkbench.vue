<template>
  <div class="page-container">
    <PageHeader title="训练工作台" />

    <!-- 步骤条 -->
    <div class="content-card">
      <el-steps :active="currentStep" finish-status="success" align-center>
        <el-step title="数据选择" />
        <el-step title="基座模型" />
        <el-step title="参数配置" />
        <el-step title="GPU选择" />
      </el-steps>
    </div>

    <!-- Step 1: 数据选择 -->
    <div v-if="currentStep === 0" class="content-card">
      <div class="card-title">选择数据集</div>
      <el-form label-width="100px">
        <el-form-item label="数据集">
          <el-select v-model="trainConfig.dataset" placeholder="请选择数据集" style="width:400px">
            <el-option
              v-for="ds in availableDatasets"
              :key="ds.name"
              :label="`${ds.name} (${ds.samples}条)`"
              :value="ds.name"
            />
          </el-select>
        </el-form-item>
      </el-form>
    </div>

    <!-- Step 2: 基座模型 -->
    <div v-if="currentStep === 1" class="content-card">
      <div class="card-title">
        选择基座模型
        <el-tag v-if="localCount > 0" type="success" size="small" style="margin-left:8px">本地已有 {{ localCount }} 个</el-tag>
        <span style="font-size:13px;color:#909399;margin-left:8px">（共 {{ baseModels.length }} 个可用）</span>
      </div>

      <el-input
        v-model="trainConfig.baseModel"
        placeholder="输入 HuggingFace 模型名或项目内 models/ 下的路径"
        clearable
        style="margin-bottom:12px"
      >
        <template #prepend>模型路径</template>
      </el-input>

      <el-alert
        v-if="currentStep === 1 && (!trainConfig.baseModel || !trainConfig.baseModel.trim())"
        title="请选择或输入一个基座模型路径"
        type="warning"
        show-icon
        :closable="false"
        style="margin-bottom:12px"
      />
      <el-alert
        v-if="currentStep === 1 && trainConfig.baseModel && trainConfig.baseModel.trim()"
        :title="'当前选择: ' + trainConfig.baseModel"
        type="success"
        show-icon
        :closable="false"
        style="margin-bottom:12px"
      />

      <el-row :gutter="8" style="margin-bottom:12px">
        <el-col :span="12">
          <el-select v-model="trainConfig.baseModel" filterable placeholder="从列表中选择..." style="width:100%" clearable>
            <el-option-group v-if="localModels.length > 0" label="── 本地已有 ──">
              <el-option v-for="m in localModels" :key="m.value" :label="m.label" :value="m.value">
                <div class="option-row">
                  <span class="option-name">✓ {{ m.label }}</span>
                  <span class="option-hf" style="color:#67c23a">本地已有</span>
                </div>
              </el-option>
            </el-option-group>
            <el-option-group label="── 远程模型（需下载） ──">
              <el-option v-for="m in remoteModels" :key="m.value" :label="m.label" :value="m.value">
                <div class="option-row">
                  <span class="option-name">{{ m.label }}</span>
                  <span class="option-hf">需下载</span>
                </div>
              </el-option>
            </el-option-group>
          </el-select>
        </el-col>
        <el-col :span="12">
          <el-input v-model="modelSearch" placeholder="搜索模型名称..." clearable>
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
        </el-col>
      </el-row>

      <div class="model-grid">
        <el-card
          v-for="model in filteredModels.slice(0, 30)"
          :key="model.value"
          class="model-card"
          :class="{ selected: trainConfig.baseModel === model.value, local: model.local }"
          shadow="hover"
          @click="trainConfig.baseModel = model.value"
        >
          <div class="model-name">
            <el-tag v-if="model.local" type="success" size="small" effect="dark" style="margin-right:4px">本地</el-tag>
            {{ model.label }}
          </div>
          <div class="model-info">{{ model.hf }}</div>
        </el-card>
      </div>
      <div v-if="filteredModels.length > 30" style="text-align:center;color:#909399;margin-top:8px">
        仅显示前 30 个，使用搜索过滤更多
      </div>
    </div>

    <!-- Step 3: 参数配置 -->
    <div v-if="currentStep === 2" class="content-card">
      <div class="card-title">参数配置</div>
      <el-form :model="trainConfig" label-width="150px" size="small">

        <!-- 训练模式 + 微调方式 -->
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="训练阶段">
              <el-select v-model="trainConfig.mode" style="width:100%">
                <el-option label="SFT 指令微调" value="sft" />
                <el-option label="DPO 偏好对齐" value="dpo" />
                <el-option label="PT  预训练" value="pt" />
                <el-option label="RM  奖励模型" value="rm" />
                <el-option label="KTO 偏好对齐" value="kto" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="微调方式">
              <el-select v-model="trainConfig.finetuning_type" style="width:100%">
                <el-option label="LoRA" value="lora" />
                <el-option label="全量微调 (Full)" value="full" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="对话模板">
              <el-select v-model="trainConfig.template" style="width:100%" filterable>
                <el-option label="default" value="default" />
                <el-option label="qwen" value="qwen" />
                <el-option label="llama3" value="llama3" />
                <el-option label="chatglm3" value="chatglm3" />
                <el-option label="deepseek" value="deepseek" />
                <el-option label="baichuan2" value="baichuan2" />
                <el-option label="mistral" value="mistral" />
                <el-option label="yi" value="yi" />
                <el-option label="gemma" value="gemma" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">训练参数</el-divider>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="学习率 (Learning Rate)">
              <el-input v-model="trainConfig.learning_rate" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="训练轮数 (Epochs)">
              <el-input-number v-model="trainConfig.num_train_epochs" :min="1" :max="100" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="批次大小 (Batch Size)">
              <el-input-number v-model="trainConfig.per_device_train_batch_size" :min="1" :max="128" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="截断长度 (Cutoff Len)">
              <el-input-number v-model="trainConfig.cutoff_len" :min="128" :max="32768" :step="128" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="梯度累积 (Grad Accum)">
              <el-input-number v-model="trainConfig.gradient_accumulation_steps" :min="1" :max="64" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="最大样本数 (Max Samples)">
              <el-input-number v-model="trainConfig.max_samples" :min="100" :max="10000000" :step="10000" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="LR 调度器">
              <el-select v-model="trainConfig.lr_scheduler_type" style="width:100%">
                <el-option label="cosine" value="cosine" />
                <el-option label="linear" value="linear" />
                <el-option label="constant" value="constant" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="Warmup 步数">
              <el-input-number v-model="trainConfig.warmup_steps" :min="0" :max="10000" :step="50" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="梯度裁剪 (Max Norm)">
              <el-input v-model="trainConfig.max_grad_norm" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="优化器 (Optimizer)">
              <el-select v-model="trainConfig.optim" style="width:100%">
                <el-option label="adamw_torch" value="adamw_torch" />
                <el-option label="adamw_8bit" value="adamw_8bit" />
                <el-option label="sgd" value="sgd" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="计算精度 (Dtype)">
              <el-select v-model="trainConfig.dtype" style="width:100%">
                <el-option label="bf16" value="bf16" />
                <el-option label="fp16" value="fp16" />
                <el-option label="fp32" value="fp32" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="Flash Attn">
              <el-select v-model="trainConfig.flash_attn" style="width:100%">
                <el-option label="auto" value="auto" />
                <el-option label="disabled" value="disabled" />
                <el-option label="sdpa" value="sdpa" />
                <el-option label="fa2" value="fa2" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <!-- LoRA 参数 (仅 lora 模式显示) -->
        <template v-if="trainConfig.finetuning_type === 'lora'">
          <el-divider content-position="left">LoRA 参数</el-divider>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="LoRA Rank (r)">
                <el-input-number v-model="trainConfig.lora_rank" :min="4" :max="1024" :step="8" style="width:100%" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="LoRA Alpha">
                <el-input-number v-model="trainConfig.lora_alpha" :min="8" :max="2048" :step="16" style="width:100%" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="LoRA Dropout">
                <el-input v-model="trainConfig.lora_dropout" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="LoRA 目标模块 (Target)">
            <el-input v-model="trainConfig.lora_target" placeholder="默认: all" />
          </el-form-item>
        </template>

        <el-divider content-position="left">保存 & 日志</el-divider>
        <el-form-item label="输出目录">
          <el-input v-model="trainConfig.output_dir" placeholder="留空自动生成 output/task_xxx" clearable style="width:100%" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="从 checkpoint 继续">
              <el-switch v-model="trainConfig.resume_from_checkpoint" />
            </el-form-item>
          </el-col>
          <el-col :span="16" v-if="trainConfig.resume_from_checkpoint">
            <el-form-item label="Checkpoint 路径">
              <el-input v-model="trainConfig.checkpoint_path" placeholder="如: output/task_20260703_xxx/checkpoint-200" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="保存步数 (Save Steps)">
              <el-input-number v-model="trainConfig.save_steps" :min="10" :max="10000" :step="10" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="日志步数 (Log Steps)">
              <el-input-number v-model="trainConfig.logging_steps" :min="5" :max="1000" :step="5" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="最大保存数 (Limit)">
              <el-input-number v-model="trainConfig.save_total_limit" :min="1" :max="20" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="验证集 (Do Eval)">
              <el-switch v-model="trainConfig.do_eval" />
            </el-form-item>
          </el-col>
          <el-col :span="8" v-if="trainConfig.do_eval">
            <el-form-item label="自动划分比例">
              <el-input v-model="trainConfig.val_size" placeholder="0.1 (从训练集切10%)" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8" v-if="trainConfig.do_eval">
            <el-form-item label="验证数据集（可选）">
              <el-select v-model="trainConfig.eval_dataset" placeholder="留空则自动划分" clearable style="width:100%">
                <el-option v-for="ds in availableDatasets" :key="ds.name" :label="`${ds.name} (${ds.samples}条)`" :value="ds.name" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </div>

    <!-- Step 4: GPU选择 -->
    <div v-if="currentStep === 3" class="content-card">
      <div class="card-title">GPU选择与硬件自检</div>
      <div v-if="gpuList.length > 0 && gpuList[0].total_mem_gb > 0">
        <el-table :data="gpuList" stripe @selection-change="onGpuSelect" v-loading="gpuLoading" ref="gpuTable">
          <el-table-column type="selection" width="50" />
          <el-table-column prop="name" label="GPU" />
          <el-table-column prop="model" label="型号" width="160" />
          <el-table-column label="总显存" width="100">
            <template #default="{ row }">{{ row.total_mem_gb }}GB</template>
          </el-table-column>
          <el-table-column label="已用显存" width="160">
            <template #default="{ row }">
              <el-progress
                :percentage="row.used_percent"
                :color="row.used_percent > 90 ? '#f56c6c' : row.used_percent > 70 ? '#e6a23c' : '#67c23a'"
                :stroke-width="10"
              />
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.used_percent > 90 ? 'danger' : 'success'" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
        <el-alert v-if="hardwareCheck" :type="hardwareCheck.type" :title="hardwareCheck.msg" show-icon :closable="false" style="margin-top:16px" />
      </div>
      <el-empty v-else description="未检测到 NVIDIA GPU">
        <template #default>
          <p style="color:#909399;font-size:13px;margin-top:8px">
            本机无 NVIDIA 显卡或 nvidia-smi 不可用。<br/>
            可以直接提交训练，llamafactory 会自动使用 CPU 或可用设备。
          </p>
        </template>
      </el-empty>
    </div>

    <!-- 操作按钮 -->
    <div class="step-actions">
      <el-button v-if="currentStep > 0" @click="currentStep--">上一步</el-button>
      <el-button v-if="currentStep < 3" type="primary" @click="handleNext">下一步</el-button>
      <el-button v-if="currentStep === 3" type="success" :loading="submitting" @click="submitTask">
        <el-icon><VideoPlay /></el-icon>提交训练
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import PageHeader from '@/components/common/PageHeader.vue'
import { fetchDatasets, type DatasetItem } from '@/api/datasets'
import { createTask, fetchGpuInfo, fetchSupportedModels, type GpuInfo } from '@/api/training'
import type { TrainConfig } from '@/api/training'

const router = useRouter()
const currentStep = ref(0)
const submitting = ref(false)
const gpuLoading = ref(false)
const modelSearch = ref('')
const availableDatasets = ref<DatasetItem[]>([])
const gpuList = ref<GpuInfo[]>([])
const selectedGpus = ref<GpuInfo[]>([])

const trainConfig = reactive<TrainConfig & {
  finetuning_type: string
  learning_rate: string; num_train_epochs: number; per_device_train_batch_size: number
  cutoff_len: number; gradient_accumulation_steps: number; max_samples: number
  lr_scheduler_type: string; warmup_steps: number; max_grad_norm: string
  optim: string; dtype: string; template: string
  lora_rank: number; lora_alpha: number; lora_dropout: string; lora_target: string
  do_eval: boolean; eval_steps: number; save_steps: number
  logging_steps: number; save_total_limit: number; flash_attn: string
}>({
  mode: 'sft',
  finetuning_type: 'lora',
  dataset: '',
  base_model: '',
  preset: 'standard',
  learning_rate: '1e-5',
  num_train_epochs: 3,
  per_device_train_batch_size: 4,
  cutoff_len: 1024,
  gradient_accumulation_steps: 4,
  max_samples: 100000,
  lr_scheduler_type: 'cosine',
  warmup_steps: 100,
  max_grad_norm: '1.0',
  optim: 'adamw_torch',
  dtype: 'bf16',
  template: 'qwen',
  lora_rank: 8,
  lora_alpha: 16,
  lora_dropout: '0.01',
  lora_target: 'all',
  do_eval: false,
  val_size: '0.1',
  eval_dataset: '',
  eval_steps: 50,
  save_steps: 100,
  logging_steps: 50,
  save_total_limit: 5,
  output_dir: '',
  resume_from_checkpoint: false,
  checkpoint_path: '',
  flash_attn: 'auto',
  gpu: '0',
  num_gpus: 1,
})

const baseModels = ref<{ value: string; label: string; hf: string; local: boolean }[]>([])
const localCount = ref(0)

const localModels = computed(() => baseModels.value.filter(m => m.local))
const remoteModels = computed(() => baseModels.value.filter(m => !m.local))

const filteredModels = computed(() => {
  const q = modelSearch.value.toLowerCase()
  if (!q) return baseModels.value
  return baseModels.value.filter(m => m.label.toLowerCase().includes(q) || m.hf.toLowerCase().includes(q))
})

const onGpuSelect = (selection: GpuInfo[]) => {
  selectedGpus.value = selection
  trainConfig.gpu = selection.map(s => s.name.replace('GPU-', '')).join(',')
  trainConfig.num_gpus = selection.length
}

const hardwareCheck = computed(() => {
  if (gpuList.value.length === 0 || gpuList.value[0].total_mem_gb <= 0) return null
  if (selectedGpus.value.length === 0) return { type: 'info' as const, msg: '未选择 GPU，默认使用 GPU-0。如本机无 GPU 则自动回退 CPU' }
  if (selectedGpus.value.length > 1) return { type: 'success' as const, msg: `已选择 ${selectedGpus.value.length} 个 GPU，将使用分布式训练` }
  const gpu = selectedGpus.value[0]
  if (gpu.used_percent > 90) return { type: 'error' as const, msg: '显存不足：所选GPU可用显存不足，请更换GPU或降低参数' }
  if (gpu.used_percent > 70) return { type: 'warning' as const, msg: '显存预警：预估显存占用接近可用上限，建议降低批次大小或截断长度' }
  return { type: 'success' as const, msg: '硬件自检通过：显存充足，可以开始训练' }
})

const handleNext = () => {
  if (currentStep.value === 0 && !trainConfig.dataset) {
    ElMessage.warning('请选择数据集')
    return
  }
  currentStep.value++
  // 进入 GPU 步骤时加载 GPU 信息
  if (currentStep.value === 3) loadGpuInfo()
}

const loadDatasets = async () => {
  try {
    const res = await fetchDatasets()
    if (res.code === 0) availableDatasets.value = res.data
  } catch (e) { console.error('加载数据集失败', e) }
}

const loadGpuInfo = async () => {
  gpuLoading.value = true
  try {
    const res = await fetchGpuInfo()
    if (res.code === 0) gpuList.value = res.data
    // 自动选中第一个可用 GPU
    if (gpuList.value.length > 0 && gpuList.value[0].total_mem_gb > 0) {
      selectedGpus.value = [gpuList.value[0]]
      trainConfig.gpu = gpuList.value[0].name.replace('GPU-', '')
    }
  } catch (e) { console.error('加载GPU信息失败', e) }
  finally { gpuLoading.value = false }
}

const submitTask = async () => {
  if (!trainConfig.dataset) { ElMessage.warning('请选择数据集'); return }
  if (!trainConfig.base_model || !trainConfig.base_model.trim()) {
    ElMessage.warning('请选择或输入基座模型路径')
    return
  }
  submitting.value = true
  try {
    const payload = JSON.parse(JSON.stringify(trainConfig))
    const res = await createTask(payload as any)
    if (res.code === 0) {
      ElMessage.success('训练任务已提交')
      router.push('/training/monitor')
    } else {
      ElMessage.error('任务提交失败')
    }
  } catch (e: any) {
    ElMessage.error('提交失败: ' + e.message)
  } finally {
    submitting.value = false
  }
}

const loadModels = async () => {
  try {
    const res = await fetchSupportedModels()
    if (res.code === 0) {
      baseModels.value = res.data.map((m: any) => ({
        value: m.local && m.local_path ? m.local_path : (m.huggingface || m.name),
        label: m.name,
        hf: m.local && m.local_path ? m.local_path : (m.huggingface || ''),
        local: m.local || false,
      }))
      localCount.value = res.local_count || 0
      // 自动选第一个本地模型
      if (!trainConfig.base_model) {
        const firstLocal = baseModels.value.find(m => m.local)
        if (firstLocal) trainConfig.base_model = firstLocal.value
      }
    }
  } catch (e) { console.error('加载模型列表失败', e) }
}

onMounted(async () => {
  const saved = sessionStorage.getItem('retrain_config')
  if (saved) {
    try {
      const cfg = JSON.parse(saved)
      Object.keys(cfg).forEach(k => {
        if (k in (trainConfig as any)) (trainConfig as any)[k] = cfg[k]
      })
      sessionStorage.removeItem('retrain_config')
      ElMessage.success('已恢复上次训练参数，可修改后重新提交')
    } catch {}
  }
  loadDatasets(); loadModels()
})
</script>

<style lang="scss" scoped>
.model-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  max-height: 420px;
  overflow-y: auto;
}

.model-card {
  cursor: pointer;
  transition: border-color 0.3s;
  &.selected { border-color: #409eff; }
  &.local { border-left: 3px solid #67c23a; }
  .model-name { font-weight: 600; font-size: 13px; color: #303133; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: flex; align-items: center; }
  .model-info { font-size: 11px; color: #909399; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
}

.option-row {
  display: flex; justify-content: space-between; width: 100%;
  .option-name { font-weight: 500; }
  .option-hf { font-size: 11px; color: #909399; }
}

.step-actions { margin-top: 20px; display: flex; justify-content: center; gap: 12px; }
</style>
