"""邮箱推送（推到你的邮箱）。用 SMTP，配置在 .env / config/settings.json。

邮箱地址由你后补（EMAIL_TO）。未配置则只打印不推送。
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send(results: list[dict], email_cfg: dict) -> bool:
    to = email_cfg.get("to") or os.getenv("EMAIL_TO", "")
    if not to:
        print("[email] 未配置 EMAIL_TO，跳过推送（在 .env 补上即可）。")
        return False
    host = email_cfg.get("smtp_host") or os.getenv("SMTP_HOST", "smtp.qq.com")
    port = int(email_cfg.get("smtp_port") or os.getenv("SMTP_PORT", 465))
    user = email_cfg.get("smtp_user") or os.getenv("SMTP_USER", "")
    pwd = email_cfg.get("smtp_pass") or os.getenv("SMTP_PASS", "")
    if not user or not pwd:
        print("[email] 未配置 SMTP 账号密码，跳过推送。")
        return False

    subject = f"[聪明钱雷达] {len(results)} 个高确定性信号"
    body = format_body(results)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.attach(MIMEText(body, "html", "utf-8"))

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as s:
                s.login(user, pwd)
                s.sendmail(user, [to], msg.as_string())
        else:
            with smtplib.SMTP(host, port) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(user, pwd)
                s.sendmail(user, [to], msg.as_string())
        print(f"[email] 已推送到 {to}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[email] 发送失败: {e}")
        return False


def format_body(results: list[dict]) -> str:
    rows = ""
    for r in results:
        tk = r["token"]
        reasons = "<br>".join("· " + x for x in r["social"]["reasons"]) or "—"
        mcap_k = f"${float(tk.get('market_cap') or 0) / 1000:.0f}K"
        rows += (
            f"<tr><td>{tk.get('chain', '?')}</td>"
            f"<td><a href='{tk.get('url', '#')}'>{tk.get('symbol', '?')}</a></td>"
            f"<td>{mcap_k}</td>"
            f"<td>{tk.get('smart_buy', 0)}/{tk.get('smart_sell', 0)}</td>"
            f"<td><b>{r['score']['score']}</b></td>"
            f"<td>{reasons}</td></tr>"
        )
    return f"""<html><body>
<h2>聪明钱雷达 · 高确定性信号</h2>
<table border="1" cellpadding="6" cellspacing="0">
<tr><th>链</th><th>代币</th><th>市值</th><th>聪明钱买/卖</th><th>总分</th><th>为什么涨</th></tr>
{rows}
</table>
<p>策略：注意力/聪明钱强 + 市值低 + 合约安全 = 小亏大赚。非投资建议。</p>
</body></html>"""
