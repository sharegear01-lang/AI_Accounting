// 交易分类常量（与后端 app/api/transactions.py DEFAULT_CATEGORIES 保持一致）
export const CATEGORIES = ['餐饮', '交通', '购物', '娱乐', '居住', '医疗', '教育', '工资', '理财', '其他']

// 金额格式化：支出红色（+），收入绿色（-）
export function formatAmount(amount) {
  const v = Number(amount) || 0
  const sign = v > 0 ? '+' : v < 0 ? '-' : ''
  return `${sign}¥${Math.abs(v).toFixed(2)}`
}

// 根据金额判断收支类型
export function isExpense(amount) {
  return Number(amount) > 0
}
