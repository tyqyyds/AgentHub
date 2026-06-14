// 配置文件 - 只使用环境变量和默认值
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

export const POLLING_INTERVAL = {
  DASHBOARD: Number(import.meta.env.VITE_POLLING_DASHBOARD) || 30000,
  INTENT_HISTORY: Number(import.meta.env.VITE_POLLING_INTENT_HISTORY) || 10000,
  RATE_LIMIT: Number(import.meta.env.VITE_POLLING_RATE_LIMIT) || 5000,
  AUDIT_LOGS: 10000
}

export const DEBOUNCE = {
  SEARCH: Number(import.meta.env.VITE_DEBOUNCE_SEARCH) || 300,
  VALIDATION: Number(import.meta.env.VITE_DEBOUNCE_VALIDATION) || 500
}

export const FEATURES = {
  DEBUG_PANEL: import.meta.env.VITE_ENABLE_DEBUG_PANEL === 'true' || false,
  MOCK_DATA: import.meta.env.VITE_ENABLE_MOCK_DATA === 'true' || false,
  AUTO_SAVE: true
}

export const UI = {
  PAGE_SIZE: 20,
  MAX_FILE_SIZE: 10485760,
  TOAST_DURATION: 3000,
  MODAL_ANIMATION_DURATION: 300
}

export const VALIDATION = {
  TOOL_NAME: {
    MIN_LENGTH: 3,
    MAX_LENGTH: 32,
    PATTERN: /^[a-zA-Z][a-zA-Z0-9_]{2,31}$/
  },
  TOOL_DESCRIPTION: {
    MIN_LENGTH: 10,
    MAX_LENGTH: 500
  },
  PARAM_NAME: {
    MIN_LENGTH: 2,
    MAX_LENGTH: 32,
    PATTERN: /^[a-zA-Z][a-zA-Z0-9_]{1,31}$/
  },
  PARAM_DESCRIPTION: {
    MIN_LENGTH: 10,
    MAX_LENGTH: 200
  },
  MAX_PARAMS: 10
}
