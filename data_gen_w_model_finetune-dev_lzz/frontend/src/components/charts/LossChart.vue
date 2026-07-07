<template>
  <div ref="chartRef" class="loss-chart" />
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps<{
  data?: number[] | { step: number; loss: number }[]
}>()

const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

function normalizeData(input?: number[] | { step: number; loss: number }[]) {
  // 输入为空时返回空（不画 mock）
  if (!input || input.length === 0) {
    return []
  }
  if (typeof input[0] === 'number') {
    return (input as number[]).map((loss, i) => ({ step: i + 1, loss }))
  }
  return input as { step: number; loss: number }[]
}

function initChart() {
  if (!chartRef.value) return
  if (!chart) {
    chart = echarts.init(chartRef.value)
  }

  const data = normalizeData(props.data)

  if (data.length === 0) {
    chart.clear()
    return
  }

  chart.setOption({
    title: { show: false },
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => `Step ${params[0].name}: ${params[0].value}`,
    },
    grid: { top: 20, right: 20, bottom: 30, left: 50 },
    xAxis: {
      type: 'category',
      data: data.map(d => d.step),
      name: 'Step',
    },
    yAxis: {
      type: 'value',
      name: 'Loss',
      min: 0,
    },
    series: [
      {
        type: 'line',
        data: data.map(d => Number(d.loss.toFixed(4))),
        smooth: true,
        lineStyle: { color: '#409eff', width: 2 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(64,158,255,0.3)' },
            { offset: 1, color: 'rgba(64,158,255,0.02)' },
          ]),
        },
        itemStyle: { color: '#409eff' },
      },
    ],
  })
}

onMounted(() => {
  initChart()
  const resize = () => chart?.resize()
  window.addEventListener('resize', resize)
  onUnmounted(() => {
    window.removeEventListener('resize', resize)
    chart?.dispose()
  })
})

// 数据变化时自动更新图表
watch(() => props.data, () => {
  if (chart) initChart()
}, { deep: true })
</script>

<style scoped>
.loss-chart {
  width: 100%;
  height: 300px;
}
</style>
