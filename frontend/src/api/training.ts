/**
 * 训练管理 API
 */
import request from './index'

// 训练任务
export const trainingApi = {
  listTasks: () => request.get('/training/tasks'),
  getTask: (id: string) => request.get(`/training/tasks/${id}`),
  createTask: (config: any) => request.post('/training/tasks', config),
  cancelTask: (id: string) => request.post(`/training/tasks/${id}/cancel`),
  resumeTask: (id: string) => request.post(`/training/tasks/${id}/resume`),
  fixStatus: () => request.post('/training/tasks/fix-status'),

  // 模型
  listModels: () => request.get('/training/models'),
  listMergedModels: () => request.get('/training/merged-models'),
  listLoraModels: () => request.get('/training/lora-models'),
  listVerifyModels: () => request.get('/training/verify-models'),

  // GPU
  getGpuInfo: () => request.get('/training/gpu'),

  // Dashboard
  getDashboard: () => request.get('/training/dashboard'),

  // 导出
  exportModel: (data: any) => request.post('/training/export', data),
  getExportStatus: (jobId: string) => request.get(`/training/export/status/${jobId}`),

  // 在线验证
  verifyLoad: (data: any) => request.post('/training/verify-load', data),
  verifyUnload: (data: any) => request.post('/training/verify-unload', data),
  verifyChat: (data: any) => request.post('/training/verify-chat', data),
  getVerifyStatus: (path: string) => request.get(`/training/verify-status/${encodeURIComponent(path)}`),

  // 训练数据集管理
  listTrainingDatasets: () => request.get<TrainingDatasetItem[]>('/training/datasets'),
  uploadTrainingDataset: (file: File, datasetName: string) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('dataset_name', datasetName)
    return request.post<UploadDatasetResult>('/training/datasets/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  registerGovernanceDataset: (data: { name: string; file_name: string; formatting?: string; description?: string }) =>
    request.post('/training/datasets/register', data),
  deleteTrainingDataset: (name: string) => request.delete(`/training/datasets/${encodeURIComponent(name)}`),
  previewTrainingDataset: (name: string, limit: number = 20) =>
    request.get(`/training/datasets/${encodeURIComponent(name)}/preview`, { params: { limit } }),
  exportFromGovernance: (data: {
    project_id: string
    dataset_id: string
    train_name: string
    data_format?: string
    split_strategy?: string
    train_ratio?: number
    val_ratio?: number
    test_ratio?: number
  }) => request.post<any>('/training/datasets/export-from-governance', data),
}

/** 训练数据集条目 */
export interface TrainingDatasetItem {
  name: string
  file_name: string
  formatting: string
  samples: number
  exists: boolean
  size: number
  columns?: Record<string, string>
  tags?: Record<string, string>
}

/** 上传数据集结果 */
export interface UploadDatasetResult {
  name: string
  file_name: string
  formatting: string
  samples: number
  size: number
}

// WebSocket 连接
export function connectTrainMonitor(taskId: string): WebSocket {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return new WebSocket(`${protocol}//${location.host}/api/v1/training/ws/${taskId}`)
}
