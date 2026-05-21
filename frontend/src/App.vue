<script setup lang="ts">
import { ref } from 'vue'
import router from './router'

const activeMenu = ref('Dashboard')

const menuItems = [
  { name: 'Dashboard', icon: '🖥️', path: '/' },
  { name: 'IntentCenter', icon: '🎯', path: '/intent' },
  { name: 'Topology', icon: '🔗', path: '/topology' },
  { name: 'SelfHealing', icon: '🛡️', path: '/self-healing' },
  { name: 'AuditLogs', icon: '📋', path: '/audit' }
]

const handleMenuClick = (name: string, path: string) => {
  activeMenu.value = name
  router.push(path)
}
</script>

<template>
  <div class="app-container">
    <aside class="sidebar">
      <div class="logo">
        <div class="logo-icon">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
          </svg>
        </div>
        <span class="logo-text">智维 AgentHub</span>
      </div>
      <nav class="menu">
        <button
          v-for="item in menuItems"
          :key="item.name"
          :class="['menu-item', { active: activeMenu === item.name }]"
          @click="handleMenuClick(item.name, item.path)"
        >
          <span class="menu-icon">{{ item.icon }}</span>
          <span class="menu-text">{{ item.name }}</span>
        </button>
      </nav>
    </aside>
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
  min-height: 100vh;
}

.app-container {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: 260px;
  background: rgba(30, 41, 59, 0.8);
  backdrop-filter: blur(12px);
  border-right: 1px solid rgba(255, 255, 255, 0.1);
  padding: 24px 0;
  display: flex;
  flex-direction: column;
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 24px 32px;
}

.logo-icon {
  width: 40px;
  height: 40px;
  background: linear-gradient(135deg, #165DFF 0%, #69B1FF 100%);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}

.logo-icon svg {
  width: 24px;
  height: 24px;
}

.logo-text {
  font-size: 18px;
  font-weight: 700;
  color: white;
}

.menu {
  flex: 1;
  padding: 0 12px;
}

.menu-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  margin-bottom: 4px;
  border: none;
  background: transparent;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.3s ease;
  color: #94A3B8;
}

.menu-item:hover {
  background: rgba(22, 93, 255, 0.1);
  color: #E2E8F0;
}

.menu-item.active {
  background: linear-gradient(135deg, rgba(22, 93, 255, 0.2) 0%, rgba(105, 177, 255, 0.1) 100%);
  color: white;
}

.menu-icon {
  font-size: 18px;
}

.menu-text {
  font-size: 14px;
  font-weight: 500;
}

.main-content {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
}
</style>