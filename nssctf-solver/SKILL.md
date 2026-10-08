---
name: nssctf-solver
description: Work NSSCTF challenges one at a time — open the docker env, pull attachments, read the statement and WriteUps, derive the flag, submit it, and record failures. Use when the user asks to 刷题, 做题, 提flag, 继续做题, or continue where the last attempt stopped on NSSCTF. Do not use for other CTF platforms or for theory questions.
---

# NSSCTF Solver

一题一题推进，每题走同一条流水线。核心约束是**不在单题上死磕**。

## 前置检查（每次开工先做）

```powershell
python scripts/cdp.py 324
```

能打印 `code=200 ... is_solved=` 说明浏览器通道正常。若报 `cookie.txt 不存在`，
在已登录 NSSCTF 的浏览器里执行 `python scripts/cdp.py save-cookie` 重建。

依赖：`pip install websocket-client`。

## 固定流水线

对每个 pid 依次执行，不跳步、不批量扫描：

```powershell
$env:NSS_WORK="<工作目录>"            # 附件与题面落盘处
python scripts/flow.py <pid>                   # 开环境 + 下附件 + 抓题面 + 抓题解
python scripts/flow.py <pid> --target          # 交互式题：打印 host:port
python scripts/flow.py <pid> --submit "<flag>" # 提交，可重复 --submit 给多个候选
```

`flow.py` 自动开环境、下载并解压附件、题面存到 `$NSS_WORK/q/P<pid>.txt`、
题解存到 `q/P<pid>.wp*.txt`。

**先读题解**。读不出来再自己逆向——这是最快的路径，别跳过直接硬啃。

## 硬性约束

**flag 前缀只试 3 种**，不穷举变体：

1. 本体原文（题面或程序里出现的格式）
2. 赛事缩写 `{...}`
3. `NSSCTF{}`

题面通常会明示用哪种，读题面时先确认。

**时间控制**：一题短时间出不来就记表换下一题。不要反复试几十种解法。

**已解出的跳过**：看到 `is_solved=True` 直接下一题。

**失败的记入 `FAILED_TABLE.md`**，写清三件事：附件是什么、逆向到了什么结论、卡在哪。
下次遇到同类题可直接跳过。

## 业务码语义

`submit` 返回的 `code` 决定下一步，含义搞错会白费时间：

| code | 含义 | 动作 |
|---|---|---|
| 200 | 判题通过 | 记下 flag，下一题 |
| 203 | 已 solved 重复提交 | flag 对，别再试 |
| 204 | 答案错误 | 换思路，别再试同一前缀 |
| 201 | UNAUTHORIZED | 登录态失效，重建 cookie |
| 202 | NOT_FOUND | 附件不存在 |

提交后用 `detail(pid)` 的 `is_solved` 复核；`code=203` 时以它为准。

## 交互式题（socket）

题面是脚本交互（给 A、C 让你回 x）时，附件里通常是 `.sage`/`.py` 脚本。
用 `--target` 拿地址，再按脚本逻辑对话：

```python
import socket, time
s = socket.create_connection((host, port), timeout=60)
s.settimeout(1.0)
buf = b""
def until(pat, tmo=120):
    end = time.time() + tmo
    while time.time() < end and pat not in buf:
        try: d = s.recv(65536)
        except socket.timeout: continue
        if not d: break
        buf += d
    return buf
```

脚本常打印期望阈值（如 `norm of vector x*A-C <= 785.77`）。**把自己的结果和阈值比**，
别只看"服务器没报错"——阈值是自校验，能省掉大量盲试。

## 选题顺序

用 `todo_fresh.md` 之类的清单按顺序推进。未列出时用 `cdp.py` 的 `plist()`
拉题目列表，配合 `detail(pid)` 的 `is_solved` / `wa` 判断从哪继续。

## 不要做的事

- 不要批量扫题，一题一题来
- 没有题解时先评估逆向成本，值不值再动手
- 不要提交超过 3 种前缀变体
- 不要用 Python 直连 HTTP 提交（返回 402），必须走浏览器通道