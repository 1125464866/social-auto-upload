import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAccountStore = defineStore('account', () => {
  // 存储所有账号信息
  const accounts = ref([])
  
  // 平台类型映射
  const platformTypes = {
    1: '小红书',
    2: '视频号',
    3: '抖音',
    4: '快手'
  }
  
  // 设置账号列表
  const setAccounts = (accountsData) => {
    // 转换后端返回的数据格式为前端使用的格式
    accounts.value = accountsData.map(item => {
      let statusStr = '异常'
      if (item[4] === 1) statusStr = '正常'
      else if (item[4] === 0) statusStr = '异常'
      else if (typeof item[4] === 'string') statusStr = item[4]

      return {
        id: item[0],
        type: item[1],
        filePath: item[2],
        name: item[3],
        status: statusStr,
        platform: platformTypes[item[1]] || '未知',
        avatar: '/vite.svg' // 默认使用vite.svg作为头像
      }
    })
  }
  
  // 添加账号
  const addAccount = (account) => {
    accounts.value.push(account)
  }
  
  // 更新账号
  const updateAccount = (id, updatedAccount) => {
    const index = accounts.value.findIndex(acc => acc.id === id)
    if (index !== -1) {
      accounts.value[index] = { ...accounts.value[index], ...updatedAccount }
    }
  }
  
  // 删除账号
  const deleteAccount = (id) => {
    accounts.value = accounts.value.filter(acc => acc.id !== id)
  }
  
  // 更新单个账号（从后端原始数据）
  const updateAccountFromRaw = (rawItem) => {
    const id = rawItem[0]
    const index = accounts.value.findIndex(acc => acc.id === id)
    if (index !== -1) {
      let statusStr = '异常'
      if (rawItem[4] === 1) statusStr = '正常'
      else if (rawItem[4] === 0) statusStr = '异常'
      else if (typeof rawItem[4] === 'string') statusStr = rawItem[4]

      accounts.value[index] = {
        ...accounts.value[index],
        id: rawItem[0],
        type: rawItem[1],
        filePath: rawItem[2],
        name: rawItem[3],
        status: statusStr,
        platform: platformTypes[rawItem[1]] || '未知'
      }
    }
  }
  
  // 根据平台获取账号
  const getAccountsByPlatform = (platform) => {
    return accounts.value.filter(acc => acc.platform === platform)
  }
  
  return {
    accounts,
    setAccounts,
    addAccount,
    updateAccount,
    updateAccountFromRaw,
    deleteAccount,
    getAccountsByPlatform
  }
})