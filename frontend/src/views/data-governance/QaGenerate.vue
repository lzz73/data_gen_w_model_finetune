<template>
  <div class="page-container">
    <PageHeader title="问答对生成">
      <el-button
        type="primary"
        :loading="generating"
        @click="startGenerate"
        :disabled="!projectStore.hasProject || !canGenerate"
      >
        <el-icon><VideoPlay /></el-icon>
        {{ generateButtonLabel }}
      </el-button>
    </PageHeader>

    <EmptyState
      v-if="!projectStore.hasProject"
      description="请先在首页选择一个项目"
      action-text="前往首页"
      @action="$router.push('/')"
    />

    <template v-else>
      <!-- 数据源类型切换 -->
      <div class="content-card" style="margin-bottom: 16px;">
        <el-radio-group v-model="dataSourceType" size="large" @change="handleDataSourceChange">
          <el-radio-button value="unstructured">
            <el-icon style="margin-right: 4px;"><Document /></el-icon>
            非结构化数据（切片）
          </el-radio-button>
          <el-radio-button value="structured">
            <el-icon style="margin-right: 4px;"><Grid /></el-icon>
            结构化数据（表格）
          </el-radio-button>
        </el-radio-group>
        <div style="margin-top: 8px;">
          <el-text type="info" size="small">
            {{ dataSourceType === 'unstructured'
              ? '基于已切片的文档内容，调用大模型生成问答对'
              : '基于结构化数据的字段映射关系，将每行数据转化为指令-回复对'
            }}
          </el-text>
        </div>
      </div>

      <el-row :gutter="16">
        <!-- 左侧：数据选择 -->
        <el-col :span="14">
          <!-- ========== 非结构化模式：切片选择 ========== -->
          <template v-if="dataSourceType === 'unstructured'">
            <div class="content-card">
              <div class="card-title" style="display: flex; align-items: center; justify-content: space-between;">
                <span>选择切片</span>
                <div style="display: flex; gap: 8px;">
                  <el-button
                    type="primary"
                    plain
                    size="small"
                    :disabled="chunkedFiles.length === 0 || selectedChunkIds.length === 0"
                    @click="handleGenerateFromSelection"
                  >
                    <el-icon><Check /></el-icon>
                    勾选切片生成（{{ selectedChunkIds.length }} 个）
                  </el-button>
                  <el-button
                    size="small"
                    :disabled="chunkedFiles.length === 0"
                    @click="toggleSelectAllChunks"
                  >
                    {{ isAllChunksSelected ? '取消全选' : '全选切片' }}
                  </el-button>
                </div>
              </div>

              <!-- 无切片提示 -->
              <el-empty
                v-if="!loadingFiles && chunkedFiles.length === 0"
                description="暂无已切片的文件，请先在非结构化数据处理页面完成切片"
                :image-size="80"
              >
                <el-button type="primary" size="small" @click="$router.push('/data-governance/unstructured')">
                  前往切片
                </el-button>
              </el-empty>

              <!-- 文件-切片树 -->
              <div v-loading="loadingFiles">
                <div
                  v-for="file in chunkedFiles"
                  :key="file.id"
                  class="file-chunk-group"
                >
                  <div class="file-chunk-header" @click="toggleFileExpand(file.id)">
                    <div style="display: flex; align-items: center; gap: 8px;">
                      <el-checkbox
                        :model-value="isFileAllSelected(file.id)"
                        :indeterminate="isFilePartialSelected(file.id)"
                        @change="(val: boolean) => toggleFileChunks(file.id, val)"
                        @click.stop
                      />
                      <el-icon :size="14" style="color: #909399; transition: transform 0.2s;" :style="{ transform: expandedFiles.has(file.id) ? 'rotate(90deg)' : 'rotate(0deg)' }">
                        <ArrowRight />
                      </el-icon>
                      <el-icon :size="16" :color="fileIconColor(file.file_type)"><Document /></el-icon>
                      <span style="font-weight: 500; font-size: 13px;">{{ file.filename }}</span>
                      <el-tag size="small" type="info">{{ fileChunkMap[file.id]?.length || 0 }} 个切片</el-tag>
                    </div>
                  </div>

                  <!-- 展开的切片列表 -->
                  <div v-if="expandedFiles.has(file.id)" class="chunk-select-list">
                    <div
                      v-for="chunk in fileChunkMap[file.id] || []"
                      :key="chunk.id"
                      class="chunk-select-item"
                    >
                      <el-checkbox
                        :model-value="selectedChunkIds.includes(chunk.id)"
                        @change="(val: boolean) => toggleChunk(chunk.id, val)"
                      >
                        <span class="chunk-select-name">{{ chunk.name || `切片 ${chunk.id?.slice(0,8)}` }}</span>
                      </el-checkbox>
                      <span class="chunk-select-info">{{ chunk.content?.length || 0 }} 字符</span>
                      <span v-if="chunk.summary" class="chunk-select-summary" :title="chunk.summary">{{ chunk.summary }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <!-- ========== 结构化模式：文件选择 ========== -->
          <template v-else>
            <div class="content-card">
              <div class="card-title" style="display: flex; align-items: center; justify-content: space-between;">
                <span>选择结构化文件</span>
                <div style="display: flex; gap: 8px;">
                  <el-button
                    size="small"
                    :disabled="structuredFiles.length === 0"
                    @click="toggleSelectAllStructured"
                  >
                    {{ isAllStructuredSelected ? '取消全选' : '全选文件' }}
                  </el-button>
                </div>
              </div>

              <!-- 无文件提示 -->
              <el-empty
                v-if="!loadingFiles && structuredFiles.length === 0"
                description="暂无已处理的结构化文件，请先在结构化数据处理页面完成字段标注"
                :image-size="80"
              >
                <el-button type="primary" size="small" @click="$router.push('/data-governance/structured')">
                  前往处理
                </el-button>
              </el-empty>

              <!-- 结构化文件列表 -->
              <el-table
                ref="structuredTableRef"
                :data="structuredFiles"
                stripe
                v-loading="loadingFiles"
                @selection-change="handleStructuredSelectionChange"
              >
                <el-table-column type="selection" width="45" />
                <el-table-column prop="filename" label="文件名" />
                <el-table-column label="大小" width="100">
                  <template #default="{ row }">
                    {{ row.size ? formatSize(row.size) : '-' }}
                  </template>
                </el-table-column>
                <el-table-column label="字段" width="120">
                  <template #default="{ row }">
                    <el-button
                      link
                      type="primary"
                      size="small"
                      @click.stop="openFieldPreview(row)"
                    >
                      查看字段映射
                    </el-button>
                  </template>
                </el-table-column>
                <el-table-column label="数据行数" width="100">
                  <template #default="{ row }">
                    <span style="color: #909399;">{{ row.row_count ?? '-' }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <!-- 已选文件的字段映射预览 -->
            <div v-if="selectedStructuredFiles.length > 0" class="content-card" style="margin-top: 16px;">
              <div class="card-title">字段映射预览</div>
              <el-alert
                type="info"
                :closable="false"
                style="margin-bottom: 12px;"
              >
                <template #title>
                  系统将根据字段角色自动生成问答对：业务属性字段作为问题输入，输出字段作为答案目标，冗余字段将被忽略
                </template>
              </el-alert>
              <el-table :data="currentFieldMapping" stripe size="small">
                <el-table-column prop="name" label="字段名" width="140" />
                <el-table-column prop="type" label="数据类型" width="100" />
                <el-table-column label="字段角色" width="120">
                  <template #default="{ row }">
                    <el-tag
                      :type="row.role === 'target' ? 'success' : row.role === 'redundant' ? 'info' : ''"
                      size="small"
                    >
                      {{ roleLabel(row.role) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="生成方式" min-width="200">
                  <template #default="{ row }">
                    <span v-if="row.role === 'redundant'" style="color: #909399;">忽略，不参与生成</span>
                    <span v-else-if="row.role === 'target'" style="color: #67c23a;">作为答案（模型需预测的目标）</span>
                    <span v-else style="color: #409eff;">作为问题条件（输入信息）</span>
                  </template>
                </el-table-column>
                <el-table-column label="脱敏" width="60">
                  <template #default="{ row }">
                    <el-tag v-if="row.desensitize" type="warning" size="small">是</el-tag>
                    <span v-else style="color: #909399;">否</span>
                  </template>
                </el-table-column>
              </el-table>

              <!-- 生成示例预览 -->
              <div class="generate-preview">
                <div class="preview-title">生成示例预览</div>
                <div class="preview-item" v-for="(example, i) in generateExamples" :key="i">
                  <div class="preview-label">
                    示例 {{ i + 1 }}
                    <el-tag v-if="example.type === 'forward'" size="small" style="margin-left: 6px;">正向查询</el-tag>
                    <el-tag v-else-if="example.type === 'reverse'" size="small" type="warning" style="margin-left: 6px;">逆向推理</el-tag>
                    <el-tag v-else-if="example.type === 'multi_target'" size="small" type="success" style="margin-left: 6px;">多目标</el-tag>
                    <el-tag v-else-if="example.type === 'summary'" size="small" type="info" style="margin-left: 6px;">概括型</el-tag>
                  </div>
                  <div class="preview-content">
                    <p><strong>指令：</strong>{{ example.instruction }}</p>
                    <p><strong>输出：</strong>{{ example.output }}</p>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <!-- 生成进度（两种模式共用） -->
          <div v-if="latestTaskData && taskStatus" class="content-card generate-task-panel" :class="`is-${taskStatus}`" style="margin-top: 16px;">
            <div class="generate-task-panel__head">
              <div class="generate-task-panel__title-wrap">
                <span class="generate-task-panel__title">问答对生成任务</span>
                <span class="generate-task-panel__status">{{ taskStatusLabel }}</span>
              </div>
              <div class="generate-task-panel__right">
                <el-button
                  v-if="hasActiveTask && taskStatus !== 'cancelling'"
                  type="danger"
                  size="small"
                  plain
                  :loading="cancellingTask"
                  @click="handleCancelTask"
                >
                  <el-icon v-if="!cancellingTask"><Close /></el-icon>
                  <span>取消任务</span>
                </el-button>
                <span v-if="taskStatus === 'cancelling'" class="cancelling-hint">正在取消...</span>
                <span class="generate-task-panel__percent">{{ progress }}%</span>
              </div>
            </div>
              <el-progress :percentage="progress" :stroke-width="8" :show-text="false" :status="progress === 100 ? 'success' : ''" />
              <div class="generate-task-panel__meta">
                <template v-if="taskSummary.isStructured">
                  <span>已处理 {{ taskSummary.processed }} / {{ taskSummary.total }} 行</span>
                  <span>已生成 {{ taskSummary.createdQuestions }} 个问答对</span>
                </template>
                <template v-else>
                  <span>已处理 {{ taskSummary.processed }} / {{ taskSummary.total }} 个块</span>
                  <span v-if="taskSummary.total !== taskSummary.totalChunks" class="meta-detail">
                    （原 {{ taskSummary.totalChunks }} 个切片，合并后 {{ taskSummary.total }} 个块）
                  </span>
                  <span>已生成 {{ taskSummary.createdQuestions }} 个问题</span>
                  <span>已生成 {{ taskSummary.createdAnswers }} 个答案</span>
                  <span v-if="taskSummary.skipped > 0">跳过 {{ taskSummary.skipped }} 个</span>
                  <span v-if="taskSummary.failedAnswers > 0" class="failed-info">答案失败 {{ taskSummary.failedAnswers }} 个</span>
                </template>
              </div>
            <div v-if="taskError" class="generate-task-panel__error">{{ taskError }}</div>
          </div>

          <!-- 问答对列表（两种模式共用） -->
          <div v-if="qaList.length > 0 || hasHistoryBatches" class="content-card" style="margin-top: 16px;">
            <div class="card-title" style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
              <span style="white-space: nowrap;">生成结果{{ qaList.length > 0 ? `（${qaList.length}条）` : '' }}</span>
              <div style="display: flex; gap: 6px; align-items: center; flex-wrap: wrap;">
                <el-select
                  v-if="historyBatches.length > 0"
                  v-model="currentBatchId"
                  placeholder="选择批次"
                  size="small"
                  style="width: 220px;"
                  @change="onBatchSelect"
                >
                  <el-option
                    v-for="b in historyBatches"
                    :key="b.batch_id"
                    :label="`${b.label} · ${b.total_count}条 · ${formatBatchTime(b.created_at)}`"
                    :value="b.batch_id"
                  />
                </el-select>
                <el-button
                  v-if="currentBatchId"
                  size="small"
                  plain
                  @click="showRenameDialog = true"
                >
                  重命名
                </el-button>
                <el-input
                  v-model="qaSearch"
                  placeholder="搜索..."
                  size="small"
                  style="width: 140px;"
                  clearable
                  :prefix-icon="Search"
                />
                <el-radio-group v-model="qaViewMode" size="small">
                  <el-radio-button value="list">列表</el-radio-button>
                  <el-radio-button value="file">按文件</el-radio-button>
                </el-radio-group>
                <el-button
                  size="small"
                  type="danger"
                  plain
                  @click="handleDeleteBatch"
                >
                  删除本批次
                </el-button>
              </div>
            </div>

            <!-- 列表视图 -->
            <div v-if="qaViewMode === 'list'" class="qa-card-list" v-loading="loadingQa">
              <div
                v-for="(qa, i) in filteredQaList"
                :key="qa.id || i"
                class="qa-card-item"
              >
                <div class="qa-card-header">
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <el-tag size="small" type="primary">Q{{ i + 1 }}</el-tag>
                    <el-tag size="small" :type="qa.answer_status === 'completed' ? 'success' : qa.answer_status === 'failed' ? 'danger' : 'warning'">
                      {{ answerStatusLabel(qa.answer_status) }}
                    </el-tag>
                    <el-tag v-if="qa.source" size="small" type="info">{{ sourceLabel(qa.source) }}</el-tag>
                    <el-tag
                      v-if="(qa as any).generation_metadata?.template_type"
                      size="small"
                      :type="(qa as any).generation_metadata.template_type === 'reverse' ? 'warning' : (qa as any).generation_metadata.template_type === 'multi_target' ? 'success' : (qa as any).generation_metadata.template_type === 'summary' ? 'info' : ''"
                    >
                      {{ templateTypeLabel((qa as any).generation_metadata?.template_type) }}
                    </el-tag>
                  </div>
                  <el-button link type="danger" size="small" @click="handleDeleteQuestion(qa)">删除</el-button>
                </div>
                <div class="qa-card-question">{{ qa.content }}</div>
                <div class="qa-card-answer">
                  <span class="qa-answer-label">答：</span>{{ qa.answer || '（无答案）' }}
                </div>
                <div v-if="qa.answer_error" class="qa-card-error">
                  <el-icon :size="12" color="#f56c6c"><WarningFilled /></el-icon>
                  {{ qa.answer_error }}
                </div>
              </div>
              <el-empty v-if="filteredQaList.length === 0 && qaList.length > 0" description="没有匹配的问答对" :image-size="60" />
            </div>

            <!-- 按文件分组视图 -->
            <div v-else class="qa-file-groups" v-loading="loadingQa">
              <div
                v-for="group in questionsByFile"
                :key="group.file_id"
                class="qa-file-group"
              >
                <div class="qa-file-group-header" @click="toggleFileGroup(group.file_id)">
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <el-icon :size="14" style="color: #909399; transition: transform 0.2s;" :style="{ transform: collapsedFileGroups.has(group.file_id) ? 'rotate(-90deg)' : 'rotate(0deg)' }">
                      <ArrowRight />
                    </el-icon>
                    <el-icon :size="16" color="#409eff"><Document /></el-icon>
                    <span style="font-weight: 500; font-size: 13px;">{{ group.file_name }}</span>
                    <el-tag size="small" type="info">{{ group.questions.length }} 个问答对</el-tag>
                  </div>
                </div>
                <div v-if="!collapsedFileGroups.has(group.file_id)" class="qa-file-group-content">
                  <div
                    v-for="(qa, i) in group.questions"
                    :key="qa.id || i"
                    class="qa-card-item"
                  >
                    <div class="qa-card-header">
                      <div style="display: flex; align-items: center; gap: 8px;">
                        <el-tag size="small" type="primary">Q{{ i + 1 }}</el-tag>
                        <el-tag size="small" :type="qa.answer_status === 'completed' ? 'success' : qa.answer_status === 'failed' ? 'danger' : 'warning'">
                          {{ answerStatusLabel(qa.answer_status) }}
                        </el-tag>
                        <el-tag v-if="qa.source" size="small" type="info">{{ sourceLabel(qa.source) }}</el-tag>
                        <el-tag
                          v-if="(qa as any).generation_metadata?.template_type"
                          size="small"
                          :type="(qa as any).generation_metadata.template_type === 'reverse' ? 'warning' : (qa as any).generation_metadata.template_type === 'multi_target' ? 'success' : (qa as any).generation_metadata.template_type === 'summary' ? 'info' : ''"
                        >
                          {{ templateTypeLabel((qa as any).generation_metadata?.template_type) }}
                        </el-tag>
                      </div>
                      <el-button link type="danger" size="small" @click="handleDeleteQuestion(qa)">删除</el-button>
                    </div>
                    <div class="qa-card-question">{{ qa.content }}</div>
                    <div class="qa-card-answer">
                      <span class="qa-answer-label">答：</span>{{ qa.answer || '（无答案）' }}
                    </div>
                    <div v-if="qa.answer_error" class="qa-card-error">
                      <el-icon :size="12" color="#f56c6c"><WarningFilled /></el-icon>
                      {{ qa.answer_error }}
                    </div>
                  </div>
                </div>
              </div>
              <el-empty v-if="questionsByFile.length === 0 && qaList.length > 0" description="没有匹配的问答对" :image-size="60" />
            </div>
          </div>
        </el-col>

        <!-- 右侧：参数配置 -->
        <el-col :span="10">
          <!-- 已选数据提示 -->
          <div v-if="hasSelection" class="content-card" style="border-left: 3px solid #409eff;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <el-icon :size="18" color="#409eff"><Document /></el-icon>
              <span style="font-weight: 500;">{{ selectionSummary }}</span>
            </div>
            <div style="margin-top: 4px; font-size: 12px; color: #909399;">
              {{ selectionDetail }}
            </div>
          </div>
          <div v-else class="content-card" style="border-left: 3px solid #e6a23c;">
            <div style="display: flex; align-items: center; gap: 8px; color: #909399;">
              <el-icon :size="18"><InfoFilled /></el-icon>
              <span>{{ dataSourceType === 'unstructured' ? '请在左侧选择需要生成问答的切片' : '请在左侧选择需要生成问答的结构化文件' }}</span>
            </div>
          </div>

          <!-- 生成模式（非结构化专用） -->
          <div v-if="dataSourceType === 'unstructured'" class="content-card">
            <div class="card-title">生成模式</div>
            <el-radio-group v-model="generateMode" size="large" style="width: 100%;">
              <el-radio-button value="local" style="width: 50%;">局部模式</el-radio-button>
              <el-radio-button value="enhanced" style="width: 50%;">领域增强</el-radio-button>
            </el-radio-group>
            <el-radio-group v-model="generateMode" size="large" style="width: 100%; margin-top: 8px;">
              <el-radio-button value="fulltext" style="width: 50%;">全文模式</el-radio-button>
              <el-radio-button value="all" style="width: 50%;">组合模式</el-radio-button>
            </el-radio-group>
            <div class="mode-desc">
              <el-text type="info" size="small">{{ modeDescriptions[generateMode] }}</el-text>
            </div>
          </div>

          <!-- 结构化生成策略 -->
          <div v-if="dataSourceType === 'structured'" class="content-card">
            <div class="card-title">生成策略</div>
            <el-radio-group v-model="structuredStrategy" style="width: 100%;">
              <el-radio value="template" style="width: 100%; margin-bottom: 8px;">
                <span style="font-weight: 500;">模板生成</span>
                <div style="font-size: 12px; color: #909399; margin-left: 22px; margin-top: 2px;">
                  根据字段映射关系和数据类型，自动生成多样化的指令-回复对，支持正向查询、逆向推理、多目标组合等，无需调用大模型
                </div>
              </el-radio>
              <el-radio value="llm" style="width: 100%;">
                <span style="font-weight: 500;">大模型增强</span>
                <div style="font-size: 12px; color: #909399; margin-left: 22px; margin-top: 2px;">
                  调用大模型基于行数据生成更自然、多样的问答对
                </div>
              </el-radio>
            </el-radio-group>
          </div>

          <!-- 高级参数 -->
          <div class="content-card">
            <div class="card-title">高级参数</div>
            <el-form :model="params" label-width="120px" size="small">
              <el-form-item v-if="dataSourceType === 'unstructured' || structuredStrategy === 'llm'" label="生成模型">
                <el-select v-model="params.model" style="width: 100%" placeholder="选择模型">
                  <el-option
                    v-for="m in chatModels"
                    :key="m.id"
                    :label="m.model_name"
                    :value="m.id"
                  />
                  <template #empty>
                    <div style="padding: 10px; color: #909399;">
                      暂无可用模型，<el-link type="primary" @click="$router.push('/data-governance/model-config')">去配置</el-link>
                    </div>
                  </template>
                </el-select>
              </el-form-item>
              <el-form-item v-if="dataSourceType === 'unstructured'" label="答案生成模型">
                <el-select v-model="params.answerModel" style="width: 100%" placeholder="默认与问题模型相同" clearable>
                  <el-option
                    v-for="m in chatModels"
                    :key="m.id"
                    :label="m.model_name"
                    :value="m.id"
                  />
                </el-select>
                <div style="font-size: 12px; color: #909399; margin-top: 4px;">留空则与问题生成模型相同</div>
              </el-form-item>
              <el-form-item v-if="dataSourceType === 'unstructured' || structuredStrategy === 'llm'" label="Temperature">
                <el-slider v-model="params.temperature" :min="0" :max="100" :step="5" show-input />
              </el-form-item>
              <el-form-item v-if="dataSourceType === 'unstructured'" label="答案 Temperature">
                <el-slider v-model="params.answerTemperature" :min="0" :max="100" :step="5" show-input />
              </el-form-item>
              <el-form-item v-if="dataSourceType === 'unstructured' || structuredStrategy === 'llm'" label="并发数">
                <el-input-number v-model="params.concurrency" :min="1" :max="10" style="width: 100%" />
              </el-form-item>
              <el-form-item v-if="dataSourceType === 'unstructured'" label="每块问题数">
                <el-input-number v-model="params.count" :min="1" :max="10" style="width: 100%" />
                <div style="font-size: 12px; color: #909399; margin-top: 4px;">每个切片最大生成问题数，实际数量会根据切片长度动态调整</div>
              </el-form-item>
              <el-form-item v-if="dataSourceType === 'structured'" label="每行生成数">
                <el-input-number v-model="params.questionsPerRow" :min="1" :max="5" style="width: 100%" />
                <div style="font-size: 12px; color: #909399; margin-top: 4px;">每行数据生成的问答对数量</div>
              </el-form-item>
              <el-form-item v-if="dataSourceType === 'unstructured'" label="脏数据过滤">
                <el-switch v-model="params.dirtyDataFilter" />
                <div style="font-size: 12px; color: #909399; margin-top: 4px;">启用后，LLM 会先评估切片内容质量，跳过乱码、目录等低质量内容</div>
              </el-form-item>
              <el-form-item v-if="dataSourceType === 'unstructured'" label="思维模式">
                <el-switch v-model="params.thinkingMode" />
                <div style="font-size: 12px; color: #909399; margin-top: 4px;">启用后，LLM 会先分析文本结构再生成问答对</div>
              </el-form-item>

              <!-- 高级参数折叠区 -->
              <el-collapse v-if="dataSourceType === 'unstructured'" style="margin-top: 8px; border: none;">
                <el-collapse-item title="更多参数" name="advanced">
                  <el-form-item label="全文最大字符">
                    <el-input-number v-model="params.fullDocMaxChars" :min="10000" :max="200000" :step="10000" style="width: 100%" />
                    <div style="font-size: 12px; color: #909399; margin-top: 4px;">全文模式中文档超过此字符数将先摘要再生成</div>
                  </el-form-item>
                  <el-form-item label="自定义提示词">
                    <el-input
                      v-model="params.presetPrompt"
                      type="textarea"
                      :rows="4"
                      placeholder="留空使用默认提示词。自定义提示词将替换系统默认的问题生成指导原则..."
                      style="width: 100%"
                    />
                  </el-form-item>
                </el-collapse-item>
              </el-collapse>

              <el-form-item>
                <el-button
                  type="primary"
                  :loading="generating"
                  :disabled="!canGenerate"
                  @click="startGenerate"
                  style="width: 100%"
                >
                  {{ generating ? '生成中...' : generateButtonLabel }}
                </el-button>
              </el-form-item>
            </el-form>
          </div>
        </el-col>
      </el-row>
    </template>

    <!-- 字段映射预览弹窗 -->
    <el-dialog
      v-model="fieldPreviewVisible"
      :title="`字段映射 - ${fieldPreviewFile?.filename || ''}`"
      width="650px"
      destroy-on-close
    >
      <el-table :data="fieldPreviewData" stripe size="small">
        <el-table-column prop="name" label="字段名" width="140" />
        <el-table-column prop="type" label="数据类型" width="100" />
        <el-table-column prop="sample" label="示例值" min-width="120" />
        <el-table-column label="字段角色" width="120">
          <template #default="{ row }">
            <el-tag
              :type="row.role === 'target' ? 'success' : row.role === 'redundant' ? 'info' : ''"
              size="small"
            >
              {{ roleLabel(row.role) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="脱敏" width="60">
          <template #default="{ row }">
            <el-tag v-if="row.desensitize" type="warning" size="small">是</el-tag>
            <span v-else style="color: #909399;">否</span>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="fieldPreviewVisible = false">关闭</el-button>
        <el-button type="primary" @click="goToStructuredPage">前往配置字段</el-button>
      </template>
    </el-dialog>

    <!-- 重命名批次对话框 -->
    <el-dialog v-model="showRenameDialog" title="重命名批次" width="400px" destroy-on-close>
      <el-input v-model="renameValue" placeholder="输入批次名称" maxlength="100" show-word-limit />
      <template #footer>
        <el-button @click="showRenameDialog = false">取消</el-button>
        <el-button type="primary" :loading="renameLoading" @click="confirmRename">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { questionApi, modelApi, fileApi, chunkApi } from '@/api'
import { formatSize } from '@/composables/useFormatters'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight, Search, WarningFilled, Loading, Close } from '@element-plus/icons-vue'
import PageHeader from '@/components/common/PageHeader.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import type { Question, Model, FileItem, Chunk, FieldSchemaItem } from '@/types'
import type { ElTable } from 'element-plus'

const router = useRouter()
const projectStore = useProjectStore()

// 数据源类型
const dataSourceType = ref<'unstructured' | 'structured'>('unstructured')

// 结构化生成策略
const structuredStrategy = ref<'template' | 'llm'>('template')

// 通用状态
const generating = ref(false)
const progress = ref(0)
const taskStatus = ref('')
const taskError = ref('')
const cancellingTask = ref(false)
const latestTaskData = ref<any>(null)
const prevTaskStatus = ref('')  // 上次任务状态，用于检测状态变化避免重复通知
const loadingQa = ref(false)
const qaList = ref<Question[]>([])
const qaSearch = ref('')
const qaViewMode = ref<'list' | 'file'>('file')
const collapsedFileGroups = ref<Set<string>>(new Set())
const currentBatchId = ref<string | null>(null)  // 当前生成任务的批次 ID
const historyBatches = ref<any[]>([])  // 项目历史批次列表
const chatModels = ref<Model[]>([])
let pollTimer: ReturnType<typeof setInterval> | null = null

// 非结构化：切片选择相关
const loadingFiles = ref(false)
const chunkedFiles = ref<FileItem[]>([])
const fileChunkMap = ref<Record<string, Chunk[]>>({})
const selectedChunkIds = ref<string[]>([])
const expandedFiles = ref<Set<string>>(new Set())

// 结构化：文件选择相关
const structuredFiles = ref<FileItem[]>([])
const selectedStructuredFiles = ref<FileItem[]>([])
const selectedStructuredFileIds = ref<string[]>([])
const structuredTableRef = ref<InstanceType<typeof ElTable>>()

// 字段映射预览
const fieldPreviewVisible = ref(false)
const fieldPreviewFile = ref<FileItem | null>(null)
const fieldPreviewData = ref<any[]>([])

// 当前选中文件的字段映射（用于右侧预览）
const currentFieldMapping = ref<any[]>([])

const generateMode = ref('local')

const modeDescriptions: Record<string, string> = {
  local: '仅基于当前文本切片生成事实型问答，答案直接引用切片原文',
  enhanced: '引入前后相邻切片作为上下文增强信息，降低语义片面性',
  fulltext: '以文档全文作为上下文生成摘要型、推理型问答',
  all: '同时生成三种来源的问答对',
}

const params = reactive({
  model: '',
  temperature: 70,
  concurrency: 5,
  questionsPerRow: 1,
  // 非结构化专用参数
  count: 3,             // 每块最大问题数
  dirtyDataFilter: true, // 脏数据过滤
  thinkingMode: true,    // 思维模式
  answerModel: '',       // 答案生成模型（空则与问题模型相同）
  answerTemperature: 70, // 答案生成温度
  fullDocMaxChars: 80000, // 全文模式最大字符数
  presetPrompt: '',      // 自定义提示词（空则使用后端默认）
})

// 内置参数，不暴露给用户
const CONTEXT_WINDOW = 2

// ========== 计算属性 ==========

const isAllChunksSelected = computed(() => {
  const allIds = Object.values(fileChunkMap.value).flat().map(c => c.id)
  return allIds.length > 0 && selectedChunkIds.value.length === allIds.length
})

const isAllStructuredSelected = computed(() =>
  structuredFiles.value.length > 0 && selectedStructuredFileIds.value.length === structuredFiles.value.length
)

const hasSelection = computed(() => {
  if (dataSourceType.value === 'unstructured') {
    return selectedChunkIds.value.length > 0
  }
  return selectedStructuredFileIds.value.length > 0
})

const selectionSummary = computed(() => {
  if (dataSourceType.value === 'unstructured') {
    return `已选择 ${selectedChunkIds.value.length} 个切片`
  }
  return `已选择 ${selectedStructuredFileIds.value.length} 个结构化文件`
})

const selectionDetail = computed(() => {
  if (dataSourceType.value === 'unstructured') {
    const fileIds = new Set<string>()
    for (const chunk of Object.values(fileChunkMap.value).flat()) {
      if (selectedChunkIds.value.includes(chunk.id) && chunk.file_id) {
        fileIds.add(chunk.file_id)
      }
    }
    return `来自 ${fileIds.size} 个文件`
  }
  const targetFields = currentFieldMapping.value.filter(f => f.role === 'target').length
  const featureFields = currentFieldMapping.value.filter(f => f.role === 'feature').length
  return `${featureFields} 个输入字段，${targetFields} 个输出字段`
})

const canGenerate = computed(() => {
  if (dataSourceType.value === 'unstructured') {
    return selectedChunkIds.value.length > 0
  }
  // 结构化模式：需要有选中的文件，且至少有一个输出字段
  if (selectedStructuredFileIds.value.length === 0) return false
  if (structuredStrategy.value === 'llm' && !params.model) return false
  return true
})

const generateButtonLabel = computed(() => {
  if (generating.value) return '生成中...'
  if (dataSourceType.value === 'unstructured') {
    return `生成问答（${selectedChunkIds.value.length} 个切片）`
  }
  return `生成问答（${selectedStructuredFileIds.value.length} 个文件）`
})

// 生成示例预览
const generateExamples = computed(() => {
  const features = currentFieldMapping.value.filter(f => f.role === 'feature')
  const targets = currentFieldMapping.value.filter(f => f.role === 'target')
  if (features.length === 0 || targets.length === 0) return []

  // 类型感知的疑问词
  const typeQuestionWords: Record<string, string> = {
    string: '什么',
    integer: '多少',
    float: '多少',
    date: '什么时候',
    boolean: '是否',
  }

  // 获取首个样本值或占位符
  const getSample = (f: any) => f.sample?.[0] || 'X'

  // 格式化条件描述
  const formatCondition = (f: any) => {
    const val = getSample(f)
    if (f.desensitize) return `${f.name}为***`
    if (f.type === 'boolean') {
      const boolVal = val.toLowerCase()
      if (['true', '是', '1', 'yes'].includes(boolVal)) return f.name
      return `未${f.name}`
    }
    return `${f.name}为${val}`
  }

  const conditionStr = features.map(f => formatCondition(f)).join('，')
  const firstCondition = formatCondition(features[0])
  const examples: any[] = []

  // 1. 正向查询：已知条件 → 查询目标
  const t0 = targets[0]
  const qword0 = typeQuestionWords[t0.type] || '什么'
  examples.push({
    instruction: `已知${conditionStr}，请问${t0.name}是${qword0}？`,
    output: t0.desensitize ? `${t0.name}为***。` : `${t0.name}是${getSample(t0)}。`,
    type: 'forward',
  })

  // 2. 如果 questionsPerRow >= 2 或有多个 target，展示逆向推理
  if (targets.length > 0 && features.length > 0) {
    const tFirst = targets[0]
    const fFirst = features[0]
    const tSample = getSample(tFirst)
    const qwordF = typeQuestionWords[fFirst.type] || '什么'
    if (tSample && tSample !== 'X') {
      examples.push({
        instruction: `已知${tFirst.name}为${tFirst.desensitize ? '***' : tSample}，请问${fFirst.name}是什么？`,
        output: fFirst.desensitize ? `${fFirst.name}为***。` : `${fFirst.name}是${getSample(fFirst)}。`,
        type: 'reverse',
      })
    }
  }

  // 3. 如果有多个 target，展示多目标查询
  if (targets.length >= 2) {
    const validTargets = targets.filter(t => getSample(t) && getSample(t) !== 'X')
    if (validTargets.length >= 2) {
      const targetNames = validTargets.map(t => t.name).join('和')
      examples.push({
        instruction: `已知${conditionStr}，请分别说明${targetNames}的值。`,
        output: validTargets.map(t => t.desensitize ? `${t.name}为***` : `${t.name}是${getSample(t)}`).join('，') + '。',
        type: 'multi_target',
      })
    }
  }

  // 4. 概括型
  if (features.length >= 1) {
    examples.push({
      instruction: `请描述${conditionStr}对应的完整记录。`,
      output: '（包含所有字段的完整描述）',
      type: 'summary',
    })
  }

  return examples
})

// ========== 非结构化切片操作 ==========

const isFileAllSelected = (fileId: string) => {
  const chunks = fileChunkMap.value[fileId] || []
  return chunks.length > 0 && chunks.every(c => selectedChunkIds.value.includes(c.id))
}

const isFilePartialSelected = (fileId: string) => {
  const chunks = fileChunkMap.value[fileId] || []
  const selected = chunks.filter(c => selectedChunkIds.value.includes(c.id)).length
  return selected > 0 && selected < chunks.length
}

const toggleFileExpand = (fileId: string) => {
  if (expandedFiles.value.has(fileId)) {
    expandedFiles.value.delete(fileId)
  } else {
    expandedFiles.value.add(fileId)
  }
  expandedFiles.value = new Set(expandedFiles.value)
}

const toggleFileChunks = (fileId: string, checked: boolean) => {
  const chunks = fileChunkMap.value[fileId] || []
  const chunkIds = chunks.map(c => c.id)
  if (checked) {
    const newIds = chunkIds.filter(id => !selectedChunkIds.value.includes(id))
    selectedChunkIds.value = [...selectedChunkIds.value, ...newIds]
  } else {
    selectedChunkIds.value = selectedChunkIds.value.filter(id => !chunkIds.includes(id))
  }
}

const toggleChunk = (chunkId: string, checked: boolean) => {
  if (checked) {
    if (!selectedChunkIds.value.includes(chunkId)) {
      selectedChunkIds.value.push(chunkId)
    }
  } else {
    selectedChunkIds.value = selectedChunkIds.value.filter(id => id !== chunkId)
  }
}

const toggleSelectAllChunks = () => {
  if (isAllChunksSelected.value) {
    selectedChunkIds.value = []
  } else {
    const allIds = Object.values(fileChunkMap.value).flat().map(c => c.id)
    selectedChunkIds.value = [...allIds]
  }
}

const handleGenerateFromSelection = () => {
  if (selectedChunkIds.value.length === 0) {
    ElMessage.warning('请先选择切片')
    return
  }
  startGenerate()
}

const fileIconColor = (fileType: string) => {
  const map: Record<string, string> = { pdf: '#f56c6c', docx: '#e6a23c', doc: '#e6a23c', txt: '#909399', md: '#67c23a' }
  return map[fileType] || '#409eff'
}

// ========== 结构化文件操作 ==========

const handleStructuredSelectionChange = (selection: FileItem[]) => {
  selectedStructuredFiles.value = selection
  selectedStructuredFileIds.value = selection.map(f => f.id)
  // 更新字段映射预览（取第一个文件的字段）
  if (selection.length > 0) {
    loadFieldMapping(selection[0].id)
  } else {
    currentFieldMapping.value = []
  }
}

const toggleSelectAllStructured = () => {
  if (isAllStructuredSelected.value) {
    structuredTableRef.value?.clearSelection()
  } else {
    structuredFiles.value.forEach(row => {
      structuredTableRef.value?.toggleRowSelection(row, true)
    })
  }
}

const openFieldPreview = (file: FileItem) => {
  fieldPreviewFile.value = file
  fieldPreviewData.value = (file.field_schema || []) as FieldSchemaItem[]
  fieldPreviewVisible.value = true
}

const goToStructuredPage = () => {
  fieldPreviewVisible.value = false
  router.push('/data-governance/structured')
}

const loadFieldMapping = async (fileId: string) => {
  // 从已加载的文件数据中获取字段映射
  const file = structuredFiles.value.find(f => f.id === fileId)
  if (file?.field_schema?.length) {
    currentFieldMapping.value = file.field_schema as FieldSchemaItem[]
  } else if (projectStore.currentProjectId) {
    // 自动提取字段信息
    try {
      const res = await fileApi.extractFields(projectStore.currentProjectId, fileId)
      const data = (res as any)?.data || res
      const fields = data?.fields || []
      if (file) {
        file.field_schema = fields
        file.row_count = data?.total_rows || 0
        file.status = 'completed'
      }
      currentFieldMapping.value = fields as FieldSchemaItem[]
    } catch (e) {
      currentFieldMapping.value = []
    }
  } else {
    currentFieldMapping.value = []
  }
}

const roleLabel = (role: string) => {
  const map: Record<string, string> = { feature: '业务属性', target: '输出字段', redundant: '冗余字段' }
  return map[role] || role
}

// ========== 数据源切换 ==========

const handleDataSourceChange = () => {
  // 切换数据源类型时，重置进度条状态，避免同步另一类型的进度
  stopPolling()
  generating.value = false
  progress.value = 0
  taskStatus.value = ''
  taskError.value = ''
  prevTaskStatus.value = ''
  latestTaskData.value = null
  currentBatchId.value = null
  qaList.value = []

  // 重新加载数据
  if (dataSourceType.value === 'unstructured') {
    fetchFilesAndChunks()
  } else {
    fetchStructuredFiles()
  }

  // 恢复当前类型的任务状态
  resumeRunningTask()
}

// ========== 数据获取 ==========

const fetchModels = async () => {
  try {
    const res = await modelApi.list()
    const allModels = Array.isArray(res) ? res : (res && typeof res === 'object' && 'items' in res) ? (res as any).items || [] : []
    chatModels.value = allModels.filter((m: Model) => m.model_type === 'chat')
    const defaultModel = chatModels.value.find((m: Model) => m.is_default === 'true')
    if (defaultModel) params.model = defaultModel.id
  } catch (e) {
    chatModels.value = []
  }
}

const fetchFilesAndChunks = async () => {
  if (!projectStore.currentProjectId) return
  loadingFiles.value = true
  try {
    const filesRes = await fileApi.list(projectStore.currentProjectId)
    let allFiles: FileItem[] = []
    if (Array.isArray(filesRes)) {
      allFiles = filesRes
    } else if (filesRes && typeof filesRes === 'object' && 'items' in filesRes) {
      allFiles = (filesRes as any).items || []
    }

    // 只显示已切片完成的非结构化文件
    chunkedFiles.value = allFiles.filter(f =>
      f.status === 'completed' && ['pdf', 'docx', 'doc', 'txt', 'md', 'epub'].includes(f.file_type)
    )

    // 获取每个文件的切片
    const chunkMap: Record<string, Chunk[]> = {}
    for (const file of chunkedFiles.value) {
      try {
        const chunksRes = await chunkApi.list(projectStore.currentProjectId, { file_id: file.id })
        let chunks: Chunk[] = []
        if (chunksRes && typeof chunksRes === 'object' && 'items' in chunksRes) {
          chunks = (chunksRes as any).items || []
        } else if (Array.isArray(chunksRes)) {
          chunks = chunksRes
        }
        chunkMap[file.id] = chunks
      } catch (e) {
        chunkMap[file.id] = []
      }
    }
    fileChunkMap.value = chunkMap

    // 默认全部折叠，点击才展开
    expandedFiles.value = new Set()
  } catch (e) {
    chunkedFiles.value = []
    fileChunkMap.value = {}
  } finally {
    loadingFiles.value = false
  }
}

const fetchStructuredFiles = async () => {
  if (!projectStore.currentProjectId) return
  loadingFiles.value = true
  try {
    const filesRes = await fileApi.list(projectStore.currentProjectId)
    let allFiles: FileItem[] = []
    if (Array.isArray(filesRes)) {
      allFiles = filesRes
    } else if (filesRes && typeof filesRes === 'object' && 'items' in filesRes) {
      allFiles = (filesRes as any).items || []
    }

    // 只显示已处理完成的结构化文件
    structuredFiles.value = allFiles.filter(f =>
      f.status === 'completed' && ['xlsx', 'xls', 'csv'].includes(f.file_type)
    )
  } catch (e) {
    structuredFiles.value = []
  } finally {
    loadingFiles.value = false
  }
}

const fetchQaList = async () => {
  if (!projectStore.currentProjectId) return
  // 只在有批次 ID 时才加载问答对，避免加载不属于当前生成批次的数据
  if (!currentBatchId.value) {
    qaList.value = []
    return
  }
  loadingQa.value = true
  try {
    const res = await questionApi.list(projectStore.currentProjectId, {
      batch_id: currentBatchId.value,
      page_size: 500,
    })
    if (Array.isArray(res)) {
      qaList.value = res
    } else if (res && typeof res === 'object' && 'items' in res) {
      qaList.value = (res as any).items || []
    } else {
      qaList.value = []
    }
  } catch (e) {
    qaList.value = []
  } finally {
    loadingQa.value = false
  }
}

// ========== 生成逻辑 ==========

const startGenerate = async () => {
  if (!projectStore.currentProjectId) {
    ElMessage.warning('请先选择项目')
    return
  }

  if (dataSourceType.value === 'unstructured') {
    await startUnstructuredGenerate()
  } else {
    await startStructuredGenerate()
  }
}

const startUnstructuredGenerate = async () => {
  if (selectedChunkIds.value.length === 0) {
    ElMessage.warning('请先选择切片')
    return
  }
  if (!params.model) {
    ElMessage.warning('请先选择生成模型')
    return
  }

  generating.value = true
  progress.value = 0
  taskStatus.value = 'running'
  taskError.value = ''
  prevTaskStatus.value = ''
  latestTaskData.value = null

  try {
    // 前端 generateMode → 后端 generation_mode 映射
    const modeMap: Record<string, string> = {
      local: 'local',
      enhanced: 'context_enhanced',
      fulltext: 'full_doc',
      all: 'all',
    }

    const requestData: any = {
      chunk_ids: selectedChunkIds.value,
      generation_mode: modeMap[generateMode.value] || 'all',
      model_id: params.model,
      temperature: params.temperature / 100,
      concurrency: params.concurrency,
      context_window: CONTEXT_WINDOW,
      count: params.count,
      dirty_data_filter: params.dirtyDataFilter,
      thinking_mode: params.thinkingMode,
      answer_temperature: params.answerTemperature / 100,
      full_doc_max_chars: params.fullDocMaxChars,
    }

    // 答案生成模型（如指定且与问题模型不同）
    if (params.answerModel && params.answerModel !== params.model) {
      requestData.answer_model_id = params.answerModel
    }

    // 自定义提示词（非空时传递，空则使用后端默认值）
    if (params.presetPrompt.trim()) {
      requestData.preset_prompt = params.presetPrompt.trim()
    }

    const res = await questionApi.generateQA(projectStore.currentProjectId, requestData)
    const data = (res as any)?.data || res
    currentBatchId.value = data?.batch_id || null

    // 乐观初始化：只设 total_chunks，不设 total_steps
    // total_steps 由后端计算（组合模式 = chunks × 3），轮询后自动更新
    latestTaskData.value = {
      id: data?.task_id || '',
      task_type: 'generate_qa',
      status: 'running',
      progress: 0,
      result: {
        created_questions: 0,
        created_answers: 0,
        processed_chunks: 0,
        skipped_chunks: 0,
        total_chunks: data?.chunk_count || 0,
        failed_answers: 0,
      },
      error: null,
    }

    ElMessage.info(`已为 ${selectedChunkIds.value.length} 个切片启动问答生成`)

    // 500ms 后立即获取真实状态，之后 watch 会接管轮询
    setTimeout(async () => {
      await fetchLatestTaskStatus()
    }, 500)
  } catch (error: any) {
    ElMessage.error(error?.message || '启动生成失败')
    generating.value = false
    taskStatus.value = ''
    latestTaskData.value = null
  }
}

const startStructuredGenerate = async () => {
  if (selectedStructuredFileIds.value.length === 0) {
    ElMessage.warning('请先选择结构化文件')
    return
  }
  if (structuredStrategy.value === 'llm' && !params.model) {
    ElMessage.warning('请先选择生成模型')
    return
  }

  // 检查字段映射是否完整
  const filesWithoutTarget = selectedStructuredFiles.value.filter(f => {
    const fields = f.field_schema || []
    return !fields.some(field => field.role === 'target')
  })
  if (filesWithoutTarget.length > 0) {
    ElMessage.warning(`文件 ${filesWithoutTarget[0].filename} 没有设置输出字段，请先在结构化数据处理页面标注字段角色`)
    return
  }

  generating.value = true
  progress.value = 0
  taskError.value = ''
  prevTaskStatus.value = ''
  latestTaskData.value = null

  try {
    taskStatus.value = 'running'

    const res = await questionApi.generateStructuredQA(projectStore.currentProjectId!, {
      file_ids: selectedStructuredFileIds.value,
      strategy: structuredStrategy.value,
      model_id: structuredStrategy.value === 'llm' ? params.model : undefined,
      temperature: structuredStrategy.value === 'llm' ? params.temperature / 100 : undefined,
      questions_per_row: params.questionsPerRow,
    })
    const data = (res as any)?.data || res
    currentBatchId.value = data?.batch_id || null

    // 乐观初始化任务状态
    latestTaskData.value = {
      id: data?.task_id || '',
      task_type: 'generate_structured_qa',
      status: 'running',
      progress: 0,
      result: {
        created_questions: 0,
        processed_rows: 0,
        total_rows: 0,
      },
      error: null,
    }

    const strategyLabel = structuredStrategy.value === 'template' ? '模板' : '大模型增强'
    ElMessage.info(`已为 ${selectedStructuredFileIds.value.length} 个文件启动${strategyLabel}问答生成`)

    // 500ms 后立即获取真实状态
    setTimeout(async () => {
      await fetchLatestTaskStatus()
    }, 500)
  } catch (error: any) {
    ElMessage.error(error?.message || '启动生成失败')
    generating.value = false
    taskStatus.value = ''
    latestTaskData.value = null
  }
}

const startPolling = () => {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    await fetchLatestTaskStatus()
  }, 1500)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

/**
 * 获取最新任务状态（轮询核心方法）
 * - 更新 latestTaskData、progress、taskStatus、taskError
 * - 检测状态变化，避免重复通知
 * - 终态时自动停止轮询、刷新数据
 */
const fetchLatestTaskStatus = async () => {
  if (!projectStore.currentProjectId) return
  try {
    // 按当前数据源类型过滤任务，避免串进度
    const taskType = dataSourceType.value === 'unstructured' ? 'generate_qa' : 'generate_structured_qa'
    const res = await questionApi.latestQATask(projectStore.currentProjectId, { task_type: taskType })
    const taskData = res as any
    if (!taskData || typeof taskData !== 'object' || !taskData.status) {
      console.log('[QA轮询] 无有效任务数据:', taskData)
      return
    }

    // 保存完整任务数据，供 taskSummary 读取
    latestTaskData.value = taskData

    // 进度：completed 强制 100，否则取后端值
    const newProgress = taskData.status === 'completed' ? 100
      : (typeof taskData.progress === 'number' ? taskData.progress : 0)
    progress.value = newProgress
    taskStatus.value = taskData.status

    // 提取错误信息
    if (taskData.status === 'failed' && taskData.error) {
      taskError.value = taskData.error
    }

    // 状态变化检测：只在状态真正改变时通知
    const newStatus = taskData.status
    if (prevTaskStatus.value && prevTaskStatus.value !== newStatus) {
      if (newStatus === 'completed') {
        ElMessage.success('问答生成完成')
      } else if (newStatus === 'failed') {
        ElMessage.error('问答生成失败')
      } else if (newStatus === 'cancelling') {
        ElMessage.info('正在取消任务，已生成的内容将被保存...')
      } else if (newStatus === 'stopped' || newStatus === 'cancelled') {
        ElMessage.warning('问答生成已取消')
      }
    }
    prevTaskStatus.value = newStatus

    console.log('[QA轮询] status:', taskData.status, 'progress:', newProgress,
      'questions:', taskData.result?.created_questions,
      'answers:', taskData.result?.created_answers)

    // 终态处理：停止轮询、刷新数据
    // cancelling 状态继续轮询，等后台任务完成后变为 cancelled
    if (['completed', 'failed', 'stopped', 'cancelled'].includes(taskData.status)) {
      stopPolling()
      generating.value = false
      if (taskData.status === 'completed') {
        progress.value = 100
      }
      await fetchQaList()
      await fetchHistoryBatches()
    }
  } catch (e) {
    console.error('[QA轮询] 请求失败:', e)
  }
}

/**
 * 恢复进行中的任务：页面加载时检查是否有未完成的任务
 */
const resumeRunningTask = async () => {
  if (!projectStore.currentProjectId) return
  try {
    // 按当前数据源类型过滤任务
    const taskType = dataSourceType.value === 'unstructured' ? 'generate_qa' : 'generate_structured_qa'
    const res = await questionApi.latestQATask(projectStore.currentProjectId, { task_type: taskType })
    const taskData = res as any
    if (taskData && typeof taskData === 'object' && taskData.status) {
      // 恢复 batch_id 以便加载问答对列表
      const batchId = taskData.result?.batch_id || null
      if (batchId) currentBatchId.value = batchId

      const isActive = ['pending', 'running', 'cancelling'].includes(taskData.status)
      if (isActive) {
        // 有正在运行的任务，恢复进度显示
        latestTaskData.value = taskData
        generating.value = true
        progress.value = taskData.status === 'completed' ? 100 : (taskData.progress || 0)
        taskStatus.value = taskData.status
        prevTaskStatus.value = taskData.status  // 恢复时不触发通知
        if (taskData.error) taskError.value = taskData.error
        // 自动开始轮询
        startPolling()
      } else if (['completed', 'failed', 'stopped', 'cancelled'].includes(taskData.status)) {
        // 显示最近一次任务的结果（可能已刷新页面）
        latestTaskData.value = taskData
        progress.value = taskData.status === 'completed' ? 100 : (taskData.progress || 0)
        taskStatus.value = taskData.status
        if (taskData.error) taskError.value = taskData.error
        // 加载该批次的问答对
        if (batchId) await fetchQaList()
      }
    }
  } catch (e) {
    // 静默处理
  }
}

// 监听任务状态变化，自动启停轮询
watch(taskStatus, (status) => {
  if (['pending', 'running'].includes(status)) {
    if (!pollTimer) startPolling()
  } else {
    stopPolling()
  }
})

const handleCancelTask = async () => {
  if (!projectStore.currentProjectId || !latestTaskData.value?.id) return
  cancellingTask.value = true
  try {
    await questionApi.cancelTask(projectStore.currentProjectId, latestTaskData.value.id)
    ElMessage.success('正在取消任务，已生成的内容将被保存...')
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || error?.message || '取消失败')
  } finally {
    cancellingTask.value = false
  }
}

const sourceLabel = (source: string) => {
  const map: Record<string, string> = { local: '局部', context: '增强', full: '全文', all: '组合', structured_template: '模板', structured_llm: 'LLM增强', generated_qa: '局部', generated_qa_local: '局部', generated_qa_context_enhanced: '增强', generated_qa_full_doc: '全文' }
  return map[source] || source
}

const answerStatusLabel = (status?: string) => {
  const map: Record<string, string> = { completed: '成功', failed: '失败', pending: '待处理', processing: '生成中' }
  return map[status || ''] || status || '未知'
}

const templateTypeLabel = (type?: string) => {
  const map: Record<string, string> = { forward: '正向查询', reverse: '逆向推理', multi_target: '多目标', summary: '概括型' }
  return map[type || ''] || ''
}

const filteredQaList = computed(() => {
  if (!qaSearch.value.trim()) return qaList.value
  const keyword = qaSearch.value.trim().toLowerCase()
  return qaList.value.filter(qa =>
    qa.content?.toLowerCase().includes(keyword) ||
    qa.answer?.toLowerCase().includes(keyword)
  )
})

const questionsByFile = computed(() => {
  const list = qaSearch.value.trim() ? filteredQaList.value : qaList.value
  const map = new Map<string, any[]>()
  list.forEach(qa => {
    const fileId = (qa as any).file_id || 'unknown'
    if (!map.has(fileId)) map.set(fileId, [])
    map.get(fileId)!.push(qa)
  })
  return Array.from(map.entries()).map(([fileId, items]) => ({
    file_id: fileId,
    file_name: (items[0] as any)?.file_name || '未知文件',
    questions: items,
  }))
})

const toggleFileGroup = (fileId: string) => {
  const next = new Set(collapsedFileGroups.value)
  if (next.has(fileId)) {
    next.delete(fileId)
  } else {
    next.add(fileId)
  }
  collapsedFileGroups.value = next
}

const hasHistoryBatches = computed(() => historyBatches.value.length > 0)

const taskSummary = computed(() => {
  const result = latestTaskData.value?.result || {}
  const taskType = latestTaskData.value?.task_type || ''
  const isStructured = taskType === 'generate_structured_qa' || result.total_rows !== undefined

  if (isStructured) {
    return {
      isStructured: true,
      processed: result.processed_rows || result.processed_chunks || 0,
      total: result.total_rows || 0,
      totalChunks: 0,
      createdQuestions: result.created_questions || 0,
      createdAnswers: result.created_answers || 0,
      skipped: result.skipped_rows || 0,
      failedAnswers: result.failed_answers || 0,
    }
  }
  return {
    isStructured: false,
    processed: result.processed_chunks || 0,
    total: result.total_steps || result.total_chunks || result.total_rows || 0,
    totalChunks: result.total_chunks || 0,
    createdQuestions: result.created_questions || 0,
    createdAnswers: result.created_answers || 0,
    skipped: result.skipped_chunks || 0,
    failedAnswers: result.failed_answers || 0,
  }
})

const hasActiveTask = computed(() => {
  return ['pending', 'running', 'cancelling'].includes(taskStatus.value)
})

const taskStatusLabel = computed(() => {
  const map: Record<string, string> = {
    pending: '排队中',
    running: '生成中',
    cancelling: '正在取消...',
    completed: '已完成',
    failed: '生成失败',
    stopped: '已取消',
    cancelled: '已取消',
  }
  return map[taskStatus.value] || taskStatus.value || '等待中'
})

const formatBatchTime = (t: string | null) => {
  if (!t) return ''
  try {
    const d = new Date(t)
    if (isNaN(d.getTime())) return ''
    const month = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    const hour = String(d.getHours()).padStart(2, '0')
    const min = String(d.getMinutes()).padStart(2, '0')
    return `${month}-${day} ${hour}:${min}`
  } catch {
    return ''
  }
}

const fetchHistoryBatches = async () => {
  if (!projectStore.currentProjectId) return
  try {
    const res = await questionApi.listBatches(projectStore.currentProjectId)
    const data = (res as any)?.batches || res || []
    historyBatches.value = Array.isArray(data) ? data : []
  } catch {
    historyBatches.value = []
  }
}

const onBatchSelect = (batchId: string) => {
  currentBatchId.value = batchId
  fetchQaList()
}

// ========== 删除操作 ==========

const handleDeleteQuestion = async (qa: Question) => {
  if (!projectStore.currentProjectId || !qa.id) return
  try {
    await ElMessageBox.confirm('确定删除这条问答对？', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await questionApi.delete(projectStore.currentProjectId, qa.id)
    ElMessage.success('问答对已删除')
    // 从列表中移除
    qaList.value = qaList.value.filter(q => q.id !== qa.id)
  } catch {
    // 用户取消
  }
}

const handleDeleteBatch = async () => {
  if (!projectStore.currentProjectId || !currentBatchId.value) return
  try {
    await ElMessageBox.confirm(
      `确定删除当前批次的所有问答对？共 ${qaList.value.length} 条将被永久删除。`,
      '删除确认',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      }
    )
    await questionApi.deleteBatch(projectStore.currentProjectId, currentBatchId.value)
    ElMessage.success('批次已删除')
    qaList.value = []
    currentBatchId.value = null
    await fetchHistoryBatches()
  } catch {
    // 用户取消
  }
}

// ========== 批次重命名 ==========
const showRenameDialog = ref(false)
const renameValue = ref('')
const renameLoading = ref(false)

watch(showRenameDialog, (visible) => {
  if (visible && currentBatchId.value) {
    const batch = historyBatches.value.find((b: any) => b.batch_id === currentBatchId.value)
    renameValue.value = batch?.name || batch?.label || ''
  }
})

const confirmRename = async () => {
  if (!projectStore.currentProjectId || !currentBatchId.value || !renameValue.value.trim()) return
  renameLoading.value = true
  try {
    await questionApi.renameBatch(projectStore.currentProjectId, currentBatchId.value, renameValue.value.trim())
    ElMessage.success('批次名称已更新')
    showRenameDialog.value = false
    await fetchHistoryBatches()
  } catch (e: any) {
    ElMessage.error(e?.message || '重命名失败')
  } finally {
    renameLoading.value = false
  }
}

// ========== 生命周期 ==========

watch(() => projectStore.currentProjectId, (newId) => {
  if (newId) {
    selectedChunkIds.value = []
    selectedStructuredFileIds.value = []
    selectedStructuredFiles.value = []
    currentFieldMapping.value = []
    currentBatchId.value = null
    qaList.value = []
    fetchFilesAndChunks()
    fetchStructuredFiles()
    fetchModels()
    fetchHistoryBatches()
  }
})

onMounted(() => {
  if (projectStore.currentProjectId) {
    fetchFilesAndChunks()
    fetchStructuredFiles()
    fetchModels()
    fetchHistoryBatches()
    // 恢复进行中的任务（页面刷新后仍可看到进度）
    resumeRunningTask()
  }
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style lang="scss" scoped>
.mode-desc {
  margin-top: 8px;
}

.progress-info {
  margin-top: 12px;
  display: flex;
  gap: 24px;
  font-size: 13px;
  color: #909399;
}

.qa-card-list {
  max-height: 600px;
  overflow-y: auto;
  padding-top: 4px;
}

.qa-file-groups {
  max-height: 600px;
  overflow-y: auto;
}

.qa-file-group {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  margin-bottom: 12px;
  overflow: hidden;
}

.qa-file-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: #f5f7fa;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;

  &:hover {
    background: #ecf0f5;
  }
}

.qa-file-group-content {
  padding: 12px;

  .qa-card-item {
    margin-bottom: 10px;

    &:last-child {
      margin-bottom: 0;
    }
  }
}

.qa-card-item {
  margin-bottom: 12px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 14px;
  transition: box-shadow 0.2s;

  &:hover {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  }

  .qa-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
  }

  .qa-card-question {
    font-size: 14px;
    font-weight: 500;
    color: #303133;
    line-height: 1.6;
    margin-bottom: 8px;
    padding: 8px 10px;
    background: #f0f5ff;
    border-radius: 6px;
    border-left: 3px solid #409eff;
  }

  .qa-card-answer {
    font-size: 13px;
    color: #606266;
    line-height: 1.6;
    padding: 8px 10px;
    background: #f5f7fa;
    border-radius: 6px;

    .qa-answer-label {
      font-weight: 500;
      color: #303133;
    }
  }

  .qa-card-error {
    margin-top: 8px;
    font-size: 12px;
    color: #f56c6c;
    display: flex;
    align-items: center;
    gap: 4px;
  }
}

.file-chunk-group {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  margin-bottom: 8px;
  overflow: hidden;

  .file-chunk-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 14px;
    cursor: pointer;
    transition: background 0.2s;

    &:hover {
      background: #f5f7fa;
    }
  }

  .chunk-select-list {
    border-top: 1px solid #ebeef5;
    background: #fafbfc;
    padding: 4px 0;

    .chunk-select-item {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 14px 6px 36px;
      transition: background 0.2s;

      &:hover {
        background: #f0f7ff;
      }

      .chunk-select-name {
        font-size: 13px;
        color: #303133;
        max-width: 200px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .chunk-select-info {
        font-size: 12px;
        color: #909399;
        flex-shrink: 0;
      }

      .chunk-select-summary {
        font-size: 12px;
        color: #909399;
        flex: 1;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
    }
  }
}

.generate-preview {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;

  .preview-title {
    font-size: 13px;
    font-weight: 500;
    color: #303133;
    margin-bottom: 12px;
  }

  .preview-item {
    margin-bottom: 12px;
    border: 1px solid #ebeef5;
    border-radius: 8px;
    padding: 12px;
    transition: box-shadow 0.2s;

    &:hover {
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
    }

    .preview-label {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      font-weight: 500;
      color: #303133;
      margin-bottom: 8px;
    }

    .preview-content {
      font-size: 13px;
      line-height: 1.8;

      p {
        margin: 0 0 4px 0;
      }

      strong {
        color: #303133;
      }
    }
  }
}

// ========== 生成任务进度面板 ==========
.generate-task-panel {
  border-left: 3px solid #409eff;
  transition: border-color 0.3s, background-color 0.3s;

  &.is-running {
    border-left-color: #409eff;
    background-color: rgba(64, 158, 255, 0.02);
  }

  &.is-pending {
    border-left-color: #909399;
    background-color: rgba(144, 147, 153, 0.02);
  }

  &.is-cancelling {
    border-left-color: #e6a23c;
    background-color: rgba(230, 162, 60, 0.04);
  }

  &.is-completed {
    border-left-color: #67c23a;
    background-color: rgba(103, 194, 58, 0.04);
  }

  &.is-failed {
    border-left-color: #f56c6c;
    background-color: rgba(245, 108, 108, 0.04);
  }

  &.is-stopped,
  &.is-cancelled {
    border-left-color: #e6a23c;
    background-color: rgba(230, 162, 60, 0.04);
  }

  .generate-task-panel__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
  }

  .generate-task-panel__title-wrap {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .generate-task-panel__title {
    font-size: 15px;
    font-weight: 600;
    color: #303133;
  }

  .generate-task-panel__status {
    font-size: 12px;
    padding: 2px 10px;
    border-radius: 10px;
    background: #ecf5ff;
    color: #409eff;
    font-weight: 500;
  }

  &.is-running .generate-task-panel__status {
    background: #ecf5ff;
    color: #409eff;
  }

  &.is-pending .generate-task-panel__status {
    background: #f4f4f5;
    color: #909399;
  }

  &.is-cancelling .generate-task-panel__status {
    background: #fdf6ec;
    color: #e6a23c;
  }

  &.is-completed .generate-task-panel__status {
    background: #f0f9eb;
    color: #67c23a;
  }

  &.is-failed .generate-task-panel__status {
    background: #fef0f0;
    color: #f56c6c;
  }

  &.is-stopped .generate-task-panel__status,
  &.is-cancelled .generate-task-panel__status {
    background: #fdf6ec;
    color: #e6a23c;
  }

  .generate-task-panel__right {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .cancelling-hint {
    color: #e6a23c;
    font-size: 13px;
    animation: blink 1.2s ease-in-out infinite;
  }

  @keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  .generate-task-panel__percent {
    font-size: 20px;
    font-weight: 700;
    color: #409eff;
    font-variant-numeric: tabular-nums;
  }

  &.is-completed .generate-task-panel__percent {
    color: #67c23a;
  }

  &.is-cancelling .generate-task-panel__percent {
    color: #e6a23c;
  }

  &.is-failed .generate-task-panel__percent {
    color: #f56c6c;
  }

  &.is-stopped .generate-task-panel__percent,
  &.is-cancelled .generate-task-panel__percent {
    color: #e6a23c;
  }

  .generate-task-panel__meta {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-top: 10px;
    font-size: 13px;
    color: #606266;

    .meta-detail {
      font-size: 12px;
      color: #909399;
    }

    .failed-info {
      color: #f56c6c;
      font-weight: 500;
    }
  }

  .generate-task-panel__error {
    margin-top: 10px;
    padding: 8px 12px;
    background: #fef0f0;
    border-radius: 6px;
    font-size: 13px;
    color: #f56c6c;
    line-height: 1.5;
  }
}
</style>
