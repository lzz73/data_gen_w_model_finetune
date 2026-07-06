<template>
  <div class="stat-card" :style="{ borderTop: `3px solid ${color}` }">
    <div class="stat-icon" :style="{ background: color + '20', color: color }">
      <el-icon :size="24"><component :is="icon" /></el-icon>
    </div>
    <div class="stat-info">
      <div class="stat-value">{{ value }}</div>
      <div class="stat-label">{{ label }}</div>
    </div>
    <div v-if="trend" class="stat-trend" :class="trend > 0 ? 'up' : 'down'">
      <el-icon><Top v-if="trend > 0" /><Bottom v-else /></el-icon>
      {{ Math.abs(trend) }}%
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  icon: string
  label: string
  value: string | number
  color?: string
  trend?: number
}>()
</script>

<style lang="scss" scoped>
.stat-card {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  transition: box-shadow 0.3s;

  &:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
  }

  .stat-icon {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .stat-info {
    flex: 1;

    .stat-value {
      font-size: 24px;
      font-weight: 700;
      color: #303133;
      line-height: 1.2;
    }

    .stat-label {
      font-size: 13px;
      color: #909399;
      margin-top: 4px;
    }
  }

  .stat-trend {
    font-size: 13px;
    display: flex;
    align-items: center;
    gap: 2px;

    &.up {
      color: #67c23a;
    }

    &.down {
      color: #f56c6c;
    }
  }
}
</style>
