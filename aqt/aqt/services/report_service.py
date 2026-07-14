from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html import escape

from sqlalchemy.orm import Session

from ..config import Settings
from ..models import NotificationLog, Signal, User
from ..notifier import send_email
from .dashboard_service import build_dashboard


@dataclass
class ReportDeliveryResult:
    attempted: bool
    success: bool
    reason: str = ""


def user_mail_settings(user: User) -> Settings:
    return Settings(
        smtp_host=user.smtp_host or Settings.smtp_host,
        smtp_port=user.smtp_port or Settings.smtp_port,
        smtp_user=user.smtp_user or "",
        smtp_password=user.smtp_password or "",
    )


def _today_window() -> tuple[datetime, datetime]:
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _today_signals(user_id: int, db: Session) -> list[Signal]:
    start, end = _today_window()
    return (
        db.query(Signal)
        .filter(
            Signal.user_id == user_id,
            Signal.created_at >= start,
            Signal.created_at < end,
        )
        .order_by(Signal.created_at.desc())
        .all()
    )


def build_market_close_report(user: User, db: Session, report_date: date | None = None) -> dict:
    report_date = report_date or date.today()
    dashboard = build_dashboard(user, db)["data"]
    signals = _today_signals(user.id, db)

    positions = dashboard["positions"]
    sorted_positions = sorted(
        positions,
        key=lambda item: abs(float(item.get("unrealized_pnl") or 0)),
        reverse=True,
    )
    top_positions = sorted_positions[:5]

    highlights: list[str] = []
    if dashboard["total_pnl"] > 0:
        highlights.append("总持仓当前为浮盈状态")
    elif dashboard["total_pnl"] < 0:
        highlights.append("总持仓当前仍处于浮亏状态")
    if signals:
        highlights.append(f"今日新增 {len(signals)} 条策略信号")
    sell_count = sum(1 for signal in signals if signal.direction == "SELL")
    if sell_count:
        highlights.append(f"其中包含 {sell_count} 条 SELL 信号，需关注减仓或止损风险")
    if not highlights:
        highlights.append("今日未发现新的结构化风险提示")

    return {
        "date": report_date.strftime("%Y-%m-%d"),
        "total_pnl": round(float(dashboard["total_pnl"]), 2),
        "positions": top_positions,
        "signals": [
            {
                "symbol": signal.symbol,
                "direction": signal.direction,
                "strategy": signal.strategy,
                "reason": signal.reason,
                "created_at": signal.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for signal in signals
        ],
        "highlights": highlights,
    }


def render_market_close_report_text(report: dict) -> str:
    lines = [
        f"[AQT 收盘简报] {report['date']}",
        "",
        f"今日总浮盈：{report['total_pnl']:+.2f}",
        "------------------------------",
        "持仓摘要:",
    ]

    if report["positions"]:
        for position in report["positions"]:
            lines.append(
                f"  {position['symbol']} 现价 {position['last_price']:.2f} / 浮盈 {position['unrealized_pnl']:+.2f} ({position['pnl_pct']:+.2f}%)"
            )
    else:
        lines.append("  暂无持仓")

    lines.append("")
    lines.append("今日信号:")
    if report["signals"]:
        for signal in report["signals"]:
            lines.append(
                f"  {signal['symbol']} {signal['direction']} [{signal['strategy']}] {signal['reason']}"
            )
    else:
        lines.append("  今日无新增信号")

    lines.append("")
    lines.append("重点观察:")
    for highlight in report["highlights"]:
        lines.append(f"  - {highlight}")

    return "\n".join(lines)


def render_market_close_report_html(report: dict) -> str:
    position_rows = "".join(
        (
            "<tr>"
            f"<td>{escape(position['symbol'])}</td>"
            f"<td>{float(position['last_price']):.2f}</td>"
            f"<td>{float(position['unrealized_pnl']):+.2f}</td>"
            f"<td>{float(position['pnl_pct']):+.2f}%</td>"
            "</tr>"
        )
        for position in report["positions"]
    ) or "<tr><td colspan='4'>暂无持仓</td></tr>"

    signal_rows = "".join(
        (
            "<li>"
            f"{escape(signal['symbol'])} "
            f"{escape(signal['direction'])} "
            f"[{escape(signal['strategy'])}] "
            f"{escape(signal['reason'])}"
            "</li>"
        )
        for signal in report["signals"]
    ) or "<li>今日无新增信号</li>"

    highlight_rows = "".join(f"<li>{escape(item)}</li>" for item in report["highlights"])

    return f"""
<html>
  <body style="font-family:Segoe UI,Arial,sans-serif;color:#222;line-height:1.5">
    <h2>[AQT 收盘简报] {escape(report["date"])}</h2>
    <p><strong>今日总浮盈：</strong>{report["total_pnl"]:+.2f}</p>
    <h3>持仓摘要</h3>
    <table style="border-collapse:collapse;min-width:520px">
      <thead>
        <tr>
          <th style="border:1px solid #ddd;padding:8px;text-align:left">代码</th>
          <th style="border:1px solid #ddd;padding:8px;text-align:left">现价</th>
          <th style="border:1px solid #ddd;padding:8px;text-align:left">浮盈</th>
          <th style="border:1px solid #ddd;padding:8px;text-align:left">收益率</th>
        </tr>
      </thead>
      <tbody>{position_rows}</tbody>
    </table>
    <h3>今日信号</h3>
    <ul>{signal_rows}</ul>
    <h3>重点观察</h3>
    <ul>{highlight_rows}</ul>
  </body>
</html>
""".strip()


def log_notification(db: Session, user_id: int, success: bool, recipient: str, subject: str, body: str, error: str = ""):
    log = NotificationLog(
        user_id=user_id,
        ntype="email",
        recipient=recipient,
        subject=subject[:256],
        body_snippet=body[:256] if body else "",
        success=1 if success else 0,
        error_msg=error[:256] if error else "",
    )
    db.add(log)


def send_market_close_report(user: User, db: Session, report_date: date | None = None) -> ReportDeliveryResult:
    if not user.email:
        return ReportDeliveryResult(attempted=False, success=False, reason="missing email")

    mail_settings = user_mail_settings(user)
    if not mail_settings.smtp_user or not mail_settings.smtp_password:
        return ReportDeliveryResult(attempted=False, success=False, reason="missing smtp credentials")

    report = build_market_close_report(user, db, report_date=report_date)
    subject = f"[AQT 收盘简报] {report['date']}"
    text_body = render_market_close_report_text(report)
    html_body = render_market_close_report_html(report)

    ok = send_email(mail_settings, user.email, subject, text_body, html_body=html_body)
    log_notification(db, user.id, ok, user.email, subject, text_body, "" if ok else "send failed")
    return ReportDeliveryResult(attempted=True, success=ok, reason="" if ok else "send failed")
