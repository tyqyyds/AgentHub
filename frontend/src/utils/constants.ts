export const STATUS_CONFIG = {
  success: {
    label: '成功',
    color: '#52C41A',
    class: 'success'
  },
  pending: {
    label: '待审批',
    color: '#FF7D00',
    class: 'pending'
  },
  failed: {
    label: '失败',
    color: '#FF4D4F',
    class: 'failed'
  },
  approved: {
    label: '已批准',
    color: '#52C41A',
    class: 'approved'
  },
  rejected: {
    label: '已拒绝',
    color: '#FF4D4F',
    class: 'rejected'
  },
  running: {
    label: '运行中',
    color: '#1890FF',
    class: 'running'
  },
  completed: {
    label: '已完成',
    color: '#52C41A',
    class: 'completed'
  },
  cancelled: {
    label: '已取消',
    color: '#8C8C8C',
    class: 'cancelled'
  }
} as const

export type StatusType = keyof typeof STATUS_CONFIG

export const getStatusConfig = (status: string) => {
  return STATUS_CONFIG[status as StatusType] || {
    label: status,
    color: '#8C8C8C',
    class: 'default'
  }
}
