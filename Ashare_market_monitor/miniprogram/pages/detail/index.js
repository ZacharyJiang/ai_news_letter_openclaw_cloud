const { request } = require('../../utils/api')

const PERIOD_OPTIONS = [
  { label: '日K', value: 'day' },
  { label: '周K', value: 'week' },
  { label: '月K', value: 'month' }
]

Page({
  data: {
    code: '',
    name: '',
    loading: false,
    error: '',

    periodIndex: 0,
    periodOptions: PERIOD_OPTIONS,

    stats: {
      ath: null,
      atl: null,
      drawdown_from_ath_pct: null,
      rebound_from_atl_pct: null
    },
    bars: [],

    canvasWidth: 355,
    canvasHeight: 260
  },

  onLoad(options) {
    const code = (options.code || '').trim()
    const name = decodeURIComponent(options.name || '')

    if (!code) {
      wx.showToast({ title: '参数错误', icon: 'none' })
      return
    }

    wx.setNavigationBarTitle({ title: `${name || code} K线` })

    const windowWidth = wx.getSystemInfoSync().windowWidth
    this.setData(
      {
        code,
        name,
        canvasWidth: windowWidth - 24,
        canvasHeight: 300
      },
      () => this.fetchKline()
    )
  },

  async fetchKline() {
    const code = this.data.code
    const period = PERIOD_OPTIONS[this.data.periodIndex].value

    this.setData({ loading: true, error: '' })

    try {
      const res = await request({
        url: `/api/etfs/${code}/kline`,
        data: { period }
      })

      this.setData(
        {
          loading: false,
          bars: res.bars || [],
          stats: {
            ath: res.ath,
            atl: res.atl,
            drawdown_from_ath_pct: res.drawdown_from_ath_pct,
            rebound_from_atl_pct: res.rebound_from_atl_pct
          }
        },
        () => this.drawKline()
      )
    } catch (err) {
      this.setData({
        loading: false,
        error: err.message || '加载失败',
        bars: []
      })
      this.drawEmpty()
    }
  },

  onPeriodChange(e) {
    this.setData({ periodIndex: Number(e.detail.value) }, () => this.fetchKline())
  },

  formatPrice(v) {
    return Number(v || 0).toFixed(3)
  },

  computeMA(closes, period) {
    const out = []
    for (let i = 0; i < closes.length; i += 1) {
      if (i + 1 < period) {
        out.push(null)
        continue
      }
      let sum = 0
      for (let j = i - period + 1; j <= i; j += 1) {
        sum += closes[j]
      }
      out.push(sum / period)
    }
    return out
  },

  drawEmpty() {
    const ctx = wx.createCanvasContext('klineCanvas', this)
    const { canvasWidth, canvasHeight } = this.data
    ctx.setFillStyle('#ffffff')
    ctx.fillRect(0, 0, canvasWidth, canvasHeight)
    ctx.setFillStyle('#94a3b8')
    ctx.setFontSize(14)
    ctx.fillText('暂无K线数据', canvasWidth / 2 - 50, canvasHeight / 2)
    ctx.draw()
  },

  drawKline() {
    const { bars, canvasWidth, canvasHeight } = this.data
    if (!bars || bars.length === 0) {
      this.drawEmpty()
      return
    }

    // Keep recent candles to maintain readability.
    const showBars = bars.slice(-120)
    const highs = showBars.map((b) => b.high)
    const lows = showBars.map((b) => b.low)
    const closes = showBars.map((b) => b.close)

    let maxPrice = Math.max(...highs)
    let minPrice = Math.min(...lows)
    if (maxPrice <= minPrice) {
      maxPrice = minPrice + 1
    }

    const paddingRate = 0.03
    const priceSpan = maxPrice - minPrice
    maxPrice += priceSpan * paddingRate
    minPrice -= priceSpan * paddingRate

    const margin = {
      left: 48,
      right: 14,
      top: 20,
      bottom: 34
    }

    const plotWidth = canvasWidth - margin.left - margin.right
    const plotHeight = canvasHeight - margin.top - margin.bottom
    const stepX = plotWidth / showBars.length
    const candleWidth = Math.max(2, stepX * 0.62)

    const toY = (price) => {
      const ratio = (maxPrice - price) / (maxPrice - minPrice)
      return margin.top + ratio * plotHeight
    }

    const ctx = wx.createCanvasContext('klineCanvas', this)

    // background
    ctx.setFillStyle('#ffffff')
    ctx.fillRect(0, 0, canvasWidth, canvasHeight)

    // grid
    ctx.setStrokeStyle('#e2e8f0')
    ctx.setLineWidth(1)
    for (let i = 0; i <= 4; i += 1) {
      const y = margin.top + (plotHeight / 4) * i
      ctx.beginPath()
      ctx.moveTo(margin.left, y)
      ctx.lineTo(canvasWidth - margin.right, y)
      ctx.stroke()

      const price = maxPrice - ((maxPrice - minPrice) / 4) * i
      ctx.setFillStyle('#64748b')
      ctx.setFontSize(10)
      ctx.fillText(this.formatPrice(price), 4, y + 3)
    }

    // axis line
    ctx.setStrokeStyle('#94a3b8')
    ctx.beginPath()
    ctx.moveTo(margin.left, margin.top)
    ctx.lineTo(margin.left, canvasHeight - margin.bottom)
    ctx.lineTo(canvasWidth - margin.right, canvasHeight - margin.bottom)
    ctx.stroke()

    // MA lines
    const ma5 = this.computeMA(closes, 5)
    const ma10 = this.computeMA(closes, 10)

    const drawLine = (arr, color) => {
      ctx.setStrokeStyle(color)
      ctx.setLineWidth(1)
      let started = false
      for (let i = 0; i < arr.length; i += 1) {
        const v = arr[i]
        if (v === null) {
          continue
        }
        const x = margin.left + stepX * i + stepX / 2
        const y = toY(v)
        if (!started) {
          ctx.beginPath()
          ctx.moveTo(x, y)
          started = true
        } else {
          ctx.lineTo(x, y)
        }
      }
      if (started) {
        ctx.stroke()
      }
    }

    drawLine(ma5, '#2563eb')
    drawLine(ma10, '#f59e0b')

    // Candles
    for (let i = 0; i < showBars.length; i += 1) {
      const bar = showBars[i]
      const x = margin.left + stepX * i + stepX / 2

      const openY = toY(bar.open)
      const closeY = toY(bar.close)
      const highY = toY(bar.high)
      const lowY = toY(bar.low)

      const rise = bar.close >= bar.open
      const color = rise ? '#d92d20' : '#0b8f55'

      // wick
      ctx.setStrokeStyle(color)
      ctx.setLineWidth(1)
      ctx.beginPath()
      ctx.moveTo(x, highY)
      ctx.lineTo(x, lowY)
      ctx.stroke()

      // body
      const bodyTop = Math.min(openY, closeY)
      const bodyHeight = Math.max(Math.abs(closeY - openY), 1)
      ctx.setFillStyle(color)
      ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight)
    }

    // x labels
    const firstDate = showBars[0].date
    const midDate = showBars[Math.floor(showBars.length / 2)].date
    const lastDate = showBars[showBars.length - 1].date
    ctx.setFillStyle('#64748b')
    ctx.setFontSize(10)
    ctx.fillText(firstDate, margin.left, canvasHeight - 10)
    ctx.fillText(midDate, canvasWidth / 2 - 25, canvasHeight - 10)
    ctx.fillText(lastDate, canvasWidth - margin.right - 70, canvasHeight - 10)

    // legend
    ctx.setFillStyle('#334155')
    ctx.setFontSize(10)
    ctx.fillText('MA5', margin.left + 4, 12)
    ctx.setFillStyle('#2563eb')
    ctx.fillRect(margin.left + 26, 6, 14, 2)
    ctx.setFillStyle('#334155')
    ctx.fillText('MA10', margin.left + 46, 12)
    ctx.setFillStyle('#f59e0b')
    ctx.fillRect(margin.left + 76, 6, 14, 2)

    ctx.draw()
  }
})
