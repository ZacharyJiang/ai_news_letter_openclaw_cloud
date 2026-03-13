const app = getApp()

function getBaseUrl() {
  return app?.globalData?.apiBase || 'http://127.0.0.1:8000'
}

function request({ url, method = 'GET', data = {} }) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${getBaseUrl()}${url}`,
      method,
      data,
      timeout: 15000,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
        } else {
          reject(new Error(res.data?.detail || `HTTP ${res.statusCode}`))
        }
      },
      fail: (err) => reject(err)
    })
  })
}

module.exports = {
  request
}
