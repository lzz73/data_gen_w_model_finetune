/**
 * API Response Types
 */

// Base API response wrapper
export interface ApiResponse<T = any> {
  success: boolean
  message: string
  data: T
  error: string | null
  timestamp: string
}

// Paginated response
export interface PaginatedResponse<T = any> extends ApiResponse<T> {
  page?: number
  page_size?: number
  total?: number
}

// List items wrapper
export interface ListResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

// Simple ID response
export interface IdResponse {
  id: string
}
