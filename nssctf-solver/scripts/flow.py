"""一题流水线：开环境 -> 下附件 -> 抓题面 -> 抓题解 -> 提交候选。

用法
----
    python flow.py <pid>                  # 走完一题，产出附件/题面/题解
    python flow.py <pid> --submit "flag"  # 提交候选（可多次给多个 --submit）
    python flow.py <pid> --target         # 打印交互式环境地址

已解出的题会直接跳过（除非显式给了 --submit 要核对）。

flag 前缀只试 3 种：本体原文 / 赛事缩写{} / NSSCTF{}
"""
import argparse
import os
import re
import sys
import time
import zipfile
import tarfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cdp as C

WORK = C.WORK                      # 跟随 cdp.py 的约定，避免路径漂移
ATT = os.path.join(WORK, "att")
QD = os.path.join(WORK, "q")

# 业务码语义
CODE = {200: "通过", 203: "已解决(重复提交)", 204: "答案错误",
        201: "UNAUTHORIZED", 202: "NOT_FOUND"}


def log(*a):
    print(*a, flush=True)


def save(name, text):
    p = os.path.join(QD, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", errors="replace") as f:
        f.write(text)
    return p


def open_env(pid, tries=3):
    """开 docker 环境。附件下载的前置条件。"""
    for _ in range(tries):
        d = C.detail(pid).get("data") or {}
        if d.get("is_open"):
            return True
        C.docker_open(pid)
        for _ in range(8):
            time.sleep(4)
            if (C.detail(pid).get("data") or {}).get("is_open"):
                return True
    return False


def fetch_attachment(pid, dd):
    """下载附件并解压，返回文件路径列表。"""
    if not dd.get("annex"):
        log("  [无附件]")
        return []
    url = C.annex_url(pid)
    if not url:
        log("  [附件链接获取失败 —— 通常是没开环境]")
        return []
    import urllib.request as ur
    req = ur.Request(url, headers={"User-Agent": "Mozilla/5.0",
                                   "Referer": "%s/problem/%d" % (C.BASE, pid)})
    try:
        with ur.urlopen(req, timeout=2400) as resp:
            data = resp.read()
            cd = resp.headers.get("Content-Disposition") or ""
    except Exception as e:
        log("  [下载失败] %s" % e)
        return []
    # 优先 Content-Disposition 里的真实文件名，退回 URL 尾段
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd)
    raw = m.group(1) if m else url.rsplit("/", 1)[-1]
    safe = re.sub(r"[^\w.\-]", "_", raw)[:70] or "annex.bin"
    dest = os.path.join(ATT, "P%d_%s" % (pid, safe))
    os.makedirs(ATT, exist_ok=True)
    with open(dest, "wb") as f:
        f.write(data)
    log("  [已下载] %s (%.2f MB)" % (os.path.basename(dest), len(data) / 1048576))
    return unpack(dest, pid)


def unpack(path, pid):
    """就地解压 zip/tar；7z 等格式留给外部工具。"""
    out = []
    d = os.path.join(ATT, "P%d" % pid)
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as z:
                z.extractall(d)
            log("  [已解压] -> %s" % d)
            out.append(d)
        elif tarfile.is_tarfile(path):
            with tarfile.open(path) as t:
                t.extractall(d)
            log("  [已解压] -> %s" % d)
            out.append(d)
        else:
            out.append(path)
    except Exception as e:
        log("  [解压失败] %s" % e)
        out.append(path)
    return out


def fetch_wp(pid, limit=5):
    """抓 WriteUp 正文，存到 q/。"""
    r = C.notes(pid)
    items = r.get("data") or r.get("results") or []
    if isinstance(items, dict):
        items = items.get("results") or items.get("list") or []
    got = []
    for i, it in enumerate(items[:limit]):
        nid = it.get("id") or it.get("note_id")
        if not nid:
            continue
        t0 = (it.get("title") or "").strip()
        C.goto("/note/%s" % nid)
        time.sleep(2)
        body = C.page_text()
        p = save("P%d.wp%d.txt" % (pid, i), body)
        got.append(p)
        log("  [题解] %s -> %s (%d 字)" % (t0[:36], os.path.basename(p), len(body)))
    return got


def run(pid, submit=(), show_target=False, wp=5):
    log("=== P%d ===" % pid)
    C.auth()
    C.goto("/problem/%d" % pid)
    d = C.detail(pid)
    dd = d.get("data") or {}
    if d.get("code") != 200:
        log("  取详情失败 code=%s" % d.get("code"))
        return
    tags = [t[0] for t in (dd.get("tag") or []) if isinstance(t, list) and t]
    log("  %s" % dd.get("title"))
    log("  is_open=%s is_solved=%s wa=%s tag=%s"
        % (dd.get("is_open"), dd.get("is_solved"),
           (dd.get("info") or {}).get("wa"), "/".join(tags)))

    # 已解出且不是来核对的，直接跳过，别浪费开环境和下载
    if dd.get("is_solved") and not submit:
        log("  已 solved —— 跳过")
        return

    if not dd.get("is_open"):
        log("  开环境...")
        if not open_env(pid):
            log("  [环境未就绪，附件可能取不到]")

    log("  下载附件...")
    fetch_attachment(pid, dd)

    log("  抓题面...")
    C.goto("/problem/%d" % pid)
    time.sleep(2)
    body = C.page_text()
    p = save("P%d.txt" % pid, body)
    log("  [题面] %s (%d 字)" % (os.path.basename(p), len(body)))

    if wp:
        log("  抓题解...")
        if not fetch_wp(pid, wp):
            log("  无题解 —— 靠自己逆向")

    if show_target:
        host, port = C.docker_target(pid)
        log("  交互地址: %s:%s" % (host, port))

    for f in submit:
        r = C.submit(pid, f)
        code = r.get("code")
        time.sleep(2)
        dd2 = C.detail(pid).get("data") or {}
        log("  SUB %s -> %s (%s) is_solved=%s"
            % (f, code, CODE.get(code, r.get("msg") or ""), dd2.get("is_solved")))
        if dd2.get("is_solved"):
            log("  === SOLVED: %s ===" % f)
            break


def main():
    ap = argparse.ArgumentParser(description="NSSCTF 单题流水线")
    ap.add_argument("pid", type=int)
    ap.add_argument("--submit", action="append", default=[],
                    help="候选 flag，可重复；按顺序试")
    ap.add_argument("--target", action="store_true", help="打印交互式环境地址")
    ap.add_argument("--no-wp", action="store_true", help="不抓题解")
    a = ap.parse_args()
    run(a.pid, a.submit, a.target, 0 if a.no_wp else 5)


if __name__ == "__main__":
    main()