# AQT — A股半自动量化监控工具

## 概述

AQT 是一个极简的 A 股量化监控工具，用于监控 2-3 只自选股，根据策略自动产生买卖信号，通过邮件和页面通知用户，用户手动在券商 App 完成交易。

适用于**没有 QMT 接口的券商**（如华安证券），或**不想全自动交易**的个人投资者。

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.13 + FastAPI |
| 前端 | 单 HTML 文件（内联 CSS + JS） |
| 数据库 | SQLite（零配置） |
| 行情数据 | akshare（免费） |
| 定时调度 | APScheduler（每 5 分钟检查策略） |
| 通知 | SMTP 邮件（支持 QQ 邮箱等） |
| 认证 | JWT + bcrypt |

## 快速开始

### 1. 安装依赖

```bash
cd aqt
python -m venv .venv
source .venv/Scripts/activate   # Windows
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
JWT_SECRET=改成随机字符串
JWT_EXPIRE_HOURS=168

# QQ 邮箱 SMTP（用于接收交易信号通知）
SMTP_HOST=smtp.qq.com
SMTP_PORT=587
SMTP_USER=你的QQ邮箱@qq.com
SMTP_PASSWORD=你的SMTP授权码
```

> QQ 邮箱 SMTP 授权码获取：QQ 邮箱 → 设置 → 账户 → POP3/SMTP 服务 → 开启 → 获取授权码

### 3. 启动

```bash
python run.py
```

打开浏览器访问 `http://localhost:8000`

> 首次启动会自动创建 `data.db` 数据库文件。

## 功能模块

### 看板（Dashboard）

- 持仓盈亏汇总（总浮动盈亏、未读信号数）
- 持仓明细表（股票、成本、现价、市值、浮动盈亏百分比）
- 近 20 条交易信号列表（未读信号黄底高亮，支持标记已读）
- 自选股实时行情（代码、名称、现价、涨跌幅、启用的策略）
- 每 30 秒自动刷新
- 「立即检查信号」按钮手动触发策略

### 策略管理

- 添加/删除自选股
- 为每只自选股独立配置 3 种策略：

| 策略 | 参数 | 信号方向 | 说明 |
|------|------|----------|------|
| 双均线交叉 | 短周期 / 长周期 | BUY + SELL | 短均上穿长均买入，下穿卖出 |
| 网格交易 | 网格间距% / 基准价 | BUY + SELL | 价格触及网格线发出信号 |
| 移动止损 | 回撤% / 入场价 | SELL | 价格从最高点回落 N% 止损 |

### 持仓管理

- 添加/修改/删除持仓
- 记录股数、成本价、备注

### 设置

- 配置通知邮箱
- 配置 SMTP 服务器参数

## 工作原理

```
  akshare 实时行情
        │
        ▼
  APScheduler 每 5 分钟触发
        │
        ▼
  加载自选股 → 拉日线数据 → 遍历启用策略 → evaluate()
        │
        ▼
  产生 Signal → 去重检查 → 写入 DB → 发送邮件
        │
        ▼
  前端 30s 轮询 GET /api/dashboard
```

- **去重机制**：同日同股票同方向不重复发信号
- **盘中判断**：仅当日线最新日期为今天时才运行策略（周末/节假日自动跳过）
- **行情缓存**：实时行情缓存 30 秒，避免重复拉取 akshare 全市场数据

## API 文档

启动后访问 `http://localhost:8000/docs` 查看 Swagger 文档。

### 端点一览

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | /api/auth/register | 注册 | 否 |
| POST | /api/auth/login | 登录 | 否 |
| GET | /api/dashboard | 看板聚合数据 | 是 |
| GET/POST/DELETE | /api/watchlist[/{id}] | 自选股 CRUD | 是 |
| PUT | /api/watchlist/{id}/strategies | 策略参数配置 | 是 |
| GET/POST/PUT/DELETE | /api/positions[/{id}] | 持仓 CRUD | 是 |
| GET | /api/signals | 信号列表 | 是 |
| PUT | /api/signals/{id}/read | 标记已读 | 是 |
| PUT | /api/signals/read-all | 全部已读 | 是 |
| GET/PUT | /api/settings | 用户设置 | 是 |
| POST | /api/check-now | 立即运行策略 | 是 |

## 项目结构

```
aqt/
├── run.py                          # 启动入口
├── requirements.txt                # Python 依赖
├── .env.example                    # 环境变量模板
├── test_integration.py             # 集成测试脚本
├── static/
│   └── index.html                  # 前端界面（单文件）
└── aqt/
    ├── main.py                     # FastAPI 主入口、路由、调度器
    ├── config.py                   # 配置读取
    ├── database.py                 # SQLAlchemy 引擎
    ├── models.py                   # ORM 模型（User/Watchlist/Position/Signal）
    ├── schemas.py                  # Pydantic 请求/响应模型
    ├── auth.py                     # JWT 认证 + bcrypt 密码哈希
    ├── data_fetcher.py             # akshare 行情数据封装
    ├── engine.py                   # 策略执行引擎
    ├── notifier.py                 # SMTP 邮件发送
    └── strategies/
        ├── base.py                 # 策略基类
        ├── ma_cross.py             # 双均线交叉策略
        ├── grid.py                 # 网格交易策略
        └── trailing_stop.py        # 移动止损策略
```

## 数据库表结构

| 表 | 字段 | 说明 |
|---|---|---|
| users | id, username, password_hash, email, smtp_*, created_at | 用户及通知配置 |
| watchlist | id, user_id, symbol, name, strategy_params(JSON) | 自选股及策略参数 |
| positions | id, user_id, symbol, shares, avg_cost, note | 持仓记录 |
| signals | id, user_id, symbol, strategy, direction, price, reason, is_read | 交易信号日志 |

## 注意事项

- akshare 的 `stock_zh_a_spot_em()` 接口每次拉取全市场约 5800 只股票，约需 60-90 秒。已内置 30 秒缓存优化。
- 策略仅在交易日产生信号（通过检查最新日线日期是否为今日判断）。
- 每天每只股票的每个策略最多产生 1 个同方向信号（去重）。
- 移动止损策略的 `highest_since_entry` 会自动更新并持久化到数据库。
- 邮件通知依赖 `.env` 中的 SMTP 配置，未配置时信号仍会记录但不会发邮件。

## 后续升级方向

- 策略回测功能
- 接 QMT/XTP 实现自动交易
- WebSocket 实时推送替代轮询
- 移动端适配
- 多策略组合（或/且逻辑）
