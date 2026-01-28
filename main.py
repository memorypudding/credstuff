import argparse
import sys
import importlib
import inspect
from termcolor import colored
import runner

def load_module(module_name):
    mod = None
    # 1. Try finding it inside the 'modules' folder first
    try:
        import_name = f"modules.{module_name}" if not module_name.startswith("modules.") else module_name
        mod = importlib.import_module(import_name)
    except ImportError:
        pass

    # 2. Fallback: Try finding it in the root folder
    if not mod:
        try:
            mod = importlib.import_module(module_name)
        except ImportError:
            pass

    if not mod:
        print(colored(f"[!] Could not import module '{module_name}'", "red"))
        print(colored("    Ensure the file exists in 'modules/' or the root folder.", "yellow"))
        sys.exit(1)

    # 3. Smart Discovery: Find the main coroutine (async function)
    # This automatically picks 'matsunoya_login', 'mcdonalds_login', 'interface', etc.
    candidate = None
    for name, obj in inspect.getmembers(mod, inspect.iscoroutinefunction):
        # We only want functions defined IN this module, not imported ones like aiohttp.request
        if obj.__module__ == mod.__name__:
            candidate = obj
            break
    
    if candidate:
        return candidate
    
    # 4. Fallback for legacy hardcoded names if inspection fails
    if hasattr(mod, 'matsunoya_login'): return getattr(mod, 'matsunoya_login')
    if hasattr(mod, 'login'): return getattr(mod, 'login')
    if hasattr(mod, 'interface'): return getattr(mod, 'interface')

    print(colored(f"[!] Module loaded, but no entry function found in '{module_name}'.", "red"))
    print(colored("    Make sure your module has an async function defined.", "yellow"))
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Universal Module Runner")
    
    # Core
    parser.add_argument("-m", "--module", required=True, help="Module name (without .py)")
    parser.add_argument("-c", "--combo", required=True, help="Path to combo file")
    
    # Proxy Logic
    parser.add_argument("-p", "--proxy", help="Path to proxy file (Rotation List)")
    parser.add_argument("-t", "--type", default="socks5", help="Proxy type (http/socks4/socks5)")
    parser.add_argument("-r", "--route", help="Global Route Override (e.g. http://127.0.0.1:8080)")
    
    # Config
    parser.add_argument("-o", "--output", default="hits.txt", help="Output file")
    parser.add_argument("-th", "--threads", type=int, default=100, help="Thread count")

    args = parser.parse_args()
    
    # Load function dynamically
    func = load_module(args.module)
    
    # Mode Feedback
    if args.route:
        print(colored(f"[!] ROUTE OVERRIDE: All traffic tunneling through {args.route}", "yellow"))
    elif not args.proxy:
        print(colored("[!] PROXYLESS MODE: Running without proxies.", "red"))

    engine = runner.ModuleRunner(
        module=func,
        combo=args.combo,
        proxyless=(not args.proxy and not args.route),
        proxy_file=args.proxy,
        proxy_type=args.type,
        global_route=args.route,
        output=args.output,
        threads=args.threads
    )
    
    engine.start()

if __name__ == "__main__":
    main()