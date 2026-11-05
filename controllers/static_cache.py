"""
静态资源分流与本地缓存(Playwright / Camoufox 共用)

与 ruyipage_controller 里的 _setup_onecdn_cache 同一套策略、同一个磁盘缓存目录与格式
(Results/.onecdn_cache/*.json: {"url", "ct", "body"})，两边可互相复用已下载的脚本。

流量说明(单次注册)
  1. res.public.onecdn.static.microsoft (~1.70 MB)  -> Outlook 落地页静态资源，首次下载后走本地缓存
  2. browser.events.data.microsoft.com (~0.07 MB)   -> 微软前端遥测与埋点上报，直接吞掉
  3. res-1.cdn.office.net / fonts.googleapis (~0.07 MB) -> Office 图标与外部字体，直接断掉
"""

import os
import re
import json
import time
import hashlib
import requests
import threading

CACHE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Results", ".onecdn_cache"))
STATIC_EXT = (".js", ".mjs", ".css", ".json")

# 需要进入路由处理的主机，其余请求不进拦截器以免拖慢加载
ROUTE_PATTERN = re.compile(
    r"^https?://(?:"
    r"res\.public\.onecdn\.static\.microsoft"
    r"|res\.cdn\.office\.net"
    r"|res-1\.cdn\.office\.net"
    r"|[\w.-]*events\.data\.microsoft\.com"
    r"|fonts\.googleapis\.com"
    r"|fonts\.gstatic\.com"
    r"|update\.googleapis\.com"
    r"|dl\.google\.com"
    r"|[\w.-]*gvt1\.com"
    r")(?:[:/]|$)",
    re.I,
)

_BLANK_HOSTS = (
    "events.data.microsoft.com",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "update.googleapis.com",
    "dl.google.com",
    "gvt1.com",
)
_CACHE_HOSTS = (
    "res.public.onecdn.static.microsoft",
    "res.cdn.office.net",
)

_CACHE = {}
_FAILED_UNTIL = {}
_LOCKS = {}
_GLOBAL_LOCK = threading.Lock()
_HTTP_SESS = requests.Session()


def _preheat():
    """清理残留的 .tmp 半截文件及超过 14 天的过期缓存，并把有效缓存预热进内存"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    for fn in os.listdir(CACHE_DIR):
        fp = os.path.join(CACHE_DIR, fn)
        try:
            if fn.endswith(".tmp") or (time.time() - os.path.getmtime(fp) > 14 * 86400):
                os.remove(fp)
            elif fn.endswith(".json"):
                with open(fp, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if "url" in d and "ct" in d and "body" in d:
                    _CACHE[d["url"]] = (d["ct"], d["body"])
        except Exception:
            try:
                os.remove(fp)
            except Exception:
                pass


_preheat()


def classify(url: str) -> str:
    """
    返回处理方式: "blank"(返回空 200) / "abort"(直接断开) / "cache"(走本地缓存) / ""(放行)
    """
    if not url:
        return ""

    if any(h in url for h in _BLANK_HOSTS):
        return "blank"
    if "res-1.cdn.office.net" in url:
        return "abort"

    if any(h in url for h in _CACHE_HOSTS):
        path_lower = url.split("?", 1)[0].lower()
        return "cache" if path_lower.endswith(STATIC_EXT) else "abort"

    return ""


def get_cached(url: str, proxy_url: str = None):
    """
    取静态脚本，命中返回 (content_type, body)，取不到返回 None(调用方应放行该请求)。
    同一 URL 只下载一次；失败则 5 秒冷却，同批线程直接放行，之后的任务再重试。
    """
    cached = _CACHE.get(url)
    if cached is not None:
        return cached
    if time.time() < _FAILED_UNTIL.get(url, 0):
        return None

    with _GLOBAL_LOCK:
        lock = _LOCKS.setdefault(url, threading.Lock())

    with lock:
        cached = _CACHE.get(url)
        if cached is not None:
            return cached
        if time.time() < _FAILED_UNTIL.get(url, 0):
            return None

        try:
            proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
            try:
                r = _HTTP_SESS.get(url, proxies=proxies, timeout=(4, 15))
            except Exception:
                _HTTP_SESS.close()
                r = requests.get(url, proxies=proxies, timeout=(4, 15))

            if r.status_code == 200 and r.content:
                text = r.content.decode("utf-8")
                if text.encode("utf-8") == r.content:
                    ct = r.headers.get("Content-Type", "application/javascript; charset=utf-8")
                    cached = (ct, text)
                    _CACHE[url] = cached
                    _write_disk(url, ct, text)
                    return cached
        except Exception:
            pass

        _FAILED_UNTIL[url] = time.time() + 5.0
        return None


def _write_disk(url: str, ct: str, text: str):
    """先写 .tmp 再替换正式文件，防止中断留下损坏缓存"""
    try:
        h_key = hashlib.md5(url.encode("utf-8")).hexdigest()
        tmp_file = os.path.join(CACHE_DIR, f"{h_key}.{threading.get_ident()}.tmp")
        disk_file = os.path.join(CACHE_DIR, f"{h_key}.json")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump({"url": url, "ct": ct, "body": text}, f)
        os.replace(tmp_file, disk_file)
    except Exception:
        pass
