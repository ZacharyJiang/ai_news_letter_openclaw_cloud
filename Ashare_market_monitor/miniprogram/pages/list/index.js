const { request } = require('../../utils/api')

const DISTANCE_MODE_OPTIONS = [
  { label: '离历史最高跌幅%', value: 'from_high' },
  { label: '离历史最低涨幅%', value: 'from_low' }
]

const SORT_OPTIONS = [
  { label: '基金规模', value: 'fund_scale_billion' },
  { label: '现价', value: 'price' },
  { label: '总费率', value: 'total_fee_pct' },
  { label: '离历史最高跌幅', value: 'drawdown_from_ath_pct' },
  { label: '离历史最低涨幅', value: 'rebound_from_atl_pct' },
  { label: '代码', value: 'code' }
]

Page({
  data: {
    loading: false,
    error: '',
    items: [],
    total: 0,
    page: 1,
    pageSize: 80,
    syncStatus: {},
    lastFetchAt: '',
    autoRefresh: true,

    query: {
      keyword: '',
      min_price: '',
      max_price: '',
      min_scale: '',
      max_scale: '',
      min_fee: '',
      max_fee: '',
      min_distance: '',
      max_distance: '',
      distance_mode: 'from_high',
      sort_by: 'fund_scale_billion',
      order: 'desc'
    },

    distanceModeOptions: DISTANCE_MODE_OPTIONS,
    distanceModeIndex: 0,
    sortOptions: SORT_OPTIONS,
    sortIndex: 0
  },

  onLoad() {
    this.fetchList(true)
    this.startAutoRefresh()
  },

  onUnload() {
    this.stopAutoRefresh()
  },

  startAutoRefresh() {
    this.stopAutoRefresh()
    this._timer = setInterval(() => {
      if (this.data.autoRefresh) {
        this.fetchList(false)
      }
    }, 10000)
  },

  stopAutoRefresh() {
    if (this._timer) {
      clearInterval(this._timer)
      this._timer = null
    }
  },

  toNumber(value) {
    if (value === '' || value === null || value === undefined) {
      return undefined
    }
    const num = Number(value)
    return Number.isNaN(num) ? undefined : num
  },

  buildParams(forceFirstPage) {
    const q = this.data.query
    return {
      keyword: q.keyword || undefined,
      min_price: this.toNumber(q.min_price),
      max_price: this.toNumber(q.max_price),
      min_scale: this.toNumber(q.min_scale),
      max_scale: this.toNumber(q.max_scale),
      min_fee: this.toNumber(q.min_fee),
      max_fee: this.toNumber(q.max_fee),
      min_distance: this.toNumber(q.min_distance),
      max_distance: this.toNumber(q.max_distance),
      distance_mode: q.distance_mode,
      sort_by: q.sort_by,
      order: q.order,
      page: forceFirstPage ? 1 : this.data.page,
      page_size: this.data.pageSize
    }
  },

  async fetchList(forceFirstPage) {
    if (this.data.loading) {
      return
    }

    this.setData({ loading: true, error: '' })

    try {
      const params = this.buildParams(forceFirstPage)
      const res = await request({
        url: '/api/etfs',
        data: params
      })

      this.setData({
        items: res.items || [],
        total: res.total || 0,
        page: res.page || 1,
        pageSize: res.page_size || this.data.pageSize,
        syncStatus: res.sync_status || {},
        lastFetchAt: new Date().toLocaleTimeString(),
        loading: false
      })
    } catch (err) {
      this.setData({
        loading: false,
        error: err.message || '加载失败'
      })
    }
  },

  onKeywordInput(e) {
    this.setData({ 'query.keyword': e.detail.value })
  },

  onNumericInput(e) {
    const field = e.currentTarget.dataset.field
    this.setData({ [`query.${field}`]: e.detail.value })
  },

  onDistanceModeChange(e) {
    const index = Number(e.detail.value)
    this.setData({
      distanceModeIndex: index,
      'query.distance_mode': DISTANCE_MODE_OPTIONS[index].value
    })
  },

  onSortChange(e) {
    const index = Number(e.detail.value)
    this.setData({
      sortIndex: index,
      'query.sort_by': SORT_OPTIONS[index].value
    })
  },

  toggleOrder() {
    const next = this.data.query.order === 'desc' ? 'asc' : 'desc'
    this.setData({ 'query.order': next })
  },

  toggleAutoRefresh(e) {
    this.setData({ autoRefresh: !!e.detail.value })
  },

  applyFilter() {
    this.setData({ page: 1 }, () => this.fetchList(true))
  },

  resetFilter() {
    this.setData(
      {
        page: 1,
        distanceModeIndex: 0,
        sortIndex: 0,
        query: {
          keyword: '',
          min_price: '',
          max_price: '',
          min_scale: '',
          max_scale: '',
          min_fee: '',
          max_fee: '',
          min_distance: '',
          max_distance: '',
          distance_mode: 'from_high',
          sort_by: 'fund_scale_billion',
          order: 'desc'
        }
      },
      () => this.fetchList(true)
    )
  },

  goDetail(e) {
    const code = e.currentTarget.dataset.code
    const name = e.currentTarget.dataset.name
    wx.navigateTo({
      url: `/pages/detail/index?code=${code}&name=${encodeURIComponent(name || '')}`
    })
  },

  goPrev() {
    if (this.data.page <= 1) {
      return
    }
    this.setData({ page: this.data.page - 1 }, () => this.fetchList(false))
  },

  goNext() {
    const maxPage = Math.ceil((this.data.total || 0) / this.data.pageSize)
    if (this.data.page >= maxPage) {
      return
    }
    this.setData({ page: this.data.page + 1 }, () => this.fetchList(false))
  }
})
