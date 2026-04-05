const state = {
  query: {
    keyword: '',
    min_price: undefined,
    max_price: undefined,
    min_scale: undefined,
    max_scale: undefined,
    min_fee: undefined,
    max_fee: undefined,
    min_distance: undefined,
    max_distance: undefined,
    distance_mode: 'from_high',
    sort_by: 'fund_scale_billion',
    order: 'desc',
    page: 1,
    page_size: 80
  },
  total: 0,
  items: [],
  selectedCode: null,
  selectedName: null,
  period: 'day',
  autoRefresh: true,
  timer: null,
  loading: false
}

const els = {
  totalCount: document.getElementById('totalCount'),
  lastFetchAt: document.getElementById('lastFetchAt'),
  syncState: document.getElementById('syncState'),
  pageInfo: document.getElementById('pageInfo'),
  rows: document.getElementById('etfRows'),
  chartTitle: document.getElementById('chartTitle'),
  chartSubtitle: document.getElementById('chartSubtitle'),
  chartStats: document.getElementById('chartStats'),
  canvas: document.getElementById('klineCanvas'),
  keyword: document.getElementById('keyword'),
  minScale: document.getElementById('minScale'),
  maxScale: document.getElementById('maxScale'),
  minPrice: document.getElementById('minPrice'),
  maxPrice: document.getElementById('maxPrice'),
  minFee: document.getElementById('minFee'),
  maxFee: document.getElementById('maxFee'),
  minDistance: document.getElementById('minDistance'),
  maxDistance: document.getElementById('maxDistance'),
  distanceMode: document.getElementById('distanceMode'),
  sortBy: document.getElementById('sortBy'),
  toggleOrder: document.getElementById('toggleOrder'),
  applyFilter: document.getElementById('applyFilter'),
  resetFilter: document.getElementById('resetFilter'),
  autoRefresh: document.getElementById('autoRefresh'),
  manualRefresh: document.getElementById('manualRefresh'),
  prevPage: document.getElementById('prevPage'),
  nextPage: document.getElementById('nextPage'),
  periodBtns: Array.from(document.querySelectorAll('.period'))
}

const canvasCtx = els.canvas.getContext('2d')

function numberOrUndefined(v) {
  if (v === null || v === undefined || v === '') {
    return undefined
  }
  const n = Number(v)
  return Number.isFinite(n) ? n : undefined
}

function formatNum(v, d = 4) {
  if (v === null || v === undefined) {
    return '--'
  }
  return Number(v).toFixed(d)
}

function formatPct(v, d = 2) {
  if (v === null || v === undefined) {
    return '--'
  }
  return `${Number(v).toFixed(d)}%`
}

function prettyTime() {
  const now = new Date()
  return now.toLocaleString('zh-CN', { hour12: false })
}

async function apiGet(url, params = {}) {
  const q = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') {
      q.set(k, String(v))
    }
  })
  const finalUrl = q.toString() ? `${url}?${q.toString()}` : url
  const res = await fetch(finalUrl)
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

function setLoading(flag) {
  state.loading = flag
  els.manualRefresh.disabled = flag
  els.applyFilter.disabled = flag
  if (flag) {
    els.manualRefresh.textContent = '刷新中...'
  } else {
    els.manualRefresh.textContent = '立即刷新'
  }
}

function renderRows() {
  if (!state.items.length) {
    els.rows.innerHTML = '<tr><td colspan="8">暂无数据</td></tr>'
    return
  }

  els.rows.innerHTML = state.items
    .map((item) => {
      const active = state.selectedCode === item.code ? 'active' : ''
      return `
      <tr class="${active}" data-code="${item.code}" data-name="${item.name}">
        <td class="code">${item.code}</td>
        <td title="${item.name}">${item.name}</td>
        <td>${formatNum(item.price, 4)}</td>
        <td>${formatNum(item.fund_scale_billion, 2)}</td>
        <td>${formatNum(item.total_fee_pct, 4)}</td>
        <td class="value-fall">${formatPct(item.drawdown_from_ath_pct, 2)}</td>
        <td class="value-rise">${formatPct(item.rebound_from_atl_pct, 2)}</td>
        <td><button class="view-k" data-kline="${item.code}" data-name="${item.name}">查看</button></td>
      </tr>
    `
    })
    .join('')

  Array.from(els.rows.querySelectorAll('tr')).forEach((tr) => {
    tr.addEventListener('click', () => {
      const code = tr.dataset.code
      const name = tr.dataset.name
      selectEtf(code, name)
    })
  })

  Array.from(els.rows.querySelectorAll('button[data-kline]')).forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation()
      selectEtf(btn.dataset.kline, btn.dataset.name)
    })
  })
}

function renderHeader(syncStatus) {
  els.totalCount.textContent = String(state.total)
  els.lastFetchAt.textContent = prettyTime()
  const sync = syncStatus || {}
  if (sync.running) {
    els.syncState.textContent = `同步状态: 进行中 ${sync.processed || 0}/${sync.total || 0}`
  } else {
    els.syncState.textContent = '同步状态: 空闲'
  }

  const maxPage = Math.max(1, Math.ceil(state.total / state.query.page_size))
  els.pageInfo.textContent = `第 ${state.query.page} / ${maxPage} 页`
}

async function fetchEtfList() {
  if (state.loading) {
    return
  }
  setLoading(true)

  try {
    const data = await apiGet('/api/etfs', state.query)
    state.total = data.total || 0
    state.items = data.items || []
    renderRows()
    renderHeader(data.sync_status || {})

    if (!state.selectedCode && state.items.length) {
      const first = state.items[0]
      selectEtf(first.code, first.name)
    }
  } catch (err) {
    console.error(err)
    els.rows.innerHTML = `<tr><td colspan="8">列表加载失败: ${err.message}</td></tr>`
  } finally {
    setLoading(false)
  }
}

function drawEmpty(message) {
  const { width, height } = els.canvas
  canvasCtx.clearRect(0, 0, width, height)
  canvasCtx.fillStyle = '#fafdff'
  canvasCtx.fillRect(0, 0, width, height)
  canvasCtx.fillStyle = '#516f89'
  canvasCtx.font = '500 14px Manrope'
  canvasCtx.fillText(message, width / 2 - 80, height / 2)
}

function toY(price, maxPrice, minPrice, top, drawH) {
  return top + ((maxPrice - price) / (maxPrice - minPrice)) * drawH
}

function drawKline(bars) {
  if (!bars || !bars.length) {
    drawEmpty('暂无 K 线数据')
    return
  }

  const { width, height } = els.canvas
  canvasCtx.clearRect(0, 0, width, height)
  canvasCtx.fillStyle = '#fafdff'
  canvasCtx.fillRect(0, 0, width, height)

  const show = bars.slice(-140)
  const highs = show.map((x) => x.high)
  const lows = show.map((x) => x.low)

  let maxPrice = Math.max(...highs)
  let minPrice = Math.min(...lows)
  if (maxPrice <= minPrice) {
    maxPrice = minPrice + 1
  }
  const pad = (maxPrice - minPrice) * 0.04
  maxPrice += pad
  minPrice -= pad

  const area = { top: 24, left: 56, right: 14, bottom: 34 }
  const drawW = width - area.left - area.right
  const drawH = height - area.top - area.bottom

  canvasCtx.strokeStyle = 'rgba(24, 76, 115, 0.18)'
  canvasCtx.lineWidth = 1
  for (let i = 0; i <= 4; i += 1) {
    const y = area.top + (drawH / 4) * i
    canvasCtx.beginPath()
    canvasCtx.moveTo(area.left, y)
    canvasCtx.lineTo(width - area.right, y)
    canvasCtx.stroke()

    const p = maxPrice - ((maxPrice - minPrice) * i) / 4
    canvasCtx.fillStyle = '#5c7691'
    canvasCtx.font = '12px IBM Plex Mono'
    canvasCtx.fillText(p.toFixed(3), 6, y + 4)
  }

  canvasCtx.strokeStyle = '#7ca7c8'
  canvasCtx.beginPath()
  canvasCtx.moveTo(area.left, area.top)
  canvasCtx.lineTo(area.left, height - area.bottom)
  canvasCtx.lineTo(width - area.right, height - area.bottom)
  canvasCtx.stroke()

  const step = drawW / show.length
  const bodyW = Math.max(2.4, step * 0.65)

  show.forEach((bar, i) => {
    const x = area.left + step * i + step / 2
    const openY = toY(bar.open, maxPrice, minPrice, area.top, drawH)
    const closeY = toY(bar.close, maxPrice, minPrice, area.top, drawH)
    const highY = toY(bar.high, maxPrice, minPrice, area.top, drawH)
    const lowY = toY(bar.low, maxPrice, minPrice, area.top, drawH)

    const rise = bar.close >= bar.open
    const color = rise ? '#db3a34' : '#0c8c58'

    canvasCtx.strokeStyle = color
    canvasCtx.lineWidth = 1
    canvasCtx.beginPath()
    canvasCtx.moveTo(x, highY)
    canvasCtx.lineTo(x, lowY)
    canvasCtx.stroke()

    const top = Math.min(openY, closeY)
    const h = Math.max(1, Math.abs(closeY - openY))
    canvasCtx.fillStyle = color
    canvasCtx.fillRect(x - bodyW / 2, top, bodyW, h)
  })

  const firstDate = show[0].date
  const midDate = show[Math.floor(show.length / 2)].date
  const lastDate = show[show.length - 1].date
  canvasCtx.fillStyle = '#5c7691'
  canvasCtx.font = '12px IBM Plex Mono'
  canvasCtx.fillText(firstDate, area.left, height - 10)
  canvasCtx.fillText(midDate, width / 2 - 45, height - 10)
  canvasCtx.fillText(lastDate, width - area.right - 90, height - 10)
}

function renderChartStats(payload) {
  els.chartStats.innerHTML = [
    { k: '历史最高', v: formatNum(payload.ath, 4), cls: '' },
    { k: '历史最低', v: formatNum(payload.atl, 4), cls: '' },
    { k: '离历史最高跌幅', v: formatPct(payload.drawdown_from_ath_pct, 2), cls: 'value-fall' },
    { k: '离历史最低涨幅', v: formatPct(payload.rebound_from_atl_pct, 2), cls: 'value-rise' }
  ]
    .map(
      (x) => `
      <div class="stat">
        <div class="k">${x.k}</div>
        <div class="v ${x.cls}">${x.v}</div>
      </div>
    `
    )
    .join('')
}

async function selectEtf(code, name) {
  if (!code) {
    return
  }
  state.selectedCode = code
  state.selectedName = name
  renderRows()

  els.chartTitle.textContent = `${name || code} (${code}) 历史至今 K 线`
  els.chartSubtitle.textContent = `周期: ${state.period.toUpperCase()} | 数据源: /api/etfs/${code}/kline`

  try {
    const payload = await apiGet(`/api/etfs/${code}/kline`, { period: state.period })
    drawKline(payload.bars || [])
    renderChartStats(payload)
  } catch (err) {
    drawEmpty(`K 线加载失败: ${err.message}`)
    els.chartStats.innerHTML = ''
  }
}

function syncQueryFromInput() {
  state.query.keyword = els.keyword.value.trim()
  state.query.min_scale = numberOrUndefined(els.minScale.value)
  state.query.max_scale = numberOrUndefined(els.maxScale.value)
  state.query.min_price = numberOrUndefined(els.minPrice.value)
  state.query.max_price = numberOrUndefined(els.maxPrice.value)
  state.query.min_fee = numberOrUndefined(els.minFee.value)
  state.query.max_fee = numberOrUndefined(els.maxFee.value)
  state.query.min_distance = numberOrUndefined(els.minDistance.value)
  state.query.max_distance = numberOrUndefined(els.maxDistance.value)
  state.query.distance_mode = els.distanceMode.value
  state.query.sort_by = els.sortBy.value
}

function setDefaultInput() {
  els.keyword.value = ''
  els.minScale.value = ''
  els.maxScale.value = ''
  els.minPrice.value = ''
  els.maxPrice.value = ''
  els.minFee.value = ''
  els.maxFee.value = ''
  els.minDistance.value = ''
  els.maxDistance.value = ''
  els.distanceMode.value = 'from_high'
  els.sortBy.value = 'fund_scale_billion'
}

function bindEvents() {
  els.applyFilter.addEventListener('click', () => {
    syncQueryFromInput()
    state.query.page = 1
    fetchEtfList()
  })

  els.resetFilter.addEventListener('click', () => {
    state.query = {
      keyword: '',
      min_price: undefined,
      max_price: undefined,
      min_scale: undefined,
      max_scale: undefined,
      min_fee: undefined,
      max_fee: undefined,
      min_distance: undefined,
      max_distance: undefined,
      distance_mode: 'from_high',
      sort_by: 'fund_scale_billion',
      order: 'desc',
      page: 1,
      page_size: 80
    }
    setDefaultInput()
    els.toggleOrder.textContent = '排序: 降序'
    fetchEtfList()
  })

  els.toggleOrder.addEventListener('click', () => {
    state.query.order = state.query.order === 'desc' ? 'asc' : 'desc'
    els.toggleOrder.textContent = `排序: ${state.query.order === 'desc' ? '降序' : '升序'}`
  })

  els.autoRefresh.addEventListener('change', () => {
    state.autoRefresh = els.autoRefresh.checked
  })

  els.manualRefresh.addEventListener('click', () => {
    fetchEtfList()
  })

  els.prevPage.addEventListener('click', () => {
    if (state.query.page <= 1) {
      return
    }
    state.query.page -= 1
    fetchEtfList()
  })

  els.nextPage.addEventListener('click', () => {
    const maxPage = Math.max(1, Math.ceil(state.total / state.query.page_size))
    if (state.query.page >= maxPage) {
      return
    }
    state.query.page += 1
    fetchEtfList()
  })

  els.periodBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      const p = btn.dataset.period
      if (!p || p === state.period) {
        return
      }
      state.period = p
      els.periodBtns.forEach((x) => x.classList.toggle('active', x === btn))
      if (state.selectedCode) {
        selectEtf(state.selectedCode, state.selectedName)
      }
    })
  })
}

function startAutoRefresh() {
  if (state.timer) {
    clearInterval(state.timer)
  }

  state.timer = setInterval(() => {
    if (state.autoRefresh) {
      fetchEtfList()
    }
  }, 10000)
}

function initCanvasForHiDPI() {
  const ratio = Math.max(1, window.devicePixelRatio || 1)
  const cssWidth = els.canvas.clientWidth
  const cssHeight = els.canvas.clientHeight
  els.canvas.width = Math.floor(cssWidth * ratio)
  els.canvas.height = Math.floor(cssHeight * ratio)
  canvasCtx.setTransform(ratio, 0, 0, ratio, 0, 0)
}

window.addEventListener('resize', () => {
  initCanvasForHiDPI()
  if (state.selectedCode) {
    selectEtf(state.selectedCode, state.selectedName)
  }
})

async function boot() {
  bindEvents()
  initCanvasForHiDPI()
  drawEmpty('加载中...')
  await fetchEtfList()
  startAutoRefresh()
}

boot()
