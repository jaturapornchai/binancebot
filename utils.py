"""
🛠️ Utility functions for Binance trading bot
Common helper functions and time utilities
"""

import time
from datetime import datetime, timezone, timedelta


def get_thailand_time() -> datetime:
    """
    🇹🇭 Get current Thailand time (UTC+7)
    Returns datetime object in Thailand timezone
    """
    utc_now = datetime.now(timezone.utc)
    thailand_tz = timezone(timedelta(hours=7))
    return utc_now.astimezone(thailand_tz)


def countdown_sleep(total_seconds: int, target_hour: int, reason: str = "Waiting"):
    """
    🕐 Real-time countdown display with live updates every second
    Shows dynamic countdown timer that refreshes every second until target time
    Uses Thailand time (UTC+7)
    """
    if total_seconds <= 0:
        print("⏰ Already past the target time, continuing immediately")
        return
    
    print(f"\n{reason} until {target_hour:02d}:00:00 (Thailand Time)")
    print("=" * 50)
    
    for remaining in range(int(total_seconds), 0, -1):
        minutes = remaining // 60
        seconds = remaining % 60
        hours = minutes // 60
        minutes = minutes % 60
        
        if hours > 0:
            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            time_str = f"{minutes:02d}:{seconds:02d}"
            
        print(f"\r⏰ {reason}: {time_str} remaining...", end="", flush=True)
        time.sleep(1)
    
    print("\n" + "=" * 50)


def retry_call(fn, *args, retries=3, backoff=1.5, **kwargs):
    """
    🔄 Retry function calls with exponential backoff
    Removed sleep delays per user request for no API rate limits
    """
    last_exc = None
    for i in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            # No sleep for API rate limit per user request
    if last_exc:
        raise last_exc


def format_number(num: float, decimals: int = 4) -> str:
    """Format number with specified decimal places"""
    return f"{num:.{decimals}f}"


def safe_float(value: str, default: float = 0.0) -> float:
    """Safely convert string to float with default value"""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default
