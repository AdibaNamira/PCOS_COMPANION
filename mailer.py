"""
Sends the 2FA code by email.

DEV FALLBACK, on purpose: if SMTP isn't configured in .env, the code is
printed to the server console instead of emailed, and login still works.
This means you can build and test the whole auth flow without setting up
an email account first - and it fails loudly in the log rather than
silently locking you out of your own app.

To send real email with Gmail:
  1. Enable 2-Step Verification on the Google account
  2. Create an App Password (Google Account > Security > App passwords)
  3. Put that 16-character password in .env as SMTP_PASSWORD
Your normal Gmail password will NOT work.
"""

import os
import smtplib
import ssl
from email.message import EmailMessage

try:
    import certifi
    _CA_FILE = certifi.where()
except ImportError:
    # Falls back to the system trust store. On macOS this often fails with
    # CERTIFICATE_VERIFY_FAILED unless Install Certificates.command has been
    # run for the exact interpreter in use - hence preferring certifi.
    _CA_FILE = None

from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM") or SMTP_USERNAME or "noreply@pcos-companion.local"

SUBJECT = "Your PCOS Companion login code"

BODY_TEMPLATE = """Hi,

Your login code is: {code}

It expires in 10 minutes. If you didn't try to log in, you can ignore
this email - your account is still secure.

- PCOS Companion
"""


def _is_configured():
    return bool(SMTP_USERNAME and SMTP_PASSWORD)


def send_login_code(to_email, code):
    """
    Returns (sent_by_email: bool, error_or_None).
    Never raises - a mail failure must not crash the login route.
    """
    if not _is_configured():
        print("\n" + "=" * 62)
        print(f"  [DEV MODE] SMTP not configured - not sending real email.")
        print(f"  Login code for {to_email}: {code}")
        print("=" * 62 + "\n")
        return False, None

    message = EmailMessage()
    message["Subject"] = SUBJECT
    message["From"] = SMTP_FROM
    message["To"] = to_email
    message.set_content(BODY_TEMPLATE.format(code=code))

    try:
        context = ssl.create_default_context(cafile=_CA_FILE)
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=15) as server:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(message)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                server.starttls(context=context)
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(message)
        return True, None
    except Exception as e:
        print(f"[warning] could not send login email: {e}")
        print(f"  [FALLBACK] Login code for {to_email}: {code}")
        return False, str(e)


# --- Support source alert -------------------------------------------

ALERT_SUBJECT = "{name} has asked you to check in on them"

ALERT_BODY = """Hi {contact_name},

{name} is using PCOS Companion, a support app, and has pressed a button
asking us to let you know that they would like your support right now.

They chose to send this themselves. We have not shared anything they
talked about - only that they wanted you to know.

If you can, reach out to them directly.

If you are worried about their immediate safety, these can help:
  Kaan Pete Roi (emotional support and suicide prevention helpline)
  09612-119911, open daily 3pm - 3am
  National emergency services: 999

Thank you for being someone they trust.

- PCOS Companion
(This is an automated message. Please reply directly to {name}, not to
this address.)
"""


def send_support_alert(contact_email, contact_name, patient_label):
    """
    Tells a trusted contact that the patient wants support.

    PRIVACY, deliberate: the patient's actual messages are NEVER included.
    The contact is told only that support was requested. Someone in crisis
    pressing a help button has not consented to their conversation being
    forwarded, and including it could deter them from ever pressing it.

    Returns (sent: bool, error_or_None). Never raises.
    """
    if not _is_configured():
        print("\n" + "=" * 62)
        print(f"  [DEV MODE] SMTP not configured - alert NOT actually sent.")
        print(f"  Would have emailed: {contact_email} ({contact_name})")
        print("=" * 62 + "\n")
        return False, "Email is not configured on this server."

    message = EmailMessage()
    message["Subject"] = ALERT_SUBJECT.format(name=patient_label)
    message["From"] = SMTP_FROM
    message["To"] = contact_email
    message.set_content(ALERT_BODY.format(contact_name=contact_name, name=patient_label))

    try:
        context = ssl.create_default_context(cafile=_CA_FILE)
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=15) as server:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(message)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                server.starttls(context=context)
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(message)
        return True, None
    except Exception as e:
        print(f"[warning] could not send support alert: {e}")
        return False, str(e)
