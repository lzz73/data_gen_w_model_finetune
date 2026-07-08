/**
 * 数据治理数据集 API
 * 用于数据治理模块的数据集列表/导出（走 /projects/{id}/datasets 路由）
 * 训练数据集管理请使用 trainingApi.listTrainingDatasets() 等（见 @/api/training）
 */
import request from './index'

export interface GovernanceDatasetItem {
  id: string
  name: string
  description?: string
  question_count?: number
  extra_data?: Record<string, any>
  created_at: string
}

/** 数据治理数据集 API（基于项目） */
export const governanceDatasetApi = {
  /** 获取当前项目的数据集列表 */
  list: (projectId: string) => request.get(`/projects/${projectId}/datasets`),

  /** 导出数据集为 JSONL/JSON/Excel ZIP */
  export: (projectId: string, datasetId: string, data: any) =>
    request.post(`/projects/${projectId}/datasets/${datasetId}/export`, data, {
      responseType: 'blob',
    }),
}
