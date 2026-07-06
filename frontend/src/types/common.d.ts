/**
 * Common Types
 */

// File types
export interface FileItem {
  id: string
  filename: string
  file_type: string
  size?: number
  status: string
  field_schema?: FieldSchemaItem[]
  row_count?: number
  created_at: string
  updated_at: string
}

// Field schema for structured files
export interface FieldSchemaItem {
  name: string
  type: string  // string, integer, float, date, boolean
  sample?: string[]
  missing_rate?: number
  role: 'feature' | 'target' | 'redundant'
  desensitize: boolean
  missing_strategy?: 'ignore' | 'drop_row' | 'fill_mode' | 'fill_default'
  fill_value?: string
}

// Chunk types
export interface Chunk {
  id: string
  name?: string
  content: string
  summary?: string
  word_count?: number
  file_id?: string
  created_at: string
  updated_at: string
}

// Question types
export interface Question {
  id: string
  content: string
  answer?: string
  question_type?: string
  chunk_id?: string
  batch_id?: string
  file_id?: string
  file_name?: string
  source: string
  generation_status?: string
  answer_status?: string
  answer_error?: string
  quality_score?: number
  generation_metadata?: any
  created_at: string
  updated_at: string
}

// Dataset types
export interface Dataset {
  id: string
  name: string
  description?: string
  dataset_type?: string
  question_count?: number
  created_at: string
  updated_at: string
}

// Dialog props
export interface DialogProps {
  visible: boolean
  loading?: boolean
}

export interface DeleteDialogProps extends DialogProps {
  itemName?: string
  itemType?: string
}
