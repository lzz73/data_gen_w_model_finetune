<template>
  <div class="page-container">
    <PageHeader title="用户权限">
      <el-button type="primary" @click="showAddDialog = true">
        <el-icon><Plus /></el-icon>添加用户
      </el-button>
    </PageHeader>

    <div class="content-card">
      <el-table :data="users" stripe>
        <el-table-column prop="name" label="用户名" width="120" />
        <el-table-column prop="email" label="邮箱" width="200" />
        <el-table-column prop="role" label="角色" width="120">
          <template #default="{ row }">
            <el-tag :type="row.role === '管理员' ? 'danger' : ''" size="small">{{ row.role }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === '启用' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="lastLogin" label="最后登录" width="180" />
        <el-table-column prop="created" label="创建时间" width="180" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="editUser(row)">编辑</el-button>
            <el-button link :type="row.status === '启用' ? 'warning' : 'success'" size="small">
              {{ row.status === '启用' ? '禁用' : '启用' }}
            </el-button>
            <el-button v-if="row.role !== '管理员'" link type="danger" size="small">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 添加/编辑用户对话框 -->
    <el-dialog v-model="showAddDialog" :title="editingUser ? '编辑用户' : '添加用户'" width="450px">
      <el-form :model="userForm" label-width="80px">
        <el-form-item label="用户名">
          <el-input v-model="userForm.name" :disabled="!!editingUser" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="userForm.email" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="userForm.role">
            <el-option label="管理员" value="管理员" />
            <el-option label="普通用户" value="普通用户" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="showAddDialog = false">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'

const showAddDialog = ref(false)
const editingUser = ref(null)

const userForm = reactive({ name: '', email: '', role: '普通用户' })

const users = [
  { name: 'admin', email: 'admin@ygsoft.com', role: '管理员', status: '启用', lastLogin: '2026-07-01 09:00', created: '2026-01-01' },
  { name: 'zhangsan', email: 'zhangsan@ygsoft.com', role: '普通用户', status: '启用', lastLogin: '2026-06-30 14:00', created: '2026-03-15' },
  { name: 'lisi', email: 'lisi@ygsoft.com', role: '普通用户', status: '启用', lastLogin: '2026-06-29 10:00', created: '2026-04-20' },
  { name: 'wangwu', email: 'wangwu@ygsoft.com', role: '普通用户', status: '禁用', lastLogin: '2026-05-10 16:00', created: '2026-02-28' },
]

const editUser = (row: any) => {
  editingUser.value = row
  userForm.name = row.name
  userForm.email = row.email
  userForm.role = row.role
  showAddDialog.value = true
}
</script>
