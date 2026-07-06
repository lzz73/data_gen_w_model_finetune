/**
 * Model Configuration Types
 */

export interface Model {
  id: string
  provider: ModelProvider
  model_type: ModelType
  model_name: string
  api_key?: string
  api_base?: string
  is_default: 'true' | 'false'
  connection_status?: 'untested' | 'connected' | 'disconnected'
  created_at?: string
  updated_at?: string
}

export interface ModelConfig {
  id: string
  provider: ModelProvider
  model_type: ModelType
  model_name: string
  api_key?: string
  api_base?: string
  is_default: 'true' | 'false'
  connection_status?: 'untested' | 'connected' | 'disconnected'
  created_at?: string
  updated_at?: string
}

export type ModelProvider = 'minimax' | 'glm' | 'openai' | 'ali'

export type ModelType = 'chat' | 'vlm' | 'embedding' | 'rerank'

export interface ModelCreate {
  provider: ModelProvider
  model_type: ModelType
  model_name: string
  api_key: string
  api_base?: string
  is_default: boolean
}

export interface ProviderOption {
  value: ModelProvider
  label: string
  abbr: string
}
