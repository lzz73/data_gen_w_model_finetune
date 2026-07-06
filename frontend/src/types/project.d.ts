/**
 * Project Types
 */

export interface Project {
  id: string
  name: string
  description?: string
  type: string
  created_at: string
  updated_at: string
}

export interface ProjectCreate {
  name: string
  description: string
  type: string
}

export interface ProjectUpdate {
  name?: string
  description?: string
  type?: string
}

export interface ProjectStats {
  file_count: number
  chunk_count: number
  question_count: number
  dataset_count: number
  eval_count: number
}
