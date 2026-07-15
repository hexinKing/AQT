# AQT — A股半自动量化监控工具

半自动量化监控：软件负责**行情监控 + 策略信号 + 页面/邮件通知**，用户手动在券商 App 下单。适用于没有 QMT 接口的券商（如华安证券），监控 2-5 只自选股即可。

## 技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| 后端 | Python 3.13 + FastAPI | 轻量、自带 Swagger |
| 前端 | 单 HTML 文件（内联 CSS + JS） | 零构建、零依赖 |
| 数据库 | SQLite + SQLAlchemy (WAL) | 零配置、单文件 |
| 行情数据 | **腾讯财经** (qt.gtimg.cn) | 免费、稳定、支持前复权 |
| K 线日线 | **腾讯财经** (web.ifzq.gtimg.cn) | 前复权 OHLCV |
| 分时图 | **腾讯财经** (ifzq.gtimg.cn) | 240 分钟级数据 |
| 定时调度 | APScheduler | 策略检查每 5 分钟、数据刷新每 15 分钟 |
| 通知 | SMTP 邮件 (QQ 邮箱) | 标准库、零依赖 |
| 认证 | JWT + bcrypt | 轻量 |

## 快速开始

### 1. 安装依赖

```bash
cd aqt
python -m venv .venv

# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. 配置文件

```bash
cp .env.example .env
```

编辑 `.env`，修改 JWT_SECRET 为随机字符串即可，SMTP 可暂时留空：

```env
JWT_SECRET=改成随机字符串
```

### 3. 启动

```bash
python run.py
```

### 4. 打开浏览器

访问 **http://localhost:8000**，注册账号后即可使用。

---

## 功能概览

### 看板 (Dashboard)

- 持仓盈亏汇总（总浮动盈亏、未读信号数）
- 持仓明细（现价、市值、浮动盈亏百分比）
- 自选股实时行情：**名称、现价、涨跌幅、PE、换手率、市值**
- **30 日 sparkline 走势图**（点击弹出完整 K 线）
- 交易信号列表（未读黄底高亮、一键标记已读）
- 前端每 30 秒自动刷新
- 热点资讯仅针对自选股拉取，默认 30 分钟新闻缓存，保留来源标识并跳转原文

### K 线图 + 分时图

点击自选股的 sparkline 即可弹出：

- **日 K 蜡烛图**：前复权 OHLCV + 成交量，红涨绿跌
- **分时图**：实时价格曲线 + 昨收参考线 + 均价线 + 每分钟成交量，每 30 秒自动刷新
- ESC / 点击遮罩 / 点 ✕ 关闭

### 策略管理

| 策略 | 参数 | 方向 | 说明 |
|------|------|------|------|
| 双均线交叉 | 短周期 / 长周期 | BUY + SELL | 短均上穿买入、下穿卖出 |
| 网格交易 | 网格% / 基准价 | BUY + SELL | 价格触及网格线触发信号 |
| 移动止损 | 回撤% / 入场价 | SELL | 从最高点回落 N% 止损 |

### 持仓管理

手动维护股数、成本价、备注。⚠️ 不与券商账户自动同步，请保持与实际一致。

### 设置

配置邮箱 + SMTP 参数后，策略产生信号时自动发送邮件通知。

---

## 数据架构

```
腾讯财经 qt.gtimg.cn           腾讯财经 web.ifzq.gtimg.cn
   (实时行情)                      (K线 + 分时图)
       │                               │
       ▼                               ▼
  10秒内存缓存                    5分钟内存缓存
       │                               │
       ▼                               ▼
  ┌─────────────────────────────────────────┐
  │           /api/dashboard                 │
  │   fetch_realtime_batch()  (1次请求)      │
  │   fetch_daily()            (磁盘缓存)    │
  └─────────────────────────────────────────┘
       │
       ▼
  前端 30s 轮询 → 渲染看板 / K线 / 分时
```

### 缓存策略

| 数据类型 | 内存 TTL | 磁盘持久化 | 说明 |
|----------|----------|------------|------|
| 实时行情 | 10 秒 | 名称持久化 | 腾讯批量接口，1 次拉全部 |
| K 线日线 | 5 分钟 | `.daily_cache.json` | 腾讯前复权数据 |
| 分时图 | 60 秒 | 无 | 仅盘中有效 |

### 后台刷新

- 服务启动时：立即预热所有自选股的实时行情 + K 线
- 盘中（周一至五 9:30-15:00）：每 15 分钟自动刷新缓存
- 策略检查：每 5 分钟运行一次，仅在交易日产生信号

---

## API 端点

启动后访问 http://localhost:8000/docs 查看 Swagger 文档。

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | /api/auth/register | 注册 | - |
| POST | /api/auth/login | 登录 | - |
| GET | /api/dashboard | 看板聚合数据 | JWT |
| GET/POST/DELETE | /api/watchlist[/{id}] | 自选股 CRUD | JWT |
| PUT | /api/watchlist/{id}/strategies | 策略参数保存 | JWT |
| GET/POST/PUT/DELETE | /api/positions[/{id}] | 持仓 CRUD | JWT |
| GET | /api/signals | 信号列表 | JWT |
| PUT | /api/signals/{id}/read | 标记已读 | JWT |
| PUT | /api/signals/read-all | 全部已读 | JWT |
| GET/PUT | /api/settings | 用户设置 | JWT |
| GET | /api/kline/{symbol} | K 线日线数据 | JWT |
| GET | /api/kline/{symbol}/minute | 分时图数据 | JWT |
| POST | /api/check-now | 手动运行策略 | JWT |

---

## 项目结构

```
aqt/
├── run.py                          # 启动入口
├── requirements.txt                # Python 依赖
├── .env.example                    # 环境变量模板
├── start.bat                       # Windows 双击启动脚本
├── static/
│   └── index.html                  # 前端（单文件，Canvas 绘图）
└── aqt/
    ├── main.py                     # FastAPI 入口 + lifespan + 调度
    ├── config.py                   # 环境变量配置
    ├── database.py                 # SQLAlchemy (WAL 模式)
    ├── models.py                   # 5 张 ORM 表
    ├── schemas.py                  # Pydantic 请求/响应模型
    ├── auth.py                     # JWT + bcrypt
    ├── data_fetcher.py             # 腾讯财经 API 封装（实时/K线/分时）
    ├── engine.py                   # 策略执行引擎
    ├── risk.py                     # 风控过滤（ST/涨跌停/非交易时段）
    ├── notifier.py                 # SMTP 邮件发送
    ├── routers/
    │   ├── auth.py
    │   ├── watchlist.py
    │   ├── positions.py
    │   ├── signals.py
    │   ├── dashboard.py            # 含 K 线/分时图端点
    │   └── settings.py
    ├── services/
    │   └── dashboard_service.py    # 看板数据聚合
    └── strategies/
        ├── base.py                 # 策略基类
        ├── ma_cross.py             # 双均线交叉
        ├── grid.py                 # 网格交易
        └── trailing_stop.py        # 移动止损
```

## 数据库表

| 表 | 关键字段 | 说明 |
|---|---|---|
| users | username, password_hash, email, smtp_* | 用户及通知配置 |
| watchlist | user_id, symbol, name, strategy_params(JSON) | 自选股及策略参数 |
| positions | user_id, symbol, shares, avg_cost, note | 持仓（手动维护） |
| signals | user_id, symbol, strategy, direction, price, reason, is_read | 交易信号 |
| notification_logs | user_id, ntype, recipient, subject, success, error_msg | 通知发送追踪 |

---

## 信号产生与风控

### 流程

```
APScheduler 每 5 分钟触发
  → 遍历用户自选股
    → 拉日线数据（优先磁盘缓存）
    → 检查是否为今日数据（非交易日跳过）
    → 遍历启用的策略 → evaluate()
    → 风控检查（ST/涨跌停/非交易时段/信号上限）
    → 当日去重（同股票同方向不重复）
    → 写入 DB + 发送邮件通知
```

### 风控规则

- **交易时段过滤**：仅在 9:25-11:35 和 13:00-14:55 产生信号
- **ST/退市过滤**：名称含 ST、\*ST、NST 的股票自动跳过
- **涨跌停过滤**：触及 ±10% 时不产生同方向信号
- **单日上限**：每只股票每天最多 3 个信号
- **去重**：同日同股票同策略同方向不重复

---

## 注意事项

- **持仓数据手动维护**，不与券商账户同步，请保持与实际一致
- 分时图仅在**盘中交易时段**有数据，盘后显示"暂无分时数据"
- K 线数据自动缓存在 `.daily_cache.json`，即使 API 暂时不可用也能展示历史走势
- 邮件通知非必须项，不配置 SMTP 不影响正常使用（信号仍在页面展示）

## 后续方向

- 策略回测
- WebSocket 实时推送替代轮询
- 接入 QMT/XTP 实现自动交易
- 移动端适配
