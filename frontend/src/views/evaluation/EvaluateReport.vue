<template>
  <div class="page-container">
    <PageHeader title="评估报告">
      <template #default>
        <el-select v-model="selectedReport" size="small" style="width: 250px">
          <el-option label="电力SFT-v3评估" value="1" />
          <el-option label="合同DPO-v2评估" value="2" />
        </el-select>
      </template>
    </PageHeader>

    <el-tabs v-model="activeTab" type="border-card">
      <!-- 总览面板 -->
      <el-tab-pane label="总览" name="overview">
        <div class="stat-row">
          <StatCard icon="Trophy" label="综合得分" :value="82" color="#409eff" />
          <StatCard icon="CircleCheck" label="正确率" value="68%" color="#67c23a" />
          <StatCard icon="Warning" label="部分正确" value="18%" color="#e6a23c" />
          <StatCard icon="CircleClose" label="错误率" value="14%" color="#f56c6c" />
        </div>
        <div class="content-card">
          <div class="card-title">各维度通过率</div>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="核心事实正确性">
              <el-progress :percentage="85" :stroke-width="12" />
            </el-descriptions-item>
            <el-descriptions-item label="信息完整性">
              <el-progress :percentage="72" :stroke-width="12" color="#e6a23c" />
            </el-descriptions-item>
            <el-descriptions-item label="无幻觉">
              <el-progress :percentage="90" :stroke-width="12" color="#67c23a" />
            </el-descriptions-item>
            <el-descriptions-item label="格式合规性">
              <el-progress :percentage="78" :stroke-width="12" color="#409eff" />
            </el-descriptions-item>
          </el-descriptions>
        </div>
        <div class="content-card">
          <div class="card-title">评审可信度</div>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="LLM评审与人工一致率">82%</el-descriptions-item>
            <el-descriptions-item label="可信度标记">
              <el-tag type="success" size="small">可信</el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </div>
      </el-tab-pane>

      <!-- 错误分类面板 -->
      <el-tab-pane label="错误分类" name="errors">
        <div class="content-card">
          <div class="card-title">错误分布</div>
          <div class="error-stats">
            <div v-for="err in errorStats" :key="err.type" class="error-type">
              <div class="error-header">
                <el-tag :type="err.color" size="small">{{ err.type }}</el-tag>
                <span class="error-count">{{ err.count }}条 ({{ err.percent }}%)</span>
              </div>
              <el-progress :percentage="err.percent" :color="err.barColor" :stroke-width="10" />
              <div class="error-desc">{{ err.desc }}</div>
            </div>
          </div>
        </div>
        <div class="content-card">
          <div class="card-title">错误样例</div>
          <el-table :data="errorSamples" stripe size="small">
            <el-table-column prop="type" label="类型" width="100">
              <template #default="{ row }">
                <el-tag :type="errorColorMap[row.type]" size="small">{{ row.type }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="question" label="问题" show-overflow-tooltip />
            <el-table-column prop="standard" label="标准答案" show-overflow-tooltip />
            <el-table-column prop="model" label="模型回答" show-overflow-tooltip />
            <el-table-column prop="reason" label="评审原因" show-overflow-tooltip />
          </el-table>
        </div>
      </el-tab-pane>

      <!-- 修复建议面板 -->
      <el-tab-pane label="修复建议" name="suggestions">
        <div class="content-card">
          <div v-for="(sug, i) in suggestions" :key="i" class="suggestion-item">
            <div class="sug-header">
              <el-icon :size="20" :color="sug.iconColor"><component :is="sug.icon" /></el-icon>
              <span class="sug-title">{{ sug.title }}</span>
            </div>
            <div class="sug-content">{{ sug.content }}</div>
          </div>
        </div>
      </el-tab-pane>

      <!-- 迭代对比面板 -->
      <el-tab-pane label="迭代对比" name="compare">
        <div class="content-card">
          <div class="card-title">v2 → v3 变化</div>
          <el-table :data="iterationCompare" stripe>
            <el-table-column prop="category" label="错误类型" width="120" />
            <el-table-column prop="v2" label="v2数量" width="100" />
            <el-table-column prop="v3" label="v3数量" width="100" />
            <el-table-column label="变化" width="200">
              <template #default="{ row }">
                <el-text :type="row.change < 0 ? 'success' : row.change > 0 ? 'danger' : 'info'">
                  {{ row.change > 0 ? '+' : '' }}{{ row.change }}条 ({{ row.changePercent }})
                </el-text>
              </template>
            </el-table-column>
            <el-table-column label="判定" width="200">
              <template #default="{ row }">
                <el-tag :type="row.change < -0.2 ? 'success' : row.change > 0 ? 'danger' : 'warning'" size="small">
                  {{ row.change < -0.2 ? '调整可能生效' : row.change > 0 ? '建议检查调整方向' : '调整可能未生效' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatCard from '@/components/common/StatCard.vue'

const activeTab = ref('overview')
const selectedReport = ref('1')

const errorStats = [
  { type: '混淆', count: 8, percent: 36, color: 'danger' as const, barColor: '#f56c6c', desc: '模型回答的值像是另一个实体的属性值' },
  { type: '不完整', count: 6, percent: 27, color: 'warning' as const, barColor: '#e6a23c', desc: '事实正确但缺少部分信息' },
  { type: '幻觉', count: 4, percent: 18, color: 'danger' as const, barColor: '#f56c6c', desc: '回答中存在标准答案没有的内容' },
  { type: '格式偏差', count: 3, percent: 14, color: '' as const, barColor: '#409eff', desc: '语义正确但措辞与预期不符' },
  { type: '其他', count: 1, percent: 5, color: 'info' as const, barColor: '#909399', desc: '不属于以上任何类型' },
]

const errorColorMap: Record<string, string> = { '混淆': 'danger', '不完整': 'warning', '幻觉': 'danger', '格式偏差': '', '其他': 'info' }

const errorSamples = [
  { type: '混淆', question: 'XX项目的合同金额是多少？', standard: '1,250,000.00元', model: '1,500,000.00元（实际为YY项目金额）', reason: '模型将YY项目的金额混淆为XX项目' },
  { type: '不完整', question: '采购流程包含哪些步骤？', standard: '需求提出、审批、招标、签约、验收五个步骤', model: '采购流程包括需求提出、审批和招标', reason: '缺少签约和验收两个步骤' },
  { type: '幻觉', question: '安全生产培训的频率？', standard: '每季度一次', model: '每月一次，由安全部组织', reason: '标准答案中无"每月一次"和"安全部组织"信息' },
]

const suggestions = [
  { icon: 'Warning', iconColor: '#f56c6c', title: '混淆类错误占比最高（36%）', content: '建议检查训练数据中指令相似但答案不同的样本对，增加对比样本以提升模型区分能力。' },
  { icon: 'Info', iconColor: '#e6a23c', title: '不完整类错误占比27%', content: '建议统一同类问题的答案详略标准，确保训练数据中完整答案的占比。' },
  { icon: 'Success', iconColor: '#67c23a', title: '格式偏差类错误较少（14%）', content: '当前格式合规性尚可，可在提示词模板中增加格式约束进一步降低。' },
]

const iterationCompare = [
  { category: '混淆', v2: 35, v3: 8, change: -27, changePercent: '下降77%' },
  { category: '不完整', v2: 20, v3: 6, change: -14, changePercent: '下降70%' },
  { category: '幻觉', v2: 10, v3: 4, change: -6, changePercent: '下降60%' },
  { category: '格式偏差', v2: 5, v3: 3, change: -2, changePercent: '下降40%' },
  { category: '其他', v2: 2, v3: 1, change: -1, changePercent: '下降50%' },
]
</script>

<style lang="scss" scoped>
.error-stats {
  .error-type {
    margin-bottom: 16px;

    .error-header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 6px;

      .error-count {
        font-size: 13px;
        color: #606266;
      }
    }

    .error-desc {
      font-size: 12px;
      color: #909399;
      margin-top: 4px;
    }
  }
}

.suggestion-item {
  padding: 16px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  margin-bottom: 12px;

  .sug-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;

    .sug-title {
      font-weight: 600;
      font-size: 14px;
      color: #303133;
    }
  }

  .sug-content {
    font-size: 13px;
    color: #606266;
    line-height: 1.6;
    padding-left: 28px;
  }
}
</style>
