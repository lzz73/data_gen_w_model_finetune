<template>
  <div class="page-container">
    <PageHeader title="非结构化数据处理" />

    <el-row :gutter="16">
      <!-- 文档列表 -->
      <el-col :span="14">
        <div class="content-card">
          <div class="card-title">文档列表</div>
          <el-table :data="documents" stripe>
            <el-table-column prop="name" label="文档名称" />
            <el-table-column prop="pages" label="页数" width="80" />
            <el-table-column prop="chunks" label="切片数" width="80" />
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.status === '已完成' ? 'success' : row.status === '处理中' ? 'warning' : 'info'" size="small">
                  {{ row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="previewDoc = row">预览</el-button>
                <el-button link type="primary" size="small">处理</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>

      <!-- 切片参数配置 -->
      <el-col :span="10">
        <div class="content-card">
          <div class="card-title">切片参数配置</div>
          <el-form :model="splitConfig" label-width="120px" size="small">
            <el-form-item label="分割策略">
              <el-select v-model="splitConfig.strategy">
                <el-option label="递归字符分割" value="recursive" />
                <el-option label="语义嵌入分割" value="semantic_embedding" />
                <el-option label="Markdown结构分割" value="markdown_structure" />
                <el-option label="Excel结构化分割" value="excel_structured" />
              </el-select>
            </el-form-item>
            <el-form-item label="切片大小">
              <el-slider v-model="splitConfig.chunkSize" :min="200" :max="2000" :step="100" show-input />
            </el-form-item>
            <el-form-item label="重叠大小">
              <el-slider v-model="splitConfig.chunkOverlap" :min="0" :max="500" :step="10" show-input />
            </el-form-item>
            <el-form-item v-if="splitConfig.strategy === 'semantic_embedding'" label="相似度阈值">
              <el-slider v-model="splitConfig.similarityThreshold" :min="10" :max="90" :step="5" show-input />
            </el-form-item>
            <el-form-item label="页眉过滤">
              <el-switch v-model="splitConfig.filterHeader" />
            </el-form-item>
            <el-form-item label="页脚过滤">
              <el-switch v-model="splitConfig.filterFooter" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="showPreview = true">预览切片效果</el-button>
            </el-form-item>
          </el-form>
        </div>

        <!-- 切片预览 -->
        <div v-if="showPreview" class="content-card">
          <div class="card-title">切片预览（前3个）</div>
          <div v-for="(chunk, i) in previewChunks" :key="i" class="chunk-item">
            <div class="chunk-header">
              <el-tag size="small">切片 {{ i + 1 }}</el-tag>
              <span class="chunk-size">{{ chunk.length }} 字符</span>
            </div>
            <div class="chunk-text">{{ chunk }}</div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'

const showPreview = ref(false)
const previewDoc = ref(null)

const documents = [
  { name: '电力招标文件-2024.pdf', pages: 45, chunks: 38, status: '已完成' },
  { name: '合同管理办法.docx', pages: 12, chunks: 10, status: '已完成' },
  { name: '安全生产规程.pdf', pages: 68, chunks: 0, status: '待处理' },
  { name: '财务管理制度.pdf', pages: 30, chunks: 25, status: '已完成' },
  { name: '采购流程规范.docx', pages: 18, chunks: 0, status: '处理中' },
]

const splitConfig = reactive({
  strategy: 'recursive',
  chunkSize: 1000,
  chunkOverlap: 100,
  similarityThreshold: 60,
  filterHeader: true,
  filterFooter: true,
})

const previewChunks = [
  '第一条 为规范公司电力采购招标活动，保证招标过程的公开、公平、公正，根据《中华人民共和国招标投标法》及相关法律法规，结合公司实际情况，制定本办法。第二条 本办法适用于公司及所属各单位进行的电力设备、材料及服务的招标采购活动...',
  '第三条 招标分为公开招标和邀请招标两种方式。公开招标是指招标人以招标公告的方式邀请不特定的法人或者其他组织投标；邀请招标是指招标人以投标邀请书的方式邀请特定的法人或者其他组织投标...',
  '第四条 招标文件应当包括招标项目的技术要求、对投标人资格审查的标准、投标报价要求和评标标准等所有实质性要求和条件以及拟签订合同的主要条款。招标项目需要划分标段、确定工期的，招标人应当合理划分标段、确定工期...',
]
</script>

<style lang="scss" scoped>
.chunk-item {
  margin-bottom: 12px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 12px;

  .chunk-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;

    .chunk-size {
      font-size: 12px;
      color: #909399;
    }
  }

  .chunk-text {
    font-size: 13px;
    color: #606266;
    line-height: 1.6;
    max-height: 120px;
    overflow-y: auto;
  }
}
</style>
