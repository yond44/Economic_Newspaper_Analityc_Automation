import re
from datetime import datetime

def clean_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()

def truncate_text(text: str, max_length: int = 500, suffix: str = "...") -> str:
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix

def format_date(date_str: str = None) -> str:
    if date_str:
        try:
            dt = datetime.fromisoformat(date_str)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            pass
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")