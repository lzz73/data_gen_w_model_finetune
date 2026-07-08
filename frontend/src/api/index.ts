import axios from 'axios'
import type { AxiosInstance } from 'axios'
import type { Project, ProjectCreate, ProjectUpdate, ProjectStats, Model, ModelCreate } from '@/types'

const apiBaseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

const request: AxiosInstance = axios.create({
  baseURL: apiBaseURL,
  timeout: 60000
})

// Request interceptor
request.interceptors.request.use(
  config => config,
  error => Promise.reject(error)
)

// Response interceptor - unified unpacking
request.interceptors.response.use(
  response => {
    // Blob 响应（文件下载）直接返回，不做解包
    if (response.config?.responseType === 'blob') {
      return response.data
    }

    const data = response.data
    // Handle ApiResponse format: { success: true, data: ... }
    if (data.success !== undefined) {
      if (data.success) {
        // Check if this is a paginated response
        if (data.pagination) {
          return {
            items: data.data,
            total: data.pagination.total,
            page: data.pagination.page,
            page_size: data.pagination.page_size,
            total_pages: data.pagination.total_pages
          }
        }
        return data.data
      } else {
        return Promise.reject(new Error(data.message || data.error || '请求失败'))
      }
    }
    // Handle legacy training/evaluation format: { code: 0, data: ... }
    if (data.code !== undefined) {
      if (data.code === 0) {
        return data.data
      } else {
        return Promise.reject(new Error(data.message || data.error || `请求失败 (code: ${data.code})`))
      }
    }
    return data
  },
  error => {
    // 从后端响应中提取友好错误消息
    const data = error.response?.data
    let message = '请求失败'
    if (data) {
      // Blob 响应（文件下载请求出错时，后端返回 JSON 但被当成 Blob）
      if (data instanceof Blob) {
        // 同步方式无法读取 Blob，简单提示
        message = '导出失败'
      } else if (typeof data === 'object') {
        // ApiResponse 格式: { success: false, message: "..." }
        if (data.message) {
          message = data.message
        } else if (data.error?.message) {
          message = data.error.message
        }
      }
    } else {
      message = error.message || '请求失败'
    }
    console.error('API Error:', message)
    return Promise.reject(new Error(message))
  }
)

// Project API
export const projectApi = {
  list: (params?: { page?: number; page_size?: number }) =>
    request.get<{ items: Project[]; pagination: { total: number } }>('/projects', { params }),
  get: (id: string) => request.get<Project>(`/projects/${id}`),
  create: (data: ProjectCreate) => request.post<{ id: string }>('/projects', data),
  update: (id: string, data: ProjectUpdate) => request.put<Project>(`/projects/${id}`, data),
  delete: (id: string) => request.delete(`/projects/${id}`),
  stats: (id: string) => request.get<ProjectStats>(`/projects/${id}/stats`)
}

// File API
export const fileApi = {
  upload: (projectId: string, formData: FormData) =>
    request.post(`/projects/${projectId}/files/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }),
  list: (projectId: string) => request.get(`/projects/${projectId}/files`),
  get: (projectId: string, fileId: string) => request.get(`/projects/${projectId}/files/${fileId}`),
  delete: (projectId: string, fileId: string) => request.delete(`/projects/${projectId}/files/${fileId}`),
  preview: (projectId: string, fileId: string) =>
    request.get(`/projects/${projectId}/files/${fileId}/raw`, { responseType: 'text' }),
  extractFields: (projectId: string, fileId: string) =>
    request.post(`/projects/${projectId}/files/${fileId}/extract-fields`),
  updateFieldSchema: (projectId: string, fileId: string, data: any) =>
    request.put(`/projects/${projectId}/files/${fileId}/field-schema`, data),
}

// Chunk API
export const chunkApi = {
  split: (projectId: string, data: any) =>
    request.post(`/projects/${projectId}/chunks/split`, data, {
      timeout: 300000
    }),
  list: (projectId: string, params?: any) => request.get(`/projects/${projectId}/chunks`, { params }),
  get: (projectId: string, chunkId: string) => request.get(`/projects/${projectId}/chunks/${chunkId}`),
  update: (projectId: string, chunkId: string, data: any) => request.put(`/projects/${projectId}/chunks/${chunkId}`, data),
  delete: (projectId: string, chunkId: string) => request.delete(`/projects/${projectId}/chunks/${chunkId}`)
}

// Question API
export const questionApi = {
  generate: (projectId: string, data: any) => request.post(`/projects/${projectId}/questions/generate`, data),
  latestTask: (projectId: string) => request.get(`/projects/${projectId}/questions/tasks/latest`),
  generateAnswers: (projectId: string, data: any) => request.post(`/projects/${projectId}/questions/generate-answers`, data),
  latestAnswerTask: (projectId: string) => request.get(`/projects/${projectId}/questions/answer-tasks/latest`),
  list: (projectId: string, params?: any) => request.get(`/projects/${projectId}/questions`, { params }),
  listOutputFolders: (projectId: string) => request.get(`/projects/${projectId}/questions/output-folders`),
  getOutputFolderDetails: (projectId: string, folderName: string) => request.get(`/projects/${projectId}/questions/output-folders/${encodeURIComponent(folderName)}`),
  renameFolder: (projectId: string, folderName: string, newName: string) => request.put(`/projects/${projectId}/questions/output-folders/${encodeURIComponent(folderName)}/rename?new_name=${encodeURIComponent(newName)}`),
  deleteFolder: (projectId: string, folderName: string) => request.delete(`/projects/${projectId}/questions/output-folders/${encodeURIComponent(folderName)}`),
  // Answer folders
  listAnswerFolders: (projectId: string) => request.get(`/projects/${projectId}/questions/answer-folders`),
  getAnswerFolderDetails: (projectId: string, folderName: string) => request.get(`/projects/${projectId}/questions/answer-folders/${encodeURIComponent(folderName)}`),
  renameAnswerFolder: (projectId: string, folderName: string, newName: string) => request.put(`/projects/${projectId}/questions/answer-folders/${encodeURIComponent(folderName)}/rename?new_name=${encodeURIComponent(newName)}`),
  deleteAnswerFolder: (projectId: string, folderName: string) => request.delete(`/projects/${projectId}/questions/answer-folders/${encodeURIComponent(folderName)}`),
  cancelTask: (projectId: string, taskId: string) => request.post(`/projects/${projectId}/questions/tasks/${taskId}/cancel`),
  update: (projectId: string, questionId: string, data: any) => request.put(`/projects/${projectId}/questions/${questionId}`, data),
  delete: (projectId: string, questionId: string) => request.delete(`/projects/${projectId}/questions/${questionId}`),
  // QA pair generation (one-step: generate both question and answer)
  generateQA: (projectId: string, data: any) => request.post(`/projects/${projectId}/questions/generate-qa`, data),
  generateStructuredQA: (projectId: string, data: any) => request.post(`/projects/${projectId}/questions/generate-structured-qa`, data, {
    timeout: 120000,  // 模板模式可能需要较长时间处理大量数据
  }),
  latestQATask: (projectId: string, params?: { task_type?: string }) => request.get(`/projects/${projectId}/questions/qa-tasks/latest`, { params }),
  // Quality validation
  validate: (projectId: string, data?: any) => request.post(`/projects/${projectId}/questions/validate`, data || {}),
  regenerate: (projectId: string, questionId: string) => request.post(`/projects/${projectId}/questions/${questionId}/regenerate`),
  // Manual QA creation
  createManual: (projectId: string, data: { content: string; answer: string; source?: string; question_type?: string; rejected_answer?: string; batch_id?: string }) =>
    request.post(`/projects/${projectId}/questions/manual`, data),
  batchImport: (projectId: string, items: Array<{ content: string; answer: string; source?: string; question_type?: string; rejected_answer?: string }>) =>
    request.post(`/projects/${projectId}/questions/batch-import`, { items }),
  // Check embedding model (for semantic validation)
  checkEmbeddingModel: (projectId: string) => request.get(`/projects/${projectId}/questions/batches/check-embedding`),
  // QA folders
  listQAFolders: (projectId: string) => request.get(`/projects/${projectId}/questions/qa-folders`),
  getQAFolderDetails: (projectId: string, folderName: string) => request.get(`/projects/${projectId}/questions/qa-folders/${encodeURIComponent(folderName)}`),
  renameQAFolder: (projectId: string, folderName: string, newName: string) => request.put(`/projects/${projectId}/questions/qa-folders/${encodeURIComponent(folderName)}/rename?new_name=${encodeURIComponent(newName)}`),
  deleteQAFolder: (projectId: string, folderName: string) => request.delete(`/projects/${projectId}/questions/qa-folders/${encodeURIComponent(folderName)}`),
  // QA batches
  listBatches: (projectId: string) => request.get(`/projects/${projectId}/questions/batches`),
  getBatchDetails: (projectId: string, batchId: string, params?: any) => request.get(`/projects/${projectId}/questions/batches/${batchId}`, { params }),
  renameBatch: (projectId: string, batchId: string, name: string) =>
    request.put(`/projects/${projectId}/questions/batches/${batchId}/rename`, { name }),
  deleteBatch: (projectId: string, batchId: string) => request.delete(`/projects/${projectId}/questions/batches/${batchId}`),
  // Desensitize preview
  desensitizePreview: (projectId: string, text: string) =>
    request.post(`/projects/${projectId}/questions/desensitize-preview`, { text }),
  // Audit logs
  auditLogs: (projectId: string, params?: { chunk_id?: string; file_id?: string; page?: number; page_size?: number }) =>
    request.get(`/projects/${projectId}/questions/audit-logs`, { params }),
}

// Dataset API
export const datasetApi = {
  list: (projectId: string) => request.get(`/projects/${projectId}/datasets`),
  create: (projectId: string, data: any) => request.post(`/projects/${projectId}/datasets`, data),
  get: (projectId: string, datasetId: string) => request.get(`/projects/${projectId}/datasets/${datasetId}`),
  delete: (projectId: string, datasetId: string) => request.delete(`/projects/${projectId}/datasets/${datasetId}`),
  batchDelete: (projectId: string, datasetIds: string[]) => request.post(`/projects/${projectId}/datasets/batch-delete`, { dataset_ids: datasetIds }),
  export: (projectId: string, datasetId: string, data: any) =>
    request.post(`/projects/${projectId}/datasets/${datasetId}/export`, data, {
      responseType: 'blob'
    })
}

// Eval API
export const evalApi = {
  list: (projectId: string) => request.get(`/projects/${projectId}/eval`),
  create: (projectId: string, data: any) => request.post(`/projects/${projectId}/eval`, data),
  get: (projectId: string, evalId: string) => request.get(`/projects/${projectId}/eval/${evalId}`),
  run: (projectId: string, evalId: string) => request.post(`/projects/${projectId}/eval/${evalId}/evaluate`),
  delete: (projectId: string, evalId: string) => request.delete(`/projects/${projectId}/eval/${evalId}`),
  getResults: (projectId: string, taskId: string, params?: { page?: number; page_size?: number; type?: string; is_correct?: string }) =>
    request.get(`/projects/${projectId}/eval/tasks/${taskId}/results`, { params }),
  getResultsStats: (projectId: string, taskId: string) => request.get(`/projects/${projectId}/eval/tasks/${taskId}/results/stats`),
  listTasks: (projectId: string, params?: any) => request.get(`/projects/${projectId}/eval/tasks`, { params }),
  createTask: (projectId: string, data: any) => request.post(`/projects/${projectId}/eval/tasks`, data),
  getTask: (projectId: string, taskId: string) => request.get(`/projects/${projectId}/eval/tasks/${taskId}`),
  startTask: (projectId: string, taskId: string, data?: any) => request.post(`/projects/${projectId}/eval/tasks/${taskId}/start`, data || {}),
  stopTask: (projectId: string, taskId: string) => request.post(`/projects/${projectId}/eval/tasks/${taskId}/stop`),
  deleteTask: (projectId: string, taskId: string) => request.delete(`/projects/${projectId}/eval/tasks/${taskId}`)
}

// Model API
export const modelApi = {
  list: () => request.get<Model[]>('/models'),
  get: (id: string) => request.get<Model>(`/models/${id}`),
  create: (data: ModelCreate) => request.post<{ id: string }>('/models', data),
  update: (id: string, data: Partial<Model>) => request.put<Model>(`/models/${id}`, data),
  delete: (id: string) => request.delete(`/models/${id}`),
  setDefault: (id: string) => request.post(`/models/${id}/set-default`),
  test: (id: string) => request.post<{
    test_result: { success: boolean; message: string }
    model: Model
  }>(`/models/${id}/test`)
}

// Crawler API
export const crawlerApi = {
  start: (data: { url: string; css_selector?: string; extract_title?: boolean; extract_content?: boolean; extract_links?: boolean; extract_images?: boolean; project_id?: string; max_pages?: number }) =>
    request.post<{ task_id: string }>('/crawler/start', data),
  getTask: (taskId: string) => request.get<{
    task_id: string
    status: string
    progress: number
    url: string
    error?: string
    pages: Array<{ url: string; title?: string; content?: string; links?: string[]; images?: string[] }>
  }>(`/crawler/task/${taskId}`),
  save: (taskId: string, projectId: string) =>
    request.post<{ file_ids: string[]; count: number }>('/crawler/save', { task_id: taskId, project_id: projectId })
}

// Database Connection API
export const databaseApi = {
  connect: (data: { db_type: string; host?: string; port?: number; user?: string; password?: string; database: string }) =>
    request.post('/database/connect', data),
  importTable: (data: { db_type: string; host?: string; port?: number; user?: string; password?: string; database: string; table_name: string; project_id: string }) =>
    request.post('/database/import', data),
}

export default request
