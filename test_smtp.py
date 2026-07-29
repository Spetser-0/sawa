import smtplib
from email.mime.text import MIMEText

MAIL_USERNAME = "spetser898@gmail.com"
MAIL_PASSWORD = "iwieeueiootubmf"  # الـ 16 حرف بدون مسافات
MAIL_SERVER = "smtp.gmail.com"
MAIL_PORT = 587

msg = MIMEText("هذا إيميل تجريبي من Sawa")
msg["Subject"] = "Test Email"
msg["From"] = MAIL_USERNAME
msg["To"] = MAIL_USERNAME  # أرسل لنفسك للتجربة

try:
    with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as server:
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.send_message(msg)
    print("✅ نجح الإرسال")
except Exception as e:
    print(f"❌ فشل: {e}")