<template>
  <div class="page-container">
    <PageHeader title="人工生成">
      <el-radio-group v-model="templateType" size="small" style="margin-right: 12px;">
        <el-radio-button value="instruct">指令-回复</el-radio-button>
        <el-radio-button value="dpo">DPO 偏好</el-radio-button>
      </el-radio-group>
      <el-button type="primary" :loading="saving" :disabled="qaItems.length === 0" @click="saveToProject">
        <el-icon><Check /></el-icon>保存到项目
      </el-button>
      <el-dropdown @command="handleExport" style="margin-left: 8px;">
        <el-button :disabled="qaItems.length === 0">
          另存为 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="jsonl">JSONL 格式</el-dropdown-item>
            <el-dropdown-item command="json">JSON 格式</el-dropdown-item>
            <el-dropdown-item command="excel">Excel 格式</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </PageHeader>

    <EmptyState
      v-if="!projectStore.hasProject"
      description="请先在首页选择一个项目"
      action-text="前往首页"
      @action="$router.push('/')"
    />

    <template v-else>
      <!-- 上传文件区 -->
      <div class="content-card">
        <div class="card-title">导入文件</div>
        <el-upload
          ref="uploadRef"
          drag
          :auto-upload="false"
          :accept="'.json,.jsonl,.xlsx,.xls,.csv'"
          :limit="1"
          :on-change="handleFileChange"
          :on-remove="handleFileRemove"
          :file-list="uploadFileList"
        >
          <el-icon :size="36"><UploadFilled /></el-icon>
          <div>将文件拖到此处，或<em>点击上传</em></div>
        </el-upload>
        <div style="margin-top: 8px; font-size: 12px; color: #909399; line-height: 1.8;">
          <template v-if="templateType === 'instruct'">
            支持 JSONL（每行 <code>{"instruction":"...","response":"..."}</code>）、JSON 数组、Excel/CSV（列名 instruction / response）
          </template>
          <template v-else>
            支持 JSONL（每行 <code>{"instruction":"...","chosen":"...","rejected":"..."}</code>）、JSON 数组、Excel/CSV（列名 instruction / chosen / rejected）
          </template>
        </div>
      </div>

      <!-- QA 对列表 -->
      <div class="content-card" style="margin-top: 16px;">
        <div class="card-title" style="display: flex; align-items: center; justify-content: space-between;">
          <span>QA 对列表{{ qaItems.length > 0 ? `（${qaItems.length} 条）` : '' }}</span>
          <div style="display: flex; gap: 8px;">
            <el-button size="small" type="primary" plain @click="addRow">
              <el-icon><Plus /></el-icon>新增一行
            </el-button>
            <el-button
              size="small"
              type="danger"
              plain
              :disabled="selectedIds.length === 0"
              @click="batchDelete"
            >
              批量删除（已选 {{ selectedIds.length }} 个）
            </el-button>
          </div>
        </div>

        <el-table
          :data="qaItems"
          stripe
          @selection-change="handleSelectionChange"
          style="width: 100%;"
          empty-text="暂无数据，请上传文件或点击「新增一行」"
        >
          <el-table-column type="selection" width="45" />
          <el-table-column label="#" width="50" align="center">
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <el-table-column label="Instruction" min-width="280">
            <template #default="{ row }">
              <el-input
                v-model="row.instruction"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 6 }"
                placeholder="输入指令/问题"
                @input="markModified(row)"
              />
            </template>
          </el-table-column>
          <el-table-column :label="templateType === 'dpo' ? 'Chosen（优质回答）' : 'Response（回复）'" min-width="280">
            <template #default="{ row }">
              <el-input
                v-model="row.response"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 6 }"
                :placeholder="templateType === 'dpo' ? '输入优质回答' : '输入回复内容'"
                @input="markModified(row)"
              />
            </template>
          </el-table-column>
          <el-table-column v-if="templateType === 'dpo'" label="Rejected（劣质回答）" min-width="280">
            <template #default="{ row }">
              <el-input
                v-model="row.rejected"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 6 }"
                placeholder="输入劣质回答"
                @input="markModified(row)"
              />
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="row._status === 'new'" size="small" type="info">新建</el-tag>
              <el-tag v-else-if="row._status === 'saved'" size="small" type="success">已存</el-tag>
              <el-tag v-else size="small" type="warning">已改</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="70" fixed="right">
            <template #default="{ row, $index }">
              <el-button link type="danger" size="small" @click="deleteRow($index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useProjectStore } from '@/stores/project'
import { questionApi } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import PageHeader from '@/components/common/PageHeader.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import type { UploadFile } from 'element-plus'

// 兼容非 HTTPS 环境的 UUID 生成（crypto.randomUUID 仅在安全上下文中可用）
const generateId = (): string => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

const projectStore = useProjectStore()

// 模板类型
const templateType = ref<'instruct' | 'dpo'>('instruct')

// QA 对列表
interface QAItem {
  id: string
  instruction: string
  response: string
  rejected: string
  _status: 'new' | 'saved' | 'modified'
  _dbId?: string
}

const qaItems = ref<QAItem[]>([])
const selectedIds = ref<string[]>([])
const saving = ref(false)
const uploadFileList = ref<UploadFile[]>([])
const uploadRef = ref()

// 标记修改
const markModified = (row: QAItem) => {
  if (row._status === 'saved') {
    row._status = 'modified'
  }
}

// 选择变化
const handleSelectionChange = (selection: QAItem[]) => {
  selectedIds.value = selection.map(s => s.id)
}

// 新增一行
const addRow = () => {
  qaItems.value.push({
    id: generateId(),
    instruction: '',
    response: '',
    rejected: '',
    _status: 'new',
  })
}

// 删除一行
const deleteRow = (index: number) => {
  qaItems.value.splice(index, 1)
}

// 批量删除
const batchDelete = async () => {
  if (selectedIds.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${selectedIds.value.length} 条？`,
      '批量删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch (_) { return }
  qaItems.value = qaItems.value.filter(item => !selectedIds.value.includes(item.id))
  selectedIds.value = []
}

// ==================== 文件上传解析 ====================

const handleFileChange = async (file: UploadFile) => {
  if (!file.raw) return
  uploadFileList.value = [file]

  const fileName = (file.name || '').toLowerCase()
  try {
    if (fileName.endsWith('.jsonl')) {
      await parseJsonl(file.raw)
    } else if (fileName.endsWith('.json')) {
      await parseJson(file.raw)
    } else if (fileName.endsWith('.xlsx') || fileName.endsWith('.xls') || fileName.endsWith('.csv')) {
      await parseExcel(file.raw)
    } else {
      ElMessage.warning('不支持的文件格式')
    }
  } catch (e: any) {
    ElMessage.error(`文件解析失败：${e?.message || '未知错误'}`)
  }
}

const handleFileRemove = () => {
  uploadFileList.value = []
}

// 解析 JSONL
const parseJsonl = async (file: File) => {
  const text = await file.text()
  const lines = text.split('\n').filter(l => l.trim())
  const items: QAItem[] = []
  let detectedDpo = false

  for (const line of lines) {
    try {
      const obj = JSON.parse(line)
      const hasRejected = !!(obj.rejected || obj.rejected_answer)

      // 自动检测 DPO
      if (hasRejected) detectedDpo = true

      items.push({
        id: generateId(),
        instruction: obj.instruction || obj.question || obj.content || '',
        response: obj.response || obj.answer || obj.chosen || obj.output || '',
        rejected: obj.rejected || obj.rejected_answer || '',
        _status: 'new',
      })
    } catch (_e) {
      // 跳过无效行
    }
  }

  if (items.length === 0) {
    ElMessage.warning('未解析到有效的 QA 对')
    return
  }

  // 如果检测到 DPO 字段，自动切换模板
  if (detectedDpo && templateType.value === 'instruct') {
    templateType.value = 'dpo'
  }

  qaItems.value = [...qaItems.value, ...items]
  ElMessage.success(`成功解析 ${items.length} 条 QA 对`)
}

// 解析 JSON
const parseJson = async (file: File) => {
  const text = await file.text()
  const data = JSON.parse(text)
  const arr = Array.isArray(data) ? data : (data.data || data.items || data.qa_pairs || [])

  if (!Array.isArray(arr) || arr.length === 0) {
    ElMessage.warning('JSON 文件中未找到有效的 QA 数组')
    return
  }

  const items: QAItem[] = []
  let detectedDpo = false

  for (const obj of arr) {
    const hasRejected = !!(obj.rejected || obj.rejected_answer)
    if (hasRejected) detectedDpo = true

    items.push({
      id: generateId(),
      instruction: obj.instruction || obj.question || obj.content || '',
      response: obj.response || obj.answer || obj.chosen || obj.output || '',
      rejected: obj.rejected || obj.rejected_answer || '',
      _status: 'new',
    })
  }

  if (detectedDpo && templateType.value === 'instruct') {
    templateType.value = 'dpo'
  }

  qaItems.value = [...qaItems.value, ...items]
  ElMessage.success(`成功解析 ${items.length} 条 QA 对`)
}

// 解析 Excel/CSV
const parseExcel = async (file: File) => {
  const XLSX = await import('xlsx')
  const buffer = await file.arrayBuffer()
  const workbook = XLSX.read(buffer, { type: 'array' })
  const sheetName = workbook.SheetNames[0]
  const sheet = workbook.Sheets[sheetName]
  const rows: any[] = XLSX.utils.sheet_to_json(sheet)

  if (rows.length === 0) {
    ElMessage.warning('Excel/CSV 文件中未找到数据')
    return
  }

  const items: QAItem[] = []
  let detectedDpo = false

  for (const row of rows) {
    const instruction = row.instruction || row.question || row['指令'] || row['问题'] || ''
    const response = row.response || row.answer || row.chosen || row.output || row['回复'] || row['答案'] || ''
    const rejected = row.rejected || row.rejected_answer || row['劣质回答'] || ''

    if (!instruction && !response) continue
    if (rejected) detectedDpo = true

    items.push({
      id: generateId(),
      instruction,
      response,
      rejected,
      _status: 'new',
    })
  }

  if (items.length === 0) {
    ElMessage.warning('未找到 instruction/response 列，请检查列名')
    return
  }

  if (detectedDpo && templateType.value === 'instruct') {
    templateType.value = 'dpo'
  }

  qaItems.value = [...qaItems.value, ...items]
  ElMessage.success(`成功解析 ${items.length} 条 QA 对`)
}

// ==================== 保存到项目 ====================

const saveToProject = async () => {
  if (!projectStore.currentProjectId) {
    ElMessage.warning('请先选择项目')
    return
  }

  // 校验：至少有一条有效数据
  const validItems = qaItems.value.filter(item => item.instruction.trim() && item.response.trim())
  if (validItems.length === 0) {
    ElMessage.warning('没有有效的 QA 对（instruction 和 response 不能为空）')
    return
  }

  saving.value = true
  let savedCount = 0
  let errorCount = 0

  try {
    // 分两组：新建的用 batchImport，修改的逐条 update
    const newItems = validItems.filter(item => item._status === 'new')
    const modifiedItems = validItems.filter(item => item._status === 'modified')

    // 批量新建
    if (newItems.length > 0) {
      const isDpo = templateType.value === 'dpo'
      // 先过滤出有效条目（有 instruction 和 response）
      const validNewItems = newItems.filter(item => item.instruction.trim() && item.response.trim())
      const importItems = validNewItems.map(item => {
        const obj: Record<string, string> = {
          content: item.instruction.trim(),
          answer: item.response.trim(),
          source: 'manual',
          question_type: isDpo ? 'dpo' : 'manual',
        }
        if (isDpo && item.rejected?.trim()) {
          obj.rejected_answer = item.rejected.trim()
        }
        return obj
      })

      if (importItems.length > 0) {
        try {
          const res = await questionApi.batchImport(projectStore.currentProjectId, importItems) as any
          const ids = res?.ids || []
          // 标记为已存，记录 dbId
          validNewItems.forEach((item, i) => {
            item._status = 'saved'
            item._dbId = ids[i] || undefined
          })
          savedCount += importItems.length
        } catch (e: any) {
          errorCount += importItems.length
          ElMessage.error(`批量导入失败：${e?.message || '未知错误'}`)
        }
      }
    }

    // 逐条更新
    for (const item of modifiedItems) {
      if (!item._dbId) continue
      try {
        const isDpo = templateType.value === 'dpo'
        await questionApi.update(projectStore.currentProjectId, item._dbId, {
          content: item.instruction,
          answer: item.response,
          ...(isDpo ? { generation_metadata: { rejected_answer: item.rejected } } : {}),
        })
        item._status = 'saved'
        savedCount++
      } catch (e: any) {
        errorCount++
      }
    }

    if (savedCount > 0) {
      ElMessage.success(`已保存 ${savedCount} 条 QA 对${errorCount > 0 ? `，${errorCount} 条失败` : ''}，可在「数据质量校验」页面查看`)
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

// ==================== 另存为导出 ====================

const handleExport = async (command: string) => {
  const validItems = qaItems.value.filter(item => item.instruction.trim())
  if (validItems.length === 0) {
    ElMessage.warning('没有可导出的数据')
    return
  }

  const isDpo = templateType.value === 'dpo'
  const timestamp = new Date().toISOString().slice(0, 10)

  if (command === 'jsonl') {
    const lines = validItems.map(item => {
      if (isDpo) {
        return JSON.stringify({ instruction: item.instruction, chosen: item.response, rejected: item.rejected })
      }
      return JSON.stringify({ instruction: item.instruction, response: item.response })
    })
    downloadFile(lines.join('\n'), `qa_pairs_${timestamp}.jsonl`, 'text/plain')
  } else if (command === 'json') {
    const data = validItems.map(item => {
      if (isDpo) {
        return { instruction: item.instruction, chosen: item.response, rejected: item.rejected }
      }
      return { instruction: item.instruction, response: item.response }
    })
    downloadFile(JSON.stringify(data, null, 2), `qa_pairs_${timestamp}.json`, 'application/json')
  } else if (command === 'excel') {
    const XLSX = await import('xlsx')
    const data = validItems.map(item => {
      const row: Record<string, string> = {
        instruction: item.instruction,
        [isDpo ? 'chosen' : 'response']: item.response,
      }
      if (isDpo) row.rejected = item.rejected
      return row
    })
    const ws = XLSX.utils.json_to_sheet(data)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'QA Pairs')
    XLSX.writeFile(wb, `qa_pairs_${timestamp}.xlsx`)
  }
}

// JSON.stringify 默认不转义中文（V8 引擎行为），无需额外处理

const downloadFile = (content: string, filename: string, mimeType: string) => {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

// ==================== 模板切换时清理 rejected ====================

watch(templateType, (newType) => {
  if (newType === 'instruct') {
    // 切到 instruct 时，清空 rejected 字段
    qaItems.value.forEach(item => { item.rejected = '' })
  }
})
</script>

<style lang="scss" scoped>
</style>
