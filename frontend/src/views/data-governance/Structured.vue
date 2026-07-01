<template>
  <div class="page-container">
    <PageHeader title="结构化数据处理" />

    <el-row :gutter="16">
      <!-- 字段标注 -->
      <el-col :span="16">
        <div class="content-card">
          <div class="card-title">字段标注</div>
          <el-table :data="fields" stripe>
            <el-table-column prop="name" label="字段名" width="150" />
            <el-table-column prop="type" label="数据类型" width="120" />
            <el-table-column prop="sample" label="示例值" />
            <el-table-column prop="missing" label="缺失率" width="100">
              <template #default="{ row }">
                <span :style="{ color: row.missing > 0.3 ? '#f56c6c' : '#67c23a' }">
                  {{ (row.missing * 100).toFixed(1) }}%
                </span>
              </template>
            </el-table-column>
            <el-table-column label="字段角色" width="160">
              <template #default="{ row }">
                <el-select v-model="row.role" size="small">
                  <el-option label="业务属性" value="feature" />
                  <el-option label="输出字段" value="target" />
                  <el-option label="冗余字段" value="redundant" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="脱敏" width="80">
              <template #default="{ row }">
                <el-switch v-model="row.desensitize" size="small" />
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>

      <!-- 缺失值统计 + 脱敏配置 -->
      <el-col :span="8">
        <div class="content-card">
          <div class="card-title">缺失值统计</div>
          <div class="missing-stats">
            <div v-for="f in fields.filter(f => f.missing > 0)" :key="f.name" class="missing-item">
              <span class="field-name">{{ f.name }}</span>
              <el-progress :percentage="f.missing * 100" :color="f.missing > 0.3 ? '#f56c6c' : '#e6a23c'" :stroke-width="8" />
            </div>
            <el-empty v-if="!fields.some(f => f.missing > 0)" description="无缺失值" :image-size="60" />
          </div>
        </div>

        <div class="content-card">
          <div class="card-title">脱敏配置</div>
          <el-form label-width="80px" size="small">
            <el-form-item label="工号脱敏">
              <el-switch v-model="desensitizeConfig.employeeId" />
            </el-form-item>
            <el-form-item label="薪资脱敏">
              <el-switch v-model="desensitizeConfig.salary" />
            </el-form-item>
            <el-form-item label="合同金额">
              <el-switch v-model="desensitizeConfig.contractAmount" />
            </el-form-item>
            <el-form-item label="自定义关键词">
              <el-select v-model="desensitizeConfig.customKeywords" multiple filterable allow-create placeholder="输入关键词" size="small" />
            </el-form-item>
          </el-form>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'

const fields = reactive([
  { name: 'contract_id', type: 'VARCHAR', sample: 'HT-2024-001', missing: 0.02, role: 'feature', desensitize: false },
  { name: 'contract_name', type: 'VARCHAR', sample: 'XX电力采购合同', missing: 0, role: 'feature', desensitize: false },
  { name: 'employee_id', type: 'VARCHAR', sample: '工号：2024001', missing: 0.05, role: 'feature', desensitize: true },
  { name: 'amount', type: 'DECIMAL', sample: '1,250,000.00', missing: 0.35, role: 'target', desensitize: true },
  { name: 'department', type: 'VARCHAR', sample: '采购部', missing: 0, role: 'feature', desensitize: false },
  { name: 'sign_date', type: 'DATE', sample: '2024-03-15', missing: 0.01, role: 'feature', desensitize: false },
  { name: 'salary', type: 'DECIMAL', sample: '15,000.00', missing: 0.42, role: 'redundant', desensitize: true },
  { name: 'remark', type: 'TEXT', sample: '按季度付款', missing: 0.15, role: 'feature', desensitize: false },
])

const desensitizeConfig = reactive({
  employeeId: true,
  salary: true,
  contractAmount: true,
  customKeywords: [] as string[],
})
</script>

<style lang="scss" scoped>
.missing-stats {
  .missing-item {
    margin-bottom: 12px;

    .field-name {
      font-size: 13px;
      color: #606266;
      margin-bottom: 4px;
      display: block;
    }
  }
}
</style>
