import smtplib
from email.message import EmailMessage
import os

GMAIL_USER = os.environ.get("GMAIL_USER", "doumetphilippe@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "niek jvnz nomm cgxi")

def send_alert_email(to_email: str, current_rate: float, target_rate: float, condition: str):
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("SMTP credentials not set. Skipping email.")
        return

    msg = EmailMessage()
    msg.set_content(
        f"Hello,\n\n"
        f"The USD/LBP exchange rate has crossed your threshold!\n"
        f"Current Mid Rate: {current_rate:,.2f} LBP\n"
        f"Your Alert: {condition} {target_rate:,.2f} LBP\n\n"
        f"Best,\nYour Exchange App"
    )
    msg["Subject"] = "Exchange Rate Alert Triggered!"
    msg["From"] = GMAIL_USER
    msg["To"] = to_email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        print(f"Failed to send email: {e}")

def send_otp_email(to_email: str, otp: str):
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print(f"SMTP credentials not set. MOCK OTP for {to_email}: {otp}")
        return

    msg = EmailMessage()
    msg.set_content(f"Your Security Verification Code is: {otp}\n\nThis code will expire in 5 minutes.")
    msg["Subject"] = "Your Security OTP"
    msg["From"] = GMAIL_USER
    msg["To"] = to_email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.send_message(msg)
            print(f"OTP email sent to {to_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")