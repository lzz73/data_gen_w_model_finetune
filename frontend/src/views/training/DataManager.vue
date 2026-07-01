<template>
  <div class="page-container">
    <PageHeader title="数据管理">
      <el-button type="primary" @click="showUploadDialog = true">
        <el-icon><Upload /></el-icon>上传数据集
      </el-button>
    </PageHeader>

    <!-- 数据集列表 -->
    <div class="content-card">
      <div class="card-title">数据集列表</div>
      <el-table :data="datasets" stripe>
        <el-table-column prop="name" label="数据集名称" />
        <el-table-column prop="format" label="格式" width="80">
          <template #default><el-tag size="small">JSONL</el-tag></template>
        </el-table-column>
        <el-table-column prop="samples" label="样本数" width="80" />
        <el-table-column prop="version" label="版本" width="80" />
        <el-table-column label="校验状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.validStatus === '通过' ? 'success' : row.validStatus === '校验中' ? 'warning' : 'danger'" size="small">
              {{ row.validStatus }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="warnings" label="警告" width="100">
          <template #default="{ row }">
            <el-text v-if="row.warnings" type="warning" size="small">{{ row.warnings }}</el-text>
            <el-text v-else type="success" size="small">无</el-text>
          </template>
        </el-table-column>
        <el-table-column prop="time" label="创建时间" width="180" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default>
            <el-button link type="primary" size="small">查看</el-button>
            <el-button link type="primary" size="small">版本</el-button>
            <el-button link type="danger" size="small">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 上传对话框 -->
    <el-dialog v-model="showUploadDialog" title="上传数据集" width="500px">
      <el-upload drag :auto-upload="false" accept=".jsonl">
        <el-icon :size="40"><UploadFilled /></el-icon>
        <div>将JSONL文件拖到此处，或<em>点击上传</em></div>
      </el-upload>
      <template #footer>
        <el-button @click="showUploadDialog = false">取消</el-button>
        <el-button type="primary" @click="showUploadDialog = false">上传并校验</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'

const showUploadDialog = ref(false)

const datasets = [
  { name: '电力招标SFT数据集', format: 'JSONL', samples: 1200, version: 'v3', validStatus: '通过', warnings: '', time: '2026-07-01 10:00' },
  { name: '合同条款DPO数据集', format: 'JSONL', samples: 580, version: 'v2', validStatus: '通过', warnings: '数据量偏少', time: '2026-06-30 14:00' },
  { name: '财务报表SFT数据集', format: 'JSONL', samples: 350, version: 'v1', validStatus: '未通过', warnings: 'output空值占比12%', time: '2026-06-29 09:00' },
  { name: '规章制度CPT数据集', format: 'JSONL', samples: 2100, version: 'v1', validStatus: '校验中', warnings: '', time: '2026-06-28 16:00' },
]
</script>
