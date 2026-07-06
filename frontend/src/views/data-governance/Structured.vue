<template>
  <div class="page-container">
    <PageHeader title="结构化数据处理" />

    <EmptyState
      v-if="!projectStore.hasProject"
      description="请先在首页选择一个项目"
      action-text="前往首页"
      @action="$router.push('/')"
    />

    <el-row v-else :gutter="16">
      <!-- 字段标注 -->
      <el-col :span="16">
        <div class="content-card">
          <div class="card-title" style="display: flex; align-items: center; justify-content: space-between;">
            <span>结构化文件列表</span>
            <div style="display: flex; gap: 8px;">
              <el-button
                type="primary"
                plain
                size="small"
                :disabled="structuredFiles.length === 0 || selectedFileIds.length === 0"
                @click="handleBatchProcess"
              >
                <el-icon><Check /></el-icon>
                勾选文件处理（已选 {{ selectedFileIds.length }} 个）
              </el-button>
              <el-button
                size="small"
                :disabled="structuredFiles.length === 0"
                @click="toggleSelectAll"
              >
                {{ isAllSelected ? '取消全选' : '全选文件' }}
              </el-button>
            </div>
          </div>
          <el-table
            ref="tableRef"
            :data="structuredFiles"
            stripe
            v-loading="loadingFiles"
            @selection-change="handleSelectionChange"
          >
            <el-table-column type="selection" width="45" />
            <el-table-column prop="filename" label="文件名" />
            <el-table-column label="大小" width="100">
              <template #default="{ row }">
                {{ row.size ? formatSize(row.size) : '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="120">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small">
                  {{ statusLabel(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="数据行" width="80">
              <template #default="{ row }">
                <span style="color: #909399;">{{ row.row_count ?? '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="字段" width="100">
              <template #default="{ row }">
                <el-button
                  link
                  type="primary"
                  size="small"
                  @click.stop="openFieldDialog(row)"
                >
                  {{ row.field_schema?.length ? `${row.field_schema.length} 个字段` : '提取字段' }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 当前选中文件的字段标注 -->
        <div v-if="currentFields.length > 0" class="content-card">
          <div class="card-title" style="display: flex; align-items: center; justify-content: space-between;">
            <span>字段标注 — {{ currentFile?.filename }}</span>
            <el-button type="primary" size="small" :loading="savingFields" @click="saveFieldConfig">
              保存配置
            </el-button>
          </div>
          <el-alert
            type="info"
            :closable="false"
            style="margin-bottom: 12px;"
          >
            <template #title>
              标注字段角色：业务属性作为问题输入，输出字段作为答案目标，冗余字段不参与问答生成。脱敏字段在生成问答时用语义化占位符替换真实值（如 张三 → **姓名值A**），防止敏感信息泄露到训练数据中
            </template>
          </el-alert>
          <el-table :data="currentFields" stripe>
            <el-table-column prop="name" label="字段名" width="150" />
            <el-table-column prop="type" label="数据类型" width="120">
              <template #default="{ row }">
                <el-tag size="small" type="info">{{ typeLabel(row.type) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="示例值" min-width="150">
              <template #default="{ row }">
                <span style="color: #606266;">{{ row.sample?.join(' / ') || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="缺失率" width="100">
              <template #default="{ row }">
                <span :style="{ color: (row.missing_rate || 0) > 0.3 ? '#f56c6c' : '#67c23a' }">
                  {{ ((row.missing_rate || 0) * 100).toFixed(1) }}%
                </span>
              </template>
            </el-table-column>
            <el-table-column label="字段角色" width="160">
              <template #default="{ row }">
                <el-select v-model="row.role" size="small">
                  <el-option label="业务属性" value="feature" />
                  <el-option label="输出字段" value="target" />
                  <el-option label="冗余字段" value="redundant" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="脱敏" width="80">
              <template #header>
                <el-tooltip content="开启后，该字段的真实值在问答生成时替换为语义化占位符（如 **姓名值A**），防止敏感信息泄露" placement="top">
                  <span style="cursor: help; border-bottom: 1px dashed #909399;">脱敏</span>
                </el-tooltip>
              </template>
              <template #default="{ row }">
                <el-switch v-model="row.desensitize" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="缺失值处理" width="180">
              <template #default="{ row }">
                <div style="display: flex; gap: 4px; align-items: center;">
                  <el-select v-model="row.missing_strategy" size="small" style="width: 110px;">
                    <el-option label="不处理" value="ignore" />
                    <el-option label="删除该行" value="drop_row" />
                    <el-option label="众数填充" value="fill_mode" />
                    <el-option label="自定义填充" value="fill_default" />
                  </el-select>
                  <el-input
                    v-if="row.missing_strategy === 'fill_default'"
                    v-model="row.fill_value"
                    size="small"
                    placeholder="填充值"
                    style="width: 60px;"
                  />
                </div>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <div v-else-if="selectedFileIds.length > 0" class="content-card">
          <el-empty description="选中文件尚未提取字段，请点击「提取字段」" :image-size="60" />
        </div>
      </el-col>

      <!-- 缺失值统计 + 脱敏配置 -->
      <el-col :span="8">
        <!-- 已选文件提示 -->
        <div v-if="selectedFileIds.length > 0" class="content-card" style="border-left: 3px solid #409eff;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <el-icon :size="18" color="#409eff"><Document /></el-icon>
            <span style="font-weight: 500;">已选择 {{ selectedFileIds.length }} 个文件</span>
          </div>
          <div style="margin-top: 8px;">
            <el-tag
              v-for="file in selectedFiles"
              :key="file.id"
              size="small"
              closable
              @close="removeSelection(file)"
              style="margin: 2px 4px;"
            >
              {{ file.filename }}
            </el-tag>
          </div>
        </div>
        <div v-else class="content-card" style="border-left: 3px solid #e6a23c;">
          <div style="display: flex; align-items: center; gap: 8px; color: #909399;">
            <el-icon :size="18"><InfoFilled /></el-icon>
            <span>请在左侧表格中勾选需要处理的文件</span>
          </div>
        </div>

        <div v-if="currentFields.length > 0" class="content-card">
          <div class="card-title">缺失值统计</div>
          <div class="missing-stats">
            <div v-for="f in currentFields.filter(f => (f.missing_rate || 0) > 0)" :key="f.name" class="missing-item">
              <span class="field-name">{{ f.name }}</span>
              <el-progress :percentage="(f.missing_rate || 0) * 100" :color="(f.missing_rate || 0) > 0.3 ? '#f56c6c' : '#e6a23c'" :stroke-width="8" />
            </div>
            <el-empty v-if="!currentFields.some(f => (f.missing_rate || 0) > 0)" description="无缺失值" :image-size="60" />
          </div>
          <el-button
            v-if="currentFields.some(f => f.missing_strategy && f.missing_strategy !== 'ignore')"
            size="small"
            type="warning"
            style="margin-top: 12px; width: 100%;"
            :loading="applyingMissingValues"
            @click="applyMissingValues"
          >
            应用缺失值处理
          </el-button>
        </div>

        <div v-if="currentFields.length > 0" class="content-card">
          <div class="card-title">字段角色统计</div>
          <div style="display: flex; gap: 12px; flex-wrap: wrap;">
            <div class="role-stat">
              <el-tag type="" size="large">{{ currentFields.filter(f => f.role === 'feature').length }}</el-tag>
              <span class="role-stat-label">业务属性</span>
            </div>
            <div class="role-stat">
              <el-tag type="success" size="large">{{ currentFields.filter(f => f.role === 'target').length }}</el-tag>
              <span class="role-stat-label">输出字段</span>
            </div>
            <div class="role-stat">
              <el-tag type="info" size="large">{{ currentFields.filter(f => f.role === 'redundant').length }}</el-tag>
              <span class="role-stat-label">冗余字段</span>
            </div>
          </div>
          <div v-if="currentFields.filter(f => f.role === 'target').length === 0" style="margin-top: 12px;">
            <el-alert type="warning" :closable="false" title="请至少将一个字段设为「输出字段」，否则无法生成问答对" />
          </div>
        </div>

        <div class="content-card">
          <div class="card-title" style="display: flex; align-items: center; justify-content: space-between;">
            <span>敏感信息脱敏配置</span>
            <el-button size="small" type="primary" plain @click="showDesensitizeConfig = !showDesensitizeConfig">
              {{ showDesensitizeConfig ? '收起' : '配置' }}
            </el-button>
          </div>
          <el-collapse-transition>
            <div v-if="showDesensitizeConfig" style="margin-top: 12px;">
              <!-- 内置正则规则 -->
              <div style="margin-bottom: 12px;">
                <div style="font-size: 13px; color: #606266; margin-bottom: 8px;">内置识别规则</div>
                <div style="display: flex; flex-wrap: wrap; gap: 6px;">
                  <el-check-tag
                    v-for="rule in builtinRules"
                    :key="rule.id"
                    :checked="activeRules.includes(rule.id)"
                    @change="toggleRule(rule.id)"
                  >
                    {{ rule.label }}
                  </el-check-tag>
                </div>
              </div>

              <!-- 黑白名单模式 -->
              <div style="margin-bottom: 12px;">
                <div style="font-size: 13px; color: #606266; margin-bottom: 8px;">匹配模式</div>
                <el-radio-group v-model="desensitizeMode" size="small">
                  <el-radio-button value="blacklist">黑名单（脱敏所有勾选项）</el-radio-button>
                  <el-radio-button value="whitelist">白名单（仅脱敏勾选项）</el-radio-button>
                </el-radio-group>
              </div>

              <!-- 关键词规则 -->
              <el-divider content-position="left" style="margin: 12px 0;">关键词规则</el-divider>
              <div style="display: flex; gap: 4px; margin-bottom: 8px;">
                <el-input v-model="newKeyword" size="small" placeholder="输入敏感关键词（如：薪资、合同金额）" style="flex: 1;" @keyup.enter="addKeyword" />
                <el-select v-model="newKeywordMode" size="small" style="width: 100px;">
                  <el-option label="精确匹配" value="exact" />
                  <el-option label="正则匹配" value="regex" />
                </el-select>
                <el-button size="small" type="primary" @click="addKeyword">添加</el-button>
              </div>
              <div v-if="keywordRules.length > 0" style="display: flex; flex-wrap: wrap; gap: 6px;">
                <el-tag
                  v-for="(rule, idx) in keywordRules"
                  :key="idx"
                  closable
                  size="small"
                  :type="rule.mode === 'regex' ? 'warning' : ''"
                  @close="removeKeyword(idx)"
                >
                  {{ rule.keyword }}
                  <span style="color: #909399; font-size: 11px; margin-left: 2px;">{{ rule.mode === 'regex' ? '正则' : '精确' }}</span>
                </el-tag>
              </div>
              <el-empty v-else description="暂无关键词规则" :image-size="40" />

              <!-- NER 开关 -->
              <el-divider content-position="left" style="margin: 12px 0;">NER 模型辅助</el-divider>
              <div style="display: flex; align-items: center; gap: 8px;">
                <el-switch v-model="nerEnabled" size="small" />
                <span style="font-size: 13px; color: #606266;">NER 识别</span>
              </div>
              <div style="font-size: 12px; color: #909399; margin-top: 4px;">
                需配置 Chat 模型。NER 会调用 LLM 识别姓名、地址、机构名等正则可能遗漏的实体。
              </div>

              <!-- 操作按钮 -->
              <el-button
                size="small"
                type="primary"
                style="margin-top: 12px; width: 100%;"
                :loading="savingDesensitize"
                @click="saveDesensitizeRules"
              >
                保存脱敏规则
              </el-button>
              <el-button
                size="small"
                style="margin-top: 8px; width: 100%;"
                @click="previewStructuredDesensitize"
                :loading="previewingStructuredDesensitize"
              >
                预览脱敏效果
              </el-button>
              <el-button
                v-if="currentFile"
                size="small"
                style="margin-top: 8px; width: 100%;"
                @click="loadStructuredAuditLogs"
                :loading="loadingAuditLogs"
              >
                查看脱敏记录
              </el-button>
            </div>
          </el-collapse-transition>
        </div>
      </el-col>
    </el-row>

    <!-- 字段管理弹窗 -->
    <el-dialog
      v-model="fieldDialogVisible"
      :title="`字段管理 - ${fieldDialogFile?.filename || ''}`"
      width="700px"
      destroy-on-close
    >
      <div v-loading="extractingFields">
        <el-table :data="dialogFields" stripe>
          <el-table-column prop="name" label="字段名" width="140" />
          <el-table-column prop="type" label="数据类型" width="110">
            <template #default="{ row }">
              <el-tag size="small" type="info">{{ typeLabel(row.type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="示例值" min-width="120">
            <template #default="{ row }">
              {{ row.sample?.join(' / ') || '-' }}
            </template>
          </el-table-column>
          <el-table-column label="缺失率" width="100">
            <template #default="{ row }">
              <span :style="{ color: (row.missing_rate || 0) > 0.3 ? '#f56c6c' : '#67c23a' }">
                {{ ((row.missing_rate || 0) * 100).toFixed(1) }}%
              </span>
            </template>
          </el-table-column>
          <el-table-column label="字段角色" width="140">
            <template #default="{ row }">
              <el-select v-model="row.role" size="small">
                <el-option label="业务属性" value="feature" />
                <el-option label="输出字段" value="target" />
                <el-option label="冗余字段" value="redundant" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="脱敏" width="70">
            <template #header>
              <el-tooltip content="开启后，该字段的真实值在问答生成时替换为 ***，防止敏感信息泄露" placement="top">
                <span style="cursor: help; border-bottom: 1px dashed #909399;">脱敏</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-switch v-model="row.desensitize" size="small" />
            </template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer>
        <el-button @click="fieldDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingFields" @click="saveDialogFieldConfig">保存配置</el-button>
      </template>
    </el-dialog>

    <!-- 结构化脱敏预览弹窗 -->
    <el-dialog
      v-model="structuredPreviewVisible"
      title="脱敏效果预览"
      width="700px"
      destroy-on-close
    >
      <div v-loading="structuredPreviewLoading">
        <template v-if="structuredPreviewData">
          <div style="margin-bottom: 16px;">
            <div style="font-weight: 500; margin-bottom: 8px;">原文</div>
            <div class="desensitize-preview-box" style="background: #fef0f0; border: 1px solid #fbc4c4;">{{ structuredPreviewData.original }}</div>
          </div>
          <div style="margin-bottom: 16px;">
            <div style="font-weight: 500; margin-bottom: 8px;">脱敏后</div>
            <div class="desensitize-preview-box" style="background: #f0f9eb; border: 1px solid #c2e7b0;">{{ structuredPreviewData.desensitized }}</div>
          </div>
          <div v-if="structuredPreviewData.records?.length > 0">
            <div style="font-weight: 500; margin-bottom: 8px;">替换记录</div>
            <el-table :data="structuredPreviewData.records" stripe size="small">
              <el-table-column prop="rule_id" label="规则" width="120" />
              <el-table-column prop="rule_type" label="类型" width="80" />
              <el-table-column prop="original_text" label="原文片段" />
              <el-table-column prop="replacement" label="替换为" />
            </el-table>
          </div>
          <el-alert v-else type="success" :closable="false" style="margin-top: 8px;">
            <template #title>未检测到敏感信息，无需替换</template>
          </el-alert>
        </template>
      </div>
      <template #footer>
        <el-button @click="structuredPreviewVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 审计日志弹窗 -->
    <el-dialog
      v-model="auditLogVisible"
      title="脱敏审计记录"
      width="700px"
      destroy-on-close
    >
      <el-table v-loading="loadingAuditLogs" :data="auditLogs" stripe size="small">
        <el-table-column prop="rule_type" label="规则类型" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.rule_type === 'ner' ? 'warning' : ''">{{ { regex: '正则', keyword: '关键词', ner: 'NER' }[row.rule_type] || row.rule_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="rule_id" label="规则" width="120" />
        <el-table-column prop="original_text" label="原文片段" />
        <el-table-column prop="replacement" label="替换为" />
        <el-table-column prop="confidence" label="置信度" width="80">
          <template #default="{ row }">{{ (row.confidence * 100).toFixed(0) }}%</template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="140" />
      </el-table>
      <el-empty v-if="!loadingAuditLogs && auditLogs.length === 0" description="暂无脱敏记录" :image-size="60" />
      <template #footer>
        <el-button @click="auditLogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, onMounted, watch } from 'vue'
import { useProjectStore } from '@/stores/project'
import { fileApi, projectApi, questionApi, chunkApi } from '@/api'
import { formatSize } from '@/composables/useFormatters'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageHeader from '@/components/common/PageHeader.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import type { FileItem, FieldSchemaItem } from '@/types'
import type { ElTable } from 'element-plus'

const projectStore = useProjectStore()
const loadingFiles = ref(false)
const extractingFields = ref(false)
const savingFields = ref(false)
const structuredFiles = ref<FileItem[]>([])
const selectedFileIds = ref<string[]>([])
const selectedFiles = ref<FileItem[]>([])

const tableRef = ref<InstanceType<typeof ElTable>>()

// 当前选中文件的字段
const currentFile = ref<FileItem | null>(null)
const currentFields = ref<FieldSchemaItem[]>([])

// 字段弹窗
const fieldDialogVisible = ref(false)
const fieldDialogFile = ref<FileItem | null>(null)
const dialogFields = ref<FieldSchemaItem[]>([])

// 脱敏规则配置
const showDesensitizeConfig = ref(false)
const newKeyword = ref('')
const newKeywordMode = ref<'exact' | 'regex'>('exact')
const keywordRules = ref<Array<{ keyword: string; mode: string; placeholder: string }>>([])
const savingDesensitize = ref(false)

// 内置规则
const builtinRules = [
  { id: 'phone', label: '手机号' },
  { id: 'id_card', label: '身份证' },
  { id: 'email', label: '邮箱' },
  { id: 'bank_card', label: '银行卡' },
  { id: 'ip_address', label: 'IP地址' },
  { id: 'employee_id', label: '内部工号' },
  { id: 'doc_number', label: '文件编号' },
]
const activeRules = ref<string[]>(['phone', 'id_card', 'email', 'bank_card', 'ip_address', 'employee_id', 'doc_number'])
const desensitizeMode = ref<'blacklist' | 'whitelist'>('blacklist')
const nerEnabled = ref(false)

const toggleRule = (ruleId: string) => {
  const idx = activeRules.value.indexOf(ruleId)
  if (idx >= 0) {
    activeRules.value.splice(idx, 1)
  } else {
    activeRules.value.push(ruleId)
  }
}

// 缺失值应用
const applyingMissingValues = ref(false)

// 审计日志
const auditLogVisible = ref(false)
const auditLogs = ref<any[]>([])
const loadingAuditLogs = ref(false)

const isAllSelected = computed(() =>
  structuredFiles.value.length > 0 && selectedFileIds.value.length === structuredFiles.value.length
)

const handleSelectionChange = (selection: FileItem[]) => {
  selectedFiles.value = selection
  selectedFileIds.value = selection.map(f => f.id)
  // 更新当前文件和字段
  if (selection.length > 0) {
    currentFile.value = selection[0]
    currentFields.value = (selection[0].field_schema || []) as FieldSchemaItem[]
    // 如果没有字段信息，自动提取
    if (!selection[0].field_schema?.length) {
      autoExtractFields(selection[0])
    }
  } else {
    currentFile.value = null
    currentFields.value = []
  }
}

const autoExtractFields = async (file: FileItem) => {
  if (!projectStore.currentProjectId) return
  extractingFields.value = true
  try {
    const res = await fileApi.extractFields(projectStore.currentProjectId, file.id)
    const data = (res as any)?.data || res
    const fields = data?.fields || []
    // 更新文件对象（后端提取字段后会自动切片并设 status=completed）
    file.field_schema = fields
    file.row_count = data?.total_rows || 0
    file.status = 'completed'
    // 如果是当前选中文件，更新显示
    if (currentFile.value?.id === file.id) {
      currentFields.value = fields as FieldSchemaItem[]
    }
    ElMessage.success(`已提取 ${fields.length} 个字段并完成切片`)
  } catch (e: any) {
    ElMessage.error(e?.message || '字段提取失败')
  } finally {
    extractingFields.value = false
  }
}

const toggleSelectAll = () => {
  if (isAllSelected.value) {
    tableRef.value?.clearSelection()
  } else {
    structuredFiles.value.forEach(row => {
      tableRef.value?.toggleRowSelection(row, true)
    })
  }
}

const removeSelection = (file: FileItem) => {
  tableRef.value?.toggleRowSelection(file, false)
}

const handleBatchProcess = async () => {
  if (selectedFileIds.value.length === 0) {
    ElMessage.warning('请先勾选文件')
    return
  }
  // 对没有字段信息的文件自动提取
  for (const file of selectedFiles.value) {
    if (!file.field_schema?.length) {
      await autoExtractFields(file)
    }
  }
  ElMessage.success(`已选择 ${selectedFileIds.value.length} 个文件进行处理`)
}

const openFieldDialog = async (file: FileItem) => {
  fieldDialogFile.value = file
  fieldDialogVisible.value = true

  // 如果没有字段信息，先提取
  if (!file.field_schema?.length) {
    await autoExtractFields(file)
  }
  dialogFields.value = ((file.field_schema || []) as FieldSchemaItem[]).map(f => ({ ...f }))
}

const saveFieldConfig = async () => {
  if (!projectStore.currentProjectId || !currentFile.value) return
  savingFields.value = true
  try {
    await fileApi.updateFieldSchema(projectStore.currentProjectId, currentFile.value.id, {
      fields: currentFields.value,
    })
    // 更新文件对象
    currentFile.value.field_schema = [...currentFields.value]
    ElMessage.success('字段配置已保存')
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    savingFields.value = false
  }
}

const saveDialogFieldConfig = async () => {
  if (!projectStore.currentProjectId || !fieldDialogFile.value) return
  savingFields.value = true
  try {
    await fileApi.updateFieldSchema(projectStore.currentProjectId, fieldDialogFile.value.id, {
      fields: dialogFields.value,
    })
    // 更新文件对象
    fieldDialogFile.value.field_schema = [...dialogFields.value]
    // 如果是当前选中文件，也更新
    if (currentFile.value?.id === fieldDialogFile.value.id) {
      currentFields.value = [...dialogFields.value] as FieldSchemaItem[]
    }
    ElMessage.success('字段配置已保存')
    fieldDialogVisible.value = false
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    savingFields.value = false
  }
}

const typeLabel = (type: string) => {
  const map: Record<string, string> = {
    string: '文本', integer: '整数', float: '小数', date: '日期', boolean: '布尔',
  }
  return map[type] || type
}

const statusLabel = (status: string) => {
  const map: Record<string, string> = { pending: '待处理', processing: '处理中', completed: '已处理', failed: '失败' }
  return map[status] || status
}

const statusTagType = (status: string) => {
  const map: Record<string, string> = { pending: 'info', processing: 'warning', completed: 'success', failed: 'danger' }
  return map[status] || 'info'
}

const addKeyword = () => {
  if (!newKeyword.value.trim()) return
  keywordRules.value.push({
    keyword: newKeyword.value.trim(),
    mode: newKeywordMode.value,
    placeholder: '敏感信息',
  })
  newKeyword.value = ''
}

const removeKeyword = (idx: number) => {
  keywordRules.value.splice(idx, 1)
}

const saveDesensitizeRules = async () => {
  if (!projectStore.currentProjectId) return
  savingDesensitize.value = true
  try {
    // Save to project extra_data
    const project = projectStore.currentProject
    const extraData = (project as any)?.extra_data || {}
    extraData.sensitive_rules = {
      ...((extraData.sensitive_rules || {}) as any),
      enabled: true,
      mode: desensitizeMode.value,
      enabled_rules: activeRules.value,
      keyword_rules: keywordRules.value,
      ner_enabled: nerEnabled.value,
    }
    // 兼容旧格式
    extraData.desensitize_rules = {
      keywords: keywordRules.value.map(r => r.keyword),
      match_mode: 'exact',
    }
    await projectApi.update(projectStore.currentProjectId, { extra_data: extraData } as any)
    ElMessage.success('脱敏规则已保存')
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    savingDesensitize.value = false
  }
}

// 加载已有的脱敏规则
const loadDesensitizeRules = () => {
  const extraData = (projectStore.currentProject as any)?.extra_data || {}
  const rules = extraData.sensitive_rules || {}
  keywordRules.value = rules.keyword_rules || []
  activeRules.value = rules.enabled_rules || builtinRules.map(r => r.id)
  desensitizeMode.value = rules.mode || 'blacklist'
  nerEnabled.value = rules.ner_enabled || false
}

// 结构化脱敏预览
const structuredPreviewVisible = ref(false)
const structuredPreviewLoading = ref(false)
const previewingStructuredDesensitize = ref(false)
const structuredPreviewData = ref<any>(null)

const previewStructuredDesensitize = async () => {
  if (!projectStore.currentProjectId) return
  previewingStructuredDesensitize.value = true
  structuredPreviewData.value = null
  structuredPreviewVisible.value = true
  structuredPreviewLoading.value = true
  try {
    // 优先用当前文件的第一个 chunk 内容，fallback 到字段样本拼接
    let sampleText = ''
    if (currentFile.value) {
      try {
        const chunks = await chunkApi.list(projectStore.currentProjectId, { file_id: currentFile.value.id, page_size: 1 }) as any
        const items = chunks?.items || chunks || []
        if (items.length > 0 && items[0].content) {
          sampleText = items[0].content
        }
      } catch { /* ignore */ }
    }
    if (!sampleText && currentFields.value.length > 0) {
      // 用字段样本值拼接
      const parts = currentFields.value
        .filter(f => f.sample?.length)
        .map(f => `${f.name}: ${f.sample![0]}`)
      sampleText = parts.join('\n')
    }
    if (!sampleText) {
      sampleText = '员工张三的薪资为15000元，李四的合同金额为80000元，王五的手机号为13987654321。'
    }
    const res = await questionApi.desensitizePreview(projectStore.currentProjectId, sampleText) as any
    structuredPreviewData.value = res
  } catch (e: any) {
    ElMessage.error(e?.message || '预览失败')
  } finally {
    structuredPreviewLoading.value = false
    previewingStructuredDesensitize.value = false
  }
}

// 缺失值应用
const applyMissingValues = async () => {
  if (!projectStore.currentProjectId || !currentFile.value) return
  try {
    await ElMessageBox.confirm(
      '将根据配置的缺失值策略重新处理数据，已有分片将被重建，是否继续？',
      '应用缺失值处理',
      { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  applyingMissingValues.value = true
  try {
    const res = await fileApi.updateFieldSchema(projectStore.currentProjectId, currentFile.value.id, {
      fields: currentFields.value,
    }) as any
    if (res?.chunks_regenerated) {
      ElMessage.success('缺失值处理已应用，分片已重建')
    } else {
      ElMessage.success('字段配置已保存')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '应用失败')
  } finally {
    applyingMissingValues.value = false
  }
}

// 审计日志
const loadStructuredAuditLogs = async () => {
  if (!projectStore.currentProjectId || !currentFile.value) return
  auditLogVisible.value = true
  loadingAuditLogs.value = true
  try {
    const res = await questionApi.auditLogs(projectStore.currentProjectId, { file_id: currentFile.value.id }) as any
    auditLogs.value = res?.items || res || []
  } catch (e: any) {
    ElMessage.error(e?.message || '加载审计日志失败')
  } finally {
    loadingAuditLogs.value = false
  }
}

const fetchFiles = async () => {
  if (!projectStore.currentProjectId) return
  loadingFiles.value = true
  try {
    const res = await fileApi.list(projectStore.currentProjectId)
    let allFiles: FileItem[] = []
    if (Array.isArray(res)) {
      allFiles = res
    } else if (res && typeof res === 'object' && 'items' in res) {
      allFiles = (res as any).items || []
    }
    structuredFiles.value = allFiles.filter(f =>
      ['xlsx', 'xls', 'csv'].includes(f.file_type)
    )
  } catch (e) {
    structuredFiles.value = []
  } finally {
    loadingFiles.value = false
  }
}

watch(() => projectStore.currentProjectId, (newId) => {
  if (newId) fetchFiles()
})

onMounted(() => {
  if (projectStore.currentProjectId) {
    fetchFiles()
    loadDesensitizeRules()
  }
})
</script>

<style lang="scss" scoped>
.missing-stats {
  .missing-item {
    margin-bottom: 12px;

    .field-name {
      font-size: 13px;
      color: #606266;
      margin-bottom: 4px;
      display: block;
    }
  }
}

.role-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;

  .role-stat-label {
    font-size: 12px;
    color: #909399;
  }
}

.desensitize-preview-box {
  font-size: 13px;
  line-height: 1.7;
  color: #303133;
  padding: 12px;
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
}
</style>
