<template>
  <div class="page-container">
    <PageHeader title="大模型配置">
      <template #subtitle>
        <el-text type="info" size="small">配置用于生成问答对的 API 大模型</el-text>
      </template>
      <el-button type="primary" @click="showAddDialog = true">
        <el-icon><Plus /></el-icon>添加模型
      </el-button>
    </PageHeader>

    <!-- 模型配置列表 -->
    <div class="content-card">
      <div class="card-title" style="display: flex; align-items: center; justify-content: space-between;">
        <span>对话模型（Chat）</span>
        <el-text type="info" size="small">问答对生成使用此处配置的 Chat 模型</el-text>
      </div>
      <el-table :data="chatModels" stripe v-loading="loading">
        <el-table-column prop="model_name" label="模型名称" />
        <el-table-column prop="provider" label="厂商" width="100">
          <template #default="{ row }">
            {{ providerLabel(row.provider) }}
          </template>
        </el-table-column>
        <el-table-column label="默认" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.is_default === 'true'" type="success" size="small">默认</el-tag>
            <el-button v-else link type="primary" size="small" @click="handleSetDefault(row)">设为默认</el-button>
          </template>
        </el-table-column>
        <el-table-column label="连接状态" width="100">
          <template #default="{ row }">
            <el-tag
              :type="row.connection_status === 'connected' ? 'success' : row.connection_status === 'disconnected' ? 'danger' : 'info'"
              size="small"
            >
              {{ connectionStatusLabel(row.connection_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="handleEdit(row)">编辑</el-button>
            <el-button link type="primary" size="small" @click="handleTest(row)">测试</el-button>
            <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <EmptyState
        v-if="!loading && chatModels.length === 0"
        description="暂无对话模型，请先添加用于生成问答对的 Chat 模型"
        action-text="添加模型"
        @action="showAddDialog = true"
      />
    </div>

    <!-- 添加/编辑模型对话框 -->
    <el-dialog v-model="showAddDialog" :title="editingModel ? '编辑模型' : '添加对话模型'" width="500px" @close="resetForm">
      <el-alert
        v-if="!editingModel"
        type="info"
        :closable="false"
        style="margin-bottom: 16px;"
      >
        <template #title>
          添加用于生成问答对的 Chat 类型大模型 API 配置
        </template>
      </el-alert>
      <el-form ref="formRef" :model="addForm" :rules="formRules" label-width="100px" label-position="top">
        <el-form-item label="厂商" prop="provider">
          <el-select v-model="addForm.provider" placeholder="选择厂商" style="width: 100%">
            <el-option v-for="p in providerOptions" :key="p.value" :label="p.label" :value="p.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型名称" prop="model_name">
          <el-input v-model="addForm.model_name" placeholder="如：qwen-plus、gpt-4o、glm-4-flash" />
        </el-form-item>
        <el-form-item label="API Key" prop="api_key">
          <el-input v-model="addForm.api_key" type="password" show-password :placeholder="editingModel ? '留空则不修改' : '输入 API Key'" />
        </el-form-item>
        <el-form-item label="API Base">
          <el-input v-model="addForm.api_base" placeholder="如：https://api.openai.com/v1" />
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="addForm.is_default" />
          <el-text type="info" size="small" style="margin-left: 8px;">默认模型将自动用于问答生成</el-text>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :loading="adding" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>

    <!-- 删除确认 -->
    <DeleteDialog
      v-model:visible="showDeleteDialog"
      :item-name="deleteTarget?.model_name"
      item-type="模型配置"
      :loading="deleteLoading"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useModels } from '@/composables/useModels'
import { ElMessage } from 'element-plus'
import PageHeader from '@/components/common/PageHeader.vue'
import DeleteDialog from '@/components/common/DeleteDialog.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import type { Model } from '@/types'
import type { FormInstance, FormRules } from 'element-plus'

const { loading, models, fetchModels, setDefaultModel, testModel, deleteModel } = useModels()

// 只展示 chat 类型
const chatModels = computed(() => models.value.filter(m => m.model_type === 'chat'))

const showAddDialog = ref(false)
const adding = ref(false)
const showDeleteDialog = ref(false)
const deleteTarget = ref<Model | null>(null)
const deleteLoading = ref(false)
const formRef = ref<FormInstance>()
const editingModel = ref<Model | null>(null)

const providerOptions = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'ali', label: '阿里云' },
  { value: 'glm', label: '智谱' },
  { value: 'minimax', label: 'MiniMax' },
]

// 添加时固定为 chat 类型
const addForm = reactive({
  provider: 'openai' as const,
  model_type: 'chat' as const,
  model_name: '',
  api_key: '',
  api_base: '',
  is_default: false,
})

const formRules: FormRules = {
  provider: [{ required: true, message: '请选择厂商', trigger: 'change' }],
  model_name: [{ required: true, message: '请输入模型名称', trigger: 'blur' }],
  api_key: [{ required: true, message: '请输入 API Key', trigger: 'blur' }],
}

const resetForm = () => {
  addForm.provider = 'openai'
  addForm.model_name = ''
  addForm.api_key = ''
  addForm.api_base = ''
  addForm.is_default = false
  editingModel.value = null
  formRef.value?.resetFields()
}

const handleEdit = (row: Model) => {
  editingModel.value = row
  addForm.provider = row.provider || 'openai'
  addForm.model_name = row.model_name || ''
  addForm.api_key = ''  // 不回显 API Key
  addForm.api_base = row.api_base || ''
  addForm.is_default = row.is_default === 'true'
  showAddDialog.value = true
}

const handleSubmit = async () => {
  // 编辑模式下 api_key 可以为空（留空不修改）
  if (editingModel.value && !addForm.api_key) {
    // 只校验非 api_key 字段
    const fieldsToValidate = ['provider', 'model_name'] as const
    let allValid = true
    for (const field of fieldsToValidate) {
      const valid = await formRef.value?.validateField(field).catch(() => false)
      if (!valid) allValid = false
    }
    if (!allValid) return
  } else {
    const valid = await formRef.value?.validate().catch(() => false)
    if (!valid) return
  }

  adding.value = true
  try {
    const { modelApi } = await import('@/api')
    const payload = {
      ...addForm,
      is_default: addForm.is_default ? 'true' : 'false',
    }

    if (editingModel.value) {
      // 编辑模式：不传空 API Key（避免覆盖）
      const updateData: any = { ...payload }
      if (!updateData.api_key) delete updateData.api_key
      await modelApi.update(editingModel.value.id, updateData)
      ElMessage.success('更新成功')
    } else {
      await modelApi.create(payload)
      ElMessage.success('添加成功')
    }
    showAddDialog.value = false
    await fetchModels()
  } catch (error: any) {
    ElMessage.error(error?.message || (editingModel.value ? '更新失败' : '添加失败'))
  } finally {
    adding.value = false
  }
}

const handleTest = async (row: Model) => {
  try {
    ElMessage.info('正在测试连接...')
    const result = await testModel(row.id)
    if (result?.success) {
      ElMessage.success('连接成功')
    } else {
      ElMessage.error(result?.message || '连接失败')
    }
    await fetchModels()
  } catch (error: any) {
    ElMessage.error(error?.message || '测试失败')
  }
}

const handleSetDefault = async (row: Model) => {
  const ok = await setDefaultModel(row.id)
  if (ok) ElMessage.success('已设为默认模型')
}

const handleDelete = (row: Model) => {
  deleteTarget.value = row
  showDeleteDialog.value = true
}

const confirmDelete = async () => {
  if (!deleteTarget.value) return
  deleteLoading.value = true
  const ok = await deleteModel(deleteTarget.value.id)
  if (ok) showDeleteDialog.value = false
  deleteLoading.value = false
}

const providerLabel = (provider: string) => {
  return providerOptions.find(p => p.value === provider)?.label || provider
}

const connectionStatusLabel = (status?: string) => {
  const map: Record<string, string> = { connected: '已连接', disconnected: '断开', untested: '未测试' }
  return map[status || ''] || '未测试'
}

onMounted(() => {
  fetchModels()
})
</script>
