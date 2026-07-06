<template>
  <div class="page-container">
    <PageHeader title="非结构化数据处理" />

    <EmptyState
      v-if="!projectStore.hasProject"
      description="请先在首页选择一个项目"
      action-text="前往首页"
      @action="$router.push('/')"
    />

    <el-row v-else :gutter="16">
      <!-- 文件列表 -->
      <el-col :span="14">
        <div class="content-card">
          <div class="card-title" style="display: flex; align-items: center; justify-content: space-between;">
            <span>文档列表</span>
            <div style="display: flex; gap: 8px;">
              <el-button
                type="primary"
                plain
                size="small"
                :disabled="documents.length === 0 || selectedFileIds.length === 0"
                @click="handleBatchSplit"
              >
                <el-icon><Check /></el-icon>
                勾选文件切片（已选 {{ selectedFileIds.length }} 个）
              </el-button>
              <el-button
                size="small"
                :disabled="documents.length === 0"
                @click="toggleSelectAll"
              >
                {{ isAllSelected ? '取消全选' : '全选文件' }}
              </el-button>
            </div>
          </div>
          <el-table
            ref="tableRef"
            :data="documents"
            stripe
            v-loading="loadingFiles"
            @selection-change="handleSelectionChange"
            style="cursor: pointer;"
          >
            <el-table-column type="selection" width="45" />
            <el-table-column prop="filename" label="文档名称" />
            <el-table-column label="大小" width="100">
              <template #default="{ row }">
                {{ row.size ? formatSize(row.size) : '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small">
                  {{ statusLabel(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="160" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click.stop="previewFile(row)">
                  预览
                </el-button>
                <el-button
                  v-if="row.status === 'completed'"
                  link type="success" size="small"
                  @click.stop="openChunkDialog(row)"
                >
                  查看切片
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-empty v-if="!loadingFiles && documents.length === 0" description="暂无非结构化文件，请先在数据源页面上传 PDF/Word 文档" :image-size="80" />
        </div>

        <!-- 切片结果列表 -->
        <div v-if="chunks.length > 0" class="content-card" style="margin-top: 16px;">
          <div class="card-title">切片结果（共 {{ chunksTotal }} 个）</div>
          <el-table :data="chunks" stripe max-height="400">
            <el-table-column label="切片名" width="200">
              <template #default="{ row }">
                {{ row.name || `切片 ${row.id?.slice(0,8)}` }}
              </template>
            </el-table-column>
            <el-table-column label="字数" width="80">
              <template #default="{ row }">
                {{ row.word_count || row.content?.length || 0 }}
              </template>
            </el-table-column>
            <el-table-column label="摘要" prop="summary" show-overflow-tooltip />
            <el-table-column label="内容" prop="content" show-overflow-tooltip />
          </el-table>
          <div v-if="chunksTotal > chunks.length" style="text-align: center; padding: 12px; color: #909399; font-size: 13px;">
            显示前 {{ chunks.length }} 条，共 {{ chunksTotal }} 条
          </div>
        </div>
      </el-col>

      <!-- 切片参数配置 -->
      <el-col :span="10">
        <!-- 当前选中文件提示 -->
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
            <span>请在左侧表格中勾选需要切片的文件</span>
          </div>
        </div>

        <div class="content-card">
          <div class="card-title">切片参数配置</div>
          <el-form :model="splitConfig" label-width="120px" size="small">
            <el-form-item label="分割策略">
              <el-select v-model="splitConfig.method">
                <el-option label="递归字符分割" value="recursive" />
                <el-option label="语义嵌入分割" value="semantic_embedding" />
                <el-option label="Markdown结构分割" value="markdown_structure" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="splitConfig.method === 'recursive'" label="切片大小">
              <el-slider v-model="splitConfig.chunkSize" :min="200" :max="2000" :step="100" show-input />
            </el-form-item>
            <el-form-item v-if="splitConfig.method === 'recursive'" label="重叠大小">
              <el-slider v-model="splitConfig.overlap" :min="0" :max="500" :step="10" show-input />
            </el-form-item>
            <el-alert
              v-if="splitConfig.method === 'semantic_embedding' && hasEmbeddingModel"
              type="info"
              :closable="false"
              style="margin-bottom: 12px;"
            >
              <template #title>
                语义嵌入分割按话题转变自动切分，无需设置切片大小，保证语义完整性
              </template>
            </el-alert>
            <el-alert
              v-if="splitConfig.method === 'semantic_embedding' && !hasEmbeddingModel"
              type="error"
              :closable="false"
              style="margin-bottom: 12px;"
            >
              <template #title>
                语义嵌入分割需要先配置 Embedding 模型
              </template>
              请前往「模型配置」页面添加 embedding 类型模型并设为默认，否则将降级为规则分割
            </el-alert>
            <el-form-item>
              <el-button
                type="primary"
                :loading="splitting"
                :disabled="selectedFileIds.length === 0 || (splitConfig.method === 'semantic_embedding' && !hasEmbeddingModel)"
                @click="handleSplit"
              >
                {{ splitting ? '切片进行中...' : '执行切片' }}
              </el-button>
              <el-text v-if="selectedFileIds.length === 0" type="info" size="small" style="margin-left: 8px;">请先勾选文件</el-text>
            </el-form-item>
          </el-form>
        </div>

        <!-- 预处理配置 -->
        <div class="content-card">
          <div class="card-title" style="display: flex; align-items: center; justify-content: space-between;">
            <span>预处理配置</span>
          </div>
          <el-form label-width="120px" size="small">
            <el-form-item label="页眉过滤">
              <el-slider
                v-model="preprocessingConfig.headerThreshold"
                :min="0" :max="20" :step="1"
                show-input
                style="width: 200px;"
              />
              <el-text type="info" size="small" style="margin-left: 8px;">过滤顶部 0~{{ preprocessingConfig.headerThreshold }}% 高度文本</el-text>
            </el-form-item>
            <el-form-item label="页脚过滤">
              <el-slider
                v-model="preprocessingConfig.footerThreshold"
                :min="80" :max="100" :step="1"
                show-input
                style="width: 200px;"
              />
              <el-text type="info" size="small" style="margin-left: 8px;">过滤底部 {{ preprocessingConfig.footerThreshold }}%~100% 高度文本</el-text>
            </el-form-item>
            <el-form-item label="自定义页眉词">
              <div style="display: flex; flex-wrap: wrap; gap: 6px; width: 100%;">
                <el-tag
                  v-for="(kw, idx) in preprocessingConfig.customHeaderPatterns"
                  :key="idx"
                  closable
                  size="small"
                  @close="preprocessingConfig.customHeaderPatterns.splice(idx, 1)"
                >
                  {{ kw }}
                </el-tag>
                <el-input
                  v-model="newHeaderKeyword"
                  size="small"
                  placeholder="输入关键词后回车"
                  style="width: 160px;"
                  @keyup.enter="addHeaderKeyword"
                />
              </div>
            </el-form-item>
            <el-form-item label="自定义页脚词">
              <div style="display: flex; flex-wrap: wrap; gap: 6px; width: 100%;">
                <el-tag
                  v-for="(kw, idx) in preprocessingConfig.customFooterPatterns"
                  :key="'f'+idx"
                  closable
                  type="warning"
                  size="small"
                  @close="preprocessingConfig.customFooterPatterns.splice(idx, 1)"
                >
                  {{ kw }}
                </el-tag>
                <el-input
                  v-model="newFooterKeyword"
                  size="small"
                  placeholder="输入关键词后回车"
                  style="width: 160px;"
                  @keyup.enter="addFooterKeyword"
                />
              </div>
            </el-form-item>
            <el-form-item>
              <el-button size="small" type="primary" plain @click="savePreprocessingConfig">保存预处理配置</el-button>
            </el-form-item>
          </el-form>
        </div>

        <!-- 敏感信息脱敏配置 -->
        <div class="content-card">
          <div class="card-title" style="display: flex; align-items: center; justify-content: space-between;">
            <span>敏感信息脱敏</span>
            <el-switch v-model="sensitiveConfig.enabled" active-text="启用" inactive-text="关闭" />
          </div>
          <div v-if="sensitiveConfig.enabled">
            <el-form label-width="120px" size="small">
              <el-form-item label="内置规则">
                <div style="display: flex; flex-wrap: wrap; gap: 6px;">
                  <el-check-tag
                    v-for="rule in sensitiveConfig.builtinRules"
                    :key="rule.id"
                    :checked="rule.enabled"
                    @change="rule.enabled = !rule.enabled"
                    style="font-size: 12px;"
                  >
                    {{ rule.label }}
                  </el-check-tag>
                </div>
              </el-form-item>
              <el-form-item label="匹配模式">
                <el-radio-group v-model="sensitiveConfig.mode" size="small">
                  <el-radio value="blacklist">黑名单（脱敏所有勾选项）</el-radio>
                  <el-radio value="whitelist">白名单（仅脱敏勾选项）</el-radio>
                </el-radio-group>
              </el-form-item>

              <!-- 关键词规则 -->
              <el-form-item label="关键词规则">
                <div style="width: 100%;">
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
                </div>
              </el-form-item>

              <!-- NER 开关 -->
              <el-form-item label="NER 模型辅助">
                <div>
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <el-switch v-model="sensitiveConfig.nerEnabled" size="small" />
                    <span style="font-size: 13px; color: #606266;">NER 识别</span>
                  </div>
                  <div style="font-size: 12px; color: #909399; margin-top: 4px;">
                    需配置 Chat 模型。NER 会调用 LLM 识别姓名、地址、机构名等正则可能遗漏的实体。
                  </div>
                </div>
              </el-form-item>

              <el-form-item>
                <el-button size="small" type="primary" plain @click="saveSensitiveConfig">保存脱敏配置</el-button>
                <el-button size="small" plain @click="previewDesensitize" :loading="previewingDesensitize">预览效果</el-button>
              </el-form-item>
            </el-form>
            <el-alert type="info" :closable="false" style="margin-top: 8px;">
              <template #title>
                脱敏在切片生成后自动执行。手机号、身份证等替换为语义化占位符（如 **手机A**），同一文档内相同内容始终替换为相同占位符。
              </template>
            </el-alert>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-dialog
      v-model="chunkDialogVisible"
      :title="`切片管理 - ${chunkDialogFile?.filename || ''}`"
      width="720px"
      destroy-on-close
    >
      <div v-loading="loadingChunks">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
          <el-text type="info" size="small">共 {{ dialogChunks.length }} 个切片</el-text>
          <div style="display: flex; gap: 8px; align-items: center;">
            <el-button size="small" plain @click="loadChunkAuditLogs" :loading="loadingAuditLogs">查看脱敏记录</el-button>
            <el-input
              v-model="chunkSearch"
              placeholder="搜索切片内容..."
              size="small"
              style="width: 220px;"
              clearable
              :prefix-icon="Search"
            />
          </div>
        </div>

        <!-- 脱敏审计记录 -->
        <div v-if="auditLogs.length > 0" style="margin-bottom: 16px;">
          <el-alert type="info" :closable="true" @close="auditLogs = []" style="margin-bottom: 8px;">
            <template #title>该文件共 {{ auditLogs.length }} 条脱敏替换记录</template>
          </el-alert>
          <el-table :data="auditLogs" stripe size="small" max-height="200">
            <el-table-column prop="rule_id" label="规则" width="120" />
            <el-table-column prop="rule_type" label="类型" width="80">
              <template #default="{ row }">
                <el-tag size="small" :type="row.rule_type === 'regex' ? '' : row.rule_type === 'keyword' ? 'warning' : 'danger'">
                  {{ row.rule_type === 'regex' ? '正则' : row.rule_type === 'keyword' ? '关键词' : 'NER' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="original_text" label="原文片段" />
            <el-table-column prop="replacement" label="替换为" />
          </el-table>
        </div>

        <div class="chunk-card-list">
          <div
            v-for="(chunk, i) in filteredDialogChunks"
            :key="chunk.id || i"
            class="chunk-card-item"
          >
            <div class="chunk-card-header">
              <div style="display: flex; align-items: center; gap: 8px;">
                <el-tag size="small" type="primary">{{ chunk.name || `切片 ${i + 1}` }}</el-tag>
                <span class="chunk-size">{{ chunk.content?.length || 0 }} 字符</span>
              </div>
              <div class="chunk-card-actions">
                <el-button link type="primary" size="small" @click="handleEditChunk(chunk, i)">编辑</el-button>
                <el-button link type="danger" size="small" @click="handleDeleteChunk(chunk, i)">删除</el-button>
              </div>
            </div>
            <div v-if="chunk.summary" class="chunk-summary">摘要：{{ chunk.summary }}</div>
            <div class="chunk-text markdown-body" v-html="renderMarkdown(chunk.content)"></div>
          </div>

          <el-empty v-if="filteredDialogChunks.length === 0" description="暂无切片数据" :image-size="60" />
        </div>
      </div>

      <template #footer>
        <el-button @click="chunkDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 文件预览弹窗 -->
    <el-dialog
      v-model="previewVisible"
      :title="`预览 - ${previewFileName}`"
      width="680px"
      destroy-on-close
    >
      <div v-loading="previewLoading" style="max-height: 500px; overflow-y: auto;">
        <div v-if="previewContent" class="preview-content markdown-body" v-html="renderMarkdown(previewContent)"></div>
        <el-empty v-else description="无法预览该文件" :image-size="60" />
      </div>
      <template #footer>
        <el-button @click="previewVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 编辑切片弹窗 -->
    <el-dialog
      v-model="editChunkVisible"
      title="编辑切片"
      width="560px"
      destroy-on-close
    >
      <el-form label-width="80px">
        <el-form-item label="切片名称">
          <el-input v-model="editingChunk.name" placeholder="输入切片名称" />
        </el-form-item>
        <el-form-item label="摘要">
          <el-input v-model="editingChunk.summary" type="textarea" :rows="2" placeholder="输入摘要" />
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="editingChunk.content" type="textarea" :rows="8" placeholder="切片内容" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editChunkVisible = false">取消</el-button>
        <el-button type="primary" @click="saveChunkEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 脱敏预览弹窗 -->
    <el-dialog
      v-model="desensitizePreviewVisible"
      title="脱敏效果预览"
      width="700px"
      destroy-on-close
    >
      <div v-loading="desensitizePreviewLoading">
        <el-alert v-if="!desensitizePreviewData" type="info" :closable="false" style="margin-bottom: 12px;">
          <template #title>请先保存脱敏配置，然后点击"预览效果"查看脱敏替换结果</template>
        </el-alert>
        <template v-if="desensitizePreviewData">
          <div style="margin-bottom: 16px;">
            <div style="font-weight: 500; margin-bottom: 8px;">原文</div>
            <div class="desensitize-preview-box" style="background: #fef0f0; border: 1px solid #fbc4c4;">{{ desensitizePreviewData.original }}</div>
          </div>
          <div style="margin-bottom: 16px;">
            <div style="font-weight: 500; margin-bottom: 8px;">脱敏后</div>
            <div class="desensitize-preview-box" style="background: #f0f9eb; border: 1px solid #c2e7b0;">{{ desensitizePreviewData.desensitized }}</div>
          </div>
          <div v-if="desensitizePreviewData.records?.length > 0">
            <div style="font-weight: 500; margin-bottom: 8px;">替换记录</div>
            <el-table :data="desensitizePreviewData.records" stripe size="small">
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
        <el-button @click="desensitizePreviewVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, watch, computed } from 'vue'
import { useProjectStore } from '@/stores/project'
import { fileApi, chunkApi, modelApi, projectApi, questionApi } from '@/api'
import { formatSize } from '@/composables/useFormatters'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { marked } from 'marked'
import PageHeader from '@/components/common/PageHeader.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import type { FileItem, Chunk } from '@/types'
import type { ElTable } from 'element-plus'

// Configure marked for safe rendering
marked.setOptions({
  breaks: true,
  gfm: true,
})

const renderMarkdown = (content: string | undefined): string => {
  if (!content) return ''
  return marked.parse(content) as string
}

const projectStore = useProjectStore()

const loadingFiles = ref(false)
const splitting = ref(false)
const documents = ref<FileItem[]>([])
const chunks = ref<Chunk[]>([])
const chunksTotal = ref(0)
const selectedFileIds = ref<string[]>([])
const selectedFiles = ref<FileItem[]>([])
let pollTimer: ReturnType<typeof setInterval> | null = null

// Embedding 模型配置检查
const hasEmbeddingModel = ref(false)
const checkEmbeddingModel = async () => {
  try {
    const res = await modelApi.list()
    const models = Array.isArray(res) ? res : (res as any)?.items || []
    hasEmbeddingModel.value = models.some((m: any) => m.model_type === 'embedding' && m.is_default === 'true')
  } catch {
    hasEmbeddingModel.value = false
  }
}

const tableRef = ref<InstanceType<typeof ElTable>>()

// 切片弹窗相关
const chunkDialogVisible = ref(false)
const chunkDialogFile = ref<FileItem | null>(null)
const dialogChunks = ref<Chunk[]>([])
const loadingChunks = ref(false)
const chunkSearch = ref('')

// 脱敏审计记录
const auditLogs = ref<any[]>([])
const loadingAuditLogs = ref(false)

const loadChunkAuditLogs = async () => {
  if (!projectStore.currentProjectId || !chunkDialogFile.value) return
  loadingAuditLogs.value = true
  try {
    const res = await questionApi.auditLogs(projectStore.currentProjectId, {
      file_id: chunkDialogFile.value.id,
      page_size: 100,
    }) as any
    auditLogs.value = res?.items || []
    if (auditLogs.value.length === 0) {
      ElMessage.info('该文件暂无脱敏替换记录')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '加载脱敏记录失败')
  } finally {
    loadingAuditLogs.value = false
  }
}

// 预处理配置
const preprocessingConfig = reactive({
  headerThreshold: 0,
  footerThreshold: 100,
  customHeaderPatterns: [] as string[],
  customFooterPatterns: [] as string[],
})
const newHeaderKeyword = ref('')
const newFooterKeyword = ref('')

const addHeaderKeyword = () => {
  if (newHeaderKeyword.value.trim()) {
    preprocessingConfig.customHeaderPatterns.push(newHeaderKeyword.value.trim())
    newHeaderKeyword.value = ''
  }
}

const addFooterKeyword = () => {
  if (newFooterKeyword.value.trim()) {
    preprocessingConfig.customFooterPatterns.push(newFooterKeyword.value.trim())
    newFooterKeyword.value = ''
  }
}

const savePreprocessingConfig = async () => {
  if (!projectStore.currentProjectId) return
  try {
    const project = projectStore.currentProject as any
    const extraData = project?.extra_data || {}
    extraData.preprocessing_config = {
      header_threshold: preprocessingConfig.headerThreshold,
      footer_threshold: preprocessingConfig.footerThreshold,
      custom_header_patterns: [...preprocessingConfig.customHeaderPatterns],
      custom_footer_patterns: [...preprocessingConfig.customFooterPatterns],
    }
    await projectApi.update(projectStore.currentProjectId, { extra_data: extraData } as any)
    ElMessage.success('预处理配置已保存')
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  }
}

// 敏感信息脱敏配置
const sensitiveConfig = reactive({
  enabled: false,
  mode: 'blacklist' as 'blacklist' | 'whitelist',
  nerEnabled: false,
  builtinRules: [
    { id: 'phone', label: '手机号', enabled: true },
    { id: 'id_card', label: '身份证', enabled: true },
    { id: 'email', label: '邮箱', enabled: true },
    { id: 'bank_card', label: '银行卡', enabled: true },
    { id: 'ip_address', label: 'IP地址', enabled: true },
    { id: 'employee_id', label: '内部工号', enabled: true },
    { id: 'doc_number', label: '文件编号', enabled: true },
  ],
})

// 关键词规则
const newKeyword = ref('')
const newKeywordMode = ref<'exact' | 'regex'>('exact')
const keywordRules = ref<Array<{ keyword: string; mode: string; placeholder: string }>>([])

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

const saveSensitiveConfig = async () => {
  if (!projectStore.currentProjectId) return
  try {
    const project = projectStore.currentProject as any
    const extraData = project?.extra_data || {}
    extraData.sensitive_rules = {
      enabled: sensitiveConfig.enabled,
      mode: sensitiveConfig.mode,
      enabled_rules: sensitiveConfig.builtinRules.filter(r => r.enabled).map(r => r.id),
      keyword_rules: keywordRules.value,
      ner_enabled: sensitiveConfig.nerEnabled,
    }
    // 兼容旧格式
    extraData.desensitize_rules = {
      keywords: keywordRules.value.map(r => r.keyword),
      match_mode: 'exact',
    }
    await projectApi.update(projectStore.currentProjectId, { extra_data: extraData } as any)
    ElMessage.success('脱敏配置已保存')
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  }
}

// 加载项目配置
const loadProjectConfig = () => {
  const extraData = (projectStore.currentProject as any)?.extra_data || {}
  const prep = extraData.preprocessing_config || {}
  preprocessingConfig.headerThreshold = prep.header_threshold || 0
  preprocessingConfig.footerThreshold = prep.footer_threshold || 100
  preprocessingConfig.customHeaderPatterns = prep.custom_header_patterns || []
  preprocessingConfig.customFooterPatterns = prep.custom_footer_patterns || []

  const sens = extraData.sensitive_rules || {}
  sensitiveConfig.enabled = sens.enabled || false
  sensitiveConfig.mode = sens.mode || 'blacklist'
  sensitiveConfig.nerEnabled = sens.ner_enabled || false
  if (sens.enabled_rules) {
    const enabledSet = new Set(sens.enabled_rules as string[])
    sensitiveConfig.builtinRules.forEach(r => { r.enabled = enabledSet.has(r.id) })
  }
  keywordRules.value = sens.keyword_rules || []
}

// 脱敏预览
const desensitizePreviewVisible = ref(false)
const desensitizePreviewLoading = ref(false)
const previewingDesensitize = ref(false)
const desensitizePreviewData = ref<any>(null)

const previewDesensitize = async () => {
  if (!projectStore.currentProjectId) return
  previewingDesensitize.value = true
  desensitizePreviewData.value = null
  desensitizePreviewVisible.value = true
  desensitizePreviewLoading.value = true
  try {
    // 用一段示例文本测试脱敏效果
    const sampleText = '张三的手机号是13812345678，身份证号110101199001011234，邮箱zhangsan@yg.com，工号：10086，银行卡6222021234567890123。'
    const res = await questionApi.desensitizePreview(projectStore.currentProjectId, sampleText) as any
    desensitizePreviewData.value = res
  } catch (e: any) {
    ElMessage.error(e?.message || '预览失败')
  } finally {
    desensitizePreviewLoading.value = false
    previewingDesensitize.value = false
  }
}
const editChunkVisible = ref(false)
const editingChunk = reactive<{ name: string; summary: string; content: string; index: number }>({
  name: '', summary: '', content: '', index: -1
})

const filteredDialogChunks = computed(() => {
  if (!chunkSearch.value) return dialogChunks.value
  const kw = chunkSearch.value.toLowerCase()
  return dialogChunks.value.filter(c =>
    (c.name || '').toLowerCase().includes(kw) ||
    (c.content || '').toLowerCase().includes(kw) ||
    (c.summary || '').toLowerCase().includes(kw)
  )
})

const isAllSelected = computed(() =>
  documents.value.length > 0 && selectedFileIds.value.length === documents.value.length
)

const splitConfig = reactive({
  method: 'recursive',
  chunkSize: 500,
  overlap: 50,
})

// 切换到语义嵌入分割时检查 embedding 配置
watch(() => splitConfig.method, (method) => {
  if (method === 'semantic_embedding' && !hasEmbeddingModel.value) {
    checkEmbeddingModel()
  }
})

const handleSelectionChange = (selection: FileItem[]) => {
  selectedFiles.value = selection
  selectedFileIds.value = selection.map(f => f.id)
}

const toggleSelectAll = () => {
  if (isAllSelected.value) {
    tableRef.value?.clearSelection()
  } else {
    documents.value.forEach(row => {
      tableRef.value?.toggleRowSelection(row, true)
    })
  }
}

const removeSelection = (file: FileItem) => {
  tableRef.value?.toggleRowSelection(file, false)
}

const handleBatchSplit = () => {
  // 使用勾选的文件批量切片
  if (selectedFileIds.value.length === 0) {
    ElMessage.warning('请先勾选文件')
    return
  }
  handleSplit()
}

const openChunkDialog = async (file: FileItem) => {
  chunkDialogFile.value = file
  chunkDialogVisible.value = true
  chunkSearch.value = ''
  await fetchChunksForDialog(file.id)
}

// 文件预览
const previewVisible = ref(false)
const previewLoading = ref(false)
const previewContent = ref('')
const previewFileName = ref('')

const previewFile = async (file: FileItem) => {
  if (!projectStore.currentProjectId) return
  previewFileName.value = file.filename
  previewVisible.value = true
  previewLoading.value = true
  previewContent.value = ''
  try {
    const content = await fileApi.preview(projectStore.currentProjectId, file.id) as any
    previewContent.value = typeof content === 'string' ? content : ''
  } catch (e: any) {
    previewContent.value = ''
    ElMessage.error(e?.message || '预览失败')
  } finally {
    previewLoading.value = false
  }
}

const fetchChunksForDialog = async (fileId: string) => {
  if (!projectStore.currentProjectId) return
  loadingChunks.value = true
  try {
    const res = await chunkApi.list(projectStore.currentProjectId, { file_id: fileId })
    if (res && typeof res === 'object' && 'items' in res) {
      dialogChunks.value = (res as any).items || []
    } else if (Array.isArray(res)) {
      dialogChunks.value = res
    } else {
      dialogChunks.value = []
    }
  } catch (e) {
    dialogChunks.value = []
  } finally {
    loadingChunks.value = false
  }
}

const handleEditChunk = (chunk: Chunk, index: number) => {
  editingChunk.name = chunk.name || ''
  editingChunk.summary = chunk.summary || ''
  editingChunk.content = chunk.content || ''
  editingChunk.index = index
  editChunkVisible.value = true
}

const saveChunkEdit = async () => {
  if (editingChunk.index >= 0 && editingChunk.index < dialogChunks.value.length) {
    const chunk = dialogChunks.value[editingChunk.index]
    try {
      await chunkApi.update(projectStore.currentProjectId!, chunk.id, {
        name: editingChunk.name,
        summary: editingChunk.summary,
        content: editingChunk.content,
      })
      chunk.name = editingChunk.name
      chunk.summary = editingChunk.summary
      chunk.content = editingChunk.content
      ElMessage.success('切片已更新')
    } catch (e: any) {
      ElMessage.error(e?.message || '保存失败')
    }
  }
  editChunkVisible.value = false
}

const handleDeleteChunk = async (chunk: Chunk, index: number) => {
  try {
    await chunkApi.delete(projectStore.currentProjectId!, chunk.id)
    dialogChunks.value.splice(index, 1)
    ElMessage.success('切片已删除')
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
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
    documents.value = allFiles.filter(f =>
      ['pdf', 'docx', 'doc', 'txt', 'md', 'epub'].includes(f.file_type)
    )
  } catch (e) {
    documents.value = []
  } finally {
    loadingFiles.value = false
  }
}

const fetchChunks = async () => {
  if (!projectStore.currentProjectId || selectedFileIds.value.length === 0) return
  try {
    const res = await chunkApi.list(projectStore.currentProjectId, selectedFileIds.value.length === 1 ? { file_id: selectedFileIds.value[0] } : undefined)
    if (res && typeof res === 'object' && 'items' in res) {
      chunks.value = (res as any).items || []
      chunksTotal.value = (res as any).total || chunks.value.length
    } else if (Array.isArray(res)) {
      chunks.value = res
      chunksTotal.value = res.length
    } else {
      chunks.value = []
      chunksTotal.value = 0
    }
  } catch (e) {
    chunks.value = []
    chunksTotal.value = 0
  }
}

const handleSplit = async () => {
  if (!projectStore.currentProjectId) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (selectedFileIds.value.length === 0) {
    ElMessage.warning('请先勾选文件')
    return
  }

  splitting.value = true
  let successCount = 0
  let failCount = 0

  for (const fileId of selectedFileIds.value) {
    try {
      await chunkApi.split(projectStore.currentProjectId, {
        file_id: fileId,
        method: splitConfig.method,
        chunk_size: splitConfig.chunkSize,
        overlap: splitConfig.overlap,
      })
      successCount++
    } catch (error: any) {
      failCount++
    }
  }

  if (failCount > 0) {
    ElMessage.warning(`切片任务已启动：${successCount} 个成功，${failCount} 个失败`)
  } else {
    ElMessage.info(`已为 ${successCount} 个文件启动切片任务`)
  }

  startPolling()
}

const startPolling = () => {
  stopPolling()
  pollTimer = setInterval(async () => {
    if (!projectStore.currentProjectId) return
    try {
      const files = await fileApi.list(projectStore.currentProjectId!)
      let allFiles: FileItem[] = []
      if (Array.isArray(files)) {
        allFiles = files
      } else if (files && typeof files === 'object' && 'items' in files) {
        allFiles = (files as any).items || []
      }

      // Check if any selected file is still processing
      const processingFiles = selectedFileIds.value.filter(id => {
        const f = allFiles.find((af: FileItem) => af.id === id)
        return f?.status === 'processing'
      })

      if (processingFiles.length === 0) {
        stopPolling()
        splitting.value = false
        ElMessage.success('切片任务全部完成')
        await fetchFiles()
        await fetchChunks()
      }
    } catch (e) {
      // Continue polling
    }
  }, 2000)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const statusLabel = (status: string) => {
  const map: Record<string, string> = {
    pending: '待切片', processing: '切片中', completed: '已切片', failed: '失败'
  }
  return map[status] || status
}

const statusTagType = (status: string) => {
  const map: Record<string, string> = {
    pending: 'info', processing: 'warning', completed: 'success', failed: 'danger'
  }
  return map[status] || 'info'
}

watch(() => projectStore.currentProjectId, (newId) => {
  if (newId) {
    selectedFileIds.value = []
    selectedFiles.value = []
    chunks.value = []
    fetchFiles()
  }
})

onMounted(() => {
  if (projectStore.currentProjectId) {
    fetchFiles()
    loadProjectConfig()
  }
  checkEmbeddingModel()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style lang="scss" scoped>
.chunk-card-list {
  max-height: 500px;
  overflow-y: auto;
}

.chunk-card-item {
  margin-bottom: 12px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 14px;
  transition: box-shadow 0.2s;

  &:hover {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  }

  .chunk-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;

    .chunk-size {
      font-size: 12px;
      color: #909399;
    }

    .chunk-card-actions {
      display: flex;
      gap: 4px;
    }
  }

  .chunk-summary {
    font-size: 12px;
    color: #909399;
    margin-bottom: 8px;
    padding: 4px 8px;
    background: #f5f7fa;
    border-radius: 4px;
  }

  .chunk-text {
    font-size: 13px;
    color: #606266;
    line-height: 1.6;
    max-height: 200px;
    overflow-y: auto;

    &.markdown-body {
      :deep(table) {
        border-collapse: collapse;
        width: 100%;
        margin: 8px 0;
        font-size: 12px;

        th, td {
          border: 1px solid #dcdfe6;
          padding: 6px 10px;
          text-align: left;
        }

        th {
          background: #f5f7fa;
          font-weight: 600;
          color: #303133;
        }

        tr:nth-child(even) {
          background: #fafafa;
        }

        tr:hover {
          background: #f0f7ff;
        }
      }

      :deep(h1), :deep(h2), :deep(h3), :deep(h4), :deep(h5), :deep(h6) {
        margin: 8px 0 4px;
        font-weight: 600;
        color: #303133;
      }

      :deep(h1) { font-size: 16px; }
      :deep(h2) { font-size: 15px; }
      :deep(h3) { font-size: 14px; }

      :deep(p) {
        margin: 4px 0;
      }

      :deep(ul), :deep(ol) {
        padding-left: 20px;
        margin: 4px 0;
      }

      :deep(code) {
        background: #f5f7fa;
        padding: 2px 4px;
        border-radius: 3px;
        font-size: 12px;
        color: #c7254e;
      }

      :deep(pre) {
        background: #f5f7fa;
        padding: 10px;
        border-radius: 4px;
        overflow-x: auto;
        font-size: 12px;
      }

      :deep(blockquote) {
        border-left: 3px solid #dcdfe6;
        padding-left: 12px;
        margin: 8px 0;
        color: #909399;
      }
    }
  }
}

.preview-content {
  font-size: 14px;
  line-height: 1.7;
  color: #303133;
  padding: 8px;
  white-space: pre-wrap;
  word-break: break-word;

  &.markdown-body {
    :deep(h1), :deep(h2), :deep(h3) {
      margin: 12px 0 6px;
      font-weight: 600;
      color: #303133;
    }
    :deep(h1) { font-size: 18px; }
    :deep(h2) { font-size: 16px; }
    :deep(h3) { font-size: 15px; }
    :deep(p) { margin: 6px 0; }
    :deep(blockquote) {
      border-left: 3px solid #dcdfe6;
      padding-left: 12px;
      margin: 8px 0;
      color: #909399;
    }
    :deep(table) {
      border-collapse: collapse;
      width: 100%;
      margin: 8px 0;
      font-size: 13px;
      th, td { border: 1px solid #dcdfe6; padding: 6px 10px; text-align: left; }
      th { background: #f5f7fa; font-weight: 600; }
    }
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
