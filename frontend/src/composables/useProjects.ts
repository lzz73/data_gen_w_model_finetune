/**
 * 项目相关业务逻辑
 */
import { ref } from 'vue'
import { projectApi } from '@/api'
import type { Project, ProjectCreate } from '@/types'
import { ElMessage } from 'element-plus'

export function useProjects() {
  const loading = ref(false)
  const projects = ref<Project[]>([])

  const fetchProjects = async () => {
    loading.value = true
    try {
      const res = await projectApi.list()
      if (res && typeof res === 'object' && 'items' in res) {
        projects.value = res.items || []
      } else if (Array.isArray(res)) {
        projects.value = res
      } else {
        projects.value = []
      }
    } catch (error: any) {
      console.error('获取项目列表失败:', error)
      ElMessage.error('获取项目列表失败')
      projects.value = []
    } finally {
      loading.value = false
    }
  }

  const createProject = async (data: ProjectCreate): Promise<Project | null> => {
    try {
      const res = await projectApi.create(data)
      ElMessage.success('创建成功')
      await fetchProjects()
      return res as any
    } catch (error: any) {
      console.error('创建项目失败:', error)
      ElMessage.error(error?.message || '创建项目失败')
      return null
    }
  }

  const deleteProject = async (id: string): Promise<boolean> => {
    try {
      await projectApi.delete(id)
      ElMessage.success('删除成功')
      await fetchProjects()
      return true
    } catch (error: any) {
      console.error('删除项目失败:', error)
      ElMessage.error(error?.message || '删除项目失败')
      return false
    }
  }

  const fetchProject = async (id: string): Promise<Project | null> => {
    try {
      const res = await projectApi.get(id)
      return res as Project
    } catch (error: any) {
      console.error('获取项目详情失败:', error)
      ElMessage.error('获取项目详情失败')
      return null
    }
  }

  return {
    loading,
    projects,
    fetchProjects,
    createProject,
    deleteProject,
    fetchProject
  }
}
