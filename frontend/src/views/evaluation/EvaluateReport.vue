<template>
  <div class="page-container">
    <PageHeader title="评估报告">
      <template #default>
        <el-select v-model="selectedTaskId" size="small" style="width: 250px" placeholder="选择评估任务" @change="handleTaskChange">
          <el-option
            v-for="t in completedTasks"
            :key="t.id"
            :label="t.name"
            :value="t.id"
          />
        </el-select>
      </template>
    </PageHeader>

    <EmptyState
      v-if="!projectStore.hasProject"
      description="请先在首页选择一个项目"
      action-text="前往首页"
      @action="$router.push('/')"
    />

    <EmptyState
      v-else-if="completedTasks.length === 0"
      description="暂无已完成的评估任务"
      action-text="创建评估"
      @action="$router.push('/evaluation/task')"
    />

    <el-tabs v-else v-model="activeTab" type="border-card">
      <!-- 总览面板 -->
      <el-tab-pane label="总览" name="overview">
        <div class="stat-row">
          <StatCard icon="Trophy" label="综合得分" :value="statsSummary.total_score || 0" color="#409eff" />
          <StatCard icon="CircleCheck" label="正确" :value="statsSummary.correct_count || 0" color="#67c23a" />
          <StatCard icon="Warning" label="部分正确" :value="statsSummary.partial_count || 0" color="#e6a23c" />
          <StatCard icon="CircleClose" label="错误" :value="statsSummary.incorrect_count || 0" color="#f56c6c" />
        </div>
        <div class="content-card">
          <div class="card-title">各维度通过率</div>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="核心事实正确性">
              <el-progress :percentage="statsSummary.factual_accuracy || 0" :stroke-width="12" />
            </el-descriptions-item>
            <el-descriptions-item label="信息完整性">
              <el-progress :percentage="statsSummary.completeness || 0" :stroke-width="12" color="#e6a23c" />
            </el-descriptions-item>
            <el-descriptions-item label="无幻觉">
              <el-progress :percentage="statsSummary.no_hallucination || 0" :stroke-width="12" color="#67c23a" />
            </el-descriptions-item>
            <el-descriptions-item label="格式合规性">
              <el-progress :percentage="statsSummary.format_compliance || 0" :stroke-width="12" color="#409eff" />
            </el-descriptions-item>
          </el-descriptions>
        </div>
      </el-tab-pane>

      <!-- 错误分类面板 -->
      <el-tab-pane label="错误分类" name="errors">
        <div class="content-card">
          <div class="card-title">错误分布</div>
          <div class="error-stats">
            <div v-for="err in errorDistribution" :key="err.type" class="error-type">
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
          <el-table :data="errorResults" stripe size="small" v-loading="loadingResults">
            <el-table-column label="问题" prop="question_content" show-overflow-tooltip />
            <el-table-column label="标准答案" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.expected_answer || '-' }}
              </template>
            </el-table-column>
            <el-table-column label="模型回答" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.model_answer || '-' }}
              </template>
            </el-table-column>
            <el-table-column label="评审原因" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.feedback || '-' }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- 修复建议面板 -->
      <el-tab-pane label="修复建议" name="suggestions">
        <div class="content-card">
          <div v-for="(sug, i) in suggestions" :key="i" class="suggestion-item">
            <div class="sug-header">
              <el-icon :size="20" :color="sug.iconColor"><Warning /></el-icon>
              <span class="sug-title">{{ sug.title }}</span>
            </div>
            <div class="sug-content">{{ sug.content }}</div>
          </div>
          <el-empty v-if="suggestions.length === 0" description="暂无修复建议" :image-size="60" />
        </div>
      </el-tab-pane>

      <!-- 迭代对比面板 -->
      <el-tab-pane label="迭代对比" name="compare">
        <div class="content-card">
          <div class="card-title">变化趋势</div>
          <el-table :data="iterationCompare" stripe>
            <el-table-column prop="category" label="错误类型" width="120" />
            <el-table-column prop="previous" label="上轮数量" width="100" />
            <el-table-column prop="current" label="本轮数量" width="100" />
            <el-table-column label="变化" width="200">
              <template #default="{ row }">
                <el-text :type="row.change < 0 ? 'success' : row.change > 0 ? 'danger' : 'info'">
                  {{ row.change > 0 ? '+' : '' }}{{ row.change }}条
                </el-text>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="iterationCompare.length === 0" description="暂无历史对比数据" :image-size="60" />
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useProjectStore } from '@/stores/project'
import { evalApi } from '@/api'
import PageHeader from '@/components/common/PageHeader.vue'
import StatCard from '@/components/common/StatCard.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const projectStore = useProjectStore()
const activeTab = ref('overview')
const selectedTaskId = ref('')
const loadingResults = ref(false)
const allTasks = ref<any[]>([])
const statsSummary = ref<any>({})
const errorResults = ref<any[]>([])

const completedTasks = computed(() =>
  allTasks.value.filter(t => t.status === 'completed')
)

const errorDistribution = computed(() => {
  const stats = statsSummary.value
  if (!stats || !stats.error_types) return []
  const total = stats.incorrect_count || 1
  const colorMap: Record<string, any> = { '混淆': 'danger', '不完整': 'warning', '幻觉': 'danger', '格式偏差': '', '其他': 'info' }
  const barColorMap: Record<string, string> = { '混淆': '#f56c6c', '不完整': '#e6a23c', '幻觉': '#f56c6c', '格式偏差': '#409eff', '其他': '#909399' }
  const descMap: Record<string, string> = {
    '混淆': '模型回答的值像是另一个实体的属性值',
    '不完整': '事实正确但缺少部分信息',
    '幻觉': '回答中存在标准答案没有的内容',
    '格式偏差': '语义正确但措辞与预期不符',
    '其他': '不属于以上任何类型',
  }
  return Object.entries(stats.error_types || {}).map(([type, count]) => ({
    type,
    count: count as number,
    percent: Math.round((count as number) / total * 100),
    color: colorMap[type] || 'info',
    barColor: barColorMap[type] || '#909399',
    desc: descMap[type] || '',
  }))
})

const suggestions = computed(() => {
  const dist = errorDistribution.value
  if (dist.length === 0) return []
  return dist
    .filter(e => e.percent >= 3)
    .sort((a, b) => b.percent - a.percent)
    .map(e => {
      const title = `${e.type}类错误占比最高（${e.percent}%）`
      const contentMap: Record<string, string> = {
        '混淆': '建议检查训练数据中指令相似但答案不同的样本对，增加对比样本以提升模型区分能力。',
        '不完整': '建议统一同类问题的答案详略标准，确保训练数据中完整答案的占比。',
        '幻觉': '建议在训练数据中增加更多正确答案的样本，减少模型编造内容的倾向。',
        '格式偏差': '建议在提示词模板中增加格式约束，或在训练数据中统一答案格式。',
      }
      return {
        title,
        content: contentMap[e.type] || '建议人工分析该类错误的样本，找到根本原因。',
        iconColor: e.percent > 30 ? '#f56c6c' : '#e6a23c',
      }
    })
})

const iterationCompare = ref<any[]>([])

const fetchTasks = async () => {
  if (!projectStore.currentProjectId) return
  try {
    const res = await evalApi.listTasks(projectStore.currentProjectId)
    allTasks.value = Array.isArray(res) ? res : []
    // Auto-select first completed task
    if (completedTasks.value.length > 0 && !selectedTaskId.value) {
      selectedTaskId.value = completedTasks.value[0].id
      await fetchResults()
    }
  } catch (e) {
    allTasks.value = []
  }
}

const fetchResults = async () => {
  if (!projectStore.currentProjectId || !selectedTaskId.value) return
  loadingResults.value = true
  try {
    const [statsRes, resultsRes] = await Promise.all([
      evalApi.getResultsStats(projectStore.currentProjectId, selectedTaskId.value),
      evalApi.getResults(projectStore.currentProjectId, selectedTaskId.value, { is_correct: 'false' }),
    ])
    statsSummary.value = statsRes || {}
    errorResults.value = Array.isArray(resultsRes) ? resultsRes : []
  } catch (e) {
    statsSummary.value = {}
    errorResults.value = []
  } finally {
    loadingResults.value = false
  }
}

const handleTaskChange = () => {
  fetchResults()
}

watch(() => projectStore.currentProjectId, (newId) => {
  if (newId) fetchTasks()
})

onMounted(() => {
  if (projectStore.currentProjectId) fetchTasks()
})
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
