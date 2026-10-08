"""选题：列出可做的题，按解题成本排序，找下一个未解出的题。

用法
----
    python pick.py --range 320 340     # 逐个查区间的状态
    python pick.py --next --after 325  # 找 325 之后第一个未解出的题
    python pick.py --page 1 --size 20  # 按页拉列表

标记：OK=已解出  wp=未解出但有题解  --=无题解（成本高，慎选）
状态缓存在 $NSS_WORK/pick_state.json，重复查询不再打接口。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cdp as C

STATE = os.path.join(C.WORK, "pick_state.json")


def load():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {}


def save(d):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def info(pid, st):
    """取单题状态，带缓存。缓存键用 str，接口调用保持 int。"""
    key = str(pid)
    if key in st:
        return st[key]
    d = C.detail(int(pid)).get("data") or {}
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


def row(pid, r):
    mark = "OK " if r["solved"] else ("-- " if not r["wa"] else "wp ")
    return "%s %-6s %-42s %-20s wa=%-4s env=%s" % (
        mark, pid, (r.get("name") or "(untitled)")[:42],
        (r.get("tag") or "")[:20], r.get("wa"), r.get("env"))


def cmd_range(lo, hi):
    C.auth()
    st = load()
    for pid in range(lo, hi + 1):
        try:
            print(row(pid, info(pid, st)))
        except Exception as e:
            print("%-6s ERR %s" % (pid, str(e)[:60]))
    save(st)


def cmd_next(after):
    """从 after+1 起找第一个有名字且未解出的题。"""
    C.auth()
    st = load()
    pid = after + 1
    while pid < after + 500:
        try:
            r = info(pid, st)
        except Exception:
            pid += 1
            continue
        if r.get("name") and not r["solved"]:
            print("NEXT %s" % row(pid, r))
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
    for it in data:
        pid = it.get("id")
        if not pid:
            continue
        rec = {"name": it.get("title") or it.get("name"),
               "solved": bool(it.get("is_solved")),
               "open": bool(it.get("is_open")),
               "wa": it.get("wa"),
               "tag": "/".join(t[0] for t in (it.get("tag") or []) if isinstance(t, list) and t),
               "env": bool(it.get("has_environment"))}
        st[str(pid)] = rec
        print(row(pid, rec))
    save(st)


def main():
    ap = argparse.ArgumentParser(description="NSSCTF 选题")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--range", nargs=2, type=int, metavar=("START", "END"))
    g.add_argument("--next", action="store_true")
    g.add_argument("--page", type=int)
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