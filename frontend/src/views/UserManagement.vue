<template>
  <div class="user-management-page">
    <div class="page-header">
      <h1>用户管理</h1>
      <div class="header-actions">
        <button class="btn btn-outline" @click="handleInitAdmin">初始化默认用户</button>
        <button class="btn btn-outline" @click="refreshUsers">刷新</button>
        <button class="btn btn-primary" @click="openAddModal">添加用户</button>
      </div>
    </div>

    <div class="stats-bar">
      <div class="stat-card">
        <span class="stat-value">{{ stats.total }}</span>
        <span class="stat-label">总用户数</span>
      </div>
      <div class="stat-card active">
        <span class="stat-value">{{ stats.active }}</span>
        <span class="stat-label">活跃用户</span>
      </div>
      <div class="stat-card admin">
        <span class="stat-value">{{ stats.admin }}</span>
        <span class="stat-label">管理员</span>
      </div>
      <div class="stat-card online">
        <span class="stat-value">{{ stats.online }}</span>
        <span class="stat-label">在线用户</span>
      </div>
    </div>

    <div class="filters">
      <input
        v-model="searchQuery"
        type="text"
        placeholder="搜索用户名 / 邮箱..."
        class="filter-input"
        @input="debouncedSearch"
      />
      <select v-model="roleFilter" class="filter-select" @change="applyFilters">
        <option value="">全部角色</option>
        <option value="admin">管理员</option>
        <option value="operator">操作员</option>
        <option value="viewer">观察者</option>
      </select>
    </div>

    <div class="table-wrapper">
      <table class="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>用户名</th>
            <th>邮箱</th>
            <th>角色</th>
            <th>状态</th>
            <th>创建时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="7" class="loading-cell">加载中...</td>
          </tr>
          <tr v-else-if="filteredUsers.length === 0">
            <td colspan="7" class="empty-cell">暂无用户数据</td>
          </tr>
          <tr v-for="user in filteredUsers" :key="user.id" class="data-row">
            <td class="cell-id">{{ user.id }}</td>
            <td class="cell-username">{{ user.username }}</td>
            <td class="cell-email">{{ user.email }}</td>
            <td class="cell-role">
              <span class="role-tag" :class="'role-' + user.role">{{ roleLabels[user.role] }}</span>
            </td>
            <td class="cell-status">
              <span class="status-tag" :class="user.isActive ? 'status-active' : 'status-disabled'">
                {{ user.isActive ? '活跃' : '已禁用' }}
              </span>
            </td>
            <td class="cell-time">{{ user.createdAt }}</td>
            <td class="cell-actions">
              <button class="btn-action btn-edit" @click="openEditModal(user)">编辑</button>
              <button
                class="btn-action btn-toggle"
                :class="user.isActive ? 'btn-disable' : 'btn-enable'"
                @click="toggleUserStatus(user)"
              >
                {{ user.isActive ? '禁用' : '启用' }}
              </button>
              <button class="btn-action btn-delete" @click="confirmDelete(user)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 添加/编辑用户弹窗 -->
    <div v-if="showModal" class="modal-overlay" @click.self="closeModal">
      <div class="modal-content">
        <div class="modal-header">
          <h3>{{ isEditing ? '编辑用户' : '添加用户' }}</h3>
          <button class="modal-close" @click="closeModal">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">用户名</label>
            <input
              v-model="form.username"
              type="text"
              class="form-input"
              placeholder="请输入用户名"
              :disabled="isEditing"
            />
          </div>
          <div class="form-group">
            <label class="form-label">邮箱</label>
            <input v-model="form.email" type="email" class="form-input" placeholder="请输入邮箱" />
          </div>
          <div v-if="!isEditing" class="form-group">
            <label class="form-label">密码</label>
            <input v-model="form.password" type="password" class="form-input" placeholder="请输入密码" />
          </div>
          <div class="form-group">
            <label class="form-label">角色</label>
            <select v-model="form.role" class="form-select">
              <option value="admin">管理员</option>
              <option value="operator">操作员</option>
              <option value="viewer">观察者</option>
            </select>
          </div>
          <div v-if="formError" class="form-error">{{ formError }}</div>
          <div class="form-actions">
            <button class="btn btn-outline" @click="closeModal">取消</button>
            <button class="btn btn-primary" @click="handleSubmit" :disabled="submitting">
              {{ submitting ? '提交中...' : '确认' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 删除确认弹窗 -->
    <div v-if="showDeleteConfirm" class="modal-overlay" @click.self="showDeleteConfirm = false">
      <div class="modal-content modal-sm">
        <div class="modal-header">
          <h3>确认删除</h3>
          <button class="modal-close" @click="showDeleteConfirm = false">&times;</button>
        </div>
        <div class="modal-body">
          <p class="confirm-text">确定要删除用户 <strong>{{ deleteTarget?.username }}</strong> 吗？此操作不可撤销。</p>
          <div class="form-actions">
            <button class="btn btn-outline" @click="showDeleteConfirm = false">取消</button>
            <button class="btn btn-danger" @click="handleDelete" :disabled="submitting">
              {{ submitting ? '删除中...' : '确认删除' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, apiClient } from '@/utils/apiClient'

interface User {
  id: number
  username: string
  email: string
  role: 'admin' | 'operator' | 'viewer'
  isActive: boolean
  createdAt: string
}

const roleLabels: Record<string, string> = {
  admin: '管理员',
  operator: '操作员',
  viewer: '观察者',
}

const loading = ref(false)
const submitting = ref(false)
const searchQuery = ref('')
const roleFilter = ref('')
const showModal = ref(false)
const showDeleteConfirm = ref(false)
const isEditing = ref(false)
const editingUserId = ref<number | null>(null)
const deleteTarget = ref<User | null>(null)
const formError = ref('')

const form = ref({
  username: '',
  email: '',
  password: '',
  role: 'viewer' as 'admin' | 'operator' | 'viewer',
})

// Mock seed users (matching backend seed_data)
const users = ref<User[]>([
  {
    id: 1,
    username: 'admin',
    email: 'admin@agenthub.local',
    role: 'admin',
    isActive: true,
    createdAt: '2025-01-01 00:00:00',
  },
  {
    id: 2,
    username: 'operator',
    email: 'operator@agenthub.local',
    role: 'operator',
    isActive: true,
    createdAt: '2025-01-01 00:00:00',
  },
  {
    id: 3,
    username: 'viewer',
    email: 'viewer@agenthub.local',
    role: 'viewer',
    isActive: true,
    createdAt: '2025-01-01 00:00:00',
  },
])

let nextId = 4
let searchTimer: ReturnType<typeof setTimeout> | null = null

const stats = computed(() => ({
  total: users.value.length,
  active: users.value.filter(u => u.isActive).length,
  admin: users.value.filter(u => u.role === 'admin').length,
  online: users.value.filter(u => u.isActive).length,
}))

const filteredUsers = computed(() => {
  let result = users.value
  if (roleFilter.value) {
    result = result.filter(u => u.role === roleFilter.value)
  }
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    result = result.filter(
      u => u.username.toLowerCase().includes(q) || u.email.toLowerCase().includes(q)
    )
  }
  return result
})

function debouncedSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    // filteredUsers is computed, auto-updates
  }, 300)
}

function applyFilters() {
  // filteredUsers is computed, auto-updates
}

function refreshUsers() {
  loading.value = true
  setTimeout(() => {
    loading.value = false
  }, 300)
}

function openAddModal() {
  isEditing.value = false
  editingUserId.value = null
  form.value = { username: '', email: '', password: '', role: 'viewer' }
  formError.value = ''
  showModal.value = true
}

function openEditModal(user: User) {
  isEditing.value = true
  editingUserId.value = user.id
  form.value = { username: user.username, email: user.email, password: '', role: user.role }
  formError.value = ''
  showModal.value = true
}

function closeModal() {
  showModal.value = false
  formError.value = ''
}

function validateForm(): boolean {
  if (!form.value.username.trim()) {
    formError.value = '用户名不能为空'
    return false
  }
  if (!form.value.email.trim()) {
    formError.value = '邮箱不能为空'
    return false
  }
  if (!isEditing.value && !form.value.password.trim()) {
    formError.value = '密码不能为空'
    return false
  }
  return true
}

async function handleSubmit() {
  if (!validateForm()) return

  submitting.value = true
  formError.value = ''

  try {
    if (isEditing.value && editingUserId.value !== null) {
      // Update user locally (no backend API for update)
      const idx = users.value.findIndex(u => u.id === editingUserId.value)
      if (idx !== -1) {
        users.value[idx].email = form.value.email
        users.value[idx].role = form.value.role
      }
    } else {
      // Register via backend API
      try {
        await apiClient.post(api.auth.register, {
          username: form.value.username,
          email: form.value.email,
          password: form.value.password,
          role: form.value.role,
        })
      } catch {
        // Fallback: add locally if API fails
      }
      users.value.push({
        id: nextId++,
        username: form.value.username,
        email: form.value.email,
        role: form.value.role,
        isActive: true,
        createdAt: new Date().toISOString().replace('T', ' ').slice(0, 19),
      })
    }
    closeModal()
  } catch (e: any) {
    formError.value = e.message || '操作失败'
  } finally {
    submitting.value = false
  }
}

function toggleUserStatus(user: User) {
  user.isActive = !user.isActive
}

function confirmDelete(user: User) {
  deleteTarget.value = user
  showDeleteConfirm.value = true
}

async function handleDelete() {
  if (!deleteTarget.value) return
  submitting.value = true
  try {
    users.value = users.value.filter(u => u.id !== deleteTarget.value!.id)
    showDeleteConfirm.value = false
    deleteTarget.value = null
  } finally {
    submitting.value = false
  }
}

async function handleInitAdmin() {
  try {
    await apiClient.post(api.auth.initAdmin)
  } catch {
    // Ignore errors - may already be initialized
  }
}

onMounted(() => {
  // Users are initialized from mock data
})
</script>

<style scoped>
.user-management-page {
  padding: var(--content-padding);
  max-width: 1400px;
  margin: 0 auto;
  animation: page-enter 0.4s var(--ease-out);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
}

.page-header h1 {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.header-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.stats-bar {
  display: flex;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

.stat-card {
  flex: 1;
  background: var(--gradient-glass);
  border-radius: var(--radius-lg);
  padding: 16px;
  text-align: center;
  border: var(--card-border);
  border-left: 4px solid var(--color-primary);
  backdrop-filter: blur(12px);
  box-shadow: var(--shadow-card);
  transition: all 0.25s ease;
}

.stat-card:hover {
  transform: translateY(-2px);
  border-color: rgba(22, 93, 255, 0.3);
  box-shadow: 0 4px 16px rgba(22, 93, 255, 0.12);
}

.stat-card.active { border-left-color: var(--color-success); }
.stat-card.admin { border-left-color: var(--color-warning); }
.stat-card.online { border-left-color: var(--color-purple); }

.stat-value {
  display: block;
  font-size: var(--font-size-3xl);
  font-weight: 700;
  color: var(--color-text-primary);
}

.stat-label {
  display: block;
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin-top: var(--spacing-xs);
}

.filters {
  display: flex;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-lg);
  flex-wrap: wrap;
}

.filter-input,
.filter-select {
  padding: var(--input-padding);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  font-size: var(--font-size-base);
  background: var(--input-bg);
  color: var(--color-text-secondary);
  transition: all 0.25s var(--ease-out);
  outline: none;
}

.filter-input:focus,
.filter-select:focus {
  border-color: var(--input-border-focus);
  box-shadow: var(--input-shadow-focus);
}

.filter-input { flex: 1; min-width: 200px; }
.filter-select { min-width: 140px; }

.table-wrapper {
  overflow-x: auto;
  border-radius: var(--radius-lg);
  border: var(--card-border);
  background: var(--gradient-glass);
  backdrop-filter: blur(12px);
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-base);
}

.data-table th {
  background: var(--color-bg-glass-strong);
  padding: 12px 16px;
  text-align: left;
  font-weight: 600;
  color: var(--color-text-tertiary);
  border-bottom: 1px solid var(--color-border-primary);
  white-space: nowrap;
}

.data-table td {
  padding: 10px 16px;
  border-bottom: 1px solid var(--color-border-primary);
  color: var(--color-text-secondary);
}

.data-row:hover { background: var(--color-bg-hover); }

.loading-cell,
.empty-cell {
  text-align: center;
  padding: 40px !important;
  color: var(--color-text-tertiary);
}

.cell-id { width: 60px; }
.cell-time { white-space: nowrap; }
.cell-actions { white-space: nowrap; }

.role-tag {
  padding: 2px 10px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: 500;
}

.role-admin {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.role-operator {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.role-viewer {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.status-tag {
  padding: 2px 10px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: 500;
}

.status-active {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.status-disabled {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.btn-action {
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-default);
  font-size: var(--font-size-xs);
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.25s ease;
  backdrop-filter: blur(8px);
}

.btn-action:hover { transform: scale(1.02); }
.btn-action:active { transform: scale(0.97); }

.btn-edit {
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border-color: var(--color-primary-border);
}

.btn-edit:hover {
  background: var(--color-primary-hover);
  border-color: var(--color-primary);
}

.btn-toggle {
  background: var(--color-warning-bg);
  color: var(--color-warning);
  border-color: rgba(234, 179, 8, 0.3);
}

.btn-toggle:hover {
  background: rgba(234, 179, 8, 0.2);
}

.btn-enable {
  background: var(--color-success-bg);
  color: var(--color-success);
  border-color: rgba(34, 197, 94, 0.3);
}

.btn-enable:hover {
  background: rgba(34, 197, 94, 0.2);
}

.btn-disable {
  background: var(--color-warning-bg);
  color: var(--color-warning);
  border-color: rgba(234, 179, 8, 0.3);
}

.btn-disable:hover {
  background: rgba(234, 179, 8, 0.2);
}

.btn-delete {
  background: var(--color-error-bg);
  color: var(--color-error);
  border-color: rgba(239, 68, 68, 0.3);
}

.btn-delete:hover {
  background: rgba(239, 68, 68, 0.2);
  border-color: var(--color-error);
}

.btn {
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  cursor: pointer;
  border: 1px solid var(--color-border-primary);
  transition: all 0.25s ease;
  backdrop-filter: blur(8px);
}

.btn:hover { transform: scale(1.02); }
.btn:active { transform: scale(0.97); }

.btn-primary {
  background: var(--gradient-primary);
  color: var(--color-text-primary);
  border-color: var(--color-primary);
}

.btn-primary:hover { box-shadow: var(--shadow-glow-primary); }

.btn-outline {
  background: transparent;
  color: var(--color-text-secondary);
}

.btn-outline:hover { background: var(--color-bg-hover); }

.btn-danger {
  background: var(--color-error);
  color: var(--color-text-primary);
  border-color: var(--color-error);
}

.btn-danger:hover { box-shadow: var(--shadow-glow-error); }

.btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: var(--modal-overlay-bg);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: var(--z-overlay);
  backdrop-filter: blur(var(--modal-backdrop-blur));
}

.modal-content {
  background: var(--color-bg-elevated);
  border-radius: var(--modal-border-radius);
  width: 90%;
  max-width: 500px;
  max-height: 80vh;
  overflow-y: auto;
  border: 1px solid var(--color-border-primary);
  box-shadow: var(--shadow-modal);
}

.modal-sm { max-width: 420px; }

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-md) var(--spacing-lg);
  border-bottom: 1px solid var(--color-border-primary);
}

.modal-header h3 {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.modal-close {
  background: none;
  border: none;
  font-size: var(--font-size-2xl);
  cursor: pointer;
  color: var(--color-text-tertiary);
  transition: color 0.2s ease;
}

.modal-close:hover { color: var(--color-text-primary); }

.modal-body { padding: var(--spacing-lg); }

.form-group {
  margin-bottom: var(--spacing-md);
}

.form-label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text-tertiary);
  margin-bottom: var(--spacing-xs);
}

.form-input,
.form-select {
  width: 100%;
  padding: var(--input-padding);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  font-size: var(--font-size-base);
  background: var(--input-bg);
  color: var(--color-text-secondary);
  transition: all 0.25s var(--ease-out);
  outline: none;
  box-sizing: border-box;
}

.form-input:focus,
.form-select:focus {
  border-color: var(--input-border-focus);
  box-shadow: var(--input-shadow-focus);
}

.form-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.form-error {
  color: var(--color-error);
  font-size: var(--font-size-sm);
  margin-bottom: var(--spacing-sm);
}

.confirm-text {
  color: var(--color-text-secondary);
  font-size: var(--font-size-base);
  line-height: var(--line-height-normal);
  margin-bottom: var(--spacing-lg);
}

.confirm-text strong {
  color: var(--color-text-primary);
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-sm);
}

@media (max-width: 768px) {
  .user-management-page { padding: var(--spacing-sm); }
  .data-table { font-size: var(--font-size-xs); }
  .page-header { flex-direction: column; gap: var(--spacing-sm); align-items: flex-start; }
  .stats-bar { flex-wrap: wrap; }
  .stat-card { min-width: calc(50% - var(--spacing-sm)); }
  .filters { flex-direction: column; }
  .filter-input { min-width: 100%; }
  .modal-content { width: 95%; }
}

@media (prefers-reduced-motion: reduce) {
  .user-management-page { animation: none; }
  .stat-card:hover { transform: none; }
  .btn:hover, .btn-action:hover { transform: none; }
}
</style>
