import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '@/views/Dashboard.vue'
import IntentCenter from '@/views/IntentCenter.vue'
import Topology from '@/views/Topology.vue'
import SelfHealing from '@/views/SelfHealing.vue'
import AuditLogs from '@/views/AuditLogs.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'Dashboard',
      component: Dashboard
    },
    {
      path: '/intent',
      name: 'IntentCenter',
      component: IntentCenter
    },
    {
      path: '/topology',
      name: 'Topology',
      component: Topology
    },
    {
      path: '/self-healing',
      name: 'SelfHealing',
      component: SelfHealing
    },
    {
      path: '/audit',
      name: 'AuditLogs',
      component: AuditLogs
    }
  ]
})

export default router