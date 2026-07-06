/**
 * 模型相关业务逻辑
 */
import { ref } from 'vue'
import { modelApi } from '@/api'
import type { Model, ModelCreate } from '@/types'
import { ElMessage } from 'element-plus'

export function useModels() {
  const loading = ref(false)
  const models = ref<Model[]>([])

  const fetchModels = async () => {
    loading.value = true
    try {
      const res = await modelApi.list()
      if (Array.isArray(res)) {
        models.value = res
      } else if (res && typeof res === 'object' && 'items' in res) {
        models.value = (res as any).items || []
      } else {
        models.value = []
      }
    } catch (error: any) {
      console.error('获取模型列表失败:', error)
      ElMessage.error('获取模型列表失败')
      models.value = []
    } finally {
      loading.value = false
    }
  }

  const addModel = async (data: ModelCreate): Promise<boolean> => {
    try {
      await modelApi.create(data)
      ElMessage.success('添加成功')
      await fetchModels()
      return true
    } catch (error: any) {
      console.error('添加模型失败:', error)
      ElMessage.error(error?.message || '添加模型失败')
      return false
    }
  }

  const updateModel = async (id: string, data: Partial<Model>): Promise<boolean> => {
    try {
      await modelApi.update(id, data)
      ElMessage.success('更新成功')
      await fetchModels()
      return true
    } catch (error: any) {
      console.error('更新模型失败:', error)
      ElMessage.error(error?.message || '更新模型失败')
      return false
    }
  }

  const deleteModel = async (id: string): Promise<boolean> => {
    try {
      await modelApi.delete(id)
      ElMessage.success('删除成功')
      await fetchModels()
      return true
    } catch (error: any) {
      console.error('删除模型失败:', error)
      ElMessage.error(error?.message || '删除模型失败')
      return false
    }
  }

  const setDefaultModel = async (id: string): Promise<boolean> => {
    try {
      await modelApi.setDefault(id)
      ElMessage.success('设置成功')
      await fetchModels()
      return true
    } catch (error: any) {
      console.error('设置默认模型失败:', error)
      ElMessage.error(error?.message || '设置默认模型失败')
      return false
    }
  }

  const testModel = async (id: string): Promise<{ success: boolean; message: string } | null> => {
    try {
      const res = await modelApi.test(id)
      return res.test_result
    } catch (error: any) {
      console.error('测试模型失败:', error)
      ElMessage.error(error?.message || '测试模型失败')
      return null
    }
  }

  return {
    loading,
    models,
    fetchModels,
    addModel,
    updateModel,
    deleteModel,
    setDefaultModel,
    testModel
  }
}
