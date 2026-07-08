/**
 * 系统管理 API
 */
import request from './index'

export const systemApi = {
  getGpuDashboard: () => request.get('/system/gpu'),
  getHealth: () => request.get('/system/health'),
}
