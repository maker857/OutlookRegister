import os
import json
import time
import random
import platform
from playwright.sync_api import sync_playwright
from camoufox.sync_api import NewBrowser, NewContext
from .base_controller import BaseBrowserController
from . import static_cache


#   Camoufox 自带指纹伪装(navigator / screen / WebGL / fonts / voices)与 humanize 鼠标轨迹，
#   页面 API 就是原生 Playwright，所以注册主流程 base_controller.outlook_register 与
#   get_token.py 可以直接复用，不需要 ruyipage 那样的兼容层。
#
#   省流量相关的 Firefox 偏好。只放与流量/遥测有关、不影响指纹的项：
#   图片用 block_images、语言用 locale、窗口用 window，这些交给 Camoufox 自己处理，不在这里改 pref。
TRAFFIC_PREFS = {
    # 禁止下载证书库与翻译模型 (~14.8 MB)，需配合 MOZ_REMOTE_SETTINGS_DEVTOOLS=1
    "services.settings.server": "http://127.0.0.1:1/v1",
    "browser.translations.enable": False,
    "browser.safebrowsing.provider.google4.updateURL": "",

    # 安全浏览名单与下载检查
    "browser.safebrowsing.malware.enabled": False,
    "browser.safebrowsing.phishing.enabled": False,
    "browser.safebrowsing.downloads.enabled": False,
    "browser.safebrowsing.downloads.remote.enabled": False,
    "browser.safebrowsing.downloads.remote.url": "",

    # 媒体插件与自动更新
    "media.gmp-gmpopenh264.enabled": False,
    "media.gmp-gmpopenh264.autoupdate": False,
    "media.gmp-widevinecdm.enabled": False,
    "media.gmp-widevinecdm.autoupdate": False,
    "media.gmp-manager.url": "",
    "app.update.auto": False,
    "extensions.update.enabled": False,
    "extensions.getAddons.cache.enabled": False,
    "extensions.blocklist.enabled": False,

    # 预取与预测连接
    "network.prefetch-next": False,
    "network.dns.disablePrefetch": True,
    "network.dns.disablePrefetchFromHTTPS": True,
    "network.predictor.enabled": False,
    "network.predictor.enable-prefetch": False,
    "network.http.speculative-parallel-limit": 0,

    # 遥测与推荐内容
    "datareporting.healthreport.uploadEnabled": False,
    "datareporting.policy.dataSubmissionEnabled": False,
    "toolkit.telemetry.enabled": False,
    "toolkit.telemetry.unified": False,
    "toolkit.telemetry.archive.enabled": False,
    "app.normandy.enabled": False,
    "app.shield.optoutstudies.enabled": False,
    "browser.newtabpage.activity-stream.feeds.telemetry": False,
    "browser.newtabpage.activity-stream.telemetry": False,
    "browser.newtabpage.activity-stream.feeds.section.topstories": False,
    "browser.ping-centre.telemetry": False,
    "extensions.pocket.enabled": False,

    # 媒体预加载
    "media.autoplay.default": 5,
    "media.preload.default": 1,
    "media.preload.auto": 1,
}

# aggressive 模式追加。注意这项本身是可被指纹识别的特征，用它换流量
#
# 不要在这里关 dom.serviceWorkers.enabled：Playwright 在 Firefox 下的请求拦截走的就是
# ServiceWorker 那套通道，关掉后 page.route / context.route 会静默失效(handler 根本不触发)，
# 省下的那点后台脚本流量远不及拦截本身省的多。
AGGRESSIVE_PREFS = {
    "gfx.downloadable_fonts.enabled": False,    # 禁止下载远程 Web 字体
}

_HOST_OS = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}


def _resolve_os(value):
    """
    "auto"(默认) -> 跟随本机系统；"" -> 由 Camoufox 随机抽取；其余原样传入

    跟随本机的好处：画出的身份与本机 canvas / GPU 一致，Camoufox 就不必打开 canvas 噪声，
    否则页面会把浏览器读成 Tor / LibreWolf 那类隐私加固版 Firefox，反而更显眼。
    """
    if value == "auto":
        return _HOST_OS.get(platform.system())
    return value or None


def _setup_traffic_route(context, proxy_url):
    """用 page.route 复现 ruyipage 的分流策略：遥测吞掉、图标字体断掉、落地页脚本走本地缓存"""

    def handler(route):
        try:
            url = route.request.url
            action = static_cache.classify(url)

            if action == "blank":
                route.fulfill(status=200, body="", headers={"access-control-allow-origin": "*"})
                return
            if action == "abort":
                route.abort()
                return
            if action == "cache":
                hit = static_cache.get_cached(url, proxy_url)
                if hit is not None:
                    ct, body = hit
                    route.fulfill(
                        status=200,
                        body=body,
                        headers={
                            "content-type": ct,
                            "access-control-allow-origin": "*",
                            "timing-allow-origin": "*",
                        },
                    )
                    return

            route.continue_()
        except Exception:
            try:
                route.continue_()
            except Exception:
                pass

    try:
        context.route(static_cache.ROUTE_PATTERN, handler)
    except Exception as e:
        print(f"挂载流量拦截失败，已跳过: {e}")


class CamoufoxController(BaseBrowserController):

    def __init__(self):
        super().__init__()
        with open('config.json', 'r', encoding='utf-8') as f:
            data = json.load(f)

        cfg = data.get("camoufox", {})
        self.traffic_mode = cfg.get("traffic_mode", "")
        self.browser_path = cfg.get("browser_path", "")
        self.headless = bool(cfg.get("headless", False))
        self.humanize = cfg.get("humanize", True)
        self.locale = cfg.get("locale") or "zh-CN"
        self.geoip = cfg.get("geoip", True)
        self.enable_cache = bool(cfg.get("enable_cache", True))
        # 这两项 Camoufox 官方都标注为可被 WAF 检测，默认关掉，换通过率：
        #   block_images  "Blocking image requests has been reported to cause detection issues on major WAFs."
        #   disable_coop  "Disabling COOP handling can potentially be detected by sophisticated WAFs."
        # 按压验证码(PerimeterX / hsprotect)就是这类 WAF，而 Playwright 的 frame_locator
        # 点跨域 iframe 本来不需要关 COOP，patchright / playwright 两个控制器也都没关过。
        self.block_images = bool(cfg.get("block_images", False))
        self.disable_coop = bool(cfg.get("disable_coop", False))
        self.per_task_identity = bool(cfg.get("per_task_identity", True))
        self.captcha_hold = float(cfg.get("captcha_hold", 14))
        self.os_spoof = _resolve_os(cfg.get("os", "auto"))
        window = cfg.get("window") or None
        self.window = tuple(window) if window else None

    def launch_browser(self):
        try:
            # services.settings.server 的覆盖需要这个环境变量才生效
            os.environ["MOZ_REMOTE_SETTINGS_DEVTOOLS"] = "1"

            prefs = dict(TRAFFIC_PREFS)
            if self.traffic_mode == "aggressive":
                prefs.update(AGGRESSIVE_PREFS)

            kwargs = {
                "headless": self.headless,
                "humanize": self.humanize,
                "locale": self.locale,
                "enable_cache": self.enable_cache,
                "disable_coop": self.disable_coop,
                "block_webrtc": True,
                "firefox_user_prefs": prefs,
                # 上面这些偏好会触发 Camoufox 的泄漏告警，这里是有意为之
                "i_know_what_im_doing": True,
            }

            if self.proxy:
                kwargs["proxy"] = {"server": self.proxy, "bypass": "localhost"}
            # 时区/经纬度跟随代理出口 IP，语言仍由 locale 固定为中文(注册页选择器是中文的)
            if self.geoip:
                kwargs["geoip"] = self.geoip
            if self.block_images:
                kwargs["block_images"] = True
            if self.window:
                kwargs["window"] = self.window
            if self.os_spoof:
                kwargs["os"] = self.os_spoof
            if self.browser_path:
                kwargs["executable_path"] = self.browser_path

            p = sync_playwright().start()
            b = NewBrowser(p, **kwargs)
            return p, b

        except Exception as e:
            print(f"启动浏览器失败: {e}")
            print("若提示未安装浏览器，请先执行: python -m camoufox fetch")
            return False, False

    def get_thread_page(self):
        browser = self.get_thread_browser()
        if not browser:
            return False

        # 每个注册任务单独一个 context，拿一套独立指纹(navigator / screen / WebGL / fonts)
        context = None
        if self.per_task_identity:
            try:
                context = NewContext(browser, locale=self.locale)
            except Exception as e:
                print(f"独立指纹 context 创建失败，回退到普通 context: {e}")
        if context is None:
            context = browser.new_context(locale=self.locale)

        if self.traffic_mode == "aggressive":
            _setup_traffic_route(context, self.proxy)

        return context.new_page()

    # --- 按压验证码 (PerimeterX / HUMAN) ---
    #
    # 2026-11 线上控件结构：
    #   <a   role="button" aria-label="可访问性挑战">   辅助功能入口(图标)
    #   <div role="button" aria-label="按住 人工挑战">  主按钮，文案"按住"，要求按住不放直到验证完成
    #       <div class="fetching-volume">•••</div><div id="checkmark"></div><div id="ripple"></div>
    # 旧流程里的 [aria-label="再次按下"] 已经不存在，所以"点一下再点一下"必然卡死。
    #
    # 控件在 iframe.hsprotect.net 的子 frame 里，而且同时存在多个结构相同的兄弟 iframe，
    # 用 frame_locator('iframe[style*="display: block"]') 会命中多个触发 strict mode，
    # 这里直接遍历 page.frames 找到真正带按钮的那个。控件约在进入页面 4 秒后才渲染。
    HOLD_BTN = '[aria-label^="按住"]'
    A11Y_BTN = '[aria-label="可访问性挑战"]'

    def _captcha_frame(self, page, timeout=25.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for fr in page.frames:
                if "hsprotect" not in (fr.url or ""):
                    continue
                try:
                    if fr.locator(self.HOLD_BTN).count() > 0:
                        return fr
                except Exception:
                    continue
            page.wait_for_timeout(250)
        return None

    def _captcha_passed(self, page):
        try:
            if page.get_by_text('保护你的帐户').count() > 0:
                return True
            if page.locator('[data-testid="primaryButton"]').count() > 0:
                return True
        except Exception:
            pass
        return False

    def _rate_limited(self, page):
        for text in ('一些异常活动', '此站点正在维护，暂时无法使用，请稍后重试。'):
            try:
                if page.get_by_text(text).count() > 0:
                    return True
            except Exception:
                pass
        return False

    def _challenge_status(self, page):
        """
        读控件里 aria-live 的播报，这是唯一能分辨"被拒"还是"要求再按一次"的信号：
          "Human Challenge已完成，请稍候"      -> 本次按压被接受
          "请再试一次 / Keep going / 重新开始"  -> 被拒(IP / 指纹问题)
          "再按一次 / Press and hold again"     -> 还需要一轮
        每次重新遍历 page.frames，不持有可能已销毁的 frame 句柄。
        """
        for fr in page.frames:
            if "hsprotect" not in (fr.url or ""):
                continue
            try:
                if fr.locator('[aria-live="assertive"]').count() == 0:
                    continue
                txt = fr.evaluate(
                    "() => { const e = document.querySelector('[aria-live=\"assertive\"]');"
                    " return e ? e.textContent.trim().slice(0, 80) : ''; }"
                )
                if txt:
                    return txt
            except Exception:
                continue
        return ""

    def _hold_button_present(self, page):
        """每次都重新遍历 page.frames，避免持有已被销毁的 frame 句柄"""
        for fr in page.frames:
            if "hsprotect" not in (fr.url or ""):
                continue
            try:
                if fr.locator(self.HOLD_BTN).count() > 0:
                    return True
            except Exception:
                continue
        return False

    def _press_and_hold(self, page, frame):
        """按住按钮不放，直到验证完成 / 控件消失 / 到达 captcha_hold 上限再松手"""
        btn = frame.locator(self.HOLD_BTN).first
        try:
            box = btn.bounding_box()
        except Exception:
            box = None
        if not box:
            return False

        tx = box['x'] + box['width'] / 2 + random.uniform(-8, 8)
        ty = box['y'] + box['height'] / 2 + random.uniform(-4, 4)
        self.smooth_move_to(page, tx, ty)
        page.wait_for_timeout(random.randint(90, 220))

        page.mouse.down()
        try:
            deadline = time.time() + self.captcha_hold
            while time.time() < deadline:
                page.wait_for_timeout(200)
                try:
                    # 实测按住约 2 ~ 4 秒后出现打勾动画，aria-live 播报"Human Challenge已完成"
                    if frame.locator('#checkmark.draw').count() > 0:
                        break
                    if frame.locator(self.HOLD_BTN).count() == 0:
                        break
                except Exception:
                    break
            # 完成信号出现后再多按住一会儿，让控件把动画走完
            page.wait_for_timeout(random.randint(350, 550))
        finally:
            page.mouse.up()
            self.set_last_pos(tx, ty)
        return True

    def _wait_captcha_result(self, page, timeout=35.0):
        """
        松手后页面要走一串跳转才落地：
        正在加载... -> login.live.com/oauth20_authorize.srf -> account.live.com/interrupt/credentialaction
        实测约 13 秒，期间 hsprotect 的 frame 会被销毁，不能把"查不到控件"当成失败。
        返回 "passed" / "limited" / "retry" / "timeout"
        """
        deadline = time.time() + timeout
        grace = time.time() + 2.5      # 松手后给控件一点时间消失，别立刻判成需要重按
        while time.time() < deadline:
            page.wait_for_timeout(400)
            if self._captcha_passed(page):
                return "passed"
            if self._rate_limited(page):
                return "limited"
            if time.time() > grace and self._hold_button_present(page):
                return "retry"
        return "timeout"

    def handle_captcha(self, page):

        page.wait_for_timeout(random.randint(400, 700))
        last_status = ""

        for attempt in range(0, self.max_captcha_retries + 1):

            if self._captcha_passed(page):
                return True

            frame = self._captcha_frame(page)
            if frame is None:
                if self._captcha_passed(page):
                    return True
                print(f"[Error: Captcha] - 未找到按压控件 {self.HOLD_BTN}，线上控件可能又改了，"
                      f"可用 Results/captcha_diag 下的诊断产物核对。")
                return False

            if not self._press_and_hold(page, frame):
                page.wait_for_timeout(random.randint(500, 900))
                continue

            result = self._wait_captcha_result(page)
            if result == "passed":
                return True
            if result == "limited":
                print("[Error: Rate limit] - 正常通过验证码，但当前IP注册频率过快。")
                return False

            # 控件又发了一次挑战。控件说明是"等待确认，并在出现提示时再按一次"，
            # 立刻重按会被判掉(旧的 playwright 控制器两次按压之间等了 11.5 秒)，
            # 这里先等播报里的"请稍候"消失，再按人的节奏停几秒。
            last_status = self._challenge_status(page) or last_status
            print(f"[Info: Captcha] - 第 {attempt + 1} 次按压未放行"
                  f"{('，控件播报: ' + last_status) if last_status else ''}")

            deadline = time.time() + 12
            while time.time() < deadline:
                status = self._challenge_status(page)
                if not status or ("稍候" not in status and "wait" not in status.lower()):
                    break
                page.wait_for_timeout(500)
            page.wait_for_timeout(random.randint(2500, 5000))

        if self._captcha_passed(page):
            return True

        if last_status:
            print(f"[Error: Captcha] - 按压次数用尽，控件最后播报: {last_status}")
        print("[Hint] - 每次按压都被接受却反复重发挑战，通常是出口 IP 信誉问题，换一个干净 IP 再试。")
        return False

    def clean_up(self, page=None, type="all_browser"):
        if type == "done_browser" and page:
            try:
                page.context.close()
            except Exception:
                pass

        elif type == "all_browser":
            with self.cleanup_lock:
                for p, b in self.active_resources:
                    try:
                        b.close()
                    except Exception:
                        pass
                    try:
                        p.stop()
                    except Exception:
                        pass
                self.active_resources.clear()
