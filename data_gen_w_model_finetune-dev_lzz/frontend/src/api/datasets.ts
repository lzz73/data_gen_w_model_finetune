/**
 * 数据集管理 API
 */
import { get, post, del, uploadFile } from './index'

export interface DatasetItem {
  name: string
  format: string
  samples: number
  version: string
  version_id: string
  fields: string[]
  created_at: string
  hash: string
}

export interface ValidationResult {
  level: string
  code: string
  message: string
  row: number | null
  field: string | null
}

export interface UploadResult {
  success: boolean
  message: string
  version: {
    version_id: string
    version_number: number
    row_count: number
    fields: string[]
    created_at: string
  } | null
  validation_results: ValidationResult[]
}

export function fetchDatasets(): Promise<{ code: number; data: DatasetItem[] }> {
  return get('/datasets')
}

export function uploadDataset(
  file: File,
  datasetName: string,
  format: string = 'jsonl',
  description: string = '',
  requiredFields: string = '',
) {
  return uploadFile<UploadResult>('/datasets/upload', file, {
    dataset_name: datasetName,
    format,
    description,
    required_fields: requiredFields,
  })
}

export function validateDataset(
  file: File,
  format: string = 'jsonl',
  requiredFields: string = '',
) {
  return uploadFile('/datasets/validate', file, { format, required_fields: requiredFields })
}

export function fetchVersions(datasetName: string) {
  return get(`/datasets/${encodeURIComponent(datasetName)}/versions`)
}

export function fetchDatasetData(datasetName: string, versionId?: string) {
  const query = versionId ? `?version_id=${versionId}` : ''
  return get(`/datasets/${encodeURIComponent(datasetName)}/data${query}`)
}

export function deleteVersion(versionId: string) {
  return del(`/datasets/${versionId}`)
}
