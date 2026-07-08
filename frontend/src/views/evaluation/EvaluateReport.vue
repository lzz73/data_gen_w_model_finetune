<template>
  <div class="page-container">
    <PageHeader title="评估报告">
      <el-select v-model="selectedTaskId" size="small" style="width:360px" @change="loadReport" filterable placeholder="选择一个评估任务">
        <el-option-group label="── 已完成 ──">
          <el-option v-for="t in completedTasks" :key="t.task_id" :label="`${t.name} (${t.score}分)`" :value="t.task_id" />
        </el-option-group>
        <el-option-group label="── 其他 ──">
          <el-option v-for="t in otherTasks" :key="t.task_id" :label="`${t.name} (${t.status})`" :value="t.task_id" />
        </el-option-group>
      </el-select>
    </PageHeader>

    <div v-if="report" class="report-body">
      <div class="stat-row">
        <StatCard icon="Trophy" label="综合得分" :value="report.score" color="#409eff" />
        <StatCard icon="Document" label="测试样本" :value="report.results?.total || 0" color="#67c23a" />
        <StatCard icon="TrendCharts" label="BLEU" :value="report.results?.scores?.bleu || '--'" color="#e6a23c" />
        <StatCard icon="DataLine" label="ROUGE-L" :value="report.results?.scores?.rouge_l || '--'" color="#f56c6c" />
      </div>

      <div class="content-card" v-if="report.results?.scores">
        <div class="card-title">评估指标</div>
        <el-descriptions :column="3" border>
          <el-descriptions-item v-for="(val, key) in report.results.scores" :key="key" :label="key">
            <el-tag :type="Number(val) > 50 ? 'success' : 'danger'">{{ val }}</el-tag>
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <div class="content-card" v-if="report.results?.samples?.length">
        <div class="card-title">对比样例（前20条）</div>
        <el-table :data="report.results.samples" stripe size="small" max-height="700">
          <el-table-column type="index" width="50" />
          <el-table-column label="指令" show-overflow-tooltip width="160">
            <template #default="{ row }">{{ row.instruction || '--' }}</template>
          </el-table-column>
          <el-table-column label="参考答案" show-overflow-tooltip width="180">
            <template #default="{ row }">
              <el-text size="small" truncated>{{ row.reference }}</el-text>
            </template>
          </el-table-column>
          <el-table-column label="模型预测" show-overflow-tooltip width="180">
            <template #default="{ row }">
              <el-text size="small" type="primary" truncated>{{ row.prediction }}</el-text>
            </template>
          </el-table-column>
          <el-table-column v-if="hasJudge" label="LLM评审" min-width="200">
            <template #default="{ row }">
              <div v-if="row.judge" style="display:flex;flex-wrap:wrap;gap:4px;align-items:center">
                <el-tag :type="row.judge.score >= 7 ? 'success' : row.judge.score >= 5 ? 'warning' : 'danger'" size="small">
                  综合 {{ row.judge.score }}/10
                </el-tag>
                <el-tooltip content="核心事实正确性"><el-tag size="small">{{ row.judge.factual }}</el-tag></el-tooltip>
                <el-tooltip content="信息完整性"><el-tag size="small">{{ row.judge.completeness }}</el-tag></el-tooltip>
                <el-tooltip content="无幻觉"><el-tag size="small">{{ row.judge.no_hallucination }}</el-tag></el-tooltip>
                <el-tooltip content="格式合规性"><el-tag size="small">{{ row.judge.format }}</el-tag></el-tooltip>
                <div style="font-size:11px;color:#909399;width:100%;margin-top:2px">{{ row.judge.reason }}</div>
              </div>
              <span v-else style="color:#909399">-</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <el-empty v-else description="请选择一个已完成的评估任务" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '@/components/common/PageHeader.vue'
import StatCard from '@/components/common/StatCard.vue'
import { evaluationApi } from '@/api/evaluation'

const route = useRoute()
const selectedTaskId = ref('')
const completedTasks = ref<any[]>([])
const report = ref<any>(null)
const hasJudge = computed(() => report.value?.results?.samples?.some((s: any) => s.judge))

const otherTasks = ref<any[]>([])

const loadTasks = async () => {
  try {
    const all = await evaluationApi.listTasks() || []
    completedTasks.value = all.filter((t: any) => t.status === 'completed')
    otherTasks.value = all.filter((t: any) => t.status !== 'completed')
  } catch (e) { console.error(e) }
}

const loadReport = async () => {
  if (!selectedTaskId.value) return
  try {
    report.value = await evaluationApi.getReport(selectedTaskId.value)
  } catch (e) { console.error(e) }
}

onMounted(async () => {
  await loadTasks()
  // 从路由参数恢复 taskId，自动加载报告
  const taskId = route.query.taskId as string
  if (taskId) {
    selectedTaskId.value = taskId
    await loadReport()
  }
})
</script>

<style lang="scss" scoped>
.report-body { display: flex; flex-direction: column; gap: 16px; }
</style>
