<template>
  <div class="page-container">
    <PageHeader title="训练监控">
      <template v-if="currentTask">
        <el-button v-if="currentTask.status === 'running' && (taskStatus.progress || 0) < 100" type="danger" @click="handleCancel">
          <el-icon><VideoPause /></el-icon>中断训练
        </el-button>
        <el-button v-if="currentTask.status === 'completed' || (currentTask.status === 'running' && (taskStatus.progress || 0) >= 100)" type="success" disabled>
          <el-icon><CircleCheck /></el-icon>已完成
        </el-button>
        <el-button v-if="currentTask.status === 'completed'" type="primary" @click="handleResume">
          <el-icon><RefreshRight /></el-icon>再次训练
        </el-button>
        <el-button v-if="currentTask.status === 'cancelled' || currentTask.status === 'failed'" @click="handleModifyAndRetrain">
          <el-icon><Edit /></el-icon>修改参数重训
        </el-button>
        <el-button v-if="currentTask.status === 'cancelled' || currentTask.status === 'failed'" type="primary" @click="handleResume">
          <el-icon><VideoPlay /></el-icon>原参数重训
        </el-button>
      </template>
    </PageHeader>

    <!-- 训练概览 -->
    <div class="stat-row">
      <StatCard icon="Timer" label="训练进度" :value="taskStatus.progress + '%'" color="#409eff" />
      <StatCard icon="TrendCharts" label="当前Loss" :value="taskStatus.current_loss?.toFixed(4) || '--'" color="#67c23a" />
      <StatCard icon="Monitor" label="GPU占用" :value="gpuAvgUsage" color="#e6a23c" />
      <StatCard icon="Clock" label="预计剩余" :value="taskStatus.eta || '--'" color="#909399" />
    </div>

    <el-row :gutter="16">
      <el-col :span="16">
        <div class="content-card">
          <div class="card-title">Loss曲线</div>
          <LossChart :data="lossHistory" />
        </div>
      </el-col>
      <el-col :span="8">
        <div class="content-card">
          <div class="card-title">GPU状态</div>
          <div v-if="gpus.length === 0" style="color:#909399;text-align:center;padding:20px">
            {{ wsConnected ? '加载中...' : '无GPU数据' }}
          </div>
          <div v-for="gpu in gpus" :key="gpu.name" class="gpu-item">
            <div class="gpu-header">
              <span class="gpu-name">{{ gpu.name }} ({{ gpu.model }})</span>
              <span class="gpu-mem">{{ gpu.used_mem_gb }}G / {{ gpu.total_mem_gb }}G</span>
            </div>
            <el-progress :percentage="gpu.used_percent" :color="gpu.used_percent > 90 ? '#f56c6c' : '#409eff'" :stroke-width="12" />
            <div class="gpu-detail">
              <span>温度: {{ gpu.temperature }}°C</span>
              <span>功耗: {{ gpu.power_w }}W</span>
              <span>利用率: {{ gpu.utilization }}%</span>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <div class="content-card">
      <div class="card-title">
        训练日志
        <el-tag v-if="wsConnected" type="success" size="small" style="margin-left:8px">实时连接中</el-tag>
        <el-tag v-else type="danger" size="small" style="margin-left:8px">已断开</el-tag>
        <el-tag v-if="currentTask" :type="displayStatus === 'completed' ? 'success' : statusColor(currentTask.status)" size="small" style="margin-left:8px">
          {{ statusLabel(displayStatus) }}
        </el-tag>
      </div>
      <div class="log-container" ref="logContainer">
        <div v-for="(log, i) in logs" :key="i" class="log-line" :class="log.type">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-msg">{{ log.msg }}</span>
        </div>
        <div v-if="logs.length === 0" class="log-line">
          <span class="log-msg" style="color:#6a9955">等待训练任务...</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageHeader from '@/components/common/PageHeader.vue'
import StatCard from '@/components/common/StatCard.vue'
import LossChart from '@/components/charts/LossChart.vue'
import { trainingApi, connectTrainMonitor } from '@/api/training'

interface GpuInfo {
  name: string
  model: string
  used_mem_gb: number
  total_mem_gb: number
  used_percent: number
  temperature: number
  power_w: number
  utilization: number
  status: string
}

interface LogEntry {
  time: string
  msg: string
  type: string
}

const wsConnected = ref(false)
const logs = ref<LogEntry[]>([])
const gpus = ref<GpuInfo[]>([])
const lossHistory = ref<number[]>([])
const logContainer = ref<HTMLElement | null>(null)
const currentTask = ref<any>(null)

const taskStatus = reactive({
  status: '',
  progress: 0,
  current_loss: null as number | null,
  eta: null as string | null,
})

let ws: WebSocket | null = null

const gpuAvgUsage = computed(() => {
  if (gpus.value.length === 0) return '--'
  return gpus.value.reduce((s, g) => s + g.used_percent, 0).toFixed(0) + '%'
})

const autoScroll = () => nextTick(() => {
  if (logContainer.value) logContainer.value.scrollTop = logContainer.value.scrollHeight
})

watch(logs, autoScroll, { deep: true })

const displayStatus = computed(() => {
  if (!currentTask.value) return ''
  if (currentTask.value.status === 'completed' || currentTask.value.status === 'failed' || currentTask.value.status === 'cancelled') 
    return currentTask.value.status
  if ((taskStatus.progress || 0) >= 100 || (currentTask.value?.progress || 0) >= 100) 
    return 'completed'
  return currentTask.value?.status || ''
})

const statusLabel = (s: string) => ({
  running: '训练中', completed: '已完成', failed: '失败', cancelled: '已中断', pending: '排队中'
} as any)[s] || s

const statusColor = (s: string) => ({
  running: 'warning', completed: 'success', failed: 'danger', cancelled: 'info', pending: ''
} as any)[s] || 'info'

const connectToLatestTask = async () => {
  try {
    const tasks = await trainingApi.listTasks()
    if (tasks && tasks.length > 0) {
      // 优先运行中 > 最新创建
      const running = tasks.find((t: any) => t.status === 'running')
      currentTask.value = running || tasks[0]  // tasks 已按时间倒序
      // 重置本任务的展示状态，避免上一个任务的残留
      logs.value = []
      lossHistory.value = []
      taskStatus.status = currentTask.value.status
      taskStatus.progress = currentTask.value.progress || 0
      taskStatus.current_loss = currentTask.value.current_loss ?? null
      taskStatus.eta = currentTask.value.eta ?? null
      // 拉一次最新详情（含 loss_history），再启动 WebSocket
      await refreshTaskState()
      startWebSocket(currentTask.value.task_id)
    }
  } catch (e) {
    logs.value = [{ time: '--:--:--', msg: '[ERROR] 无法连接后端', type: 'error' }]
  }
}

const startWebSocket = (taskId: string) => {
  if (ws) ws.close()
  ws = connectTrainMonitor(taskId)
  ws.onopen = () => {
    wsConnected.value = true
    // 先加载已有状态
    refreshTaskState()
  }
  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      switch (msg.type) {
        case 'log': logs.value.push(msg.data); break
        case 'loss':
          // 实时追加 loss 数据点到曲线
          if (typeof msg.value === 'number') {
            lossHistory.value.push(msg.value)
          }
          break
        case 'status':
          Object.assign(taskStatus, msg.data)
          if (currentTask.value) currentTask.value.status = msg.data.status || currentTask.value.status
          break
        case 'gpu': gpus.value = msg.data; break
        case 'done':
          wsConnected.value = false; ws?.close()
          refreshTaskState()
          // 只有新任务才是 running 时才重连
          const oldId = currentTask.value?.task_id
          setTimeout(async () => {
            try {
              const tasks = await trainingApi.listTasks()
              const running = tasks?.find((t: any) => t.status === 'running')
              if (running && running.task_id !== oldId) {
                connectToLatestTask()
              }
            } catch {}
          }, 2000)
          break
      }
    } catch {}
  }
  ws.onclose = () => { wsConnected.value = false }
  ws.onerror = () => { wsConnected.value = false }
}

const refreshTaskState = async () => {
  if (!currentTask.value) return
  try {
    const data = await trainingApi.getTask(currentTask.value.task_id)
    if (data) {
      currentTask.value = data
      // 同步刷新状态卡片（进度/Loss/ETA），避免显示上一个任务的残留数据
      Object.assign(taskStatus, {
        status: data.status,
        progress: data.progress || 0,
        current_loss: data.current_loss ?? null,
        eta: data.eta ?? null,
      })
      if (data.loss_history) lossHistory.value = data.loss_history
    }
  } catch {}
}

const handleCancel = async () => {
  if (!currentTask.value) return
  try {
    await ElMessageBox.confirm('确定中断当前训练？', '确认中断', { type: 'warning' })
    await trainingApi.cancelTask(currentTask.value.task_id)
    ElMessage.success('已发送中断指令')
    refreshTaskState()
  } catch {}
}

const handleModifyAndRetrain = () => {
  if (!currentTask.value) return
  // 把旧配置存到 sessionStorage，训练工作台会读取
  sessionStorage.setItem('retrain_config', JSON.stringify(currentTask.value.config || {}))
  router.push('/training')
}

const handleResume = async () => {
  if (!currentTask.value) return
  try {
    const data = await trainingApi.resumeTask(currentTask.value.task_id)
    if (data) {
      ElMessage.success('训练已重新启动')
      // 关闭旧WS，重新连接新任务
      if (ws) { ws.close(); wsConnected.value = false }
      logs.value = []
      lossHistory.value = []
      setTimeout(() => {
        currentTask.value!.task_id = data.task_id
        startWebSocket(data.task_id)
      }, 500)
    }
  } catch (e: any) {
    ElMessage.error('启动失败: ' + e.message)
  }
}

// 每5秒轮询任务状态（WebSocket断开时）
let pollTimer: any = null
onMounted(async () => {
  // 兜底：先把磁盘上已完成的、但状态还卡在 running/pending 的任务修正为 completed
  try { await trainingApi.fixStatus() } catch {}
  connectToLatestTask()
  pollTimer = setInterval(() => {
    if (!wsConnected.value) refreshTaskState()
  }, 5000)
})
onUnmounted(() => {
  if (ws) ws.close()
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style lang="scss" scoped>
.gpu-item {
  margin-bottom: 16px;
  .gpu-header { display: flex; justify-content: space-between; margin-bottom: 6px; .gpu-name { font-size: 13px; color: #303133; font-weight: 500; } .gpu-mem { font-size: 12px; color: #909399; } }
  .gpu-detail { display: flex; gap: 16px; margin-top: 4px; font-size: 12px; color: #909399; }
}
.log-container {
  max-height: 400px; overflow-y: auto; background: #1e1e1e; border-radius: 6px; padding: 12px;
  font-family: 'Consolas', 'Monaco', monospace; font-size: 12px;
  .log-line { padding: 2px 0; display: flex; gap: 12px; .log-time { color: #6a9955; flex-shrink: 0; } .log-msg { color: #d4d4d4; } &.warn .log-msg { color: #e6a23c; } &.error .log-msg { color: #f56c6c; } }
}
</style>
