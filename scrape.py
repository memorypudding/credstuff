import sys
import asyncio
import aiohttp
import re
import time
import json
import os
from termcolor import colored
from typing import List, Set, Dict
from aiohttp_socks import ProxyConnector, ProxyError, ProxyConnectionError, ProxyTimeoutError

# --- Configuration ---
TIMEOUT = 10
CHECK_URL = "http://httpbin.org/ip" # Simple connectivity check
SOURCES_FILE = "sources.json"
MAX_CONCURRENCY = 300 # Keep this reasonable (200-500) to avoid crashing your router

def usage():
    print(f"Usage: python3 {sys.argv[0]} <type> <output_file>")
    print("Types: http, socks4, socks5")
    sys.exit(1)

def load_sources() -> Dict[str, List[str]]:
    if not os.path.exists(SOURCES_FILE):
        print(colored(f"Error: {SOURCES_FILE} not found!", "red"))
        sys.exit(1)
    with open(SOURCES_FILE, 'r') as f:
        return json.load(f)

def save_sources(data: Dict[str, List[str]]):
    with open(SOURCES_FILE, 'w') as f:
        json.dump(data, f, indent=4)

async def check_source_health(session: aiohttp.ClientSession, url: str) -> bool:
    try:
        async with session.head(url, timeout=5) as response:
            if response.status == 200: return True
            if response.status == 405: 
                async with session.get(url, timeout=5) as r: return r.status == 200
    except Exception:
        return False
    return False

async def fetch_proxies_from_url(session: aiohttp.ClientSession, url: str) -> List[str]:
    try:
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                text = await response.text()
                # Regex for IP:PORT
                return re.findall(r'[0-9]+(?:\.[0-9]+){3}:[0-9]+', text)
    except Exception:
        pass
    return []

async def check_single_proxy(sem, proxy: str, ptype: str):
    """
    Checks a single proxy. 
    NOTE: We must create a new session/connector for SOCKS proxies 
    because the proxy is defined at the Connector level.
    """
    proxy_url = f"{ptype}://{proxy}"
    
    async with sem:
        try:
            # rdns=True is CRITICAL for SOCKS5 to keep you anonymous
            connector = ProxyConnector.from_url(proxy_url, rdns=True)
            
            async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as session:
                async with session.get(CHECK_URL, allow_redirects=True) as response:
                    if response.status == 200:
                        return proxy
        except (ProxyError, ProxyConnectionError, ProxyTimeoutError, asyncio.TimeoutError, OSError):
            pass 
        except Exception:
            pass 
        return None

async def main():
    if len(sys.argv) < 3: usage()

    ptype = sys.argv[1].lower()
    output_file = sys.argv[2]
    sources_data = load_sources()

    if ptype not in sources_data:
        print(colored(f"Error: Invalid proxy type '{ptype}'", "red"))
        usage()

    # --- Phase 1: Source Health ---
    print(colored("--- Phase 1: Checking Source Health ---", "cyan"))
    
    # Standard connector for checking sources (Direct connection)
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [check_source_health(session, url) for url in sources_data[ptype]]
        results = await asyncio.gather(*tasks)
        
        live_sources = [url for url, alive in zip(sources_data[ptype], results) if alive]
        dead = len(sources_data[ptype]) - len(live_sources)
        
        if dead > 0:
            print(colored(f"Removed {dead} dead sources.", "yellow"))
            sources_data[ptype] = live_sources
            save_sources(sources_data)
        else:
            print(colored("All sources healthy.", "green"))

        # --- Phase 2: Scrape ---
        print(colored(f"\n--- Phase 2: Scraping {ptype.upper()} Proxies ---", "cyan"))
        tasks = [fetch_proxies_from_url(session, url) for url in live_sources]
        results = await asyncio.gather(*tasks)
        
        found_proxies = set()
        for res in results: found_proxies.update(res)
        print(f"Scraped: {len(found_proxies)} unique proxies.")

    # --- Phase 3: Check ---
    print(colored(f"\n--- Phase 3: Checking (Timeout: {TIMEOUT}s, Concurrency: {MAX_CONCURRENCY}) ---", "cyan"))
    
    working_proxies = []
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    
    # Create tasks
    tasks = [asyncio.create_task(check_single_proxy(sem, p, ptype)) for p in found_proxies]
    
    total = len(tasks)
    completed = 0
    
    try:
        for future in asyncio.as_completed(tasks):
            result = await future
            if result:
                working_proxies.append(result)
            
            completed += 1
            # Dynamic Progress Bar
            per = int(completed/total*100)
            sys.stdout.write(f"\r[{per}%] Checked: {completed}/{total} | {colored(f'Working: {len(working_proxies)}', 'green')}")
            sys.stdout.flush()
            
    except KeyboardInterrupt:
        print(colored("\n[!] Interrupted! Saving what we found...", "yellow"))
        # Cancel pending
        for t in tasks: t.cancel()

    # --- Save ---
    print(f"\n\n{colored('Done!', 'green')} Found {len(working_proxies)} working proxies.")
    if working_proxies:
        with open(output_file, 'w') as f:
            f.write('\n'.join(working_proxies) + '\n')
        print(f"Saved to {output_file}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass