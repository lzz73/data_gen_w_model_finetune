<template>
  <div class="page-container">
    <PageHeader title="数据集划分">
      <el-button type="primary" @click="exportDataset">
        <el-icon><Download /></el-icon>导出数据集
      </el-button>
    </PageHeader>

    <el-row :gutter="16">
      <!-- 划分配置 -->
      <el-col :span="12">
        <div class="content-card">
          <div class="card-title">划分配置</div>
          <el-form :model="splitConfig" label-width="120px">
            <el-form-item label="数据集名称">
              <el-input v-model="splitConfig.name" placeholder="请输入数据集名称" />
            </el-form-item>
            <el-form-item label="划分策略">
              <el-radio-group v-model="splitConfig.strategy">
                <el-radio value="random">随机划分</el-radio>
                <el-radio value="file">按文件划分</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="随机种子">
              <el-input-number v-model="splitConfig.seed" :min="1" :max="9999" />
            </el-form-item>
            <el-form-item label="训练集比例">
              <el-slider v-model="splitConfig.trainRatio" :min="50" :max="98" :step="1" show-input />
            </el-form-item>
            <el-form-item label="验证集比例">
              <el-slider v-model="splitConfig.valRatio" :min="1" :max="25" :step="1" show-input />
            </el-form-item>
            <el-form-item label="测试集比例">
              <el-slider v-model="splitConfig.testRatio" :min="1" :max="25" :step="1" show-input />
            </el-form-item>
            <el-form-item>
              <el-alert
                :type="totalRatio === 100 ? 'success' : 'error'"
                :title="`比例总和：${totalRatio}%${totalRatio !== 100 ? '（需等于100%）' : ''}`"
                :closable="false"
                show-icon
              />
            </el-form-item>
          </el-form>
        </div>
      </el-col>

      <!-- 划分预览 -->
      <el-col :span="12">
        <div class="content-card">
          <div class="card-title">划分预览</div>
          <div class="split-preview">
            <div class="split-bar">
              <div class="split-segment train" :style="{ width: splitConfig.trainRatio + '%' }">
                训练集 {{ splitConfig.trainRatio }}%
              </div>
              <div class="split-segment val" :style="{ width: splitConfig.valRatio + '%' }">
                验证 {{ splitConfig.valRatio }}%
              </div>
              <div class="split-segment test" :style="{ width: splitConfig.testRatio + '%' }">
                测试 {{ splitConfig.testRatio }}%
              </div>
            </div>
            <el-descriptions :column="1" border size="small" style="margin-top: 16px">
              <el-descriptions-item label="总样本数">156</el-descriptions-item>
              <el-descriptions-item label="训练集">{{ Math.floor(156 * splitConfig.trainRatio / 100) }} 条</el-descriptions-item>
              <el-descriptions-item label="验证集">{{ Math.floor(156 * splitConfig.valRatio / 100) }} 条</el-descriptions-item>
              <el-descriptions-item label="测试集">{{ 156 - Math.floor(156 * splitConfig.trainRatio / 100) - Math.floor(156 * splitConfig.valRatio / 100) }} 条</el-descriptions-item>
            </el-descriptions>
          </div>
        </div>

        <div class="content-card">
          <div class="card-title">导出文件</div>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="训练集文件">power_contract_v1_train.jsonl</el-descriptions-item>
            <el-descriptions-item label="验证集文件">power_contract_v1_val.jsonl</el-descriptions-item>
            <el-descriptions-item label="测试集文件">power_contract_v1_test.jsonl</el-descriptions-item>
          </el-descriptions>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { reactive, computed } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { ElMessage } from 'element-plus'

const splitConfig = reactive({
  name: 'power_contract_v1',
  strategy: 'random',
  seed: 42,
  trainRatio: 90,
  valRatio: 5,
  testRatio: 5,
})

const totalRatio = computed(() => splitConfig.trainRatio + splitConfig.valRatio + splitConfig.testRatio)

const exportDataset = () => {
  if (totalRatio.value !== 100) {
    ElMessage.error('比例总和必须等于100%')
    return
  }
  ElMessage.success('数据集导出成功')
}
</script>

<style lang="scss" scoped>
.split-bar {
  display: flex;
  height: 36px;
  border-radius: 6px;
  overflow: hidden;

  .split-segment {
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fff;
    font-size: 12px;
    font-weight: 500;
    transition: width 0.3s;

    &.train { background: #409eff; }
    &.val { background: #67c23a; }
    &.test { background: #e6a23c; }
  }
}
</style>
