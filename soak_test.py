# -*- coding: utf-8 -*-
"""
稳定性测试编排（Soak Test）
========================================================
目标：不做一次性压测，而是"连续跑几个小时"，并持续观察指标是否随时间劣化。

设计思路（不改动 send_test.py 的发送逻辑，靠"反复调用 + 结果聚合"实现）：
  每轮调用一次 send_test.py（--max <batch>），单轮结果写到临时目录；
  编排脚本读取本轮指标，追加到 trend.csv；
  正常轮的明细被清掉，异常轮保留，避免一晚上堆出几千个日志/表格；
  最后只产出 4 类文件：soak.log / trend.csv / summary.json / rounds(异常轮)。

Redis 流膨胀处理（--clean）：
  monitor   = 只记录 XLEN 趋势，不清理（默认，最安全，适合中台自己消费正常的场景）
  per-round = 每轮结束后清理"回复流"：删消费组 + 清空内容 + 补一条占位
              （保留流本身，避免下轮插件因流不存在而建消费组失败；
               请求流 DataHub_req_stream 始终只监控、不清理，防止误删中台未消费的请求）

用法（Linux，建议 nohup / screen / tmux 后台运行，断开 SSH 也不停）：
  # 8 小时，每轮 1000 条，只监控不清理
  python3 soak_test.py --interface create --hours 8 --batch 1000 --clean monitor

  # 每轮清理回复流，轮间停 1 秒
  python3 soak_test.py --interface create --hours 8 --batch 1000 --clean per-round --gap 1

  # 短测：只跑 5 轮就正常收尾（--rounds 优先于 --hours，适合验证流程/快速回归）
  python3 soak_test.py --interface query --rounds 5 --batch 200 --workers 4 --wait 30

  # 先快速试跑 6 分钟（0.1 小时）验证流程
  python3 soak_test.py --interface query --hours 0.1 --batch 500

  # 其它未识别参数会原样透传给 send_test.py（--workers/--procs/--type/--wait/--quiet ...）
  python3 soak_test.py --interface create --hours 8 --batch 1000 --workers 12 --type normal --wait 60 --quiet

后台运行示例：
  nohup python3 soak_test.py --interface create --hours 8 --batch 1000 --clean monitor \
        --workers 12 --type normal --wait 60 --quiet > /dev/null 2>&1 &
  然后 tail -f out/soak/create_*/soak.log

输出（out/soak/{interface}_{ts}/）：
  soak.log       编排日志（每轮一行关键指标 + 异常）
  trend.csv      每轮指标时间序列（核心产物，可直接拉去画图）
  summary.json   整体汇总
  rounds/        异常轮（或加 --keep-round-stats 时全部轮）的 stats JSON
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEND_TEST = os.path.join(BASE_DIR, "send_test.py")
REQ_STREAM = "DataHub_req_stream"          # 请求流（中台消费）
REPLY_STREAM_FALLBACK = "WT-0-reply"       # 回复流兜底名（实际从请求字段里取）

# 异常判定阈值（只用于给该轮打"异常"标记并保留明细，不中断整体测试）
MIN_OK_RATE = 99.0        # 成功率下限 %
MIN_REPLY_RATE = 90.0     # 回复率下限 %


# ==================== 工具 ====================
def _now_str():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _read_ini_redis(cfg_dir):
    """从 DataHub.ini 读 [REDIS] 段（缺省回退环境变量/内置默认）"""
    host = os.environ.get("REDISHOST", "192.168.1.137")
    pwd = os.environ.get("REDISPWD", "QianLong@2026&")
    port = int(os.environ.get("REDISPORT", "6379"))
    db = int(os.environ.get("REDISSELECT", "0"))
    ini = os.path.join(cfg_dir, "DataHub.ini")
    if os.path.exists(ini):
        try:
            import configparser
            cp = configparser.ConfigParser()
            cp.read(ini, encoding="utf-8")
            if cp.has_section("REDIS"):
                s = cp["REDIS"]
                host = s.get("REDISHOST", host)
                pwd = s.get("REDISPWD", pwd)
                port = int(s.get("REDISPORT", port))
                db = int(s.get("REDISSELECT", db))
        except Exception:
            pass
    return host, port, pwd, db


class StreamProbe:
    """Redis 流长度监控 + 回复流清理（复用 mock_datahub 的纯 socket 客户端）"""

    def __init__(self, host, port, pwd, db):
        self._cfg = (host, port, pwd, db)
        self._conn = None
        self._reply_stream = None

    def _c(self):
        if self._conn is None:
            from mock_datahub import RespClient
            h, p, w, d = self._cfg
            self._conn = RespClient(h, p, w, d)
            self._conn.connect()
        return self._conn

    def _reset(self):
        try:
            if self._conn:
                self._conn.close()
        except Exception:
            pass
        self._conn = None

    def xlen(self, stream):
        try:
            v = self._c().cmd("XLEN", stream)
            return int(v) if v is not None else None
        except Exception:
            self._reset()
            return None

    def reply_stream(self):
        """取中台实际使用的回复流名（reply_reply_stream），失败回退 WT-0-reply"""
        if self._reply_stream:
            return self._reply_stream
        try:
            resp = self._c().cmd("XREVRANGE", REQ_STREAM, "+", "-", "COUNT", "20")
        except Exception:
            self._reset()
            return REPLY_STREAM_FALLBACK
        for entry in resp or []:
            fields = entry[1] if isinstance(entry, list) and len(entry) > 1 else []
            kv = dict(zip(fields[0::2], fields[1::2]))
            v = kv.get("reply_reply_stream")
            if v:
                self._reply_stream = v
                return v
        return REPLY_STREAM_FALLBACK

    def clean_reply(self, stream):
        """清理回复流：删消费组 + 清空内容 + 补一条占位。

        保留流本身很关键——若直接 DEL 掉，下一轮插件启动时 XGROUP CREATE 会因
        "流不存在"而失败（它没带 MKSTREAM），导致回复读取残缺。
        """
        try:
            c = self._c()
            try:
                c.cmd("XGROUP", "DESTROY", stream, "user_group")   # group 不存在会报错，忽略
            except Exception:
                pass
            try:
                c.cmd("XTRIM", stream, "MAXLEN", "0")               # 清空消息（流可能被自动删除）
            except Exception:
                pass
            c.cmd("XADD", stream, "*", "_soak_keepalive_", "1")     # 补占位，确保流仍存在
            return True
        except Exception:
            self._reset()
            return False


# ==================== 用例轮换（避免每轮重复同一批数据）====================
def _count_excel_rows(excel_path):
    """统计 Excel 数据行数（表头之后的非空行）。失败返回 0。"""
    try:
        from openpyxl import load_workbook
        wb = load_workbook(excel_path, read_only=True, data_only=True)
        ws = wb.active
        n = 0
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                continue
            if row is None or all(v is None or str(v).strip() == "" for v in row):
                continue
            n += 1
        wb.close()
        return n
    except Exception:
        return 0


def _cases_spec(offset, batch, total):
    """按行号生成 --cases 规格（1 起始，末尾回绕）。total<=0 或 batch>=total 时返回 None（全发）。"""
    if total <= 0 or batch >= total:
        return None
    parts, cur, left = [], offset % total + 1, batch
    while left > 0:
        take = min(left, total - cur + 1)
        parts.append(f"{cur}-{cur + take - 1}" if take > 1 else str(cur))
        left -= take
        cur = 1
    return ",".join(parts)


# ==================== 数值容错 ====================
# 背景（0919 soak 事故）：stats JSON 里的字段可能是字符串 'N/A'（表示"该项不适用"）。
# 'N/A' 是【非空字符串 = truthy】，所以 `int(v or 0)` 里 `or 0` 兜不住它，
# int() 会抛 ValueError。原写法 totals["expect"] += int(stats.get("期望回复数") or 0)
# 因此就地崩掉整场 soak —— 计划 32h、已跑 21.5h 的任务被一轮脏数据终止。
def _as_num(v):
    """把 stats 值安全转成数值；'N/A'/None/''/非法值一律返回 None。"""
    if isinstance(v, bool):          # bool 是 int 的子类，但不能当性能数值用
        return None
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def _int_or(v, default=0):
    n = _as_num(v)
    return int(n) if n is not None else default


def _float_or(v, default=0.0):
    n = _as_num(v)
    return float(n) if n is not None else default


def _acc_round(totals, stats):
    """把一轮 stats 累加进 totals，返回 (bad, reply_unknown)。

    reply_unknown：期望回复数是 'N/A'，说明该轮没跑到回复结算
    （多为插件未就绪、一条请求都没发出去）。这本身必须判为异常轮——
    若静默当成 0，会把"插件没起来"伪装成"正常跑完"，丢掉关键信号。

    注意：本函数不累加 totals["rounds"]（轮次计数由主循环统一负责，
    确保无论走正常/异常/失败哪条路径都只计一次，不会重复或漏计）。
    """
    ok_rate = _float_or(stats.get("成功率%"))
    reply_rate = _float_or(stats.get("回复率%"))
    reply_unknown = _as_num(stats.get("期望回复数")) is None
    bad = reply_unknown or ok_rate < MIN_OK_RATE or reply_rate < MIN_REPLY_RATE
    totals["req"] += _int_or(stats.get("总请求数"))
    totals["ok"] += _int_or(stats.get("成功数"))
    totals["fail"] += _int_or(stats.get("失败数"))
    totals["expect"] += _int_or(stats.get("期望回复数"))
    totals["got"] += _int_or(stats.get("收到回复数"))
    if reply_unknown:
        totals["reply_unknown"] += 1
    return bad, reply_unknown


# ==================== 单轮执行 ====================
def run_round(args, round_no, round_dir, cases_spec=None):
    """跑一轮 send_test.py。返回 (stats_dict 或 None, 错误信息)。"""
    os.makedirs(round_dir, exist_ok=True)
    # soak 自己的强制参数放在透传参数之后，确保覆盖（如 --max / --stats-out）
    cmd = [sys.executable, SEND_TEST] + list(args.passthrough) + [
        "--interface", args.interface,
        "--max", str(args.batch),
        "--stats-out", round_dir,
        "--no-run-log",
    ]
    if cases_spec:
        cmd += ["--cases", cases_spec]
    env = dict(os.environ)
    env["SEND_RUN_SUFFIX"] = f"_soak{round_no}"
    try:
        p = subprocess.run(cmd, cwd=BASE_DIR, env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=args.round_timeout)
        tail = (p.stdout or b"").decode("utf-8", "replace").strip().splitlines()
        tail = " | ".join(tail[-3:]) if tail else ""
    except subprocess.TimeoutExpired:
        return None, f"单轮超时 {args.round_timeout}s"
    except Exception as e:
        return None, f"子进程异常: {e}"

    stats = None
    try:
        files = sorted(
            (f for f in os.listdir(round_dir) if f.endswith("_stats.json")),
            key=lambda f: os.path.getmtime(os.path.join(round_dir, f)))
        if files:
            with open(os.path.join(round_dir, files[-1]), encoding="utf-8") as fh:
                stats = json.load(fh).get("summary")
    except Exception as e:
        return None, f"读取 stats 失败: {e}"
    if stats is None:
        return None, f"未生成 stats（退出码 {p.returncode}）{tail}"
    return stats, ""


# ==================== 主流程 ====================
def main():
    ap = argparse.ArgumentParser(
        description="稳定性测试编排（复用 send_test.py，按轮持续发送并汇总趋势）")
    ap.add_argument("--interface", required=True, help="接口名，如 create / query")
    ap.add_argument("--hours", type=float, default=8.0, help="总时长小时（默认 8）")
    ap.add_argument("--rounds", type=int, default=0,
                    help="按轮数跑（如 5），指定后忽略 --hours。便于短测："
                         "跑够 N 轮即正常收尾并生成 summary/trend")
    ap.add_argument("--batch", type=int, default=1000, help="每轮条数（默认 1000）")
    ap.add_argument("--gap", type=float, default=0.0, help="轮间间隔秒（默认 0）")
    ap.add_argument("--clean", choices=["monitor", "per-round"], default="monitor",
                    help="Redis 流处理：monitor=只监控不清理(默认)；per-round=每轮清理回复流")
    ap.add_argument("--keep-round-stats", action="store_true",
                    help="保留每一轮的 stats JSON（默认只保留异常轮，避免文件过多）")
    ap.add_argument("--round-timeout", type=float, default=300.0,
                    help="单轮最长秒数，防卡死（默认 300）")
    ap.add_argument("--soak-out", default="", help="输出根目录（默认 out/soak）")
    ap.add_argument("--rotate", action="store_true",
                    help="每轮轮换用例（按行号分段，末尾回绕），避免重复发同一批数据"
                         "（create 等有唯一性约束的接口建议开启）")
    args, unknown = ap.parse_known_args()
    args.passthrough = unknown

    host, port, pwd, db = _read_ini_redis(BASE_DIR)
    probe = StreamProbe(host, port, pwd, db)

    root = args.soak_out or os.path.join(BASE_DIR, "out", "soak")
    run_id = time.strftime("%Y%m%d_%H%M%S")
    prefix = f"soak_{args.interface}_{run_id}"
    os.makedirs(root, exist_ok=True)
    rounds_dir = os.path.join(root, f"{prefix}_rounds")
    os.makedirs(rounds_dir, exist_ok=True)

    trend_path = os.path.join(root, f"{prefix}_trend.csv")
    soak_log_path = os.path.join(root, f"{prefix}_soak.log")
    summary_path = os.path.join(root, f"{prefix}_summary.json")
    _log_fp = open(soak_log_path, "w", encoding="utf-8")

    def log(msg):
        line = f"[{_now_str()}] {msg}"
        print(line, flush=True)
        _log_fp.write(line + "\n")
        _log_fp.flush()

    total_rows = 0
    if args.rotate:
        excel = os.path.join(BASE_DIR, "data", f"{args.interface}.xlsx")
        total_rows = _count_excel_rows(excel)

    # 终止条件二选一：--rounds N（按轮数，便于短测）优先于 --hours（按时长）
    by_rounds = args.rounds > 0
    deadline = None if by_rounds else time.time() + args.hours * 3600
    target_desc = f"轮数={args.rounds}" if by_rounds else f"时长={args.hours}h"
    log(f"稳定性测试开始: 接口={args.interface} {target_desc} 每轮={args.batch} "
        f"清理={args.clean} 轮间隔={args.gap}s")
    if args.rotate:
        log(f"用例轮换: {args.interface}.xlsx 共 {total_rows} 行数据"
            + ("（每轮按行号轮换，末尾回绕）" if total_rows else "（读取失败，将不轮换）"))
    log(f"Redis={host}:{port} db={db}  输出目录={root}（前缀 {prefix}）")
    if args.passthrough:
        log(f"透传 send_test.py 参数: {' '.join(args.passthrough)}")

    header = ["轮次", "时间", "请求数", "成功数", "失败数", "成功率%",
              "期望回复", "收到回复", "缺回复", "回复率%",
              "发送耗时(s)", "等待回复(s)", "SendMQ均(µs)", "p99(µs)", "max(µs)",
              "CPU平均%", "请求流XLEN", "回复流XLEN", "异常"]
    with open(trend_path, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerow(header)

    totals = {"rounds": 0, "abnormal": 0, "skipped": 0, "req": 0, "ok": 0, "fail": 0,
              "expect": 0, "got": 0, "reply_unknown": 0}
    abnormal_rounds = []
    round_no = 0
    start_ts = time.time()

    try:
        while True:
            if by_rounds:
                if round_no >= args.rounds:
                    break
            elif time.time() >= deadline:
                break
            round_no += 1
            if by_rounds:
                remain_desc = f"剩余 {args.rounds - round_no} 轮"
            else:
                remain_desc = f"剩余 {(deadline - time.time()) / 60:.1f} 分钟"
            log(f"--- 第 {round_no} 轮开始（{remain_desc}）---")
            round_dir = os.path.join(rounds_dir, f"r{round_no:05d}")
            cases_spec = None
            if args.rotate and total_rows > 0:
                cases_spec = _cases_spec((round_no - 1) * args.batch, args.batch, total_rows)
            t0 = time.time()
            # 单轮全程异常隔离：任何一轮的意外异常只标记该轮为异常并继续，
            # 绝不允许它终止整场 soak（0919 事故：一轮的 int('N/A') 干掉了跑了 21.5h 的任务）
            req_xlen = reply_xlen = None
            try:
                stats, err = run_round(args, round_no, round_dir, cases_spec)
                dt = time.time() - t0

                req_xlen = probe.xlen(REQ_STREAM)
                reply_stream = probe.reply_stream()
                reply_xlen = probe.xlen(reply_stream)

                if stats is None:
                    # 「过滤后无用例」是轮换区间与 --type 不匹配的数据问题，不是系统异常：
                    # rotate 绕到 Excel 尾部时该段可能全是 error/destroy，被 --type normal 滤空。
                    # 计入异常会污染趋势判定（0917 那次跑出 87 个此类记录，中台其实全程正常）。
                    if "过滤后无用例" in err or "未匹配到任何用例" in err:
                        totals["skipped"] += 1
                        log(f"第 {round_no} 轮跳过（该轮用例不匹配 --type 过滤）: "
                            f"{err.split('|')[-1].strip()[:80]}")
                        continue
                    log(f"第 {round_no} 轮失败: {err}（耗时 {dt:.1f}s）")
                    totals["rounds"] += 1      # 总轮次=所有非跳过轮（含异常轮），见下
                    totals["abnormal"] += 1
                    abnormal_rounds.append(round_no)
                    # 列数必须与表头一致（19 列）：轮次/时间(2) + 中间指标(14)
                    # + 请求流XLEN/回复流XLEN/异常(3)。此前误写 15，导致异常轮多一列、
                    # 整行列错位（回复流XLEN 显示成 XXXX01、异常列变成 xlen 值）
                    row = [round_no, _now_str()] + [""] * 14 + [req_xlen, reply_xlen, f"ERR:{err}"]
                else:
                    bad, reply_unknown = _acc_round(totals, stats)
                    totals["rounds"] += 1      # 总轮次=所有非跳过轮（含异常轮）
                    if bad:
                        totals["abnormal"] += 1
                        abnormal_rounds.append(round_no)
                    # 回复未知(N/A)要显式标出：这不是"跑正常了"，而是没跑到回复结算
                    flag = ("异常(回复N/A)" if reply_unknown else "异常") if bad else ""
                    row = [round_no, _now_str(),
                           stats.get("总请求数"), stats.get("成功数"), stats.get("失败数"),
                           stats.get("成功率%"), stats.get("期望回复数"), stats.get("收到回复数"),
                           stats.get("缺回复数"), stats.get("回复率%"),
                           stats.get("发送耗时(s)"), stats.get("等待回复耗时(s)"),
                           stats.get("SendMQ平均(µs)"), stats.get("SendMQ p99(µs)"),
                           stats.get("SendMQ max(µs)"), stats.get("CPU平均%"),
                           req_xlen, reply_xlen, flag]
                    log(f"第 {round_no} 轮完成: 请求={stats.get('总请求数')} "
                        f"成功={stats.get('成功数')} "
                        f"回复={stats.get('收到回复数')}/{stats.get('期望回复数')} "
                        f"回复率={stats.get('回复率%')} 耗时={dt:.1f}s"
                        + ("  [异常]" if bad else "")
                        + ("  [回复N/A:该轮未跑到回复结算]" if reply_unknown else ""))
                    # 正常轮清掉明细避免堆积；异常轮保留供排查
                    if not args.keep_round_stats and not bad:
                        try:
                            for fn in os.listdir(round_dir):
                                os.remove(os.path.join(round_dir, fn))
                        except Exception:
                            pass
            except Exception as e:
                # 本轮出意外 -> 只记异常轮，继续下一轮（不 re-raise）
                dt = time.time() - t0
                totals["rounds"] += 1      # 总轮次=所有非跳过轮（含异常轮）
                totals["abnormal"] += 1
                abnormal_rounds.append(round_no)
                log(f"第 {round_no} 轮异常（已隔离，继续后续轮次）: "
                    f"{type(e).__name__}: {e}（耗时 {dt:.1f}s）")
                row = [round_no, _now_str()] + [""] * 14 + \
                      [req_xlen, reply_xlen, f"EXC:{type(e).__name__}: {e}"]

            with open(trend_path, "a", newline="", encoding="utf-8-sig") as f:
                csv.writer(f).writerow(row)

            if args.clean == "per-round":
                ok = probe.clean_reply(reply_stream)
                log(f"清理回复流 {reply_stream}: {'OK' if ok else '失败'}")

            # 轮间间隔：按轮数模式下无 deadline，直接用 --gap
            gap_left = args.gap if by_rounds else max(0.0, deadline - time.time())
            if gap_left > 0:
                time.sleep(min(args.gap, gap_left))
    except KeyboardInterrupt:
        log("收到中断信号，提前结束...")
    finally:
        elapsed = time.time() - start_ts
        summary = {
            "interface": args.interface,
            "run_id": run_id,
            "mode": "rounds" if by_rounds else "hours",
            "rounds_planned": args.rounds if by_rounds else None,
            "hours_planned": None if by_rounds else args.hours,
            "batch": args.batch,
            "clean_mode": args.clean,
            "rounds_total": totals["rounds"],
            "rounds_abnormal": totals["abnormal"],
            "rounds_skipped": totals["skipped"],
            "rounds_reply_unknown": totals["reply_unknown"],
            "abnormal_rounds": abnormal_rounds,
            "req_total": totals["req"],
            "ok_total": totals["ok"],
            "fail_total": totals["fail"],
            "expect_total": totals["expect"],
            "got_total": totals["got"],
            "ok_rate%": round(totals["ok"] / totals["req"] * 100, 2) if totals["req"] else 0,
            "reply_rate%": (round(totals["got"] / totals["expect"] * 100, 2)
                            if totals["expect"] else "N/A"),
            "elapsed_s": round(elapsed, 1),
        }
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        log("稳定性测试结束，汇总:")
        for k, v in summary.items():
            log(f"  {k}: {v}")
        log(f"趋势文件: {trend_path}")
        _log_fp.close()


if __name__ == "__main__":
    main()
