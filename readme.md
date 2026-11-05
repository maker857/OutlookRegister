# OutlookRegister  

简体中文 | [English](./readme_en.md)  

Outlook 注册机  
选择器经常更新，不保证时效性，自行测试。  

- 模拟人类填表操作  
- 自动过验证码  
- 注册成功  

---

### 使用步骤

1. `pip install -r requirements.txt`  
2. `python -m camoufox fetch`（推荐，如果使用 camoufox）  
3. `python -m ruyipage install`（如果使用 ruyipage）  
4. `patchright install chromium`（如果使用 patchright）  
5. 在 `config.json` 中配置代理、并发，并选定一种辅助邮箱方式填写相关内容。  
6. `python main.py`  

---

| 配置项 | 说明 |
| :--- | :--- |
| **`choose_browser`** | `"camoufox"`、`"patchright"`、`"playwright"` 或者 `"ruyipage"`，最推荐 `"camoufox"` 与 `"ruyipage"`。 |
| **`choosed_mail`** | `"moemail"` 或 `"outlookgraph"`。（不想绑定辅助邮箱见补充说明 6） |
| **`email_suffix`** | `"@outlook.com"` 或 `"@hotmail.com"`。 |
| **`bot_protection_wait`** | 单位为秒。 |
| **`camoufox.browser_path`** | 留空则使用 `camoufox fetch` 下载的版本。 |
| **`camoufox.traffic_mode`** | 可留空，或填入 `"aggressive"`（禁远程字体，并启用静态资源拦截与本地缓存）。 |
| **`camoufox.headless`** | 建议 `false`，无头会显著降低通过率。 |
| **`camoufox.humanize`** | `true` 或一个数字（鼠标移动最长耗时，单位秒）。 |
| **`camoufox.locale`** | 默认 `"zh-CN"`，注册流程的选择器是中文的，改语言需同步改选择器。 |
| **`camoufox.geoip`** | `true` 则时区、经纬度跟随代理出口 IP（首次运行会自动下载 GeoIP 库）。 |
| **`camoufox.enable_cache`** | `true` 可跨任务复用静态资源，省流量。 |
| **`camoufox.block_images`** | 默认 `false`。Camoufox 官方说明禁图片会在主流 WAF 上引发检测，按压验证码就属于这类，省流量请优先靠 `traffic_mode`。 |
| **`camoufox.disable_coop`** | 默认 `false`。关闭 COOP 同样可能被 WAF 识别，而点跨域 iframe 里的验证码并不需要它。 |
| **`camoufox.per_task_identity`** | `true` 则每个注册任务一套独立指纹（navigator / screen / WebGL / 字体）。 |
| **`camoufox.captcha_hold`** | 按住验证码按钮的最长秒数，默认 14；实测 2~4 秒就会出现完成信号并提前松手。 |
| **`camoufox.os`** | 留空随机，或填 `"windows"`、`"macos"`、`"linux"`。 |
| **`camoufox.window`** | 留空由 Camoufox 决定，或填 `[1440, 900]`。固定窗口尺寸本身是指纹特征。 |
| **`ruyipage.browser_path`** | 留空则自动获取 |
| **`ruyipage.traffic_mode`** | 可留空，或填入 `"aggressive"` |
| **`moemail.apikey`** | moemail 的 key。 |
| **`moemail.base_url`** | moemail api 基础地址。 |
| **`moemail.suffix`** | 使用的域名，留空则自动获取，逗号分隔多个域名。 |
| **`outlookgraph.strategy`** | `"file"` 或 `"single_email"`。 |
| **`outlookgraph.client_id`** | 辅助邮箱使用的 client id。 |
| **`outlookgraph.single_email`** | 单邮箱配置 `{ "email": "...", "refresh_token": "..." }`。 |
| **`outlookgraph.file.path`** | 数据格式为`账号---密码---refresh_token---access_token---expire_at` |


---

### 补充说明  

1. playwright使用性较差,如果使用playwright，则需要自行寻找指纹浏览器并填写绝对路径。  
2. 若需 OAuth2，可前往 [Azure](https://azure.microsoft.com/zh-cn/) 申请并在配置中填入 `client_id`、`redirect_url` 与 `Scopes`；不需要可留空。  
3. `client_id`与`redirect_url`格式通常类似于`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`和`http://localhost:8000`。  
4. 使用本地代理IP搭建代理池，在`config.json`填写你的代理地址。IP与成功率高度相关，同一IP短时间不宜多次注册。  
5. 邮箱自动存储到工作目录的`Results`下。  
6. 如果不绑定辅助邮箱，直接访问 `https://outlook.live.com/mail/0` 也可进入邮箱页面，请自行修改相关逻辑让其后续走 Oauth2。  
7. camoufox 本身就是 Playwright(Firefox) 驱动，注册主流程与 `get_token.py` 直接复用，不需要 ruyipage 那样的 API 兼容层；省流量策略（遥测吞掉、Office 图标与远程字体断掉、Outlook 落地页脚本本地缓存）在 `controllers/static_cache.py`，与 ruyipage 共用 `Results/.onecdn_cache` 缓存目录。  
8. camoufox 依赖 `playwright<1.63`，安装后会把已有的 playwright 降级；如果仍要用 `choose_browser: "playwright"`，注意重装对应的浏览器内核。  
9. 按压验证码（PerimeterX / HUMAN）在 2026-11 已改版：原先"点 `可访问性挑战` 再点 `再次按下`"的两段式不再存在，现在是单个 `[aria-label="按住 人工挑战"]` 按钮，需要**按住不放**直到出现打勾动画（实测 2~4 秒），松手后页面还要约 13 秒才跳到「帮助保护你的帐户」。camoufox 控制器已按新控件实现；ruyipage 与 patchright 仍是旧写法，会卡在这一步。  