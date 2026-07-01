<template>
  <div class="page-container">
    <PageHeader title="数据质量校验">
      <el-button type="primary" @click="runValidation">
        <el-icon><CircleCheck /></el-icon>执行校验
      </el-button>
    </PageHeader>

    <!-- 校验统计 -->
    <div class="stat-row">
      <StatCard icon="Document" label="总问答对" :value="156" color="#409eff" />
      <StatCard icon="CircleCheck" label="通过" :value="138" color="#67c23a" />
      <StatCard icon="Warning" label="疑似幻觉" :value="12" color="#e6a23c" />
      <StatCard icon="CircleClose" label="失败" :value="6" color="#f56c6c" />
    </div>

    <!-- 校验结果列表 -->
    <div class="content-card">
      <div class="card-title">校验结果</div>
      <el-table :data="validationResults" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="question" label="问题" show-overflow-tooltip />
        <el-table-column prop="answer" label="答案" show-overflow-tooltip />
        <el-table-column label="基础校验" width="100">
          <template #default="{ row }">
            <el-tag :type="row.basicCheck === '通过' ? 'success' : 'danger'" size="small">
              {{ row.basicCheck }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="语义校验" width="100">
          <template #default="{ row }">
            <el-tag :type="row.semanticCheck >= 0.5 ? 'success' : 'warning'" size="small">
              {{ row.semanticCheck >= 0.5 ? '通过' : '疑似幻觉' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="格式校验" width="100">
          <template #default="{ row }">
            <el-tag :type="row.formatCheck ? 'success' : 'danger'" size="small">
              {{ row.formatCheck ? '通过' : '异常' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="error" label="失败原因" width="150" show-overflow-tooltip />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button v-if="row.basicCheck === '失败'" link type="primary" size="small">重新生成</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatCard from '@/components/common/StatCard.vue'

const validationResults = ref([
  { id: 1, question: '电力采购招标的方式有哪些？', answer: '分为公开招标和邀请招标两种方式...', basicCheck: '通过', semanticCheck: 0.85, formatCheck: true, error: '' },
  { id: 2, question: '招标文件应包含哪些内容？', answer: '招标文件应包括技术要求...', basicCheck: '通过', semanticCheck: 0.72, formatCheck: true, error: '' },
  { id: 3, question: '安全生产的基本要求？', answer: '安全', basicCheck: '失败', semanticCheck: 0.15, formatCheck: false, error: '答案过短' },
  { id: 4, question: '合同审批流程是什么？', answer: '合同审批需要经过多个环节...', basicCheck: '通过', semanticCheck: 0.35, formatCheck: true, error: '疑似幻觉' },
  { id: 5, question: '财务报表的编制要求？', answer: '', basicCheck: '失败', semanticCheck: 0, formatCheck: false, error: '缺少关联内容' },
  { id: 6, question: '采购流程的步骤？', answer: '采购流程包括需求提出、审批、招标、签约、验收五个步骤', basicCheck: '通过', semanticCheck: 0.91, formatCheck: true, error: '' },
])

const runValidation = () => {
  // Mock: just a visual trigger
}
</script>
