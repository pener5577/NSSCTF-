---
name: nssctf-solver
description: Work NSSCTF challenges one at a time — open the docker env, pull attachments, read the statement and WriteUps, derive the flag, submit it, and record failures. Use when the user asks to 刷题, 做题, 提flag, 继续做题, or continue where the last attempt stopped on NSSCTF. Do not use for other CTF platforms or for theory questions.
---

# NSSCTF Solver

一题一题推进，每题走同一条流水线。核心约束是**不在单题上死磕**。

## 一次性准备

```powershell
pip install websocket-client
```

启动专用 Chrome。**必须用独立 profile** —— 已有 Chrome 窗口在跑时调试参数不生效：

```powershell
chrome.exe --remote-debugging-port=9222 --user-data-dir="$env:TEMP\chrome_nss" https://www.nssctf.cn/
```

在这个窗口手动登录 NSSCTF 一次，然后：

```powershell
$S="$env:USERPROFILE\.trae-cn\skills\nssctf-solver\scripts"
$env:NSS_WORK="$env:USERPROFILE\nss_work"     # 附件与题面落盘处
python $S\cdp.py save-cookie                  # 从浏览器会话重建 cookie.txt
```

每次开工先自检：

```powershell
python $S\cdp.py 324        # 应打印 code=200 title=... is_solved=...
```

## 选题

```powershell
python $S\pick.py --next --after 325     # 从 325 起第一个未解出的题
python $S\pick.py --range 320 340        # 区间状态一览
```

```
OK  324   [第五空间 2021]StrangeLanguage  逆向    wa=4   env=True
wp  327   [长安杯 2021]babyRSA             RSA     wa=4   env=True
--  326   [长安杯 2021]BabyAI - Practice   AIwa=22   env=False
```

`OK` 已解出 / `wp` 未解出但有题解 / `--` 无题解。**优先 `wp`**，`--` 先评估逆向成本再决定。

## 做题

```powershell
python $S\flow.py 327                    # 开环境 + 下附件 + 抓题面 + 抓题解
python $S\flow.py 327 --target           # 交互式题：打印 host:port
python $S\flow.py 327 --submit "NSSCTF{...}"   # 提交，可重复给多个候选
```

已解出的题 `flow.py` 会直接跳过（除非给了 `--submit` 要核对）。

**先读题解**，读不出来再自己逆向 —— 这是最快的路径，别跳过直接硬啃。

产出落在 `$NSS_WORK`：
- `att/P<id>_<附件名>`、`att/P<id>/`（解压后）
- `q/P<id>.txt`（题面）、`q/P<id>.wp*.txt`（题解）

## 硬性约束

**flag 前缀只试 3 种**，不穷举变体：

1. 本体原文（题面或程序里出现的格式）
2. 赛事缩写 `{...}`
3. `NSSCTF{}`

题面通常会明示用哪种，读题面时先确认。

**时间控制**：短时间出不来就记表换下一题。不要反复试几十种解法。

**失败的记入 `FAILED_TABLE.md`**，写清三件事：附件是什么、逆向到了什么结论、卡在哪一步。下次遇到同类题可直接跳过。

## 业务码语义

`submit` 返回的 `code` 决定下一步，含义搞错会白费时间：

| code | 含义 | 动作 |
|---|---|---|
| 200 | 判题通过 | 记下 flag，下一题 |
| 203 | 已 solved 重复提交 | flag 对，别再试 |
| 204 | 答案错误 | 换思路，别再试同一前缀 |
| 201 | UNAUTHORIZED | 登录态失效，重跑 `save-cookie` |
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
别只看"服务器没报错" —— 阈值是自校验，能省掉大量盲试。

## 已知平台细节

踩过的坑，已在脚本里处理：

- **提交必须走浏览器通道**，Python 直连 HTTP 返回 402
- **附件接口**是 `/api/problem/<id>/annex/download/`，返回 CDN 链接，**必须先开环境**否则 203
- `detail` 字段名是 `title` / `annex`（布尔）/ `has_environment` / `tag`，不是 name/attachment
- 新版 Chrome 校验 Origin，脚本已用 `suppress_origin` 兜底

## 不要做的事

- 不要批量扫题，一题一题来
- 没有题解时先评估逆向成本，值不值再动手
- 不要提交超过 3 种前缀变体
- 不要用 Python 直连 HTTP 提交