import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { projectApi } from '@/api'
import type { Project, ProjectStats } from '@/types'

export const useProjectStore = defineStore('project', () => {
  const currentProjectId = ref<string | null>(null)
  const currentProject = ref<Project | null>(null)
  const currentStats = ref<ProjectStats | null>(null)
  const projects = ref<Project[]>([])
  const loading = ref(false)

  const hasProject = computed(() => !!currentProjectId.value)

  const setCurrentProject = async (id: string) => {
    currentProjectId.value = id
    try {
      const [project, stats] = await Promise.all([
        projectApi.get(id),
        projectApi.stats(id)
      ])
      currentProject.value = project as Project
      currentStats.value = stats as ProjectStats
    } catch (e) {
      console.error('Failed to load project:', e)
    }
  }

  const fetchProjects = async () => {
    loading.value = true
    try {
      const res = await projectApi.list()
      if (res && typeof res === 'object' && 'items' in res) {
        projects.value = (res as any).items || []
      } else if (Array.isArray(res)) {
        projects.value = res
      } else {
        projects.value = []
      }
    } catch (e: any) {
      projects.value = []
      console.error('加载项目列表失败:', e?.message)
    } finally {
      loading.value = false
    }
  }

  const clearCurrentProject = () => {
    currentProjectId.value = null
    currentProject.value = null
    currentStats.value = null
  }

  return {
    currentProjectId,
    currentProject,
    currentStats,
    projects,
    loading,
    hasProject,
    setCurrentProject,
    fetchProjects,
    clearCurrentProject
  }
})
