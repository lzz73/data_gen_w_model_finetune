<template>
  <div class="page-header">
    <div class="page-title">{{ title }}</div>
    <div class="page-actions">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
}>()
</script>

<style lang="scss" scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;

  .page-title {
    font-size: 20px;
    font-weight: 600;
    color: #303133;
  }

  .page-actions {
    display: flex;
    gap: 10px;
  }
}
</style>
