import re
import time
from datetime import datetime
import hashlib
import json
from typing import Any

def validate_username(username: str) -> bool:
    """Validate Instagram username"""
    if not username or not isinstance(username, str):
        return False
    
    pattern = r'^[a-zA-Z0-9._]{1,30}$'
    return bool(re.match(pattern, username))

def format_count(count: int) -> str:
    """Format large numbers"""
    if count >= 1000000000:
        return f"{count/1000000000:.1f}B"
    elif count >= 1000000:
        return f"{count/1000000:.1f}M"
    elif count >= 1000:
        return f"{count/1000:.1f}K"
    else:
        return str(count)

def generate_cache_key(username: str, endpoint: str = "profile") -> str:
    """Generate cache key"""
    key_str = f"{endpoint}:{username}:{datetime.utcnow().strftime('%Y-%m-%d:%H')}"
    return hashlib.md5(key_str.encode()).hexdigest()

def safe_json_parse(json_str: str) -> Any:
    """Safely parse JSON string"""
    try:
        return json.loads(json_str)
    except:
        return None

def clean_text(text: str, max_length: int = 200) -> str:
    """Clean and truncate text"""
    if not text:
        return ""
    
    # Remove extra whitespace
    text = ' '.join(text.split())
    
    # Truncate if too long
    if len(text) > max_length:
        text = text[:max_length] + "..."
    
    return text
