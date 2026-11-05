# OutlookRegister

[简体中文](./readme.md) | English

Outlook Account Auto-Register Tool.  
Selectors may change frequently; timeliness is not guaranteed—please test on your own.

- Human-like form filling simulation
- Automatic CAPTCHA solving
- Account registration & security email binding

---

### Quick Start

1. `pip install -r requirements.txt`
2. `python -m camoufox fetch` (Recommended if using `camoufox`)
3. `python -m ruyipage install` (If using `ruyipage`)
4. `patchright install chromium` (If using `patchright`)
5. Configure proxy, concurrency , and recovery email provider settings in `config.json`.
6. `python main.py`

---

### Configuration

| Key | Description |
| :--- | :--- |
| **`choose_browser`** | `"camoufox"`, `"patchright"`, `"playwright"`, or `"ruyipage"`. `"camoufox"` and `"ruyipage"` are recommended. |
| **`choosed_mail`** | `"moemail"` or `"outlookgraph"`. (see Note 6 if you do not want to bind a recovery email). ||
| **`email_suffix`** | `"@outlook.com"` or `"@hotmail.com"`. |
| **`bot_protection_wait`** | Wait time in seconds before submitting registration. |
| **`camoufox.browser_path`** | Leave empty to use the build installed by `camoufox fetch`. |
| **`camoufox.traffic_mode`** | Leave empty, or set to `"aggressive"` (blocks remote fonts, enables static-asset interception with a local cache). |
| **`camoufox.headless`** | Keep `false`; headless significantly lowers the pass rate. |
| **`camoufox.humanize`** | `true`, or a number (max cursor movement time in seconds). |
| **`camoufox.locale`** | Defaults to `"zh-CN"`; the registration selectors are Chinese, so changing this requires changing the selectors too. |
| **`camoufox.geoip`** | `true` derives timezone and geolocation from the proxy's exit IP (the GeoIP database is downloaded on first run). |
| **`camoufox.enable_cache`** | `true` reuses static assets across tasks to save bandwidth. |
| **`camoufox.block_images`** | Defaults to `false`. Camoufox documents that blocking images triggers detection on major WAFs, and the press CAPTCHA is one; prefer `traffic_mode` for bandwidth. |
| **`camoufox.disable_coop`** | Defaults to `false`. Disabling COOP is also WAF-detectable, and clicking the CAPTCHA inside a cross-origin iframe does not need it. |
| **`camoufox.per_task_identity`** | `true` gives every registration task its own fingerprint (navigator / screen / WebGL / fonts). |
| **`camoufox.captcha_hold`** | Max seconds to hold the CAPTCHA button, default 14; in practice the completion signal arrives after 2–4 s and the button is released early. |
| **`camoufox.os`** | Leave empty for random, or set `"windows"`, `"macos"`, `"linux"`. |
| **`camoufox.window`** | Leave empty to let Camoufox decide, or set `[1440, 900]`. A fixed window size is itself a fingerprint. |
| **`ruyipage.browser_path`** | Leave empty to resolve automatically. |
| **`ruyipage.traffic_mode`** | Leave empty, or set to `"aggressive"` . |
| **`moemail.apikey`** | API key for MoeMail. |
| **`moemail.base_url`** | Base URL of the MoeMail API. |
| **`moemail.suffix`** | Domain suffix to use. Leave empty for random selection; separate multiple domains with commas. |
| **`outlookgraph.strategy`** | `"file"` or `"single_email"`. |
| **`outlookgraph.client_id`** | Client ID for the recovery email account. |
| **`outlookgraph.single_email`** | Single recovery email config: `{ "email": "...", "refresh_token": "..." }`. |
| **`outlookgraph.file.path`** | Path to account file formatted as: `email---password---refresh_token---access_token---expire_at`. |

---

### Notes

1. Standard `playwright` has poor anti-bot pass rates. If you choose `playwright`, you must use an anti-detect browser and specify its executable path.  
2. If you need OAuth2 tokens, register an app on [Azure](https://azure.microsoft.com/) and fill in `client_id`, `redirect_url`, and `Scopes` in `config.json`; otherwise, leave them empty.  
3. `client_id` and `redirect_url` typically look like `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` and `http://localhost:8000`.  
4. Set up a local proxy pool and fill in your proxy address in `config.json`. IP quality is critical to success rates—avoid registering multiple accounts from the same IP within a short period.  
5. Registered accounts are saved automatically in the `Results` folder.  
6. If you do not bind a recovery email, navigating directly to `https://outlook.live.com/mail/0` will also enter the mailbox. Please modify the logic yourself to proceed with OAuth2 afterwards.  
7. Camoufox is Playwright (Firefox) under the hood, so the registration flow and `get_token.py` are reused as-is — no API compatibility layer like the one `ruyipage` needs. The bandwidth-saving rules (telemetry swallowed, Office icons and remote fonts aborted, Outlook landing-page scripts served from a local cache) live in `controllers/static_cache.py` and share the `Results/.onecdn_cache` directory with `ruyipage`.  
8. Camoufox pins `playwright<1.63`, so installing it downgrades an existing playwright. If you still use `choose_browser: "playwright"`, reinstall the matching browser build.  
9. The press CAPTCHA (PerimeterX / HUMAN) changed in Nov 2026: the old two-step flow (click `可访问性挑战`, then `再次按下`) is gone. There is now a single `[aria-label="按住 人工挑战"]` button that must be **held down** until the checkmark animation appears (2–4 s in practice); after releasing, the page takes about 13 s to reach the "help protect your account" step. The camoufox controller implements the new widget; ruyipage and patchright still use the old flow and stall there.  