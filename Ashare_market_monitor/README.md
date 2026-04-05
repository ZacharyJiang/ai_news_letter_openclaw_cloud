# WeChat ETF Mini Program (A股场内ETF)

这个项目提供：
- 后端服务：聚合 A 股场内 ETF 数据（实时行情 + 基金规模 + 费用 + 历史K线 + 历史高低点幅度）
- 微信小程序前端：支持筛选、排序、分页、自动刷新、ETF详情K线图

## 1. 功能覆盖

### 列表页
- 展示字段：
  - 基金规模（亿）
  - 现价
  - 申赎管理交易费总百分比（见下方口径）
  - 当前离历史最高点跌幅（%）
  - 当前离历史最低点涨幅（%）
- 支持筛选：
  - 基金规模区间
  - 现价区间
  - 总费率区间
  - 历史高/低点幅度区间
- 支持排序：
  - 基金规模 / 现价 / 总费率 / 幅度 / 代码
  - 升序、降序
- 自动刷新：默认每 10 秒刷新一次行情

### 详情页
- 日K/周K/月K切换
- 原生 Canvas 绘制 K 线（红涨绿跌）
- 显示历史最高/最低与对应幅度

## 2. 数据口径

### 总费率计算（%）
`申赎管理交易费总百分比 = 管理费 + 托管费 + 销售服务费 + 申购费(最小档) + 赎回费(最小档) + 交易佣金估算`

默认交易佣金估算：`0.03%`，可通过环境变量 `DEFAULT_TRADING_FEE_PCT` 调整。

## 3. 项目结构

- `backend/`：FastAPI + AkShare 数据服务
- `miniprogram/`：微信小程序代码

## 4. 后端启动

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

可选环境变量：

```bash
export DATASOURCE_QPS=2.0
export SPOT_TTL_SECONDS=15
export KLINE_TTL_SECONDS=600
export DEFAULT_TRADING_FEE_PCT=0.03
export STARTUP_SYNC_BATCH=120
export LAZY_FILL_BATCH_PER_REQUEST=20
```

## 5. 小程序接入

1. 用微信开发者工具打开 `miniprogram/`
2. 在 `miniprogram/app.js` 修改 `apiBase` 为你的后端地址
3. 在小程序后台把后端域名加入 `request 合法域名`
4. 编译运行

## 6. API 说明

### GET `/api/etfs`
筛选和排序参数：
- `keyword`
- `min_price`, `max_price`
- `min_scale`, `max_scale`
- `min_fee`, `max_fee`
- `min_distance`, `max_distance`
- `distance_mode=from_high|from_low`
- `sort_by=code|name|price|fund_scale_billion|total_fee_pct|drawdown_from_ath_pct|rebound_from_atl_pct`
- `order=asc|desc`
- `page`, `page_size`

### GET `/api/etfs/{code}/kline?period=day|week|month`
返回该 ETF 的历史 K 线和历史高低点幅度。

### POST `/api/sync`
手动触发后台元数据同步。

## 7. 频控策略（已在代码实现）

- 数据源调用统一速率限制（`DATASOURCE_QPS`）
- 实时行情缓存（`SPOT_TTL_SECONDS`）
- K 线缓存（`KLINE_TTL_SECONDS`）
- 懒加载补齐元数据，避免首次全量打满接口

## 8. 合规与风险提示

- 本项目仅用于信息展示与研究参考，不构成投资建议。
- 生产环境请确认数据源授权条款（商业使用、抓取频率、再分发限制）。
- 建议在上线前补充：鉴权、审计日志、IP 限流、异常告警、容灾策略。
