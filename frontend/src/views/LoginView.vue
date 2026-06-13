<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const loading = ref(false)
const errorMsg = ref('')

async function handleLogin() {
  if (!username.value || !password.value) {
    errorMsg.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    await authStore.login(username.value, password.value)
    router.push('/')
  } catch {
    errorMsg.value = authStore.error || '登录失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <div class="login-logo">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
          </svg>
        </div>
        <h1>智维 AgentHub</h1>
        <p>智能运维管理平台</p>
      </div>
      <form class="login-form" @submit.prevent="handleLogin">
        <div class="form-group">
          <label>用户名</label>
          <input
            v-model="username"
            type="text"
            placeholder="请输入用户名"
            autocomplete="username"
            :disabled="loading"
          />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input
            v-model="password"
            type="password"
            placeholder="请输入密码"
            autocomplete="current-password"
            :disabled="loading"
          />
        </div>
        <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>
        <button type="submit" class="login-btn" :disabled="loading">
          {{ loading ? '登录中...' : '登 录' }}
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--gradient-dark);
}

.login-card {
  width: 400px;
  background: rgba(var(--color-bg-container-rgb), 0.9);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  border-radius: var(--radius-2xl);
  padding: var(--spacing-5xl) var(--spacing-4xl);
}

.login-header {
  text-align: center;
  margin-bottom: var(--spacing-4xl);
}

.login-logo {
  width: 56px;
  height: 56px;
  margin: 0 auto var(--spacing-lg);
  background: var(--gradient-primary);
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-white);
}

.login-logo svg {
  width: 32px;
  height: 32px;
}

.login-header h1 {
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-white);
  margin-bottom: var(--spacing-2xs);
}

.login-header p {
  font-size: var(--font-size-base);
  color: var(--color-text-tertiary);
}

.form-group {
  margin-bottom: var(--spacing-xl);
}

.form-group label {
  display: block;
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-sm);
}

.form-group input {
  width: 100%;
  padding: var(--spacing-md) var(--spacing-lg);
  background: rgba(var(--color-bg-base-rgb), 0.6);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  border-radius: var(--radius-md);
  color: var(--color-white);
  font-size: var(--font-size-base);
  outline: none;
  transition: border-color 0.3s;
}

.form-group input::placeholder {
  color: var(--color-text-quaternary);
}

.form-group input:focus {
  border-color: var(--color-primary);
}

.form-group input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.error-msg {
  color: var(--color-error-light);
  font-size: var(--font-size-sm);
  margin-bottom: var(--spacing-lg);
}

.login-btn {
  width: 100%;
  padding: var(--spacing-md);
  background: var(--gradient-primary);
  border: none;
  border-radius: var(--radius-md);
  color: var(--color-white);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
  transition: opacity 0.3s;
}

.login-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.login-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
