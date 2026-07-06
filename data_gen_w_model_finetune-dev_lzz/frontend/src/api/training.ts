/**
 * 训练管理 API
 */
import { get, post, createWebSocket } from './index'

export interface TrainConfig {
  mode: string
  dataset: string
  base_model: string
  preset: string
  learning_rate: string
  num_train_epochs: number
  per_device_train_batch_size: number
  cutoff_len: number
  gradient_accumulation_steps: number
  max_samples: number
  lr_scheduler_type: string
  warmup_steps: number
  max_grad_norm: string
  optim: string
  dtype: string
  template: string
  lora_rank: number
  lora_alpha: number
  lora_dropout: string
  lora_target: string
  finetuning_type: string
  do_eval: boolean
  val_size: string
  eval_dataset: string
  eval_steps: number
  save_steps: number
  logging_steps: number
  save_total_limit: number
  flash_attn: string
  gpu: string
}

export interface GpuInfo {
  name: string
  model: string
  total_mem_gb: number
  used_mem_gb: number
  free_mem_gb: number
  utilization: number
  temperature: number
  power_w: number
  used_percent: number
  status: string
}

export interface TrainTask {
  task_id: string
  name: string
  type: string
  model: string
  status: string         // pending | running | completed | failed | cancelled
  progress: number
  current_loss: number | null
  gpu_usage: number | null
  eta: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  config: TrainConfig
  logs: LogEntry[]
  loss_history: number[]
}

export interface LogEntry {
  time: string
  msg: string
  type: 'info' | 'warn' | 'error'
}

export interface DashboardStats {
  dataset_count: number
  training_running: number
  training_completed: number
  gpu_utilization: number
  recent_tasks: {
    name: string
    type: string
    model: string
    status: string
    time: string
  }[]
}

// --- REST API ---

export function fetchTasks() {
  return get<TrainTask[]>('/training/tasks')
}

export function fetchTask(taskId: string) {
  return get<TrainTask>(`/training/tasks/${taskId}`)
}

export function fixTaskStatus() {
  return post<{ fixed: number; message: string }>('/training/tasks/fix-status')
}

export function createTask(config: TrainConfig) {
  return post<{ task_id: string }>('/training/tasks', config)
}

export function cancelTask(taskId: string) {
  return post(`/training/tasks/${taskId}/cancel`)
}

export function resumeTask(taskId: string) {
  return post<{ task_id: string }>(`/training/tasks/${taskId}/resume`)
}

export interface SupportedModel {
  name: string
  huggingface: string
  modelscope: string
  local: boolean
  local_path: string
}

export interface ModelsResponse {
  data: SupportedModel[]
  local_count: number
  total_count: number
}

export function fetchSupportedModels() {
  return get<ModelsResponse>('/training/models')
}

export function fetchGpuInfo() {
  return get<GpuInfo[]>('/training/gpu')
}

export function fetchDashboard() {
  return get<DashboardStats>('/training/dashboard')
}

// --- WebSocket 实时监控 ---

export function exportModel(data: { task_id: string; export_dir: string; export_size: number }) {
  return post<{ export_dir: string }>('/training/export', data)
}

export function connectTrainMonitor(taskId: string): WebSocket {
  return createWebSocket(`/api/training/ws/${taskId}`)
}
