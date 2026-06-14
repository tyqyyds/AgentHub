/**
 * 主题色工具 - 将 CSS 变量解析为实际颜色值
 * 用于图表库(ECharts)和 SVG 属性等需要实际颜色值的场景
 */

// 缓存已解析的颜色值
const colorCache = new Map<string, string>()

/**
 * 解析 CSS 变量为实际颜色值
 * @param varName CSS 变量名，如 '--color-primary'
 * @returns 实际颜色值，如 '#165DFF'
 */
export function resolveColor(varName: string): string {
  if (colorCache.has(varName)) {
    return colorCache.get(varName)!
  }
  const value = getComputedStyle(document.documentElement).getPropertyValue(varName).trim()
  colorCache.set(varName, value)
  return value
}

/**
 * 预定义的主题色快捷访问
 * 使用方式：themeColors.primary → '#165DFF'
 */
export const themeColors = {
  get primary() { return resolveColor('--color-primary') },
  get primaryLight() { return resolveColor('--color-primary-light') },
  get primaryLighter() { return resolveColor('--color-primary-lighter') },
  get primaryBg() { return resolveColor('--color-primary-bg') },
  get primaryGlow() { return resolveColor('--color-primary-glow') },
  get primaryBorder() { return resolveColor('--color-primary-border') },

  get success() { return resolveColor('--color-success') },
  get successLight() { return resolveColor('--color-success-light') },
  get successBg() { return resolveColor('--color-success-bg') },
  get successGlow() { return resolveColor('--color-success-glow') },
  get successBorder() { return resolveColor('--color-success-border') },

  get error() { return resolveColor('--color-error') },
  get errorLight() { return resolveColor('--color-error-light') },
  get errorBg() { return resolveColor('--color-error-bg') },
  get errorGlow() { return resolveColor('--color-error-glow') },
  get errorBorder() { return resolveColor('--color-error-border') },

  get warning() { return resolveColor('--color-warning') },
  get warningLight() { return resolveColor('--color-warning-light') },
  get warningDeep() { return resolveColor('--color-warning-deep') },
  get warningBg() { return resolveColor('--color-warning-bg') },
  get warningGlow() { return resolveColor('--color-warning-glow') },
  get warningBorder() { return resolveColor('--color-warning-border') },

  get orange() { return resolveColor('--color-orange') },
  get cyan() { return resolveColor('--color-cyan') },
  get purple() { return resolveColor('--color-purple') },
  get emerald() { return resolveColor('--color-emerald') },

  get bgPrimary() { return resolveColor('--color-bg-primary') },
  get bgSecondary() { return resolveColor('--color-bg-secondary') },
  get bgTertiary() { return resolveColor('--color-bg-tertiary') },

  get textPrimary() { return resolveColor('--color-text-primary') },
  get textSecondary() { return resolveColor('--color-text-secondary') },
  get textTertiary() { return resolveColor('--color-text-tertiary') },
  get textDisabled() { return resolveColor('--color-text-disabled') },
}

/**
 * 清除颜色缓存（主题切换时调用）
 */
export function clearColorCache(): void {
  colorCache.clear()
}
