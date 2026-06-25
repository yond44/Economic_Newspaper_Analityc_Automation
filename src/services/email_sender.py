import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import logging
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Email configuration
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))  # Default to 587 (STARTTLS)
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER)
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
USE_SSL = os.getenv("SMTP_USE_SSL", "false").lower() == "true"  # For port 465


async def send_batch_emails(
    to_emails: List[str],
    subject: str,
    body: str,
    html_body: Optional[str] = None
) -> dict:

    if not to_emails:
        return {
            "sent_count": 0,
            "failed_emails": [],
            "error": "No recipients provided"
        }
    
    if not EMAIL_ENABLED:
        logger.info(f"📧 [DISABLED] Would send to {len(to_emails)} recipients")
        for email in to_emails:
            logger.info(f"  📧 {email}")
        return {
            "sent_count": len(to_emails),
            "failed_emails": [],
            "simulated": True,
            "message": "Email sending is disabled (EMAIL_ENABLED=false)"
        }
    
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("SMTP credentials not configured - logging emails only")
        for email in to_emails:
            logger.info(f"📧 [SIMULATED] Would send to: {email}")
        return {
            "sent_count": len(to_emails),
            "failed_emails": [],
            "simulated": True,
            "message": "SMTP not configured, emails logged only"
        }
    
    sent_count = 0
    failed_emails = []
    errors = []
    server = None
    
    try:
        logger.info(f"📧 Connecting to {SMTP_HOST}:{SMTP_PORT}")
        
        if USE_SSL or SMTP_PORT == 465:
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=30)
            logger.info("✅ Using SSL connection")
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
            logger.info("✅ Using STARTTLS connection")
            
            server.ehlo()
            server.starttls()
            server.ehlo()
        
        server.login(SMTP_USER, SMTP_PASSWORD)
        logger.info("✅ SMTP Login successful")
        
        for email in to_emails:
            try:
                msg = MIMEMultipart()
                msg["From"] = FROM_EMAIL or SMTP_USER
                msg["To"] = email
                msg["Subject"] = subject
                
                if html_body:
                    msg.attach(MIMEText(html_body, "html"))
                else:
                    html_content = body.replace("\n", "<br>")
                    msg.attach(MIMEText(html_content, "html"))

                server.send_message(msg)
                sent_count += 1
                logger.info(f"✅ Email sent to: {email}")
                
            except Exception as e:
                failed_emails.append(email)
                error_msg = f"Failed to send to {email}: {str(e)}"
                errors.append(error_msg)
                logger.error(f"❌ {error_msg}")
        
        if server:
            server.quit()
            
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"❌ SMTP Authentication failed: {str(e)}")
        logger.error("   Please check your email and app password")
        return {
            "sent_count": sent_count,
            "failed_emails": to_emails[sent_count:] if sent_count < len(to_emails) else to_emails,
            "error": "SMTP Authentication failed. Check your credentials.",
            "emails": to_emails
        }
    except smtplib.SMTPException as e:
        logger.error(f"❌ SMTP error: {str(e)}")
        return {
            "sent_count": sent_count,
            "failed_emails": to_emails[sent_count:] if sent_count < len(to_emails) else to_emails,
            "error": f"SMTP error: {str(e)}",
            "emails": to_emails
        }
    except TimeoutError:
        logger.error("❌ SMTP connection timeout")
        logger.error("   Check your internet connection and firewall settings")
        return {
            "sent_count": sent_count,
            "failed_emails": to_emails[sent_count:] if sent_count < len(to_emails) else to_emails,
            "error": "Connection timeout. Check network/firewall.",
            "emails": to_emails
        }
    except Exception as e:
        logger.error(f"❌ SMTP connection error: {str(e)}")
        return {
            "sent_count": sent_count,
            "failed_emails": to_emails[sent_count:] if sent_count < len(to_emails) else to_emails,
            "error": f"Connection error: {str(e)}",
            "emails": to_emails
        }
    
    return {
        "sent_count": sent_count,
        "failed_emails": failed_emails,
        "errors": errors,
        "emails": to_emails
    }


def get_email_list_from_contacts(contacts: List[dict]) -> List[str]:
    return [c.get("email") for c in contacts if c.get("email")]