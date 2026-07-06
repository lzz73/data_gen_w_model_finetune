import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: MainLayout,
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/Index.vue'),
        meta: { title: '首页' },
      },
      // 数据治理
      {
        path: 'data-governance/source',
        name: 'DataSource',
        component: () => import('@/views/data-governance/DataSource.vue'),
        meta: { title: '数据源接入', group: '数据治理' },
      },
      {
        path: 'data-governance/structured',
        name: 'Structured',
        component: () => import('@/views/data-governance/Structured.vue'),
        meta: { title: '结构化数据处理', group: '数据治理' },
      },
      {
        path: 'data-governance/unstructured',
        name: 'Unstructured',
        component: () => import('@/views/data-governance/Unstructured.vue'),
        meta: { title: '非结构化数据处理', group: '数据治理' },
      },
      {
        path: 'data-governance/qa-generate',
        name: 'QaGenerate',
        component: () => import('@/views/data-governance/QaGenerate.vue'),
        meta: { title: '问答对生成', group: '数据治理' },
      },
      {
        path: 'data-governance/manual-generate',
        name: 'ManualGenerate',
        component: () => import('@/views/data-governance/ManualGenerate.vue'),
        meta: { title: '人工生成', group: '数据治理' },
      },
      {
        path: 'data-governance/validate',
        name: 'DataValidate',
        component: () => import('@/views/data-governance/DataValidate.vue'),
        meta: { title: '数据质量校验', group: '数据治理' },
      },
      {
        path: 'data-governance/dataset-split',
        name: 'DatasetSplit',
        component: () => import('@/views/data-governance/DatasetSplit.vue'),
        meta: { title: '数据集划分', group: '数据治理' },
      },
      {
        path: 'data-governance/model-config',
        name: 'DataGovernanceModelConfig',
        component: () => import('@/views/data-governance/ModelConfig.vue'),
        meta: { title: '模型配置', group: '数据治理' },
      },
      // 微调训练
      {
        path: 'training/data-manager',
        name: 'DataManager',
        component: () => import('@/views/training/DataManager.vue'),
        meta: { title: '数据管理', group: '微调训练' },
      },
      {
        path: 'training/workbench',
        name: 'TrainWorkbench',
        component: () => import('@/views/training/TrainWorkbench.vue'),
        meta: { title: '训练工作台', group: '微调训练' },
      },
      {
        path: 'training/monitor',
        name: 'TrainMonitor',
        component: () => import('@/views/training/TrainMonitor.vue'),
        meta: { title: '训练监控', group: '微调训练' },
      },
      // 评估工作台
      {
        path: 'evaluation/task',
        name: 'EvaluateTask',
        component: () => import('@/views/evaluation/EvaluateTask.vue'),
        meta: { title: '评估任务', group: '评估工作台' },
      },
      {
        path: 'evaluation/report',
        name: 'EvaluateReport',
        component: () => import('@/views/evaluation/EvaluateReport.vue'),
        meta: { title: '评估报告', group: '评估工作台' },
      },
      // 模型仓库
      {
        path: 'model-repo/list',
        name: 'ModelList',
        component: () => import('@/views/model-repo/ModelList.vue'),
        meta: { title: '模型列表', group: '模型仓库' },
      },
      {
        path: 'model-repo/export',
        name: 'ModelExport',
        component: () => import('@/views/model-repo/ModelExport.vue'),
        meta: { title: '模型导出', group: '模型仓库' },
      },
      {
        path: 'model-repo/verify',
        name: 'ModelVerify',
        component: () => import('@/views/model-repo/ModelVerify.vue'),
        meta: { title: '在线验证', group: '模型仓库' },
      },
      // 实验面板
      {
        path: 'experiment/list',
        name: 'ExperimentList',
        component: () => import('@/views/experiment/ExperimentList.vue'),
        meta: { title: '实验记录', group: '实验面板' },
      },
      {
        path: 'experiment/compare',
        name: 'ExperimentCompare',
        component: () => import('@/views/experiment/ExperimentCompare.vue'),
        meta: { title: '多实验对比', group: '实验面板' },
      },
      // 系统管理
      {
        path: 'system/gpu',
        name: 'GpuDashboard',
        component: () => import('@/views/system/GpuDashboard.vue'),
        meta: { title: '硬件仪表盘', group: '系统管理' },
      },
      {
        path: 'system/log',
        name: 'LogManage',
        component: () => import('@/views/system/LogManage.vue'),
        meta: { title: '日志管理', group: '系统管理' },
      },
      {
        path: 'system/permission',
        name: 'UserPermission',
        component: () => import('@/views/system/UserPermission.vue'),
        meta: { title: '用户权限', group: '系统管理' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
