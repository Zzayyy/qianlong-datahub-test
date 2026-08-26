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

try:
    from openpyxl import load_workbook
except ImportError:
    sys.exit("缺少 openpyxl，请先执行: pip install openpyxl")

# ---------- Redis 配置（默认 + 环境变量；真正以 DataHub.ini 为准）----------
REDIS_HOST = os.environ.get("REDISHOST", "192.168.1.137")
REDIS_PASSWORD = os.environ.get("REDISPWD", "QianLong@2026&")
REDIS_PORT = int(os.environ.get("REDISPORT", "6379"))
REDIS_SELECT = int(os.environ.get("REDISSELECT", "0"))


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
    if max_cases > 0:
        cases = cases[:max_cases]
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
# 按 请求接口doc.txt 的真实 XADD 格式，写入 DataHub_req_stream，
# 这样数据中台才能取到破坏数据（此前用自定义 DataHub_destroy_stream 中台拿不到）。
def destroy_write_redis(payload, req_id):
    """绕过插件，直接向 DataHub_req_stream 写入破坏数据。返回 True=成功。"""
    try:
        conn = RespClient(REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, db=REDIS_SELECT)
        conn.connect()
        # 对齐请求接口doc.txt 格式：
        # XADD DataHub_req_stream * request_id 'WT-xxx' server_id '0' server_type 'WT'
        #     reply_req_stream 'WT-0' task '<data>'
        fields = {
            "request_id": req_id,
            "server_id": "0",
            "server_type": "WT",
            "reply_req_stream": f"WT-{req_id}",
            "task": payload,   # 畸形 JSON / 超长 / 特殊字符
        }
        # 打平成 field1 value1 field2 value2 ...
        flat = []
        for k, v in fields.items():
            flat.append(k)
            flat.append(v)
        conn.cmd("XADD", "DataHub_req_stream", "*", *flat)
        conn.close()
        print(f"  [DESTROY] 已直写 DataHub_req_stream: {req_id}")
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
    ap.add_argument("--wait", type=float, default=3.0, help="发完后等待回复秒数")
    ap.add_argument("--reply", type=int, default=0, choices=[0, 1], help="reply_flag")
    ap.add_argument("--init-wait", type=float, default=15.0, help="等待插件 inited 最大秒数")
    ap.add_argument("--mock", action="store_true", default=True, help="启动模拟应答器")
    ap.add_argument("--no-mock", dest="mock", action="store_false", help="关闭模拟应答器")
    ap.add_argument("--verify", action="store_true", help="发送后验证 Redis")
    ap.add_argument("--destroy-via-plugin", action="store_true",
                    help="破坏数据也走插件 SendMQ（默认直接写 Redis）")
    ap.add_argument("--no-send", action="store_true", help="只生成报文不发送")
    args = ap.parse_args()

    mod = load_interface(args.interface)
    excel = args.excel or os.path.join(DATA_DIR, f"{mod.NAME}.xlsx")
    cases = load_cases(excel, args.max)
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

    client = DataHubClient(so, unique=mod.NAME, reply_flag=args.reply)

    mock = None
    if args.mock:
        beat_channels = ["tradeserver_online"]
        if REDIS_SELECT > 0:
            beat_channels.append(f"tradeserver_online_{REDIS_SELECT}")
        print(f"[INFO] 启动模拟数据中台应答器，订阅频道 {beat_channels}...")
        mock = MockDataHub(REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, channels=beat_channels)
        mock.start()

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

        # 1) 插件发送（normal + error）
        if plugin_cases:
            t0 = time.time()
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                futs = [ex.submit(client.send, p, f"{c['_no']}_{i}")
                        for i, (c, p) in enumerate(plugin_cases)]
                ok = sum(1 for f in futs if f.result() >= 0)
            dt = time.time() - t0
            print(f"\n[RESULT] 插件发送成功 {ok}/{len(plugin_cases)}，耗时 {dt:.3f}s，"
                  f"平均 {len(plugin_cases) / dt:.0f} 条/s")

        # 2) 破坏测试：直写 Redis
        if destroy_cases:
            print(f"\n[DESTROY] 破坏测试 {len(destroy_cases)} 条，直接写 Redis...")
            ok = sum(1 for c, p in destroy_cases if destroy_write_redis(p, c["_no"]))

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
