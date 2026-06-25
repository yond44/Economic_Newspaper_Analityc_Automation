import os
import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
EMAIL_FILE = PROJECT_ROOT / "data" / "email_contacts.json"

EMAIL_FILE.parent.mkdir(parents=True, exist_ok=True)


def initialize_email_file():
    if not EMAIL_FILE.exists():
        default_contacts = [
            {
                "id": 1,
                "name": "Yonda Ekodirman",
                "email": "yondaekodirman@gmail.com"
            }
        ]
        with open(EMAIL_FILE, 'w') as f:
            json.dump(default_contacts, f, indent=2)
        logger.info(f"✅ Created email file with {len(default_contacts)} contacts")
        return default_contacts
    return get_all_emails()


def get_all_emails() -> List[Dict[str, Any]]:
    if not EMAIL_FILE.exists():
        return initialize_email_file()
    
    with open(EMAIL_FILE, 'r') as f:
        return json.load(f)


def get_email_by_id(email_id: int) -> Optional[Dict[str, Any]]:
    emails = get_all_emails()
    for email in emails:
        if email.get("id") == email_id:
            return email
    return None


def add_email(name: str, email: str) -> Dict[str, Any]:
    emails = get_all_emails()
    new_id = max([e.get("id", 0) for e in emails]) + 1 if emails else 1
    
    new_contact = {
        "id": new_id,
        "name": name.strip(),
        "email": email.strip()
    }
    
    emails.append(new_contact)
    
    with open(EMAIL_FILE, 'w') as f:
        json.dump(emails, f, indent=2)
    
    logger.info(f"✅ Added email: {name} ({email})")
    return new_contact


def update_email(email_id: int, name: str, email: str) -> Optional[Dict[str, Any]]:
    emails = get_all_emails()
    
    for i, contact in enumerate(emails):
        if contact.get("id") == email_id:
            emails[i] = {
                "id": email_id,
                "name": name.strip(),
                "email": email.strip()
            }
            
            with open(EMAIL_FILE, 'w') as f:
                json.dump(emails, f, indent=2)
            
            logger.info(f"✅ Updated email: {name} ({email})")
            return emails[i]
    
    return None


def delete_email(email_id: int) -> bool:
    emails = get_all_emails()
    
    for i, contact in enumerate(emails):
        if contact.get("id") == email_id:
            deleted = emails.pop(i)
            
            with open(EMAIL_FILE, 'w') as f:
                json.dump(emails, f, indent=2)
            
            logger.info(f"✅ Deleted email: {deleted.get('name')} ({deleted.get('email')})")
            return True
    
    return False


def get_email_list() -> List[str]:
    emails = get_all_emails()
    return [e.get("email") for e in emails if e.get("email")]


def get_email_string() -> str:
    return ", ".join(get_email_list())


def reset_email_file():
    if EMAIL_FILE.exists():
        EMAIL_FILE.unlink()
    return initialize_email_file()


def get_email_count() -> int:
    return len(get_all_emails())


def get_file_paths() -> dict:
    return {
        "email_file": str(EMAIL_FILE),
        "email_file_exists": EMAIL_FILE.exists()
    }