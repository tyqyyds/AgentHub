<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const isLogin = ref(true)
const username = ref('')
const password = ref('')
const email = ref('')
const showPassword = ref(false)
const confirmPassword = ref('')
const isProd = ref(import.meta.env.PROD)

const passwordStrength = computed(() => {
  const pwd = password.value || ''
  if (!pwd) return { level: '', percent: 0, text: '' }
  let score = 0
  if (pwd.length >= 6) score += 20
  if (pwd.length >= 10) score += 20
  if (/[a-z]/.test(pwd) && /[A-Z]/.test(pwd)) score += 20
  if (/\d/.test(pwd)) score += 20
  if (/[^a-zA-Z0-9]/.test(pwd)) score += 20
  if (score <= 20) return { level: 'weak', percent: 20, text: '弱' }
  if (score <= 40) return { level: 'fair', percent: 40, text: '一般' }
  if (score <= 60) return { level: 'good', percent: 60, text: '中等' }
  if (score <= 80) return { level: 'strong', percent: 80, text: '强' }
  return { level: 'very-strong', percent: 100, text: '非常强' }
})

const handleSubmit = async () => {
  if (!username.value || !password.value) return
  if (!isLogin.value && password.value !== confirmPassword.value) {
    authStore.error = '两次输入的密码不一致'
    return
  }
  let success = false
  if (isLogin.value) {
    success = await authStore.login(username.value, password.value)
  } else {
    success = await authStore.register(username.value, password.value, email.value || undefined)
  }
  if (success) {
    router.push((route.query.redirect as string) || '/')
  }
}

const toggleMode = () => {
  isLogin.value = !isLogin.value
  authStore.error = ''
  username.value = ''
  email.value = ''
  password.value = ''
  confirmPassword.value = ''
}
</script>

<template>
  <div class="login-page">
    <div class="login-bg-glow"></div>
    <div class="login-container">
      <div class="login-card">
        <div class="login-header">
          <div class="login-logo">
            <svg viewBox="0 0 24 24" fill="currentColor" role="img" aria-label="智维 AgentHub">
              <title>智维 AgentHub</title>
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
          </div>
          <h1 class="login-title">智维 AgentHub</h1>
          <p class="login-subtitle">{{ isLogin ? '登录到系统' : '创建新账户' }}</p>
        </div>

        <form class="login-form" @submit.prevent="handleSubmit">
          <div class="form-group">
            <label class="form-label">用户名</label>
            <input
              v-model="username"
              type="text"
              class="form-input"
              placeholder="请输入用户名"
              autocomplete="username"
              required
            />
          </div>

          <div v-if="!isLogin" class="form-group">
            <label class="form-label">邮箱（可选）</label>
            <input
              v-model="email"
              type="email"
              class="form-input"
              placeholder="请输入邮箱"
              autocomplete="email"
            />
          </div>

          <div class="form-group">
            <label class="form-label">密码</label>
            <div class="password-wrapper">
              <input
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                class="form-input"
                placeholder="请输入密码"
                autocomplete="current-password"
                required
                :minlength="isLogin ? undefined : 6"
              />
              <button
                type="button"
                class="password-toggle"
                @click="showPassword = !showPassword"
                aria-label="切换密码显示"
              >
                {{ showPassword ? '隐藏' : '显示' }}
              </button>
            </div>
            <div v-if="!isLogin && password" class="password-strength">
              <div class="strength-bar">
                <div :class="['strength-fill', passwordStrength.level]" :style="{ width: passwordStrength.percent + '%' }"></div>
              </div>
              <span :class="['strength-text', passwordStrength.level]">{{ passwordStrength.text }}</span>
            </div>
          </div>

          <div v-if="!isLogin" class="form-group">
            <label class="form-label">确认密码</label>
            <input
              id="confirmPassword"
              v-model="confirmPassword"
              type="password"
              class="form-input"
              placeholder="请再次输入密码"
              required
              :minlength="6"
            />
          </div>

          <div v-if="authStore.error" class="error-message">
            {{ authStore.error }}
          </div>

          <button
            type="submit"
            class="submit-btn"
            :disabled="authStore.loading || !username || !password"
            :aria-label="isLogin ? '登录' : '注册'"
          >
            <span v-if="authStore.loading" class="btn-loading"></span>
            {{ isLogin ? '登 录' : '注 册' }}
          </button>
        </form>

        <div class="login-footer">
          <span class="footer-text">
            {{ isLogin ? '还没有账户？' : '已有账户？' }}
          </span>
          <button type="button" class="footer-link" @click="toggleMode" aria-label="切换登录注册模式">
            {{ isLogin ? '立即注册' : '返回登录' }}
          </button>
        </div>

        <div v-if="isLogin && !isProd" class="demo-accounts">
          <p class="demo-title">演示账户</p>
          <div class="demo-list">
            <button type="button" class="demo-item" aria-label="使用管理员账户" @click="username = 'admin'; password = 'Admin@2024!'">
              <span class="demo-role admin">管理员</span>
              <span class="demo-cred">admin / Admin@2024!</span>
            </button>
            <button type="button" class="demo-item" aria-label="使用操作员账户" @click="username = 'operator'; password = 'Operator@2024!'">
              <span class="demo-role operator">操作员</span>
              <span class="demo-cred">operator / Operator@2024!</span>
            </button>
            <button type="button" class="demo-item" aria-label="使用观察者账户" @click="username = 'viewer'; password = 'Viewer@2024!'">
              <span class="demo-role viewer">观察者</span>
              <span class="demo-cred">viewer / Viewer@2024!</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-primary);
  position: relative;
  overflow: hidden;
  padding: 1.25rem;
  padding-left: calc(1.25rem + env(safe-area-inset-left, 0px));
  padding-right: calc(1.25rem + env(safe-area-inset-right, 0px));
}

/* 背景装饰：主光晕 */
.login-bg-glow {
  position: absolute;
  width: 600px;
  height: 600px;
  border-radius: 50%;
  background: radial-gradient(circle, var(--color-primary-glow) 0%, transparent 70%);
  top: -200px;
  right: -200px;
  pointer-events: none;
  animation: glow-drift 8s var(--ease-in-out) infinite alternate;
}

/* 背景装饰：次光晕 */
.login-page::before {
  content: '';
  position: absolute;
  width: 500px;
  height: 500px;
  border-radius: 50%;
  background: radial-gradient(circle, var(--color-success-glow) 0%, transparent 70%);
  bottom: -180px;
  left: -150px;
  pointer-events: none;
  animation: glow-drift 10s var(--ease-in-out) infinite alternate-reverse;
}

/* 背景装饰：网格纹理 */
.login-page::after {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(var(--color-border-primary) 1px, transparent 1px),
    linear-gradient(90deg, var(--color-border-primary) 1px, transparent 1px);
  background-size: 60px 60px;
  pointer-events: none;
  mask-image: radial-gradient(ellipse at center, black 30%, transparent 80%);
  -webkit-mask-image: radial-gradient(ellipse at center, black 30%, transparent 80%);
}

@keyframes glow-drift {
  0% { transform: translate(0, 0) scale(1); }
  100% { transform: translate(30px, -20px) scale(1.1); }
}

.login-container {
  width: 100%;
  max-width: 420px;
  position: relative;
  z-index: 1;
}

/* 登录卡片：增强毛玻璃效果 */
.login-card {
  background: var(--gradient-glass-strong);
  backdrop-filter: blur(24px) saturate(1.2);
  -webkit-backdrop-filter: blur(24px) saturate(1.2);
  border: 1px solid var(--color-border-secondary);
  border-radius: var(--card-border-radius);
  padding: 40px 36px;
  box-shadow: var(--shadow-card), var(--shadow-glow-primary);
  will-change: transform, box-shadow;
  transition: box-shadow 0.4s var(--ease-out), border-color 0.4s var(--ease-out);
}

.login-card:hover {
  border-color: var(--color-border-hover);
  box-shadow: var(--shadow-card-hover), var(--shadow-glow-primary);
}

.login-header {
  text-align: center;
  margin-bottom: var(--spacing-xl);
}

/* Logo：渐变 + 发光 */
.login-logo {
  width: 56px;
  height: 56px;
  margin: 0 auto var(--spacing-md);
  background: var(--gradient-primary);
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-glow-primary);
  transition: transform 0.3s var(--ease-spring), box-shadow 0.3s var(--ease-out);
}

.login-logo:hover {
  transform: scale(1.05);
  box-shadow: var(--shadow-glow-primary);
}

.login-logo svg {
  width: 32px;
  height: 32px;
  color: var(--color-text-primary);
}

.login-title {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  margin: 0 0 var(--spacing-xs);
}

.login-subtitle {
  font-size: var(--font-size-base);
  color: var(--color-text-tertiary);
  margin: 0;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.form-label {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-form-label);
}

/* 表单输入框：使用设计系统变量 */
.form-input {
  width: 100%;
  padding: var(--input-padding);
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  color: var(--color-text-secondary);
  font-size: var(--font-size-md);
  transition: all 0.25s var(--ease-out);
  outline: none;
  box-sizing: border-box;
}

.form-input:focus {
  border-color: var(--input-border-focus);
  box-shadow: var(--input-shadow-focus);
  background: var(--color-bg-primary);
}

.form-input::placeholder {
  color: var(--color-text-disabled);
}

.form-input:hover:not(:focus) {
  border-color: var(--color-border-hover);
}

.password-wrapper {
  position: relative;
}

.password-wrapper .form-input {
  padding-right: 60px;
}

.password-toggle {
  position: absolute;
  right: 0.75rem;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  padding: var(--spacing-xs) var(--spacing-sm);
  min-height: auto;
  transition: color 0.2s var(--ease-out);
}

.password-toggle:hover {
  color: var(--color-text-secondary);
}

/* 密码强度指示器：增强样式 */
.password-strength {
  margin-top: 0.375rem;
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.strength-bar {
  flex: 1;
  height: 4px;
  background: var(--color-bg-quaternary);
  border-radius: var(--radius-xs);
  overflow: hidden;
}

.strength-fill {
  height: 100%;
  border-radius: var(--radius-xs);
  transition: width 0.4s var(--ease-spring), background 0.3s var(--ease-out);
  position: relative;
}

.strength-fill.weak { background: var(--color-error); box-shadow: 0 0 6px var(--color-error-glow); }
.strength-fill.fair { background: var(--color-orange); box-shadow: var(--shadow-glow-warning); }
.strength-fill.good { background: var(--color-warning); box-shadow: 0 0 6px var(--color-warning-glow); }
.strength-fill.strong { background: var(--color-success); box-shadow: 0 0 6px var(--color-success-glow); }
.strength-fill.very-strong { background: var(--color-primary-light); box-shadow: 0 0 6px var(--color-primary-glow); }

.strength-text {
  font-size: var(--font-size-xs);
  min-width: 50px;
  font-weight: var(--font-weight-medium);
  transition: color 0.3s var(--ease-out);
}

.strength-text.weak { color: var(--color-error); }
.strength-text.fair { color: var(--color-orange); }
.strength-text.good { color: var(--color-warning); }
.strength-text.strong { color: var(--color-success); }
.strength-text.very-strong { color: var(--color-primary-light); }

/* 错误消息：增强样式 */
.error-message {
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-radius: var(--radius-md);
  padding: 10px 14px;
  color: var(--color-error-light);
  font-size: var(--font-size-base);
  animation: error-shake 0.4s var(--ease-out);
  box-shadow: var(--shadow-glow-error);
  position: relative;
  padding-left: 2.25rem;
}

.error-message::before {
  content: '⚠';
  position: absolute;
  left: 0.75rem;
  top: 50%;
  transform: translateY(-50%);
  font-size: var(--font-size-base);
}

@keyframes error-shake {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(-4px); }
  40% { transform: translateX(4px); }
  60% { transform: translateX(-2px); }
  80% { transform: translateX(2px); }
}

/* 提交按钮：渐变 + 发光 */
.submit-btn {
  width: 100%;
  padding: 14px;
  background: var(--gradient-primary);
  border: none;
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
  transition: var(--button-transition);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  min-height: var(--button-height-lg);
  box-shadow: var(--shadow-glow-primary);
  position: relative;
  overflow: hidden;
}

.submit-btn::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, var(--color-primary-bg) 0%, transparent 50%);
  opacity: 0;
  transition: opacity 0.3s var(--ease-out);
}

.submit-btn:hover:not(:disabled) {
  background: var(--gradient-primary-hover);
  transform: translateY(-1px);
  box-shadow: var(--shadow-glow-primary);
}

.submit-btn:hover:not(:disabled)::after {
  opacity: 1;
}

.submit-btn:active:not(:disabled) {
  transform: translateY(0) scale(0.98);
  box-shadow: var(--shadow-glow-primary);
}

.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-loading {
  width: 18px;
  height: 18px;
  border: 2px solid var(--color-border-primary);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

.login-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-lg);
}

.footer-text {
  font-size: var(--font-size-base);
  color: var(--color-text-tertiary);
}

.footer-link {
  background: none;
  border: none;
  color: var(--color-primary-light);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  min-height: auto;
  padding: 0;
  transition: color 0.2s var(--ease-out);
  position: relative;
}

.footer-link::after {
  content: '';
  position: absolute;
  bottom: -2px;
  left: 0;
  width: 0;
  height: 1px;
  background: var(--color-primary-light);
  transition: width 0.3s var(--ease-out);
}

.footer-link:hover {
  color: var(--color-primary-light);
}

.footer-link:hover::after {
  width: 100%;
}

/* 演示账户区域：增强样式 */
.demo-accounts {
  margin-top: var(--spacing-lg);
  padding-top: 1.25rem;
  border-top: 1px solid var(--color-border-primary);
}

.demo-title {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin: 0 0 10px;
  text-align: center;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.demo-list {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.demo-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: var(--spacing-sm) 0.75rem;
  background: var(--color-bg-hover);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.25s var(--ease-out);
  min-height: auto;
  width: 100%;
}

.demo-item:hover {
  background: var(--color-bg-active);
  border-color: var(--color-border-hover);
  transform: translateX(4px);
  box-shadow: var(--shadow-sm);
}

.demo-role {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-xs);
  flex-shrink: 0;
  border: 1px solid transparent;
}

.demo-role.admin {
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  border-color: var(--color-primary-border);
}

.demo-role.operator {
  background: var(--color-success-bg);
  color: var(--color-success);
  border-color: var(--color-success-border);
}

.demo-role.viewer {
  background: var(--color-bg-glass);
  color: var(--color-text-tertiary);
  border-color: var(--color-border-primary);
}

.demo-cred {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  font-family: var(--font-family-mono);
}

@media (max-width: 768px) {
  .login-card {
    padding: var(--spacing-xl) var(--spacing-lg);
  }

  .login-title {
    font-size: var(--font-size-xl);
  }

  .login-bg-glow {
    width: 400px;
    height: 400px;
  }

  .form-input {
    font-size: var(--font-size-md);
  }

  .password-toggle {
    min-height: var(--button-min-height-touch);
    min-width: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .footer-link {
    min-height: var(--button-min-height-touch);
    padding: var(--spacing-sm) 0.75rem;
  }

  .demo-item {
    min-height: var(--button-min-height-touch);
  }
}

@media (max-width: 480px) {
  .login-card {
    padding: 28px 1.25rem;
  }

  .login-title {
    font-size: var(--font-size-xl);
  }

  .login-bg-glow {
    width: 300px;
    height: 300px;
  }

  .demo-list {
    gap: var(--spacing-xs);
  }

  .demo-item {
    padding: 0.375rem 10px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .submit-btn:hover:not(:disabled) {
    transform: none;
  }

  .btn-loading {
    animation: none;
  }

  .login-bg-glow {
    animation: none;
  }

  .login-page::before {
    animation: none;
  }

  .error-message {
    animation: none;
  }

  .demo-item:hover {
    transform: none;
  }

  .login-logo:hover {
    transform: none;
  }
}
</style>
