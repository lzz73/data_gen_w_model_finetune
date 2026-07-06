<template>
  <el-dialog
    v-model="dialogVisible"
    title="确认删除"
    width="400px"
  >
    <div style="text-align: center; padding: 10px 0;">
      <el-icon :size="48" color="#E6A23C" style="margin-bottom: 12px;"><WarningFilled /></el-icon>
      <p>确定要删除{{ itemType }} <strong>{{ itemName }}</strong> 吗？</p>
      <p style="color: #909399; font-size: 13px; margin-top: 8px;">此操作不可撤销</p>
    </div>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="danger" :loading="loading" @click="handleConfirm">确认删除</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'

const props = defineProps<{
  visible: boolean
  itemName?: string
  itemType?: string
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
  (e: 'confirm'): void
}>()

const dialogVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val)
})

const handleConfirm = () => {
  emit('confirm')
}
</script>
