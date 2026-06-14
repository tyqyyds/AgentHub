export interface IntentPattern {
  keywords: string[]
  intentType: string
  parser: (input: string) => ParsedIntent
  minMatches: number
  priority: number
}

export interface ParsedIntent {
  intent_name: string
  targets: string[]
  actions: Array<{
    type: string
    params: Record<string, unknown>
  }>
  confidence: number
  entities: Record<string, string>
  validation_error?: string
  is_valid?: boolean
}

const parseGitCloneBandwidth = (input: string): ParsedIntent => {
  const bwMatch = input.match(/(\d+)\s*[Mm]/)
  const bw = bwMatch ? parseInt(bwMatch[1]) : 500
  const subnetMatch = input.match(/([\u4e00-\u9fa5]+子网)/)
  const subnet = subnetMatch ? subnetMatch[1] : '研发子网'

  return {
    intent_name: 'git_clone_bandwidth_guarantee',
    targets: [subnet],
    actions: [{
      type: 'qos',
      params: {
        min_bw: `${bw}M`,
        protocol: 'git',
        traffic_type: 'clone',
        priority: 'high',
        cir: bw * 1000000,
        pir: Math.floor(bw * 1000000 * 1.2)
      }
    }],
    confidence: 0.9,
    entities: { 子网: subnet, 带宽: `${bw}M`, 用途: 'Git克隆' }
  }
}

const parseBandwidthGuarantee = (input: string): ParsedIntent => {
  const bwMatch = input.match(/最小\s*(\d+)\s*[Mm]|(\d+)\s*[Mm]\s*带宽/)
  const bw = bwMatch ? `${bwMatch[1] || bwMatch[2]}M` : '100M'
  const targetMatch = input.match(/([\u4e00-\u9fa5]+\s*子网)/)
  const target = targetMatch ? targetMatch[1] : '目标网络'
  const hasVideo = /视频|会议|直播/.test(input)
  const hasPriority = /优先|保障|关键|最小/.test(input)
  const trafficType = hasVideo ? '视频会议' : /git|克隆/.test(input) ? 'Git克隆' : '通用'

  return {
    intent_name: 'bandwidth_guarantee',
    targets: [target],
    actions: [{
      type: 'qos',
      params: {
        min_bw: bw,
        protocol: hasVideo ? 'video' : 'any',
        priority: hasPriority ? 'high' : 'medium'
      }
    }],
    confidence: 0.75,
    entities: { 目标: target, 带宽: bw, 类型: trafficType, 保障方式: hasPriority ? '最小带宽保障' : '尽力而为' }
  }
}

const parseAccessControl = (input: string): ParsedIntent => {
  const sourceMatch = input.match(/([\u4e00-\u9fa5]+)\s*子网/)
  const destMatch = input.match(/到([\u4e00-\u9fa5]+(?:子网)?)/)
  const portMatch = input.match(/(\d+)\s*端口|端口\s*(\d+)/)
  const port = portMatch ? (portMatch[1] || portMatch[2]) : null
  const isOpen = /开放|允许|通过|放行/.test(input)
  const isDeny = /禁止|拒绝|封锁|限制/.test(input)

  const entities: Record<string, string> = {
    源: sourceMatch?.[1] ? sourceMatch[1] + '子网' : '未知',
    目标: destMatch?.[1] || '未知',
    动作: isOpen ? '允许' : isDeny ? '拒绝' : '允许'
  }
  if (port) entities['端口'] = port

  return {
    intent_name: 'access_control',
    targets: [sourceMatch ? sourceMatch[1] + '子网' : '源网络', destMatch ? destMatch[1] : '目标'],
    actions: [{
      type: 'acl',
      params: {
        source: sourceMatch ? sourceMatch[1] + '子网' : 'any',
        destination: destMatch ? destMatch[1] : 'any',
        action: isOpen ? 'permit' : isDeny ? 'deny' : 'permit',
        ...(port ? { port: parseInt(port) } : {})
      }
    }],
    confidence: 0.7,
    entities
  }
}

const parseLinkManagement = (input: string): ParsedIntent => {
  const isSwitch = /切换|倒换|主备|备用/.test(input)
  const isBalance = /负载|均衡|分担/.test(input)
  const isAdd = /新增|添加|增加/.test(input)
  const sourceDeviceMatch = input.match(/将?\s*([\u4e00-\u9fa5\w]+(?:交换机|路由器|防火墙)?)/)
  const destDeviceMatch = input.match(/到([\u4e00-\u9fa5\w]+(?:交换机|路由器|防火墙)?)/)
  const sourceDevice = sourceDeviceMatch ? sourceDeviceMatch[1] : null
  const destDevice = destDeviceMatch ? destDeviceMatch[1] : null

  const targets: string[] = []
  if (sourceDevice) targets.push(sourceDevice)
  if (destDevice) targets.push(destDevice)
  if (targets.length === 0) targets.push('网络链路')

  const entities: Record<string, string> = {
    操作: isSwitch ? '主备切换' : isBalance ? '负载均衡' : isAdd ? '新增链路' : '链路管理'
  }
  if (sourceDevice) entities['源设备'] = sourceDevice
  if (destDevice) entities['目标设备'] = destDevice

  return {
    intent_name: 'link_management',
    targets,
    actions: [{
      type: 'routing',
      params: {
        mode: isSwitch ? 'failover' : isBalance ? 'load_balance' : isAdd ? 'add_link' : 'redundancy',
        ...(sourceDevice ? { source: sourceDevice } : {}),
        ...(destDevice ? { destination: destDevice } : {})
      }
    }],
    confidence: 0.65,
    entities
  }
}

const parseFaultDiagnosis = (input: string): ParsedIntent => {
  const hasLink = /链路|连接|连通/.test(input)
  const hasPerf = /慢|卡|延迟|丢包|超时/.test(input)
  const hasDevice = /设备|交换机|路由器|防火墙/.test(input)
  const deviceMatch = input.match(/([\u4e00-\u9fa5\w]+(?:交换机|路由器|防火墙)?)/)
  const faultTypeMatch = input.match(/的(.+?)(?:问题|故障|异常)/)
  const faultType = faultTypeMatch ? faultTypeMatch[1] : null

  const scope = hasDevice ? 'device' : hasLink ? 'link' : hasPerf ? 'performance' : 'full'
  const entities: Record<string, string> = {
    范围: hasDevice ? '设备' : hasLink ? '链路' : hasPerf ? '性能' : '全网'
  }
  if (deviceMatch && hasDevice) entities['设备'] = deviceMatch[1]
  if (faultType) entities['故障类型'] = faultType

  return {
    intent_name: 'fault_diagnosis',
    targets: [hasDevice && deviceMatch ? deviceMatch[1] : '全网'],
    actions: [{
      type: 'diagnose',
      params: {
        scope,
        symptoms: hasPerf ? 'performance_degradation' : hasLink ? 'connectivity_loss' : 'unknown',
        ...(faultType ? { fault_type: faultType } : {})
      }
    }],
    confidence: 0.7,
    entities
  }
}

const parsePerformanceMonitoring = (input: string): ParsedIntent => {
  const hasCpu = /CPU|cpu|处理器/.test(input)
  const hasBw = /带宽|流量|吞吐/.test(input)
  const hasDelay = /延迟|时延|RTT|latency/.test(input)
  const targetMatch = input.match(/([\u4e00-\u9fa5]+子网)/)

  return {
    intent_name: 'performance_monitoring',
    targets: [targetMatch ? targetMatch[1] : '全网'],
    actions: [{
      type: 'monitor',
      params: {
        metrics: hasCpu ? 'cpu' : hasBw ? 'bandwidth' : hasDelay ? 'latency' : 'all',
        interval: 30
      }
    }],
    confidence: 0.65,
    entities: { 指标: hasCpu ? 'CPU' : hasBw ? '带宽' : hasDelay ? '延迟' : '全部' }
  }
}

const parseQoSPolicy = (input: string): ParsedIntent => {
  const bwMatch = input.match(/(\d+)\s*[Mm]/)
  const subnetMatch = input.match(/([\u4e00-\u9fa5]+子网)/)
  const priorityMatch = input.match(/(高|中|低|关键|普通)\s*级?/)
  const priorityLevel = priorityMatch ? priorityMatch[1] : null
  const isHighPriority = /优先|高优|关键|高级|高/.test(input)

  const entities: Record<string, string> = {
    子网: subnetMatch?.[1] || '未知',
    带宽: bwMatch ? `${bwMatch[1]}M` : '默认'
  }
  if (priorityLevel) entities['优先级'] = priorityLevel + '级'

  return {
    intent_name: 'qos_policy',
    targets: [subnetMatch ? subnetMatch[1] : '目标网络'],
    actions: [{
      type: 'qos_config',
      params: {
        min_bw: bwMatch ? `${bwMatch[1]}M` : '100M',
        priority: isHighPriority ? 'high' : 'medium',
        policy_type: 'qos'
      }
    }],
    confidence: 0.7,
    entities
  }
}

const parseTrafficShaping = (input: string): ParsedIntent => {
  const bwMatch = input.match(/(\d+)\s*[Mm]/)
  const isLimit = /限制|上限|整形|shaping/.test(input)
  const targetMatch = input.match(/([\u4e00-\u9fa5]+子网)/)

  return {
    intent_name: 'traffic_shaping',
    targets: [targetMatch ? targetMatch[1] : '目标网络'],
    actions: [{
      type: 'traffic_config',
      params: {
        max_bw: bwMatch ? `${bwMatch[1]}M` : '200M',
        mode: isLimit ? 'shaping' : 'policing'
      }
    }],
    confidence: 0.6,
    entities: { 目标: targetMatch?.[1] || '目标网络', 带宽上限: bwMatch ? `${bwMatch[1]}M` : '200M', 模式: isLimit ? '整形' : '监管' }
  }
}

const parseDeviceConfig = (input: string): ParsedIntent => {
  const deviceMatch = input.match(/([\u4e00-\u9fa5\w]+(?:交换机|路由器|防火墙)?)/)

  return {
    intent_name: 'device_config',
    targets: [deviceMatch ? deviceMatch[1] : '目标设备'],
    actions: [{
      type: 'config',
      params: {}
    }],
    confidence: 0.5,
    entities: { 设备: deviceMatch?.[1] || '未知' }
  }
}

const MIN_CONFIDENCE = 0.35

const parseGeneral = (_input: string): ParsedIntent => {
  return {
    intent_name: 'unrecognized_intent',
    targets: [],
    actions: [],
    confidence: 0,
    entities: {},
    is_valid: false,
    validation_error: '无法识别有效的网络运维意图，请使用更具体的描述，例如："保障研发子网最小200M带宽"、"开放办公子网到生产子网的访问"、"诊断核心路由器的连通性问题"'
  }
}

export const validateIntentInput = (input: string): { valid: boolean; error?: string } => {
  const trimmed = input.trim()

  if (!trimmed) {
    return { valid: false, error: '意图输入不能为空' }
  }

  if (trimmed.length < 4) {
    return { valid: false, error: '意图描述过短，请提供更详细的描述（至少4个字符）' }
  }

  if (trimmed.length > 2000) {
    return { valid: false, error: '意图描述过长，请控制在2000字符以内' }
  }

  if (/^(.)\1{4,}$/.test(trimmed)) {
    return { valid: false, error: '意图描述包含重复内容，请输入有意义的运维意图' }
  }

  if (/^[0-9\s\.,;:!?\-+=/\\@#$%^&*(){}\[\]]+$/.test(trimmed)) {
    return { valid: false, error: '意图描述不能仅包含数字和符号，请使用自然语言描述运维需求' }
  }

  if (/^(test|测试|hello|hi|你好|aaa|bbb|123|abc|xxx|yyy|zzz)$/i.test(trimmed)) {
    return { valid: false, error: `"${trimmed}" 不是有效的网络运维意图，请描述具体的网络操作需求` }
  }

  return { valid: true }
}

export const intentPatterns: IntentPattern[] = [
  {
    keywords: ['git', '克隆', '带宽'],
    intentType: 'git_clone_bandwidth_guarantee',
    parser: parseGitCloneBandwidth,
    minMatches: 2,
    priority: 10
  },
  {
    keywords: ['带宽', '保障', '视频', '最小'],
    intentType: 'bandwidth_guarantee',
    parser: parseBandwidthGuarantee,
    minMatches: 2,
    priority: 20
  },
  {
    keywords: ['故障', '诊断', '排查', '异常', '问题'],
    intentType: 'fault_diagnosis',
    parser: parseFaultDiagnosis,
    minMatches: 1,
    priority: 30
  },
  {
    keywords: ['监控', '性能', '指标'],
    intentType: 'performance_monitoring',
    parser: parsePerformanceMonitoring,
    minMatches: 1,
    priority: 40
  },
  {
    keywords: ['qos', 'QoS', '优先级', '策略', '配置'],
    intentType: 'qos_policy',
    parser: parseQoSPolicy,
    minMatches: 2,
    priority: 50
  },
  {
    keywords: ['流量', '整形', '限制', '上限'],
    intentType: 'traffic_shaping',
    parser: parseTrafficShaping,
    minMatches: 1,
    priority: 60
  },
  {
    keywords: ['访问', 'acl', 'ACL', '权限', '开放', '禁止', '端口'],
    intentType: 'access_control',
    parser: parseAccessControl,
    minMatches: 1,
    priority: 70
  },
  {
    keywords: ['链路', '路由', '切换', '负载', '备用'],
    intentType: 'link_management',
    parser: parseLinkManagement,
    minMatches: 1,
    priority: 80
  },
  {
    keywords: ['配置', '设备', '接口'],
    intentType: 'device_config',
    parser: parseDeviceConfig,
    minMatches: 2,
    priority: 90
  }
]

export const parseIntent = (input: string): ParsedIntent => {
  const inputValidation = validateIntentInput(input)
  if (!inputValidation.valid) {
    return {
      intent_name: 'invalid_input',
      targets: [],
      actions: [],
      confidence: 0,
      entities: {},
      is_valid: false,
      validation_error: inputValidation.error
    }
  }

  const lowerInput = input.toLowerCase()

  let bestMatch: { pattern: IntentPattern; matchCount: number } | null = null

  for (const pattern of intentPatterns) {
    const matchCount = pattern.keywords.filter(k => lowerInput.includes(k.toLowerCase())).length
    if (matchCount === 0) continue

    if (!bestMatch) {
      bestMatch = { pattern, matchCount }
    } else if (matchCount > bestMatch.matchCount) {
      bestMatch = { pattern, matchCount }
    } else if (matchCount === bestMatch.matchCount && pattern.priority > bestMatch.pattern.priority) {
      bestMatch = { pattern, matchCount }
    }
  }

  if (bestMatch && bestMatch.matchCount >= bestMatch.pattern.minMatches) {
    const result = bestMatch.pattern.parser(input)
    const totalKeywords = bestMatch.pattern.keywords.length
    const matchedRatio = bestMatch.matchCount / totalKeywords
    result.confidence = Math.min(result.confidence, 0.3 + matchedRatio * 0.7)

    if (result.confidence < MIN_CONFIDENCE) {
      result.is_valid = false
      result.validation_error = `意图识别置信度过低（${Math.round(result.confidence * 100)}%），无法确定具体操作类型。请提供更明确的描述，例如包含目标设备、操作类型和参数。`
    } else {
      result.is_valid = true
    }

    return result
  }

  return parseGeneral(input)
}
