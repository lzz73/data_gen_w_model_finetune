<template>
  <el-container class="main-layout">
    <!-- 侧边栏 -->
    <el-aside :width="isCollapsed ? '64px' : '220px'" class="sidebar">
      <div class="logo-area">
        <el-icon class="logo-icon" :size="24"><Cpu /></el-icon>
        <span v-show="!isCollapsed" class="logo-text">远光微调平台</span>
      </div>

      <!-- 当前项目指示器 -->
      <div v-if="projectStore.hasProject && !isCollapsed" class="project-indicator" @click="$router.push('/')">
        <el-icon :size="14" color="#67c23a"><CircleCheckFilled /></el-icon>
        <span class="project-indicator-text">{{ projectStore.currentProject?.name }}</span>
        <el-icon :size="12" color="#bfcbd9"><Switch /></el-icon>
      </div>
      <div v-if="projectStore.hasProject && isCollapsed" class="project-indicator-dot" @click="$router.push('/')">
        <el-tooltip content="点击切换项目" placement="right">
          <el-icon :size="14" color="#67c23a"><CircleCheckFilled /></el-icon>
        </el-tooltip>
      </div>

      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapsed"
        :collapse-transition="false"
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409eff"
        router
      >
        <!-- 首页 -->
        <el-menu-item index="/">
          <el-icon><HomeFilled /></el-icon>
          <template #title>首页</template>
        </el-menu-item>

        <!-- 数据治理 -->
        <el-sub-menu index="data-governance">
          <template #title>
            <el-icon><DataAnalysis /></el-icon>
            <span>数据治理</span>
          </template>
          <el-menu-item index="/data-governance/source">数据源接入</el-menu-item>
          <el-menu-item index="/data-governance/structured">结构化数据处理</el-menu-item>
          <el-menu-item index="/data-governance/unstructured">非结构化数据处理</el-menu-item>
          <el-menu-item index="/data-governance/qa-generate">问答对生成</el-menu-item>
          <el-menu-item index="/data-governance/manual-generate">人工生成</el-menu-item>
          <el-menu-item index="/data-governance/validate">数据质量校验</el-menu-item>
          <el-menu-item index="/data-governance/dataset-split">数据集划分</el-menu-item>
          <el-menu-item index="/data-governance/model-config">模型配置</el-menu-item>
        </el-sub-menu>

        <!-- 微调训练 -->
        <el-sub-menu index="training">
          <template #title>
            <el-icon><Cpu /></el-icon>
            <span>微调训练</span>
          </template>
          <el-menu-item index="/training/data-manager">数据管理</el-menu-item>
          <el-menu-item index="/training/workbench">训练工作台</el-menu-item>
          <el-menu-item index="/training/monitor">训练监控</el-menu-item>
        </el-sub-menu>

        <!-- 模型仓库 -->
        <el-sub-menu index="model-repo">
          <template #title>
            <el-icon><Box /></el-icon>
            <span>模型仓库</span>
          </template>
          <el-menu-item index="/model-repo/export">模型导出</el-menu-item>
          <el-menu-item index="/model-repo/list">模型配置</el-menu-item>
          <el-menu-item index="/model-repo/verify">在线验证</el-menu-item>
        </el-sub-menu>

        <!-- 评估工作台 -->
        <el-sub-menu index="evaluation">
          <template #title>
            <el-icon><DataLine /></el-icon>
            <span>评估工作台</span>
          </template>
          <el-menu-item index="/evaluation/task">评估任务</el-menu-item>
          <el-menu-item index="/evaluation/report">评估报告</el-menu-item>
        </el-sub-menu>

        <!-- 实验面板 -->
        <el-sub-menu index="experiment">
          <template #title>
            <el-icon><TrendCharts /></el-icon>
            <span>实验面板</span>
          </template>
          <el-menu-item index="/experiment/list">实验记录</el-menu-item>
          <el-menu-item index="/experiment/compare">多实验对比</el-menu-item>
        </el-sub-menu>

        <!-- 系统管理 -->
        <el-sub-menu index="system">
          <template #title>
            <el-icon><Setting /></el-icon>
            <span>系统管理</span>
          </template>
          <el-menu-item index="/system/gpu">硬件仪表盘</el-menu-item>
          <el-menu-item index="/system/log">日志管理</el-menu-item>
          <el-menu-item index="/system/permission">用户权限</el-menu-item>
        </el-sub-menu>
      </el-menu>
    </el-aside>

    <!-- 右侧 -->
    <el-container class="main-container">
      <!-- 顶部栏 -->
      <el-header class="header">
        <div class="header-left">
          <el-icon class="collapse-btn" @click="toggleCollapse">
            <Fold v-if="!isCollapsed" />
            <Expand v-else />
          </el-icon>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item v-for="item in breadcrumbs" :key="item.path">
              {{ item.title }}
            </el-breadcrumb-item>
          </el-breadcrumb>
          <!-- 顶栏当前项目标签 -->
          <el-tag
            v-if="projectStore.hasProject && route.path !== '/'"
            type="primary"
            size="small"
            effect="plain"
            class="header-project-tag"
            @click="$router.push('/')"
          >
            <el-icon :size="12"><FolderOpened /></el-icon>
            {{ projectStore.currentProject?.name }}
          </el-tag>
        </div>
        <div class="header-right">
          <el-dropdown>
            <span class="user-info">
              <el-avatar :size="32" icon="UserFilled" />
              <span class="username">管理员</span>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item>个人设置</el-dropdown-item>
                <el-dropdown-item divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- 内容区 -->
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore } from '@/stores/project'

const route = useRoute()
const projectStore = useProjectStore()
const isCollapsed = ref(false)

const activeMenu = computed(() => route.path)

const breadcrumbs = computed(() => {
  const matched = route.matched.filter(item => item.meta?.title)
  const crumbs: { path: string; title: string }[] = [{ path: '/', title: '首页' }]
  matched.forEach(item => {
    if (item.meta?.title) {
      crumbs.push({ path: item.path, title: item.meta.title as string })
    }
  })
  return crumbs
})

const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
}

// 启动时恢复上次选中的项目
onMounted(async () => {
  const savedId = localStorage.getItem('currentProjectId')
  if (savedId && !projectStore.currentProject) {
    try {
      await projectStore.setCurrentProject(savedId)
    } catch {
      projectStore.clearCurrentProject()
    }
  }
  // 同时加载项目列表
  if (projectStore.projects.length === 0) {
    projectStore.fetchProjects()
  }
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables' as *;

.main-layout {
  height: 100vh;
  overflow: hidden;
}

.sidebar {
  background: $sidebar-bg;
  transition: width 0.3s;
  overflow-x: hidden;
  overflow-y: auto;

  &::-webkit-scrollbar {
    width: 0;
  }

  .logo-area {
    height: $header-height;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);

    .logo-icon {
      width: 28px;
      height: 28px;
      flex-shrink: 0;
    }

    .logo-text {
      color: #fff;
      font-size: 16px;
      font-weight: 600;
      margin-left: 10px;
      white-space: nowrap;
    }
  }

  .project-indicator {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 10px 16px;
    background: rgba(103, 194, 58, 0.1);
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    cursor: pointer;
    transition: background 0.3s;

    &:hover {
      background: rgba(103, 194, 58, 0.2);
    }

    .project-indicator-text {
      flex: 1;
      font-size: 13px;
      color: #e0e0e0;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
  }

  .project-indicator-dot {
    display: flex;
    justify-content: center;
    padding: 10px 0;
    cursor: pointer;
  }

  :deep(.el-menu) {
    border-right: none;
  }
}

.main-container {
  flex-direction: column;
  overflow: hidden;
}

.header {
  height: $header-height;
  background: $header-bg;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  z-index: 10;

  .header-left {
    display: flex;
    align-items: center;
    gap: 16px;

    .collapse-btn {
      font-size: 20px;
      cursor: pointer;
      color: #606266;
      transition: color 0.3s;

      &:hover {
        color: $primary-color;
      }
    }

    .header-project-tag {
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 4px;
    }
  }

  .header-right {
    .user-info {
      display: flex;
      align-items: center;
      gap: 8px;
      cursor: pointer;

      .username {
        font-size: 14px;
        color: #606266;
      }
    }
  }
}

.main-content {
  background: $content-bg;
  overflow-y: auto;
  padding: $content-padding;
}
</style>
