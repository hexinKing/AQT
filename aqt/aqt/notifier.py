import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from .config import Settings


def send_email(settings: Settings, to_email: str, subject: str, body: str) -> bool:
    """Send email via SMTP. Returns True on success."""
    if not settings.smtp_user or not settings.smtp_password:
        return False

    msg = MIMEMultipart()
    msg["From"] = settings.smtp_user
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.smtp_user, [to_email], msg.as_string())
        server.quit()
        return True
    except Exception:
        return False
