<template>
  <div ref="chartRef" class="loss-chart" />
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'

const props = defineProps<{
  data?: { step: number; loss: number }[]
}>()

const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

const defaultData = Array.from({ length: 50 }, (_, i) => ({
  step: i + 1,
  loss: Math.max(0.1, 2.5 * Math.exp(-i * 0.06) + (Math.random() - 0.5) * 0.2),
}))

onMounted(() => {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value)
  const data = props.data || defaultData

  chart.setOption({
    tooltip: {
      trigger: 'axis',
      formatter: 'Step {b}: {c}',
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

  const resize = () => chart?.resize()
  window.addEventListener('resize', resize)
  onUnmounted(() => {
    window.removeEventListener('resize', resize)
    chart?.dispose()
  })
})
</script>

<style scoped>
.loss-chart {
  width: 100%;
  height: 300px;
}
</style>
