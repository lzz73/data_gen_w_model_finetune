<template>
  <div class="empty-state">
    <el-empty :description="description" :image-size="120">
      <template v-if="$slots.default">
        <slot />
      </template>
      <template v-else-if="actionText">
        <el-button type="primary" @click="$emit('action')">{{ actionText }}</el-button>
      </template>
    </el-empty>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  description?: string
  actionText?: string
}>()

defineEmits<{
  (e: 'action'): void
}>()
</script>

<style scoped>
.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 300px;
  padding: 40px 0;
}
</style>
