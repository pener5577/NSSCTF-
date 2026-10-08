"""选题：列出可做的题，标出已解出/ 有题解 / 未开环境。

用法
----
    python pick.py --page 1 --size 20       # 拉题目列表
    python pick.py --range 320 340         # 逐个查指定区间的状态
    python pick.py --next --after 325      # 找出 325 之后第一个未解出的题
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cdp as C

WORK = os.environ.get("NSS_WORK") or os.getcwd()
STATE = os.path.join(WORK, "pick_state.json")


def load():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {}


def save(d):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def info(pid, st):
    """取单题状态，带缓存。pid 保持 int，缓存键用 str。"""
    key = str(pid)
    if key in st:
        return st[key]
    d = (C.detail(int(pid)).get("data") or {})
    rec = {
        "name": d.get("title"),
        "solved": bool(d.get("is_solved")),
        "open": bool(d.get("is_open")),
        "wa": (d.get("info") or {}).get("wa"),
        "tag": "/".join(t[0] for t in (d.get("tag") or []) if isinstance(t, list) and t),
        "env": bool(d.get("has_environment")),
    }
    st[key] = rec
    return rec


def cmd_range(lo, hi):
    C.auth()
    st = load()
    for pid in range(lo, hi + 1):
        try:
            r = info(pid, st)
        except Exception as e:
            print("%d  ERR %s" % (pid, e))
            continue
        mark = "OK " if r["solved"] else ("-- " if not r["wa"] else "wp ")
        nm = r.get("name") or "(untitled)"
        print("%s %-6s %-42s %-22s wa=%-4s env=%s"
              % (mark, pid, nm[:42], (r.get("tag") or "")[:22], r.get("wa"), r.get("env")))
    save(st)


def cmd_next(after):
    """从 after+1 起找第一个未解出的题。"""
    C.auth()
    st = load()
    pid = after + 1
    while pid < after + 500:
        try:
            r = info(pid, st)
        except Exception:
            pid += 1
            continue
        if r["name"] and not r["solved"]:
            print("NEXT %d  %s  (wa=%s)" % (pid, r["name"], r["wa"]))
            save(st)
            return
        pid += 1
    print("后面 500 题都已解出或不存在")


def cmd_page(page, size):
    C.auth()
    r = C.plist(page, size)
    data = r.get("data") or r.get("results") or []
    if isinstance(data, dict):
        data = data.get("results") or data.get("list") or []
    st = load()
    print("%-6s %-46s %-6s %-5s %s" % ("id", "name", "solved", "wa", "open"))
    for it in data:
        pid = it.get("id")
        if not pid:
            continue
        rec = {"name": it.get("name"), "solved": bool(it.get("is_solved")),
               "open": bool(it.get("is_open")), "wa": it.get("wa")}
        st[str(pid)] = rec
        print("%-6d %-46s %-6s %-5s %s"
              % (pid, (rec["name"] or "")[:46], rec["solved"], rec["wa"], rec["open"]))
    save(st)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--page", type=int, help="按页拉列表")
    g.add_argument("--range", nargs=2, type=int, metavar=("START", "END"))
    g.add_argument("--next", action="store_true", help="找下一个未解出的题")
    ap.add_argument("--size", type=int, default=20)
    ap.add_argument("--after", type=int, default=0)
    a = ap.parse_args()
    if a.range:
        cmd_range(a.range[0], a.range[1])
    elif a.next:
        cmd_next(a.after)
    else:
        cmd_page(a.page, a.size)


if __name__ == "__main__":
    main()