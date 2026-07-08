/**
 * 评估工作台 API
 */
import request from './index'

export const evaluationApi = {
  listTasks: () => request.get('/evaluation/tasks'),
  runEval: (config: any) => request.post('/evaluation/run', config),
  getReport: (taskId: string) => request.get(`/evaluation/report/${taskId}`),
  deleteTask: (taskId: string) => request.delete(`/evaluation/tasks/${taskId}`),
}
