"""
Run daily via Windows Task Scheduler.
Sends follow-up emails for unpaid invoices at 7, 14, and 30 days past due.
"""
import os
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.text import MIMEText
from dotenv import load_dotenv
import qb_api

load_dotenv()

SMTP_EMAIL = os.getenv('SMTP_EMAIL', 'info@glamourupholstery.com')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
REMINDER_DAYS = {7, 14, 30}


def days_overdue(due_date_str):
    try:
        due = datetime.strptime(due_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - due).days
    except Exception:
        return 0


def build_message(client_name, invoice_num, amount, days):
    if days <= 7:
        subject = f"Invoice #{invoice_num} — Friendly Reminder"
        body = (
            f"Hi {client_name},\n\n"
            f"Just a friendly reminder that invoice #{invoice_num} "
            f"for ${amount:,.2f} is coming due. Please let us know if you have any questions.\n\n"
            f"Thank you for your business!\n\n"
            f"Fabian Bueno\nGlamour Upholstery\n"
            f"609-880-6476\ninfo@glamourupholstery.com"
        )
    elif days <= 14:
        subject = f"Invoice #{invoice_num} — Past Due Notice"
        body = (
            f"Hi {client_name},\n\n"
            f"Invoice #{invoice_num} for ${amount:,.2f} is now {days} days past due. "
            f"Please arrange payment at your earliest convenience.\n\n"
            f"If you have already sent payment, please disregard this notice.\n\n"
            f"Fabian Bueno\nGlamour Upholstery\n"
            f"609-880-6476\ninfo@glamourupholstery.com"
        )
    else:
        subject = f"Invoice #{invoice_num} — Immediate Attention Required"
        body = (
            f"Hi {client_name},\n\n"
            f"Invoice #{invoice_num} for ${amount:,.2f} is now {days} days past due. "
            f"Please contact us immediately to resolve this balance.\n\n"
            f"Fabian Bueno\nGlamour Upholstery\n"
            f"609-880-6476\ninfo@glamourupholstery.com"
        )
    return subject, body


def send_email(to, subject, body):
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = SMTP_EMAIL
    msg['To'] = to
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=15) as server:
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.send_message(msg)


def run():
    if not SMTP_PASSWORD:
        print('SMTP_PASSWORD not set in .env — skipping reminders.')
        sys.exit(0)

    invoices = qb_api.get_unpaid_invoices()
    sent = 0

    for inv in invoices:
        due_date = inv.get('DueDate')
        if not due_date:
            continue

        days = days_overdue(due_date)
        if days not in REMINDER_DAYS:
            continue

        client_name = inv.get('CustomerRef', {}).get('name', 'Customer')
        invoice_num = inv.get('DocNumber', 'N/A')
        amount = float(inv.get('Balance', 0))
        email = inv.get('BillEmail', {}).get('Address')

        if not email:
            print(f"  Invoice #{invoice_num} — no email on file, skipping.")
            continue

        subject, body = build_message(client_name, invoice_num, amount, days)
        try:
            send_email(email, subject, body)
            print(f"  Sent {days}-day reminder to {email} for invoice #{invoice_num} (${amount:,.2f})")
            sent += 1
        except Exception as e:
            print(f"  Failed to send to {email}: {e}")

    print(f"\nDone. {sent} reminder(s) sent.")


if __name__ == '__main__':
    run()
