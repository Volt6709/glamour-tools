import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

SMTP_EMAIL = os.getenv('SMTP_EMAIL', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')


def _send(to_email, subject, body):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f'Fabian Bueno — Glamour Upholstery <{SMTP_EMAIL}>'
    msg['To'] = to_email
    msg.attach(MIMEText(body, 'plain'))
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=15) as server:
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.send_message(msg)


def is_configured():
    return bool(SMTP_EMAIL and SMTP_PASSWORD)


def send_cold_email(lead):
    name = lead['name'].split()[0] if lead['name'] else 'there'
    firm = lead['firm'] or 'your studio'
    subject = "Custom upholstery work for your clients — NJ/NYC"
    body = f"""Hi {name},

I came across {firm} and wanted to reach out. I'm Fabian, owner of Glamour Upholstery — we do custom reupholstery and fabric work for residential and commercial clients across New Jersey and New York City.

A lot of designers we work with send us pieces their clients want restored or reupholstered — sofas, dining chairs, headboards, ottomans. We handle everything: fabric sourcing, custom cuts, and fast turnaround (standard jobs in 2–4 days).

If you ever have clients who need upholstery work, I'd love to be your go-to. Happy to share our portfolio or hop on a quick call.

Fabian Bueno
Glamour Upholstery | glamourupholstery.com
609-880-6476 | info@glamourupholstery.com"""
    _send(lead['email'], subject, body)


def send_followup1(lead):
    name = lead['name'].split()[0] if lead['name'] else 'there'
    subject = "Re: Custom upholstery work for your clients"
    body = f"""Hi {name},

Just following up on my note from last week. If you have a project coming up that needs upholstery work, I'm happy to give you a quick quote — no commitment.

We work with fabrics clients bring in or help source the right material for the job.

Fabian Bueno
Glamour Upholstery
609-880-6476"""
    _send(lead['email'], subject, body)


def send_followup2(lead):
    name = lead['name'].split()[0] if lead['name'] else 'there'
    subject = "Last note — Glamour Upholstery"
    body = f"""Hi {name},

One last note in case the timing wasn't right. We're always open to working with designers on upholstery projects big or small.

If something comes up down the road, feel free to reach out directly.

Fabian Bueno
Glamour Upholstery
info@glamourupholstery.com | 609-880-6476"""
    _send(lead['email'], subject, body)
