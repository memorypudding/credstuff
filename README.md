# credstuff

An asynchronous, modular credential stuffer designed for high concurrency and flexibility.

## Features

* **Modular Architecture:** Plug-and-play support for different target modules. No code changes required in the core runner.

* **Universal Loader:** Automatically detects async entry points in new modules via inspection.

* **Resumable:** Automatic checkpoint system saves progress in real-time (`.progress` files).

* **Smart Routing:** Supports standard proxy rotation (SOCKS4/5, HTTP) or global routing (e.g., Burp Suite) for debugging.

* **Grid Output:** Clean, aligned console output with color-coded custom stats.

## Installation

1. Clone the repository:

   ```
   git clone https://github.com/memorypudding/credstuff.git
   cd credstuff
   ```

2. Install dependencies:

   ```
   pip3 install -r requirements.txt
   ```

## Usage

### Standard Attack (Proxy Rotation)

Running a module with a list of proxies and 100 threads:

```
python3 main.py -m netflix -c combos.txt -p proxies.txt -t socks5 -th 100
```

### Debug Mode (Global Route)

Forcing all traffic through a local proxy (e.g., Burp Suite) to inspect payloads. This automatically disables SSL verification for the runner:

```
python3 main.py -m netflix -c combos.txt -r http://127.0.0.1:8080
```

## Arguments

| Flag | Description | Default | 
| :--- | :--- | :--- | 
| `-m`, `--module` | Name of the module file in `modules/` (without .py) | **Required** | 
| `-c`, `--combo` | Path to the `email:pass` combo file | **Required** | 
| `-p`, `--proxy` | Path to proxy list (IP:Port or User:Pass@IP:Port) | `None` | 
| `-t`, `--type` | Proxy protocol (`http`, `socks4`, `socks5`) | `socks5` | 
| `-r`, `--route` | Global route override (e.g., `http://127.0.0.1:8080`) | `None` | 
| `-th`, `--threads` | Number of concurrent workers | `100` | 
| `-o`, `--output` | File to save valid hits | `hits.txt` | 

## Creating Modules

Create a new file in the `modules/` folder (e.g., `target.py`). The runner will automatically find any async function within it.

Use the provided `modules/template.py` as a base. Your function must accept a `session` and return an integer status or a tuple:

* `0` or `(0, "Stats")`: **HIT** (Success)

* `1`: **FAIL** (Invalid Credentials)

* `2`: **RETRY** (Ban, Captcha, Error)

Example structure:

```python
async def login(session, email, password, proxy):
    # Logic here
    if success:
        return 0, "Plan: Premium | Points: 500"
    return 1
```

## Disclaimer

This tool is for educational purposes and authorized security testing only. The developer is not responsible for any misuse of this software.
