r"""NSSCTF 平台驱动：通过 Chrome DevTools Protocol 调已登录浏览器的 API。

为什么必须走浏览器：Python 直连 HTTP 提交返回 402，VIP 权限绑在浏览器登录态上。

首次使用
--------
1. 启动专用 Chrome（必须用独立 profile，否则已有 Chrome 会让调试端口失效）：

     chrome.exe --remote-debugging-port=9222 ^
                 --user-data-dir=<任意空目录>\chrome_prof ^
                 https://www.nssctf.cn/

   在这个窗口里手动登录 NSSCTF 一次。

2. 生成凭据文件（从浏览器会话读回 cookie）：

     python cdp.py save-cookie

   之后每个终端会话开头设置工作目录：

     $env:NSS_WORK="d:\Users\pener\Downloads\nss_work"

依赖：pip install websocket-client
"""
import json
import os
import sys
import time
import urllib.request as ur

BASE = "https://www.nssctf.cn"
DEBUG_PORT = 9222

# 附件/题面落盘根目录。用NSS_WORK 指定；未设置时退回用户目录，避免随 cwd 漂移。
WORK = os.environ.get("NSS_WORK") or os.path.join(os.path.expanduser("~"), "nss_work")
COOKIE_FILE = os.path.join(WORK, "cookie.txt")

_cdp = None


# ---------------- CDP 连接 ----------------
def cdp():
    """连接调试端口上的 Chrome，复用带 nssctf 的标签页。"""
    global _cdp
    if _cdp is not None:
        return _cdp
    import websocket
    try:
        tabs = json.loads(ur.urlopen("http://127.0.0.1:%d/json" % DEBUG_PORT, timeout=10).read())
    except Exception:
        raise RuntimeError(
            "连不上 Chrome 调试端口 %d。Chrome 必须以调试模式启动：\n"
            '  chrome.exe --remote-debugging-port=%d --user-data-dir=<空目录>\\chrome_prof\n'
            "注意：已有 Chrome 窗口在跑时，调试参数不生效，必须先完全退出。" % (DEBUG_PORT, DEBUG_PORT))
    pg = next((t for t in tabs if t.get("type") == "page" and "nssctf" in t.get("url", "")), None) \
        or next((t for t in tabs if t.get("type") == "page"), None)
    if not pg:
        raise RuntimeError("Chrome 已连上但没有可用标签页 —— 开一个 nssctf 页面重试")

    class _C:
        def __init__(self, url):
            # 新版 Chrome 校验 Origin。先正常连，被拒则 suppress（省得依赖启动参数）
            try:
                self.ws = websocket.create_connection(url, timeout=40)
            except Exception:
                self.ws = websocket.create_connection(url, timeout=40, suppress_origin=True)
            self.i = 0

    _cdp = _C(pg["webSocketDebuggerUrl"])
    return _cdp


def recv_id(c, want, budget=25):
    """收包直到拿到目标 id，超时返回 None，防止死等。"""
    end = time.time() + budget
    while time.time() < end:
        try:
            c.ws.settimeout(max(0.5, end - time.time()))
            m = json.loads(c.ws.recv())
        except Exception:
            return None
        if m.get("id") == want:
            return m
    return None


def ev(c, expr, budget=40):
    """在页面里执行 JS，同步取回值。"""
    c.i += 1
    eid = c.i
    c.ws.send(json.dumps({"id": eid, "method": "Runtime.evaluate",
                          "params": {"expression": expr, "returnByValue": True,
                                     "awaitPromise": True}}))
    m = recv_id(c, eid, budget)
    if not m:
        raise TimeoutError("cdp eval timeout（页面可能在跳转，重试）")
    res = m.get("result") or {}
    rr = res.get("result") or {}
    v = rr.get("value")
    if v is not None:
        return v
    if res.get("exceptionDetails"):
        raise RuntimeError("js error: %s" % json.dumps(res, ensure_ascii=False)[:200])
    return None


def auth(c=None):
    """用 cookie.txt 覆盖浏览器登录态。"""
    c = c or cdp()
    if not os.path.exists(COOKIE_FILE):
        raise FileNotFoundError(
            "%s 不存在。先在已登录的浏览器里执行： python cdp.py save-cookie" % COOKIE_FILE)
    ck = {}
    with open(COOKIE_FILE, encoding="utf-8") as f:
        for part in f.read().split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                ck[k] = v
    c.i += 1
    c.ws.send(json.dumps({"id": c.i, "method": "Network.setCookies", "params": {"cookies": [
        {"name": k, "value": v, "domain": ".nssctf.cn", "path": "/"} for k, v in ck.items()]}}))
    recv_id(c, c.i, 20)


# ---------------- API ----------------
def api(path, budget=30, method="GET", body=None):
    """在已登录页面里调 API，返回解析后的 json。"""
    c = cdp()
    payload = json.dumps(body) if body is not None else "null"
    expr = (
        "(() => { try {"
        " const r = new XMLHttpRequest();"
        f" r.open('{method}', {json.dumps(path)}, false);"
        " r.setRequestHeader('Content-Type','application/json');"
        f" r.send({payload});"
        " return r.responseText;"
        " } catch(e) { return JSON.stringify({code:0, err:''+e}); } })()"
    )
    raw = ev(c, expr, budget) or "{}"
    try:
        return json.loads(raw)
    except Exception:
        return {"_raw": raw[:300]}


def goto(path, settle=11):
    """导航到站内页面并等待 SPA 渲染。"""
    c = cdp()
    url = path if path.startswith("http") else BASE + path
    c.i += 1
    cid = c.i
    c.ws.send(json.dumps({"id": cid, "method": "Page.navigate", "params": {"url": url}}))
    recv_id(c, cid, 20)
    end = time.time() + settle
    while time.time() < end:
        try:
            if ev(c, "document.readyState", 5) in ("interactive", "complete"):
                break
        except Exception:
            pass
        time.sleep(0.4)


PAGE_TEXT = r"""
(() => {
  for (const s of ['.note-content','.markdown-body','article','.vditor-reset','.content','main']) {
    const e = document.querySelector(s);
    if (e && e.innerText && e.innerText.length > 200) return e.innerText;
  }
  return document.body.innerText;
})()
"""


def page_text():
    return ev(cdp(), PAGE_TEXT, 40) or ""


# ---------------- 题目接口 ----------------
# 关键字段：data.title / data.annex(有无附件) / data.is_open / data.is_solved
#           data.info.wa (题解数) / data.tag (题型) / data.has_environment
def detail(pid):
    return api("/api/problem/v2/%d/" % int(pid), 40)


def title(pid):
    return (detail(pid).get("data") or {}).get("title") or ""


def notes(pid):
    return api("/api/problem/%d/note/list/" % int(pid), 30)


def plist(page=1, size=15, **kw):
    return api("/api/problem/v3/list/%d/%d/" % (page, size), 40, "POST", kw)


def submit(pid, flag):
    """提交 flag。必须走浏览器通道。"""
    return api("/api/problem/submit/%d/" % int(pid), 30, "POST", {"flag": flag})


# ---------------- 环境 ----------------
def docker_open(pid):
    return api("/api/problem/docker/%d/open/" % int(pid), 90, "POST", {})


def docker_info(pid):
    return api("/api/problem/docker/%d/" % int(pid), 30)


def annex_url(pid, tries=4):
    """取附件 CDN 链接。必须先开环境，否则服务端返回 203。"""
    for _ in range(tries):
        r = api("/api/problem/%d/annex/download/" % int(pid), 120)
        if r.get("code") == 200 and isinstance(r.get("data"), str) \
                and r["data"].startswith("http"):
            return r["data"]
        time.sleep(4)
    return None


def docker_target(pid):
    """开环境并返回 (host, port)。socket 交互题用。"""
    goto("/problem/%d" % int(pid))
    for _ in range(6):
        d = detail(pid).get("data") or {}
        if d.get("is_open"):
            break
        docker_open(pid)
        time.sleep(4)
    js = r"""
    (() => {
      const h = document.documentElement.outerHTML;
      const ip = (h.match(/\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/) || [])[0];
      const port = (h.match(/nc\s+\S+\s+(\d{2,5})/) || [])[1]
                || (h.match(/host[^0-9]{0,20}(\d{2,5})/i) || [])[1];
      return (ip||'') + ' ' + (port||'');
    })()
    """
    parts = (ev(cdp(), js, 40) or "").split()
    if len(parts) >= 2:
        return parts[0], int(parts[1])
    info = docker_info(pid).get("data") or {}
    return info.get("host"), info.get("port")


# ---------------- 凭据维护 ----------------
def save_cookie(out=COOKIE_FILE):
    """从当前浏览器会话读回 nssctf cookie，重建 cookie.txt。"""
    c = cdp()
    goto("/")
    c.i += 1
    cid = c.i
    c.ws.send(json.dumps({"id": cid, "method": "Network.getAllCookies"}))
    r = recv_id(c, cid, 40) or {}
    seen, pairs = set(), []
    for ck in (r.get("result") or {}).get("cookies") or []:
        if "nssctf" not in ck.get("domain", ""):
            continue
        pair = "%s=%s" % (ck["name"], ck["value"])
        if pair not in seen:
            seen.add(pair)
            pairs.append(pair)
    if not pairs:
        print("no nssctf cookies —— 浏览器窗口未登录 NSSCTF")
        return False
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("; ".join(pairs))
    print("wrote %s (%d entries)" % (out, len(pairs)))
    return True


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "save-cookie":
        save_cookie()
    elif len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
    else:
        pid = int(sys.argv[1]) if len(sys.argv) > 1 else 0
        if not pid:
            print(__doc__)
        else:
            d = detail(pid)
            dd = d.get("data") or {}
            tags = [t[0] for t in (dd.get("tag") or []) if isinstance(t, list) and t]
            print("code=%s title=%s is_open=%s is_solved=%s wa=%s tag=%s annex=%s"
                  % (d.get("code"), dd.get("title"), dd.get("is_open"), dd.get("is_solved"),
                     (dd.get("info") or {}).get("wa"), "/".join(tags), dd.get("annex")))