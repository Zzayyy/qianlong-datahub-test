# -*- coding: utf-8 -*-
"""
模拟数据中台应答器 (Mock DataHub)
==================================
作用：在"数据中台未开放"的情况下，模拟数据中台对 libdatahub_trade_plug.so
     的心跳应答，让插件进入 system inited 状态，从而允许 SendMQ 写入 Redis。

机制（经实验确认）：
  1. 插件 CreateMQ 后往 Redis 频道 tradeserver_online 发布上线消息
     {"id":-1,"unique_string":"WT-x-...","ip":...,"mac":...}
  2. 插件同时订阅频道 <unique_string>（例如 WT-x-...）
  3. 本应答器订阅 tradeserver_online，收到 id=-1 的消息后，
     往 <unique_string> 频道应答 {"id":12345,"unique_string":"...","online":1}
  4. 插件收到应答后 id 从 -1 变为有效值 → system inited → SendMQ 成功

说明：不依赖 redis-py，用纯 socket 实现 RESP 协议（136 的 python3.9 无 redis 模块）。

用法：
  python mock_datahub.py --host 192.168.1.137 --password 'QianLong@2026&'
  常驻运行，Ctrl+C 退出。
"""
import argparse
import json
import socket
import sys
import threading
import time


class RespClient:
    """极简 Redis RESP 客户端（仅支持本脚本需要的命令）"""

    def __init__(self, host, port, password=None, db=0):
        self.host = host
        self.port = port
        self.password = password
        self.db = db
        self.sock = None

    def connect(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=10)
        if self.password:
            self._write("AUTH", self.password)
            self._read()
        if self.db:
            self._write("SELECT", self.db)
            self._read()

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def _write(self, *args):
        buf = bytearray()
        buf.extend(("*%d\r\n" % len(args)).encode())
        for a in args:
            if isinstance(a, str):
                b = a.encode("utf-8")
            else:
                b = str(a).encode("utf-8")   # int 等统一转 str
            buf.extend(("$%d\r\n" % len(b)).encode())
            buf.extend(b)
            buf.extend(b"\r\n")
        self.sock.sendall(bytes(buf))

    def _readline(self):
        data = b""
        while not data.endswith(b"\r\n"):
            chunk = self.sock.recv(1)
            if not chunk:
                raise ConnectionError("connection closed")
            data += chunk
        return data[:-2]

    def _read(self):
        line = self._readline()
        if line.startswith(b"+"):
            return line[1:].decode("utf-8", "replace")
        if line.startswith(b"-"):
            return "ERR " + line[1:].decode("utf-8", "replace")
        if line.startswith(b":"):
            return int(line[1:])
        if line.startswith(b"$"):
            n = int(line[1:])
            if n == -1:
                return None
            data = b""
            while len(data) < n:
                chunk = self.sock.recv(n - len(data))
                if not chunk:
                    raise ConnectionError("connection closed")
                data += chunk
            self._readline()  # 吃掉尾部 \r\n
            return data.decode("utf-8", "replace")
        if line.startswith(b"*"):
            n = int(line[1:])
            if n == -1:
                return None
            return [self._read() for _ in range(n)]
        return line.decode("utf-8", "replace")

    def publish(self, channel, msg):
        self._write("PUBLISH", channel, msg)
        return self._read()

    def subscribe_many(self, channels):
        """一次 SUBSCRIBE 多个频道，返回确认的频道列表"""
        self._write("SUBSCRIBE", *channels)
        confirmed = []
        while len(confirmed) < len(channels):
            resp = self._read()
            if isinstance(resp, list) and resp and resp[0] == "subscribe":
                confirmed.append(resp[1])
        return confirmed

    def cmd(self, *args):
        """执行任意命令并返回结果"""
        self._write(*args)
        return self._read()

    def subscribe(self, channel):
        self._write("SUBSCRIBE", channel)
        # 读 subscribe 确认
        while True:
            resp = self._read()
            if isinstance(resp, list) and resp and resp[0] == "subscribe":
                return resp

    def listen(self, timeout=1.0):
        """读取一条消息；超时返回 None"""
        self.sock.settimeout(timeout)
        try:
            return self._read()
        except socket.timeout:
            return None


class MockDataHub:
    """模拟数据中台：订阅 tradeserver_online，应答插件心跳"""

    ANSWER_ID = 12345
    BEAT_CHANNEL = "tradeserver_online"

    def __init__(self, host, port, password, channels=None):
        self.host = host
        self.port = port
        self.password = password
        # 频道列表：插件按 REDISSELECT 生成 "tradeserver_online" 或 "tradeserver_online_2" 等
        self.channels = channels or [self.BEAT_CHANNEL]
        self._stop = threading.Event()
        self._thread = None
        self.answered = 0          # 已应答次数
        self.last_unique = None    # 最近应答的 unique_string
        self._lock = threading.Lock()

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _publish(self, channel, msg):
        """用常驻的非订阅连接发布（订阅连接上不能执行 PUBLISH）。

        连接复用避免每条应答都重建 TCP+AUTH；断开时自动重建一次。"""
        pub = getattr(self, "_pub_conn", None)
        for attempt in (0, 1):   # 失败重建一次
            try:
                if pub is None:
                    pub = RespClient(self.host, self.port, self.password)
                    pub.connect()
                    self._pub_conn = pub
                pub.publish(channel, msg)
                return
            except Exception:
                try:
                    if pub is not None and pub.sock is not None:
                        pub.sock.close()
                except Exception:
                    pass
                self._pub_conn = None
                pub = None
                if attempt == 1:
                    raise

    def stop(self):
        self._stop.set()
        pub = getattr(self, "_pub_conn", None)
        if pub:
            try:
                pub.close()
            except Exception:
                pass
            self._pub_conn = None

    def _run(self):
        while not self._stop.is_set():
            conn = None
            try:
                conn = RespClient(self.host, self.port, self.password)
                conn.connect()
                confirmed = conn.subscribe_many(self.channels)
                print(f"[MOCK] 已订阅 {len(confirmed)} 个频道: {self.channels} "
                      f"(host={self.host})", flush=True)
                while not self._stop.is_set():
                    msg = conn.listen(timeout=1.0)
                    if msg is None:
                        continue
                    if not isinstance(msg, list) or len(msg) < 3 or msg[0] != "message":
                        continue
                    payload = msg[2]
                    try:
                        data = json.loads(payload)
                    except Exception:
                        continue
                    if data.get("id") != -1:
                        continue  # 只应答插件的上线消息
                    uniq = data.get("unique_string", "")
                    if not uniq:
                        continue
                    reply = json.dumps({
                        "id": self.ANSWER_ID,
                        "unique_string": uniq,
                        "online": 1,
                    })
                    self._publish(uniq, reply)
                    with self._lock:
                        self.answered += 1
                        self.last_unique = uniq
                    print(f"[MOCK] 收到插件上线(id=-1) → 应答到频道[{uniq}]: {reply}", flush=True)
            except Exception as e:
                if not self._stop.is_set():
                    print(f"[MOCK] 连接中断，2s 后重连: {e}", flush=True)
                    time.sleep(2)
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

    @property
    def status(self):
        with self._lock:
            return self.answered, self.last_unique


def main():
    ap = argparse.ArgumentParser(description="模拟数据中台应答器")
    ap.add_argument("--host", default="192.168.1.137", help="Redis 主机")
    ap.add_argument("--port", type=int, default=6379, help="Redis 端口")
    ap.add_argument("--password", default="QianLong@2026&", help="Redis 密码")
    args = ap.parse_args()

    mock = MockDataHub(args.host, args.port, args.password)
    mock.start()
    print(f"[MOCK] 模拟数据中台启动，应答 id={mock.ANSWER_ID}，Ctrl+C 退出", flush=True)
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n[MOCK] 退出")
        mock.stop()


if __name__ == "__main__":
    main()
