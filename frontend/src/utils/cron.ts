const pad2 = (value: string) => value.padStart(2, '0')
const isSingleNumber = (value: string) => /^\d+$/.test(value)

const describeWeekday = (value: string) => {
  const weekdayMap: Record<string, string> = {
    '0': '周日',
    '1': '周一',
    '2': '周二',
    '3': '周三',
    '4': '周四',
    '5': '周五',
    '6': '周六',
    '7': '周日',
  }

  if (value === '*') return ''
  if (value === '1-5') return '工作日'
  if (value.includes(',')) {
    return value.split(',').map(item => weekdayMap[item] || item).join('、')
  }
  if (value.includes('-')) {
    const [start, end] = value.split('-')
    if (!start || !end) return value
    return `${weekdayMap[start] || start}至${weekdayMap[end] || end}`
  }
  return weekdayMap[value] || value
}

export const describeCronExpression = (expression: string) => {
  const parts = expression.trim().split(/\s+/)
  if (parts.length !== 5) return '自定义 Cron 表达式'

  const minute = parts[0] || ''
  const hour = parts[1] || ''
  const dayOfMonth = parts[2] || ''
  const month = parts[3] || ''
  const dayOfWeek = parts[4] || ''
  if (!isSingleNumber(minute) || !isSingleNumber(hour)) {
    return '自定义 Cron 表达式'
  }
  const time = `${pad2(hour)}:${pad2(minute)}`

  if (dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
    return `每天 ${time}`
  }

  if (dayOfMonth === '*' && month === '*' && dayOfWeek !== '*') {
    const weekdayDescription = describeWeekday(dayOfWeek)
    const prefix = weekdayDescription === '工作日' ? '每个工作日' : `每${weekdayDescription}`
    return `${prefix} ${time}`
  }

  if (isSingleNumber(dayOfMonth) && month === '*' && dayOfWeek === '*') {
    return `每月 ${Number(dayOfMonth)}日 ${time}`
  }

  if (isSingleNumber(dayOfMonth) && isSingleNumber(month) && dayOfWeek === '*') {
    return `每年 ${Number(month)}月${Number(dayOfMonth)}日 ${time}`
  }

  if (dayOfMonth === '*' && isSingleNumber(month) && dayOfWeek === '*') {
    return `每年 ${Number(month)}月每天 ${time}`
  }

  return '自定义 Cron 表达式'
}
