<script setup lang="ts">
import { ref, onMounted } from 'vue'

interface UserItem {
  id: number
  username: string
  displayName: string
  role: 'admin' | 'operator' | 'viewer'
  email: string
  isActive: boolean
  lastLogin: string
  createdAt: string
}

const loading = ref(false)
const users = ref<UserItem[]>([
  { id: 1, username: 'admin', displayName: '系统管理员', role: 'admin', email: 'admin@agenthub.local', isActive: true, lastLogin: '2026-06-13 10:30', createdAt: '2026-01-01' },
  { id: 2, username: 'operator01', displayName: '张运维', role: 'operator', email: 'zhangyw@agenthub.local', isActive: true, lastLogin: '2026-06-13 09:15', createdAt: '2026-02-15' },
  { id: 3, username: 'operator02', displayName: '李安全', role: 'operator', email: 'liaq@agenthub.local', isActive: true, lastLogin: '2026-06-12 18:00', createdAt: '2026-03-01' },
  { id: 4, username: 'viewer01', displayName: '王观察', role: 'viewer', email: 'wanggc@agenthub.local', isActive: true, lastLogin: '2026-06-13 08:45', createdAt: '2026-04-10' },
  { id: 5, username: 'viewer02', displayName: '赵审计', role: 'viewer', email: 'zhaosj@agenthub.local', isActive: false, lastLogin: '2026-05-20 14:30', createdAt: '2026-03-20' }
])

const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const newUser = ref({ username: '', displayName: '', email: '', role: 'viewer' as string, password: '' })
const editingUser = ref<UserItem | null>(null)
const editRole = ref('')

function getRoleLabel(r: string) {
  return r === 'admin' ? '管理员' : r === 'operator' ? '操作员' : '观察者'
}

function toggleUserStatus(user: UserItem) {
  user.isActive = !user.isActive
}

function openEditDialog(user: UserItem) {
  editingUser.value = user
  editRole.value = user.role
  showEditDialog.value = true
}

function saveRole() {
  if (editingUser.value) {
    editingUser.value.role = editRole.value as UserItem['role']
  }
  showEditDialog.value = false
}

function createUser() {
  if (!newUser.value.username.trim() || !newUser.value.password.trim()) return
  users.value.push({
    id: users.value.length + 1,
    username: newUser.value.username,
    displayName: newUser.value.displayName || newUser.value.username,
    email: newUser.value.email,
    role: newUser.value.role as UserItem['role'],
    isActive: true,
    lastLogin: '从未登录',
    createdAt: new Date().toISOString().slice(0, 10)
  })
  newUser.value = { username: '', displayName: '', email: '', role: 'viewer', password: '' }
  showCreateDialog.value = false
}

onMounted(() => {
  // TODO: 调用API获取用户列表
})
</script>

<template>
  <div class="user-management">
    <h1 class="page-title">用户管理</h1>

    <div class="toolbar">
      <div class="stats-row">
        <div class="stat-chip admin">管理员 {{ users.filter(u => u.role === 'admin').length }}</div>
        <div class="stat-chip operator">操作员 {{ users.filter(u => u.role === 'operator').length }}</div>
        <div class="stat-chip viewer">观察者 {{ users.filter(u => u.role === 'viewer').length }}</div>
      </div>
      <button class="action-btn" @click="showCreateDialog = true">+ 创建用户</button>
    </div>

    <div class="user-table">
      <div class="table-header">
        <div class="col id-col">ID</div>
        <div class="col user-col">用户名</div>
        <div class="col name-col">显示名</div>
        <div class="col role-col">角色</div>
        <div class="col email-col">邮箱</div>
        <div class="col status-col">状态</div>
        <div class="col login-col">最后登录</div>
        <div class="col actions-col">操作</div>
      </div>
      <div v-for="user in users" :key="user.id" class="table-row">
        <div class="col id-col">{{ user.id }}</div>
        <div class="col user-col">{{ user.username }}</div>
        <div class="col name-col">{{ user.displayName }}</div>
        <div class="col role-col">
          <span :class="['role-tag', `role-${user.role}`]">{{ getRoleLabel(user.role) }}</span>
        </div>
        <div class="col email-col">{{ user.email }}</div>
        <div class="col status-col">
          <span :class="['status-badge', user.isActive ? 'active' : 'inactive']">{{ user.isActive ? '活跃' : '禁用' }}</span>
        </div>
        <div class="col login-col">{{ user.lastLogin }}</div>
        <div class="col actions-col">
          <button class="btn-sm" @click="openEditDialog(user)">角色</button>
          <button :class="['btn-sm', user.isActive ? 'danger' : 'success']" @click="toggleUserStatus(user)">{{ user.isActive ? '禁用' : '启用' }}</button>
        </div>
      </div>
    </div>

    <!-- 创建用户对话框 -->
    <div v-if="showCreateDialog" class="dialog-overlay" @click.self="showCreateDialog = false">
      <div class="dialog-box">
        <h3 class="dialog-title">创建用户</h3>
        <div class="form-group">
          <label>用户名</label>
          <input v-model="newUser.username" class="form-input" placeholder="输入用户名" />
        </div>
        <div class="form-group">
          <label>显示名</label>
          <input v-model="newUser.displayName" class="form-input" placeholder="输入显示名" />
        </div>
        <div class="form-group">
          <label>邮箱</label>
          <input v-model="newUser.email" class="form-input" placeholder="输入邮箱" />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input v-model="newUser.password" type="password" class="form-input" placeholder="输入初始密码" />
        </div>
        <div class="form-group">
          <label>角色</label>
          <select v-model="newUser.role" class="form-input">
            <option value="viewer">观察者</option>
            <option value="operator">操作员</option>
            <option value="admin">管理员</option>
          </select>
        </div>
        <div class="dialog-actions">
          <button class="btn-sm" @click="showCreateDialog = false">取消</button>
          <button class="action-btn" @click="createUser">创建</button>
        </div>
      </div>
    </div>

    <!-- 编辑角色对话框 -->
    <div v-if="showEditDialog && editingUser" class="dialog-overlay" @click.self="showEditDialog = false">
      <div class="dialog-box">
        <h3 class="dialog-title">修改角色 - {{ editingUser.displayName }}</h3>
        <div class="form-group">
          <label>当前角色: {{ getRoleLabel(editingUser.role) }}</label>
        </div>
        <div class="form-group">
          <label>新角色</label>
          <select v-model="editRole" class="form-input">
            <option value="viewer">观察者</option>
            <option value="operator">操作员</option>
            <option value="admin">管理员</option>
          </select>
        </div>
        <div class="role-warning" v-if="editRole === 'admin'">
          ⚠️ 管理员拥有系统全部权限，包括用户管理、系统配置等敏感操作
        </div>
        <div class="dialog-actions">
          <button class="btn-sm" @click="showEditDialog = false">取消</button>
          <button class="action-btn" @click="saveRole">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-title { font-size: var(--font-size-3xl); font-weight: var(--font-weight-bold); color: var(--color-white); margin-bottom: var(--spacing-2xl); }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-2xl); }
.stats-row { display: flex; gap: var(--spacing-md); }
.stat-chip { font-size: var(--font-size-sm); padding: var(--spacing-xs) var(--spacing-md-lg); border-radius: var(--radius-full); font-weight: var(--font-weight-medium); }
.stat-chip.admin { background: rgba(var(--color-purple-rgb), 0.2); color: var(--color-purple); }
.stat-chip.operator { background: rgba(var(--color-info-light-rgb), 0.2); color: var(--color-info-light); }
.stat-chip.viewer { background: rgba(var(--color-text-tertiary-rgb), 0.2); color: var(--color-text-tertiary); }

.action-btn { padding: var(--spacing-sm-md) var(--spacing-xl); background: var(--gradient-primary); color: var(--color-white); border: none; border-radius: var(--radius-lg); font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); cursor: pointer; }

.user-table { background: rgba(var(--color-bg-elevated-rgb), 0.6); border-radius: var(--radius-2xl); border: 1px solid rgba(var(--color-white-rgb), 0.1); overflow: hidden; }
.table-header { display: flex; padding: var(--spacing-md-lg) var(--spacing-xl); background: rgba(var(--color-bg-base-rgb), 0.5); font-size: var(--font-size-sm); color: var(--color-text-quaternary); font-weight: var(--font-weight-semibold); text-transform: uppercase; letter-spacing: 0.5px; }
.table-row { display: flex; padding: var(--spacing-md-lg) var(--spacing-xl); border-top: 1px solid rgba(var(--color-white-rgb), 0.05); align-items: center; transition: background var(--duration-normal); }
.table-row:hover { background: rgba(var(--color-primary-rgb), 0.05); }

.col { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
.id-col { width: 50px; color: var(--color-text-quaternary); }
.user-col { width: 120px; font-weight: var(--font-weight-medium); font-family: var(--font-family-mono); }
.name-col { width: 120px; }
.role-col { width: 90px; }
.email-col { width: 200px; color: var(--color-text-tertiary); font-size: var(--font-size-sm); }
.status-col { width: 70px; }
.login-col { width: 140px; color: var(--color-text-quaternary); font-size: var(--font-size-sm); }
.actions-col { width: 140px; display: flex; gap: var(--spacing-xs); }

.role-tag { font-size: var(--font-size-xs); padding: var(--spacing-2xs) var(--spacing-sm); border-radius: var(--radius-lg); font-weight: var(--font-weight-medium); }
.role-tag.role-admin { color: var(--color-purple); background: rgba(var(--color-purple-rgb), 0.2); }
.role-tag.role-operator { color: var(--color-info-light); background: rgba(var(--color-info-light-rgb), 0.2); }
.role-tag.role-viewer { color: var(--color-text-tertiary); background: rgba(var(--color-text-tertiary-rgb), 0.2); }

.status-badge { font-size: var(--font-size-xs); padding: var(--spacing-2xs) var(--spacing-sm); border-radius: var(--radius-lg); font-weight: var(--font-weight-medium); }
.status-badge.active { background: rgba(var(--color-success-rgb), 0.2); color: var(--color-success); }
.status-badge.inactive { background: rgba(var(--color-error-rgb), 0.2); color: var(--color-error); }

.btn-sm { padding: 5px var(--spacing-md); background: rgba(var(--color-primary-rgb), 0.2); color: var(--color-info-light); border: 1px solid rgba(var(--color-primary-rgb), 0.3); border-radius: var(--radius-md); font-size: var(--font-size-sm); cursor: pointer; }
.btn-sm.danger { background: rgba(var(--color-error-rgb), 0.2); color: var(--color-error); border-color: rgba(var(--color-error-rgb), 0.3); }
.btn-sm.success { background: rgba(var(--color-success-rgb), 0.2); color: var(--color-success); border-color: rgba(var(--color-success-rgb), 0.3); }

.dialog-overlay { position: fixed; inset: 0; background: rgba(var(--color-black-rgb), 0.6); display: flex; align-items: center; justify-content: center; z-index: var(--z-modal); }
.dialog-box { background: var(--color-bg-container); border-radius: var(--radius-2xl); padding: 28px; width: 440px; border: 1px solid rgba(var(--color-white-rgb), 0.1); }
.dialog-title { font-size: var(--font-size-xl); font-weight: var(--font-weight-semibold); color: var(--color-white); margin-bottom: var(--spacing-xl); }
.form-group { margin-bottom: var(--spacing-lg); }
.form-group label { display: block; font-size: var(--font-size-sm); color: var(--color-text-tertiary); margin-bottom: var(--spacing-xs); }
.form-input { width: 100%; padding: var(--spacing-sm-md) var(--spacing-md-lg); background: rgba(var(--color-bg-base-rgb), 0.5); border: 1px solid rgba(var(--color-white-rgb), 0.1); border-radius: var(--radius-lg); color: var(--color-white); font-size: var(--font-size-base); }
.form-input:focus { outline: none; border-color: var(--color-primary); }
.role-warning { font-size: var(--font-size-sm); color: var(--color-warning); background: rgba(var(--color-warning-rgb), 0.1); padding: var(--spacing-sm-md) var(--spacing-md-lg); border-radius: var(--radius-lg); margin-bottom: var(--spacing-md); border: 1px solid rgba(var(--color-warning-rgb), 0.2); }
.dialog-actions { display: flex; justify-content: flex-end; gap: var(--spacing-sm); margin-top: var(--spacing-xl); }
</style>
