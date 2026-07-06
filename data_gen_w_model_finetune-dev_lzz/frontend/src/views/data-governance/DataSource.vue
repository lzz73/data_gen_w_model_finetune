<template>
  <div class="page-container">
    <PageHeader title="数据源接入">
      <el-button type="primary" @click="showUploadDialog = true">
        <el-icon><Plus /></el-icon>新增数据源
      </el-button>
    </PageHeader>

    <!-- 数据源列表 -->
    <div class="content-card">
      <el-table :data="dataSources" stripe>
        <el-table-column prop="name" label="数据源名称" />
        <el-table-column prop="type" label="类型" width="120">
          <template #default="{ row }">
            <el-tag :type="typeTag(row.type)" size="small">{{ row.type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="format" label="格式" width="100" />
        <el-table-column prop="size" label="大小" width="100" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === '已接入' ? 'success' : row.status === '处理中' ? 'warning' : 'info'" size="small">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="time" label="接入时间" width="180" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default>
            <el-button link type="primary" size="small">查看</el-button>
            <el-button link type="primary" size="small">处理</el-button>
            <el-button link type="danger" size="small">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 新增数据源对话框 -->
    <el-dialog v-model="showUploadDialog" title="新增数据源" width="600px">
      <el-form :model="uploadForm" label-width="100px">
        <el-form-item label="数据源类型">
          <el-radio-group v-model="uploadForm.type">
            <el-radio value="structured">结构化数据</el-radio>
            <el-radio value="unstructured">非结构化数据</el-radio>
            <el-radio value="manual">人工制作</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="uploadForm.type === 'structured'" label="接入方式">
          <el-select v-model="uploadForm.source" placeholder="请选择">
            <el-option label="上传CSV/Excel文件" value="file" />
            <el-option label="连接数据库" value="database" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="uploadForm.type === 'unstructured'" label="文件上传">
          <el-upload drag multiple :auto-upload="false" accept=".pdf,.doc,.docx">
            <el-icon :size="40"><UploadFilled /></el-icon>
            <div>将PDF/Word文件拖到此处，或<em>点击上传</em></div>
          </el-upload>
        </el-form-item>
        <el-form-item v-if="uploadForm.type === 'structured' && uploadForm.source === 'database'" label="数据库地址">
          <el-input v-model="uploadForm.dbHost" placeholder="如：192.168.1.100:3306" />
        </el-form-item>
        <el-form-item v-if="uploadForm.type === 'structured' && uploadForm.source === 'database'" label="账号密码">
          <el-input v-model="uploadForm.dbUser" placeholder="用户名" style="margin-bottom:8px" />
          <el-input v-model="uploadForm.dbPass" type="password" placeholder="密码" show-password />
        </el-form-item>
        <el-form-item v-if="uploadForm.type === 'manual'" label="模板选择">
          <el-select v-model="uploadForm.template" placeholder="请选择模板">
            <el-option label="指令-回复模板" value="instruct" />
            <el-option label="DPO偏好模板" value="dpo" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showUploadDialog = false">取消</el-button>
        <el-button type="primary" @click="showUploadDialog = false">确认接入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'

const showUploadDialog = ref(false)
const uploadForm = reactive({
  type: 'structured',
  source: 'file',
  dbHost: '',
  dbUser: '',
  dbPass: '',
  template: 'instruct',
})

const dataSources = [
  { name: '电力招标文件集', type: '非结构化', format: 'PDF', size: '256MB', status: '已接入', time: '2026-07-01 09:00' },
  { name: '合同条款数据库', type: '结构化', format: 'MySQL', size: '1.2GB', status: '已接入', time: '2026-06-30 14:30' },
  { name: '财务报表数据', type: '结构化', format: 'CSV', size: '45MB', status: '处理中', time: '2026-06-29 10:00' },
  { name: '规章制度文档', type: '非结构化', format: 'Word', size: '128MB', status: '已接入', time: '2026-06-28 16:00' },
  { name: '人工标注-指令回复集', type: '人工制作', format: 'JSONL', size: '12MB', status: '已接入', time: '2026-06-27 11:00' },
]

const typeTag = (type: string) => {
  const map: Record<string, string> = { '结构化': 'primary', '非结构化': 'warning', '人工制作': 'success' }
  return map[type] || 'info'
}
</script>
