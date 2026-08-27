# -*- coding: utf-8 -*-
"""
通用多线程压测脚本（支持任意接口 + 正常/错误/破坏测试）
========================================================
流程：
  data/{接口}.xlsx 逐行读取测试数据
    -> 按接口定义构造报文(JSON)
    -> 多线程并发通过 libdatahub_trade_plug.so 的 SendMQ 发送
    -> 插件内部异步经 Redis 送数据中台，回复走回调返回

case_type 分流：
  normal  - 正常数据：走插件 SendMQ（性能测试）
  error   - 错误数据：走插件 SendMQ（看插件如何处理异常/是否拒绝）
  destroy - 破坏数据：默认【直接写 Redis】(绕过插件，--destroy-via-plugin 可改为走插件)

用法：
  python send_test.py --interface query            # 发送 data/query.xlsx
  python send_test.py --interface acc_sign --no-send   # 预览报文
  python send_test.py --interface query --workers 16 --max 1000
  python send_test.py --interface query --destroy-via-plugin
"""
import argparse
import ctypes
import importlib
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
INTERFACES_DIR = os.path.join(BASE_DIR, "interfaces")
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, INTERFACES_DIR)

from mock_datahub import MockDataHub, RespClient
from perf_stats import PerfStats

try:
    from openpyxl import load_workbook
except ImportError:
    sys.exit("缺少 openpyxl，请先执行: pip install openpyxl")

# ---------- Redis 配置（默认 + 环境变量；真正以 DataHub.ini 为准）----------
REDIS_HOST = os.environ.get("REDISHOST", "192.168.1.137")
REDIS_PASSWORD = os.environ.get("REDISPWD", "QianLong@2026&")
REDIS_PORT = int(os.environ.get("REDISPORT", "6379"))
REDIS_SELECT = int(os.environ.get("REDISSELECT", "0"))

# 请求流名（插件/破坏测试都写入这里，数据中台从此消费）
REQ_STREAM = "DataHub_req_stream"

# 安静模式：不打印每条报文/回复，只输出关键信息（大并发压测时减少 GUI 日志量）
QUIET = False


def load_redis_cfg(cfg_path):
    """从 DataHub.ini 读取 REDIS 配置（插件实际上读这个文件，不是环境变量）"""
    global REDIS_HOST, REDIS_PASSWORD, REDIS_PORT, REDIS_SELECT
    ini = os.path.join(cfg_path, "DataHub.ini")
    if not os.path.exists(ini):
        return
    import configparser
    cp = configparser.ConfigParser()
    try:
        cp.read(ini, encoding="utf-8")
    except Exception:
        try:
            cp.read(ini)
        except Exception:
            return
    if cp.has_section("REDIS"):
        sec = cp["REDIS"]
        REDIS_HOST = sec.get("REDISHOST", REDIS_HOST)
        REDIS_PASSWORD = sec.get("REDISPWD", REDIS_PASSWORD)
        REDIS_PORT = int(sec.get("REDISPORT", REDIS_PORT))
        REDIS_SELECT = int(sec.get("REDISSELECT", REDIS_SELECT))
        print(f"[INFO] DataHub.ini REDIS配置: host={REDIS_HOST} port={REDIS_PORT} select={REDIS_SELECT}")


SO_CANDIDATES = [
    os.environ.get("SO_PATH", ""),
    os.path.join(BASE_DIR, "libdatahub_trade_plug.so"),
    os.path.join(BASE_DIR, "..", "lib", "libdatahub_trade_plug.so"),
    "/home/yangsh/so_test/libdatahub_trade_plug.so",
    "/home/liuyi/tmp/lib/libdatahub_trade_plug.so",
]


def find_so(explicit=""):
    if explicit and os.path.exists(explicit):
        return explicit
    for p in SO_CANDIDATES:
        if p and os.path.exists(p):
            return p
    return None


def load_interface(name):
    try:
        mod = importlib.import_module(name)
    except ImportError:
        avail = [f[:-3] for f in os.listdir(INTERFACES_DIR)
                 if f.endswith(".py") and not f.startswith(("__", "_"))]
        sys.exit(f"[FAIL] 接口 {name} 不存在。可用接口: {avail}")
    for attr in ("NAME", "HEADERS", "ROWS", "build_payload"):
        if not hasattr(mod, attr):
            sys.exit(f"[FAIL] 接口 {name} 缺少 {attr}")
    return mod


def load_cases(excel, max_cases):
    wb = load_workbook(excel, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        sys.exit(f"[FAIL] {excel} 为空")

    def _key(h):
        # 用 ASCII 限定，避免 \w 在 Unicode 模式下匹配到中文（如 "(逗号分隔)"）
        m = re.search(r"\(([A-Za-z_][A-Za-z0-9_]*)\)", str(h))
        return m.group(1) if m else str(h).strip()

    headers = [_key(h) for h in rows[0]]
    cases = []
    for raw in rows[1:]:
        if raw is None or all(v is None or str(v).strip() == "" for v in raw):
            continue
        rec = {headers[i]: ("" if raw[i] is None else raw[i]) for i in range(len(headers))}
        rec["_no"] = rec.get("case_no") or f"C{len(cases) + 1}"
        rec["_type"] = (rec.get("case_type") or "normal").strip().lower()
        cases.append(rec)
    return cases


# ==================== 插件客户端 ====================
_ReplyCb = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p)


class DataHubClient:
    """封装 libdatahub_trade_plug.so 的 C API"""

    def __init__(self, so_path, unique="test", cfg_path=None, reply_flag=0):
        if cfg_path is None:
            cfg_path = BASE_DIR + "/"
        self.reply_flag = reply_flag
        self.lib = ctypes.CDLL(so_path)
        self.lib.CreateMQ.argtypes = [ctypes.c_char_p, ctypes.c_char_p, _ReplyCb]
        self.lib.CreateMQ.restype = ctypes.c_void_p
        self.lib.SendMQ.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p,
                                    ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        self.lib.SendMQ.restype = ctypes.c_int
        self.lib.get_version.restype = ctypes.c_char_p

        self._replies = []
        self._lock = threading.Lock()

        def _on_msg(msg_id, data1, data2):
            s1 = data1.decode("utf-8", "replace") if data1 else ""
            s2 = data2.decode("utf-8", "replace") if data2 else ""
            with self._lock:
                self._replies.append((s2, s1))
            if not QUIET:
                print(f"  [reply] id={msg_id} req_id={s2} data={s1[:200]}")

        self._cb = _ReplyCb(_on_msg)
        self.mq = self.lib.CreateMQ(unique.encode(), cfg_path.encode(), self._cb)
        if not self.mq:
            raise RuntimeError("CreateMQ 返回空句柄")
        print(f"[OK] CreateMQ 成功，插件版本 {self.lib.get_version().decode()}，Redis={REDIS_HOST}")

    def _send_raw(self, payload, req_id, reply_flag, err):
        return self.lib.SendMQ(self.mq, payload.encode(), req_id.encode(),
                               reply_flag, err, 128)

    def wait_ready(self, timeout=15.0, probe_payload=None):
        if probe_payload is None:
            probe_payload = json.dumps(
                {"query": {"Account": {"AccountType": 1, "AccAtt": 6, "FAccount": "probe"}}})
        err = ctypes.create_string_buffer(128)
        start = time.time()
        while time.time() - start < timeout:
            ret = self._send_raw(probe_payload, "ready_probe", 0, err)
            if ret >= 0:
                print(f"[OK] 插件已 inited（{time.time() - start:.1f}s），可发送")
                return True
            time.sleep(0.5)
        print(f"[FAIL] {timeout}s 内插件未 inited")
        return False

    def send(self, payload, req_id, reply_flag=None):
        if reply_flag is None:
            reply_flag = self.reply_flag
        err = ctypes.create_string_buffer(128)
        ret = self._send_raw(payload, req_id, reply_flag, err)
        if ret < 0:
            print(f"  [FAIL] send {req_id}: {err.value.decode('utf-8','replace')}")
        return ret


# ==================== 破坏测试：直接写 Redis ====================
# 按实测 DataHub_req_stream 的 6 字段格式写入，字段值与插件真实行为一致：
#   request_id / server_id / server_type / reply_req_stream / reply_reply_stream / task
# 破坏测试分两类：
#   type1 - 核心字段正确，task 乱写（测数据中台对畸形业务数据的处理）
#   type2 - 核心字段乱填（测数据中台对异常来源消息的处理）
# type2 固定模板轮换（按 req_id 稳定哈希取模，保证可复现）：
#   {req_id} 会被替换为实际用例编号。每套组合覆盖一类破坏：
#   0 特殊符号+超大数字 / 1 类型错误 / 2 超长溢出 / 3 空值空白 / 4 控制字符 / 5 混合乱填
_TYPE2_TEMPLATES = [
    {  # 0 特殊符号包裹 + 超大数字 + 乱值
        "request_id": "$$${req_id}###",
        "server_id": "999999999999",
        "server_type": "XXX",
        "reply_req_stream": "no_such_stream",
        "reply_reply_stream": "garbage_reply",
    },
    {  # 1 类型错误：server_id 喂非数字（其余字段正常）
        "request_id": "$$${req_id}###",
        "server_id": "abc",
        "server_type": "WT",
        "reply_req_stream": "WT-abc",
        "reply_reply_stream": "WT-abc-reply",
    },
    {  # 2 超长溢出：各字段塞超长串
        "request_id": "{req_id}" + "X" * 200,
        "server_id": "123456789012345678901234567890",
        "server_type": "A" * 300,
        "reply_req_stream": "S" * 200,
        "reply_reply_stream": "R" * 200,
    },
    {  # 3 空值/空白
        "request_id": "",
        "server_id": "   ",
        "server_type": "",
        "reply_req_stream": " ",
        "reply_reply_stream": "",
    },
    {  # 4 控制字符/特殊符号
        "request_id": "WT\x00\x01-{req_id}",
        "server_id": "1e5",
        "server_type": "W\x02T",
        "reply_req_stream": "WT-\x03-0",
        "reply_reply_stream": "reply\x00garbage",
    },
    {  # 5 混合乱填：十六进制+乱值+不存在的流
        "request_id": "###{req_id}%%%",
        "server_id": "0x1F",
        "server_type": "sysadmin",
        "reply_req_stream": "wrong_stream_123",
        "reply_reply_stream": "???",
    },
]


def destroy_write_redis(payload, req_id, destroy_mode="type1", server_id="12345"):
    """绕过插件，直接向 DataHub_req_stream 写入破坏数据。返回 True=成功。"""
    try:
        conn = RespClient(REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, db=REDIS_SELECT)
        conn.connect()
        if destroy_mode == "type2":
            # 类2：核心字段乱填。按 req_id 稳定哈希取整套模板，保证可复现
            idx = sum(ord(ch) for ch in str(req_id)) % len(_TYPE2_TEMPLATES)
            tpl = _TYPE2_TEMPLATES[idx]
            fields = {
                k: v.format(req_id=req_id) if isinstance(v, str) else v
                for k, v in tpl.items()
            }
            fields["task"] = payload
        else:
            # 类1：核心字段正确（对齐插件真实值），task 乱写
            fields = {
                "request_id": str(req_id),
                "server_id": server_id,
                "server_type": "WT",
                "reply_req_stream": f"WT-{server_id}",
                "reply_reply_stream": f"WT-{server_id}-reply",
                "task": payload,   # 畸形 JSON / 超长 / 特殊字符
            }
        # 打平成 field1 value1 field2 value2 ...
        flat = []
        for k, v in fields.items():
            flat.append(k)
            flat.append(v)
        conn.cmd("XADD", REQ_STREAM, "*", *flat)
        conn.close()
        tag = f"#{idx}" if destroy_mode == "type2" else ""
        print(f"  [DESTROY/{destroy_mode}{tag}] 已直写 DataHub_req_stream: {req_id}"
              f" server_id={fields.get('server_id', '')}")
        return True
    except Exception as e:
        print(f"  [DESTROY] 失败 {req_id}: {e}")
        return False


# ==================== 主流程 ====================
def main():
    ap = argparse.ArgumentParser(description="通用多线程压测")
    ap.add_argument("--interface", required=True, help="接口名，如 query / acc_sign")
    ap.add_argument("--excel", default="", help="Excel 路径（默认 data/{接口}.xlsx）")
    ap.add_argument("--so", default="", help=".so 路径，缺省自动查找")
    ap.add_argument("--workers", type=int, default=4, help="并发线程数")
    ap.add_argument("--max", type=int, default=0, help="最多处理多少条(0=全部)")
    ap.add_argument("--type", default="",
                    help="只发指定用例类型，逗号分隔，如 normal,error,destroy（空=全部）")
    ap.add_argument("--wait", type=float, default=3.0, help="发完后等待回复秒数")
    ap.add_argument("--reply", type=int, default=0, choices=[0, 1], help="reply_flag")
    ap.add_argument("--init-wait", type=float, default=5.0, help="等待插件 inited 最大秒数(兜底超时，正常2-3s即探测到)")
    ap.add_argument("--mock", action="store_true", default=True, help="启动模拟应答器")
    ap.add_argument("--no-mock", dest="mock", action="store_false", help="关闭模拟应答器")
    ap.add_argument("--verify", action="store_true", help="发送后验证 Redis")
    ap.add_argument("--destroy-via-plugin", action="store_true",
                    help="破坏数据也走插件 SendMQ（默认直接写 Redis）")
    ap.add_argument("--destroy-mode", default="",
                    help="破坏测试类型(type1/type2/mixed)，mixed=交替；空=按 Excel 行级 destroy_mode 列，默认 type1")
    ap.add_argument("--destroy-server-id", default="12345",
                    help="type1 用的 server_id（默认 12345，与 mock 应答一致）")
    ap.add_argument("--no-stats", dest="stats", action="store_false", default=True,
                    help="关闭性能统计(默认开)")
    ap.add_argument("--stats-out", default="",
                    help="统计输出目录（默认 out/performance/）")
    ap.add_argument("--stats-interval", type=float, default=1.0,
                    help="统计采样间隔秒数")
    ap.add_argument("--stats-json", action="store_true", default=True,
                    help="额外保存 summary JSON（供 GUI 批量汇总，默认开）")
    ap.add_argument("--no-stats-json", dest="stats_json", action="store_false",
                    help="关闭 summary JSON 保存")
    ap.add_argument("--no-send", action="store_true", help="只生成报文不发送")
    ap.add_argument("--quiet", action="store_true",
                    help="安静模式：不打印每条报文/回复，只输出关键信息")
    args = ap.parse_args()
    global QUIET
    QUIET = args.quiet

    mod = load_interface(args.interface)
    excel = args.excel or os.path.join(DATA_DIR, f"{mod.NAME}.xlsx")
    cases = load_cases(excel, 0)   # 先读全部
    # --type 过滤：只发指定用例类型（normal/error/destroy，可逗号分隔）
    if args.type:
        allowed = {t.strip().lower() for t in args.type.split(",") if t.strip()}
        cases = [c for c in cases if c["_type"] in allowed]
        if not cases:
            sys.exit(f"[FAIL] 类型 {args.type} 过滤后无用例。可用类型: normal/error/destroy")
    # --max 循环：过滤后再循环到 N 条（压测需要）
    if args.max > len(cases):
        base = cases[:]
        n0 = len(cases)
        while len(cases) < args.max:
            for c in base:
                if len(cases) >= args.max:
                    break
                c2 = dict(c)
                c2["_no"] = f"{c2['_no']}_{len(cases) - n0 + 1}"
                cases.append(c2)
    elif 0 < args.max <= len(cases):
        cases = cases[:args.max]
    print(f"[INFO] 接口={mod.NAME} 从 {excel} 读取 {len(cases)} 条用例")
    from collections import Counter
    print(f"[INFO] 类型分布: {dict(Counter(c['_type'] for c in cases))}\n")

    # 构造报文（按接口 + 行）
    payloads = []
    for c in cases:
        try:
            p = json.dumps(mod.build_payload(c), ensure_ascii=False)
        except Exception as e:
            print(f"  [WARN] {c['_no']} 报文构造失败: {e}，改用原文案")
            p = str(c.get("case_desc"))
        payloads.append(p)
        if not QUIET:
            print(f"  {c['_no']} [{c['_type']}] {p[:160]}")

    so = find_so(args.so)
    load_redis_cfg(BASE_DIR + "/")

    if args.no_send or so is None:
        if so is None and not args.no_send:
            print(f"\n[WARN] 未找到 .so（查找: {SO_CANDIDATES}），已切换为报文预览模式")
        out = os.path.join(BASE_DIR, "out", f"{mod.NAME}_requests.jsonl")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            for p in payloads:
                f.write(p + "\n")
        print(f"\n[DONE] 报文预览模式：已保存到 {out}（共 {len(payloads)} 条）")
        return

    # ---------- 1) 先启动性能统计与模拟应答器（必须先于 CreateMQ）----------
    # 插件在 CreateMQ 后立即发布上线(id=-1)；若应答器此时未完成订阅，
    # 就只能等下一轮心跳（数秒），表现为 inited 前长时间"卡顿"。
    # 因此顺序必须是：订阅就绪 -> CreateMQ -> 立刻收到上线 -> 即刻应答。

    # 性能统计采样线程
    stats = None
    if args.stats:
        stats = PerfStats(redis_cfg={
            "host": REDIS_HOST, "port": REDIS_PORT, "password": REDIS_PASSWORD,
            "db": REDIS_SELECT, "stream": REQ_STREAM,
        })
        stats.start(interval=args.stats_interval)

    mock = None
    if args.mock:
        beat_channels = ["tradeserver_online"]
        if REDIS_SELECT > 0:
            beat_channels.append(f"tradeserver_online_{REDIS_SELECT}")
        print(f"[INFO] (先于 CreateMQ) 启动模拟数据中台应答器，订阅 {beat_channels}...")
        mock = MockDataHub(REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, channels=beat_channels)
        mock.start()
        time.sleep(0.3)   # 给订阅握手指令留一点时间

    # ---------- 2) CreateMQ：插件上线后即刻被 mock 应答 ----------
    client = DataHubClient(so, unique=mod.NAME, reply_flag=args.reply)

    try:
        if not client.wait_ready(timeout=args.init_wait):
            raise SystemExit("插件未就绪，无法发送")

        # 分流：normal/error 走插件；destroy 直写 Redis（或走插件）
        plugin_cases = []
        destroy_cases = []
        for c, p in zip(cases, payloads):
            if c["_type"] == "destroy" and not args.destroy_via_plugin:
                destroy_cases.append((c, p))
            else:
                plugin_cases.append((c, p))

        # 标记发送阶段开始（真实吞吐统计用）
        if stats:
            stats.mark_send_start()

        # 1) 插件发送（normal + error）
        if plugin_cases:
            def do_send(p, req_id):
                t0 = time.perf_counter()
                ret = client.send(p, req_id)
                us = (time.perf_counter() - t0) * 1e6
                if stats:
                    stats.record_send(ret >= 0, len(p.encode("utf-8")), us)
                return ret

            t0 = time.time()
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                futs = [ex.submit(do_send, p, f"{c['_no']}_{i}")
                        for i, (c, p) in enumerate(plugin_cases)]
                ok = sum(1 for f in futs if f.result() >= 0)
            dt = time.time() - t0
            print(f"\n[RESULT] 插件发送成功 {ok}/{len(plugin_cases)}，耗时 {dt:.3f}s，"
                  f"平均 {len(plugin_cases) / dt:.0f} 条/s")

        # 2) 破坏测试：直写 Redis（分 type1/type2 两类）
        if destroy_cases:
            # --destroy-mode: type1/type2/mixed；空=按 Excel 行级 destroy_mode 列，默认 type1
            # mixed = 按顺序交替 type1/type2
            if args.destroy_mode == "mixed":
                mode_func = lambda c, i: ("type1" if i % 2 == 0 else "type2")
            elif args.destroy_mode:
                mode_func = lambda c, i: args.destroy_mode
            else:
                mode_func = lambda c, i: (c.get("destroy_mode") or "type1")
            cnt1 = sum(1 for i, (c, _) in enumerate(destroy_cases) if mode_func(c, i) == "type2")
            cnt2 = len(destroy_cases) - cnt1
            print(f"\n[DESTROY] 破坏测试共 {len(destroy_cases)} 条"
                  f"（type1 核心字段正常/业务数据畸形: {cnt2}，"
                  f"type2 核心字段乱填: {cnt1}），直写 Redis...")
            t0 = time.time()
            ok = 0
            for i, (c, p) in enumerate(destroy_cases):
                ts = time.perf_counter()
                ret = destroy_write_redis(p, c["_no"], mode_func(c, i), args.destroy_server_id)
                us = (time.perf_counter() - ts) * 1e6
                if stats:
                    stats.record_send(ret, len(p.encode("utf-8")), us)
                if ret:
                    ok += 1
            print(f"[DESTROY] 直写成功 {ok}/{len(destroy_cases)}，耗时 {time.time() - t0:.3f}s")

        # 标记发送阶段结束
        if stats:
            stats.mark_send_end()

        print(f"[INFO] 等待 {args.wait}s 收集回复...")
        time.sleep(args.wait)
        print(f"[RESULT] 收到回复数: {client.reply_count}")
        for rid, data in client._replies[:10]:
            print(f"    req_id={rid} -> {data[:200]}")

        if args.verify:
            verify_redis()

    finally:
        if mock:
            mock.stop()
        # 输出性能统计（Excel + log）——放 finally 里，确保一定执行
        if stats:
            try:
                stats.stop()
                out_dir = args.stats_out or os.path.join(BASE_DIR, "out", "performance")
                os.makedirs(out_dir, exist_ok=True)
                ts = time.strftime("%Y%m%d_%H%M%S")
                log_path = os.path.join(out_dir, f"{mod.NAME}_{ts}.log")
                xlsx_path = os.path.join(out_dir, f"{mod.NAME}_{ts}.xlsx")
                stats.save_log(log_path)
                try:
                    stats.save_excel(xlsx_path)
                except Exception as e:
                    print(f"[WARN] Excel 导出失败: {e}")
                    xlsx_path = None
                # summary JSON（供 GUI 批量汇总）
                if args.stats_json:
                    try:
                        json_path = os.path.join(out_dir, f"{mod.NAME}_{ts}_stats.json")
                        with open(json_path, "w", encoding="utf-8") as f:
                            json.dump({"interface": mod.NAME, "ts": ts,
                                       "summary": stats.summary()},
                                      f, ensure_ascii=False, indent=2)
                        print(f"[STATS] JSON 汇总已保存: {json_path}")
                    except Exception as e:
                        print(f"[WARN] JSON 汇总保存失败: {e}")
                print(f"\n[STATS] 性能统计已保存: {log_path}" + (f" / {xlsx_path}" if xlsx_path else ""))
                print("[STATS] 汇总:")
                for k, v in stats.summary().items():
                    print(f"  {k}: {v}")
            except Exception as e:
                print(f"[WARN] 统计输出失败: {e}")
                import traceback
                traceback.print_exc()
        print("[INFO] 插件有后台线程，直接强制退出（跳过 DestroyMQ）")
        os._exit(0)


def verify_redis():
    print("\n[VERIFY] 检查 Redis 中的数据...")
    try:
        conn = RespClient(REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, db=REDIS_SELECT)
        conn.connect()
        for stream in ("DataHub_req_stream",):
            try:
                n = conn.cmd("XLEN", stream)
                print(f"[VERIFY] {stream} 长度: {n}")
            except Exception as e:
                print(f"[VERIFY] {stream} XLEN 失败: {e}")
        conn.close()
    except Exception as e:
        print(f"[VERIFY] Redis 连接失败: {e}")


if __name__ == "__main__":
    main()
