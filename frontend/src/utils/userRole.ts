export type UserRole = 'admin' | 'operator' | 'viewer'

export function getUserRole(): UserRole {
  try {
    const raw = localStorage.getItem('user_info')
    if (raw) {
      const info = JSON.parse(raw)
      if (info.role === 'admin' || info.role === 'operator' || info.role === 'viewer') return info.role
    }
  } catch {}
  const token = localStorage.getItem('access_token')
  if (token) {
    try {
      const parts = token.split('.')
      if (parts.length === 3) {
        const payload = JSON.parse(atob(parts[1]))
        if (payload.role === 'admin' || payload.role === 'operator' || payload.role === 'viewer') return payload.role
      }
    } catch {}
  }
  return 'viewer'
}
