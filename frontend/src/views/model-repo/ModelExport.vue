<template>
  <div class="page-container">
    <PageHeader title="模型导出" />

    <el-row :gutter="16">
      <el-col :span="14">
        <div class="content-card">
          <div class="card-title">导出配置</div>
          <el-form :model="exportConfig" label-width="120px">
            <el-form-item label="选择模型">
              <el-select v-model="exportConfig.model" placeholder="请选择已注册模型">
                <el-option label="电力SFT-Qwen2-7B-v3" value="power_sft_v3" />
                <el-option label="合同DPO-DeepSeek-7B-v2" value="contract_dpo_v2" />
                <el-option label="规章CPT-LLaMA3-8B-v1" value="rules_cpt_v1" />
              </el-select>
            </el-form-item>
            <el-form-item label="导出方式">
              <el-radio-group v-model="exportConfig.method">
                <el-radio value="merge">LoRA合并到基座模型</el-radio>
                <el-radio value="adapter">仅导出LoRA Adapter</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="exportConfig.method === 'merge'" label="量化方式">
              <el-select v-model="exportConfig.quantization">
                <el-option label="不量化（FP16）" value="fp16" />
                <el-option label="4-bit量化（GPTQ）" value="gptq-4bit" />
                <el-option label="8-bit量化（GPTQ）" value="gptq-8bit" />
              </el-select>
            </el-form-item>
            <el-form-item label="导出路径">
              <el-input v-model="exportConfig.outputPath" placeholder="/data/models/export/" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="startExport">
                <el-icon><Download /></el-icon>开始导出
              </el-button>
            </el-form-item>
          </el-form>
        </div>
      </el-col>

      <el-col :span="10">
        <div v-if="exporting" class="content-card">
          <div class="card-title">导出进度</div>
          <el-progress :percentage="exportProgress" :status="exportProgress === 100 ? 'success' : ''" />
          <div class="export-info">
            <p v-if="exportProgress < 100">正在合并LoRA权重到基座模型...</p>
            <p v-else>导出完成！文件已保存至 {{ exportConfig.outputPath }}</p>
          </div>
        </div>

        <div class="content-card">
          <div class="card-title">多阶段合并</div>
          <el-alert type="info" :closable="false" show-icon>
            <template #title>对于多阶段训练的模型（如CPT合并后再做SFT），提供一键合并功能</template>
          </el-alert>
          <el-form label-width="100px" size="small" style="margin-top: 12px">
            <el-form-item label="第一阶段">
              <el-select v-model="exportConfig.stage1" placeholder="CPT模型" size="small">
                <el-option label="规章CPT-LLaMA3-8B-v1" value="rules_cpt_v1" />
              </el-select>
            </el-form-item>
            <el-form-item label="第二阶段">
              <el-select v-model="exportConfig.stage2" placeholder="SFT模型" size="small">
                <el-option label="电力SFT-Qwen2-7B-v3" value="power_sft_v3" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button size="small" type="warning">一键合并</el-button>
            </el-form-item>
          </el-form>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'

const exporting = ref(false)
const exportProgress = ref(0)

const exportConfig = reactive({
  model: 'power_sft_v3',
  method: 'merge',
  quantization: 'fp16',
  outputPath: '/data/models/export/',
  stage1: '',
  stage2: '',
})

const startExport = () => {
  exporting.value = true
  exportProgress.value = 0
  const timer = setInterval(() => {
    exportProgress.value += 5
    if (exportProgress.value >= 100) clearInterval(timer)
  }, 300)
}
</script>

<style lang="scss" scoped>
.export-info {
  margin-top: 12px;
  font-size: 13px;
  color: #606266;
}
</style>
