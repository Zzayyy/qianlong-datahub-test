# -*- coding: utf-8 -*-
"""
多线程压测 GUI（PySide6）
=========================
封装 make_excel.py / send_test.py 两个命令行工具：
  - 选择接口 -> 生成 Excel（本地）
  - 配置并发参数 -> 运行发送测试
      * 未启用远程：本地运行（只生成报文，.so 在 Linux 时才真正发送）
      * 启用远程：通过 SSH 在 Linux 上执行，自动上传数据文件并实时回传日志

依赖：venv 环境已装 PySide6 + paramiko（pip install PySide6 paramiko）
运行：venv/Scripts/python.exe gui_test.py
"""
import os
import subprocess
import sys

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QComboBox, QPushButton, QSpinBox,
    QDoubleSpinBox, QCheckBox, QLineEdit, QTextEdit, QGroupBox,
    QGridLayout, QVBoxLayout, QHBoxLayout, QMessageBox,
    QListWidget, QListWidgetItem, QAbstractItemView,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
INTERFACES_DIR = os.path.join(BASE_DIR, "interfaces")
PYTHON = sys.executable


def list_interfaces():
    """扫描 interfaces/ 下的接口定义文件"""
    if not os.path.isdir(INTERFACES_DIR):
        return []
    return sorted(f[:-3] for f in os.listdir(INTERFACES_DIR)
                  if f.endswith(".py") and not f.startswith(("__", "_")))


# ==================== 本地 Worker ====================
class Worker(QThread):
    """本地子进程执行（支持多条命令循环），实时回传输出"""
    line = Signal(str)
    finished = Signal(int)

    def __init__(self, cmds, cwd, parent=None):
        super().__init__(parent)
        # cmds: 单条 [..] 或多条 [[..],[..]]，依次执行
        if cmds and isinstance(cmds[0], list):
            self.cmds = cmds
        else:
            self.cmds = [cmds]
        self.cwd = cwd
        self._proc = None

    def run(self):
        rc_last = 0
        try:
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"
            for cmd in self.cmds:
                self.line.emit("$ " + " ".join(cmd))
                self._proc = subprocess.Popen(
                    cmd, cwd=self.cwd, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                    errors="replace", bufsize=1, env=env)
                for out in self._proc.stdout:
                    self.line.emit(out.rstrip("\n"))
                self._proc.wait()
                rc_last = self._proc.returncode
                if rc_last != 0:
                    break
            self.finished.emit(rc_last)
        except Exception as e:
            self.line.emit(f"[ERROR] {e}")
            self.finished.emit(-1)

    def stop(self):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass


# ==================== SSH Worker ====================
class SshWorker(QThread):
    """通过 SSH 在远程 Linux 上执行命令，实时回传输出"""
    line = Signal(str)
    finished = Signal(int)

    def __init__(self, host, port, username, password, remote_dir, command,
                 files_to_upload=None, download_config=None, parent=None,
                 ini_update=None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.remote_dir = remote_dir
        self.command = command
        self.files_to_upload = files_to_upload or []
        # download_config: {"remote": 远程目录, "local": 本地目录, "patterns": [glob...]}
        self.download_config = download_config
        # ini_update: {"kv": {REDISHOST:..., REDISPORT:...}, } 更新远程 DataHub.ini [REDIS] 段
        self.ini_update = ini_update
        self._client = None
        self._chan = None

    def run(self):
        try:
            import paramiko
        except ImportError:
            self.line.emit("[ERROR] 缺少 paramiko，请先: pip install paramiko")
            self.finished.emit(-1)
            return
        try:
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._client.connect(self.host, port=self.port,
                                 username=self.username, password=self.password,
                                 timeout=15)
            self.line.emit(f"[SSH] 已连接 {self.host}")

            # 更新远程 DataHub.ini [REDIS] 段（保留其他段落）
            if self.ini_update:
                sftp0 = self._client.open_sftp()
                try:
                    ini_path = f"{self.remote_dir}/DataHub.ini"
                    text = ""
                    try:
                        with sftp0.open(ini_path, "r") as fh:
                            text = fh.read().decode("utf-8", "replace")
                    except IOError:
                        text = "[REDIS]\n"
                    import re
                    for key, val in self.ini_update["kv"].items():
                        pat = re.compile(rf"^{key}.*$", re.M)
                        if pat.search(text):
                            text = pat.sub(f"{key}={val}", text)
                        else:
                            text = text.rstrip("\n") + f"\n{key}={val}\n"
                    with sftp0.open(ini_path, "w") as fh:
                        fh.write(text.encode("utf-8"))
                    for key, val in self.ini_update["kv"].items():
                        self.line.emit(f"[SSH] DataHub.ini {key}={val}")
                finally:
                    sftp0.close()

            # 上传文件（数据文件 + 脚本，保持最新）
            if self.files_to_upload:
                sftp = self._client.open_sftp()

                def ensure_dir(path):
                    """递归确保远程目录存在"""
                    parts = path.split("/")
                    cur = ""
                    for p in parts:
                        cur = f"{cur}/{p}".replace("//", "/")
                        if not cur or p == "":
                            continue
                        try:
                            sftp.stat(cur)
                        except IOError:
                            try:
                                sftp.mkdir(cur)
                            except IOError:
                                pass

                # 确保远程根目录 + 子目录存在
                ensure_dir(self.remote_dir)

                def needs_upload(local, remote):
                    """变更检测：远程不存在，或本地比远程新，则需上传"""
                    if not os.path.exists(local):
                        return False
                    try:
                        rstat = sftp.stat(remote)
                    except IOError:
                        return True   # 远程不存在
                    local_mtime = os.path.getmtime(local)
                    remote_mtime = rstat.st_mtime
                    return local_mtime > remote_mtime

                for local, remote in self.files_to_upload:
                    dirpath = "/".join(remote.split("/")[:-1])
                    ensure_dir(dirpath)
                    if not needs_upload(local, remote):
                        self.line.emit(f"[SSH] 跳过上传（已是最新） {os.path.basename(local)}")
                        continue
                    try:
                        sftp.put(local, remote)
                        self.line.emit(f"[SSH] 已上传 {os.path.basename(local)}")
                    except Exception as e:
                        self.line.emit(f"[SSH] 上传 {local} 失败: {e}")
                sftp.close()

            # 远程执行
            full_cmd = f"cd {self.remote_dir} && {self.command}"
            self.line.emit(f"$ {full_cmd}")
            self._chan = self._client.get_transport().open_session()
            self._chan.settimeout(0)
            self._chan.exec_command(full_cmd)
            bufs = {"out": "", "err": ""}
            while True:
                # stdout
                if self._chan.recv_ready():
                    data = self._chan.recv(4096).decode("utf-8", "replace")
                    self._drain("out", bufs, data)
                # stderr（import 错误等都会到 stderr，不读就看不到）
                if self._chan.recv_stderr_ready():
                    data = self._chan.recv_stderr(4096).decode("utf-8", "replace")
                    self._drain("err", bufs, data)
                if self._chan.exit_status_ready() and not self._chan.recv_ready() \
                        and not self._chan.recv_stderr_ready():
                    # 收尾
                    while self._chan.recv_ready():
                        self._drain("out", bufs, self._chan.recv(4096).decode("utf-8", "replace"))
                    while self._chan.recv_stderr_ready():
                        self._drain("err", bufs, self._chan.recv_stderr(4096).decode("utf-8", "replace"))
                    for name in ("out", "err"):
                        if bufs[name].strip():
                            for ln in bufs[name].split("\n"):
                                if ln.strip():
                                    self.line.emit(ln.rstrip("\r"))
                    rc = self._chan.recv_exit_status()
                    # 下载远程结果文件（性能统计 Excel/log）
                    if self.download_config:
                        try:
                            self._download_results(rc)
                        except Exception as e:
                            self.line.emit(f"[SSH] 下载结果失败: {e}")
                    self.finished.emit(rc)
                    return
                self.msleep(50)
        except Exception as e:
            self.line.emit(f"[SSH][ERROR] {e}")
            self.finished.emit(-1)
        finally:
            if self._client:
                try:
                    self._client.close()
                except Exception:
                    pass

    def _download_results(self, rc):
        """执行完后，从远程下载匹配的文件（性能统计 Excel/log）"""
        cfg = self.download_config
        remote_dir = cfg["remote"]
        local_dir = cfg["local"]
        patterns = cfg.get("patterns", ["*.xlsx", "*.log"])
        os.makedirs(local_dir, exist_ok=True)
        sftp = self._client.open_sftp()
        try:
            try:
                files = sftp.listdir_attr(remote_dir)
            except IOError:
                self.line.emit(f"[SSH] 远程目录 {remote_dir} 不存在，无结果可下载")
                return
            import fnmatch
            remote_files = sorted(files, key=lambda a: a.st_mtime, reverse=True)
            downloaded = 0
            for attr in remote_files:
                name = attr.filename
                if any(fnmatch.fnmatch(name, p) for p in patterns):
                    remote_path = f"{remote_dir}/{name}"
                    local_path = os.path.join(local_dir, name)
                    try:
                        sftp.get(remote_path, local_path)
                        self.line.emit(f"[SSH] 已下载结果: {local_path}")
                        downloaded += 1
                    except Exception as e:
                        self.line.emit(f"[SSH] 下载 {name} 失败: {e}")
            if downloaded == 0:
                self.line.emit(f"[SSH] 远程 {remote_dir} 无匹配文件（未生成统计结果）")
            else:
                self.line.emit(f"[SSH] 结果保存在: {local_dir}")
        finally:
            sftp.close()

    def _drain(self, name, bufs, data):
        """按行消费缓冲，超过一定量先强制刷出，避免越积越多"""
        bufs[name] += data
        buf = bufs[name]
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            if line.strip():
                self.line.emit(line.rstrip("\r"))
        bufs[name] = buf

    def stop(self):
        try:
            if self._chan:
                self._chan.close()
            if self._client:
                self._client.close()
        except Exception:
            pass


# ==================== 配置 ====================
CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")

DEFAULT_CONFIG = {
    "host": "192.168.1.136",
    "port": "22",
    "username": "yangsh",
    "password": "qianlong@135246",
    "remote_dir": "/home/yangsh/so_test",
    "workers": "4",
    "max": "0",
    "wait": "5.0",
    "mock": "1",
    "verify": "1",
    "destroy_via_plugin": "0",
    "download": "1",
    "download_dir": "out/performance",
}


def load_config():
    """从 config.ini 读取配置；文件不存在/缺失项用默认值"""
    cfg = dict(DEFAULT_CONFIG)
    try:
        import configparser
        cp = configparser.ConfigParser()
        cp.read(CONFIG_PATH, encoding="utf-8")
        if cp.has_section("main"):
            for k in cfg:
                if cp.has_option("main", k):
                    cfg[k] = cp.get("main", k)
    except Exception:
        pass
    return cfg


def save_config(cfg):
    """保存配置到 config.ini"""
    try:
        import configparser
        cp = configparser.ConfigParser()
        cp.add_section("main")
        for k, v in cfg.items():
            cp.set("main", k, str(v))
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            cp.write(f)
    except Exception:
        pass


# ==================== 主窗口 ====================
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("数据中台压力测试工具 (DataHub 压测客户端)")
        self.resize(900, 900)
        self.worker = None
        self.cfg = load_config()
        self._batch_names = []
        self._batch_idx = 0
        self._batch_stopped = False
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        # ---- 标题 ----
        title_lbl = QLabel("DataHub 数据中台 · 条件单压测工具")
        tfont = QFont("Microsoft YaHei", 14)
        tfont.setBold(True)
        title_lbl.setFont(tfont)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title_lbl)

        # ---- 1. 测试数据（接口多选）----
        grp1 = QGroupBox("1. 测试数据 (选择要发送的接口，可多选)")
        g1 = QGridLayout(grp1)
        self.list_ifaces = QListWidget()
        self.list_ifaces.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        for name in list_interfaces():
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)   # 默认全选
            self.list_ifaces.addItem(item)
        g1.addWidget(self.list_ifaces, 0, 0, 3, 1)
        self.btn_sel_all = QPushButton("全选")
        self.btn_sel_all.clicked.connect(lambda: self._set_all_iface(True))
        g1.addWidget(self.btn_sel_all, 0, 1)
        self.btn_sel_none = QPushButton("清空")
        self.btn_sel_none.clicked.connect(lambda: self._set_all_iface(False))
        g1.addWidget(self.btn_sel_none, 1, 1)
        self.btn_make = QPushButton("批量生成 Excel")
        self.btn_make.clicked.connect(self.on_make)
        g1.addWidget(self.btn_make, 2, 1)
        self.lbl_excel = QLabel("")
        g1.addWidget(self.lbl_excel, 0, 2, 2, 1)
        g1.setColumnStretch(0, 1)
        root.addWidget(grp1)

        # ---- 2. Redis 配置（写入远程 DataHub.ini 的 [REDIS] 段）----
        grp_redis = QGroupBox("2. Redis 配置 (保存后插件/mock/统计全部生效)")
        gr = QGridLayout(grp_redis)
        gr.addWidget(QLabel("主机:"), 0, 0)
        self.edit_r_host = QLineEdit(self.cfg.get("r_host", "192.168.1.137"))
        gr.addWidget(self.edit_r_host, 0, 1)
        gr.addWidget(QLabel("端口:"), 0, 2)
        self.edit_r_port = QLineEdit(self.cfg.get("r_port", "6379"))
        gr.addWidget(self.edit_r_port, 0, 3)
        gr.addWidget(QLabel("密码:"), 1, 0)
        self.edit_r_pwd = QLineEdit(self.cfg.get("r_pwd", "QianLong@2026&"))
        self.edit_r_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        gr.addWidget(self.edit_r_pwd, 1, 1)
        gr.addWidget(QLabel("数据库(SELECT):"), 1, 2)
        self.spin_r_db = QSpinBox()
        self.spin_r_db.setRange(0, 15)
        self.spin_r_db.setValue(int(self.cfg.get("r_db", "2")))
        gr.addWidget(self.spin_r_db, 1, 3)
        self.btn_read_redis = QPushButton("读取远程配置")
        self.btn_read_redis.clicked.connect(self.on_read_redis)
        gr.addWidget(self.btn_read_redis, 0, 4)
        self.btn_save_redis = QPushButton("保存到远程")
        self.btn_save_redis.clicked.connect(self.on_save_redis)
        gr.addWidget(self.btn_save_redis, 1, 4)
        root.addWidget(grp_redis)

        # ---- 发送参数 ----
        grp2 = QGroupBox("3. 发送参数")
        g2 = QGridLayout(grp2)

        g2.addWidget(QLabel("并发线程数:"), 0, 0)
        self.spin_workers = QSpinBox()
        self.spin_workers.setRange(1, 500)
        self.spin_workers.setValue(int(self.cfg.get("workers", "4")))
        g2.addWidget(self.spin_workers, 0, 1)

        g2.addWidget(QLabel("最多条数(0=全部):"), 0, 2)
        self.spin_max = QSpinBox()
        self.spin_max.setRange(0, 10000000)
        self.spin_max.setValue(int(self.cfg.get("max", "0")))
        g2.addWidget(self.spin_max, 0, 3)

        g2.addWidget(QLabel("等待回复秒数:"), 1, 0)
        self.spin_wait = QDoubleSpinBox()
        self.spin_wait.setRange(0, 300)
        self.spin_wait.setValue(float(self.cfg.get("wait", "5.0")))
        g2.addWidget(self.spin_wait, 1, 1)

        self.chk_mock = QCheckBox("模拟数据中台应答器 (mock)")
        self.chk_mock.setChecked(self.cfg.get("mock", "1") == "1")
        g2.addWidget(self.chk_mock, 2, 0, 1, 2)

        self.chk_verify = QCheckBox("发送后验证 Redis")
        self.chk_verify.setChecked(self.cfg.get("verify", "1") == "1")
        g2.addWidget(self.chk_verify, 2, 2, 1, 2)

        self.chk_destroy_plugin = QCheckBox("破坏数据走插件 (默认直写 Redis)")
        self.chk_destroy_plugin.setChecked(self.cfg.get("destroy_via_plugin", "0") == "1")
        g2.addWidget(self.chk_destroy_plugin, 3, 0, 1, 3)

        # 用例类型过滤（--type）
        g2.addWidget(QLabel("用例类型:"), 4, 0)
        type_box = QHBoxLayout()
        self.chk_type_normal = QCheckBox("normal")
        self.chk_type_error = QCheckBox("error")
        self.chk_type_destroy = QCheckBox("destroy")
        self.chk_type_normal.setChecked(True)
        self.chk_type_error.setChecked(True)
        self.chk_type_destroy.setChecked(True)
        for cb in (self.chk_type_normal, self.chk_type_error, self.chk_type_destroy):
            type_box.addWidget(cb)
        type_box.addStretch(1)
        g2.addLayout(type_box, 4, 1, 1, 3)
        root.addWidget(grp2)

        # ---- 远程 Linux ----
        grp3 = QGroupBox("4. 远程 Linux (发送测试在其上执行)")
        g3 = QGridLayout(grp3)
        self.chk_remote = QCheckBox("启用远程执行")
        self.chk_remote.setChecked(True)
        g3.addWidget(self.chk_remote, 0, 0, 1, 4)

        g3.addWidget(QLabel("主机:"), 1, 0)
        self.edit_host = QLineEdit(self.cfg.get("host", "192.168.1.136"))
        g3.addWidget(self.edit_host, 1, 1)
        g3.addWidget(QLabel("端口:"), 1, 2)
        self.spin_ssh_port = QSpinBox()
        self.spin_ssh_port.setRange(1, 65535)
        self.spin_ssh_port.setValue(int(self.cfg.get("port", "22")))
        g3.addWidget(self.spin_ssh_port, 1, 3)

        g3.addWidget(QLabel("用户名:"), 2, 0)
        self.edit_user = QLineEdit(self.cfg.get("username", "yangsh"))
        g3.addWidget(self.edit_user, 2, 1)
        g3.addWidget(QLabel("密码:"), 2, 2)
        self.edit_pass = QLineEdit(self.cfg.get("password", ""))
        self.edit_pass.setEchoMode(QLineEdit.EchoMode.Password)
        g3.addWidget(self.edit_pass, 2, 3)

        g3.addWidget(QLabel("远程目录:"), 3, 0)
        self.edit_remote_dir = QLineEdit(self.cfg.get("remote_dir", "/home/yangsh/so_test"))
        g3.addWidget(self.edit_remote_dir, 3, 1, 1, 3)
        root.addWidget(grp3)

        # ---- 结果保存 ----
        grp4 = QGroupBox("5. 结果保存 (性能统计 Excel/log)")
        g4 = QGridLayout(grp4)
        self.chk_download = QCheckBox("自动下载结果到本地电脑")
        self.chk_download.setChecked(self.cfg.get("download", "1") == "1")
        g4.addWidget(self.chk_download, 0, 0, 1, 4)
        g4.addWidget(QLabel("本地目录:"), 1, 0)
        _dl_dir = self.cfg.get("download_dir", "out/performance")
        if not os.path.isabs(_dl_dir):
            _dl_dir = os.path.join(BASE_DIR, _dl_dir)
        self.edit_download_dir = QLineEdit(_dl_dir)
        g4.addWidget(self.edit_download_dir, 1, 1, 1, 3)
        root.addWidget(grp4)

        # ---- 操作按钮 ----
        btns = QHBoxLayout()
        self.btn_send = QPushButton("运行发送测试")
        self.btn_send.clicked.connect(self.on_send)
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.on_stop)
        self.btn_clear = QPushButton("清空日志")
        self.btn_clear.clicked.connect(lambda: self.log.clear())
        btns.addWidget(self.btn_send)
        btns.addWidget(self.btn_stop)
        btns.addWidget(self.btn_clear)
        self.btn_upload_all = QPushButton("批量上传所有接口数据")
        self.btn_upload_all.clicked.connect(self.on_upload_all)
        btns.addWidget(self.btn_upload_all)
        btns.addStretch(1)
        root.addLayout(btns)

        # ---- 日志区 ----
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        font = QFont("Consolas", 9)
        self.log.setFont(font)
        root.addWidget(self.log, 1)

        self.update_excel_label()

    # ---------- 工具 ----------
    def selected_interfaces(self):
        """返回勾选的接口名列表"""
        names = []
        for i in range(self.list_ifaces.count()):
            it = self.list_ifaces.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                names.append(it.text())
        return names

    def _set_all_iface(self, checked):
        for i in range(self.list_ifaces.count()):
            it = self.list_ifaces.item(i)
            it.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def update_interfaces_label(self):
        n = len(self.selected_interfaces())
        total = self.list_ifaces.count()
        self.lbl_excel.setText(f"已选 {n}/{total} 个接口")

    def update_excel_label(self):
        self.update_interfaces_label()

    def append_log(self, text):
        self.log.append(text)
        self.log.moveCursor(QTextCursor.MoveOperation.End)

    def run_local(self, cmd, on_done=None):
        """本地子进程（cmd 为单条或多条命令）"""
        cmds = cmd if cmd and isinstance(cmd[0], list) else [cmd]
        if len(cmds) > 1:
            self.append_log(f"[本地] 共 {len(cmds)} 条命令")
        else:
            self.append_log("$ " + " ".join(cmds[0]))
        self.set_running(True)
        self.worker = Worker(cmds, BASE_DIR, self)
        self.worker.line.connect(self.append_log)
        self.worker.finished.connect(lambda rc: self.on_done(rc, on_done))
        self.worker.start()

    def run_remote(self, command, files_to_upload=None, on_done=None,
                   download_config=None):
        """SSH 远程执行"""
        host = self.edit_host.text().strip()
        user = self.edit_user.text().strip()
        pwd = self.edit_pass.text()
        port = self.spin_ssh_port.value()
        remote_dir = self.edit_remote_dir.text().strip()
        if not (host and user and pwd):
            QMessageBox.warning(self, "提示", "请填写远程主机/用户名/密码")
            return
        self.set_running(True)
        self.append_log(f"[SSH] 连接 {user}@{host}:{port} 目录 {remote_dir}")
        self.worker = SshWorker(host, port, user, pwd, remote_dir, command,
                                files_to_upload, download_config, self)
        self.worker.line.connect(self.append_log)
        self.worker.finished.connect(lambda rc: self.on_done(rc, on_done))
        self.worker.start()

    def on_done(self, rc, on_done=None):
        self.append_log(f"[完成] 退出码 {rc}")
        self.set_running(False)
        if on_done:
            on_done(rc)

    def set_running(self, running):
        self.btn_send.setEnabled(not running)
        self.btn_make.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        if hasattr(self, "btn_upload_all"):
            self.btn_upload_all.setEnabled(not running)
        if hasattr(self, "btn_read_redis"):
            self.btn_read_redis.setEnabled(not running)
            self.btn_save_redis.setEnabled(not running)

    # ---------- 操作 ----------
    def on_make(self):
        names = self.selected_interfaces()
        if not names:
            QMessageBox.warning(self, "提示", "请至少勾选一个接口")
            return
        cmds = [[PYTHON, os.path.join(BASE_DIR, "make_excel.py"), "--interface", n]
                for n in names]
        self.run_local(cmds, on_done=lambda rc: self.update_excel_label())

    def selected_types(self):
        """返回选中的用例类型列表"""
        sel = []
        if self.chk_type_normal.isChecked():
            sel.append("normal")
        if self.chk_type_error.isChecked():
            sel.append("error")
        if self.chk_type_destroy.isChecked():
            sel.append("destroy")
        return sel

    def build_send_cmd(self, name):
        """构造 send_test.py 的命令行"""
        parts = ["python3", "send_test.py", "--interface", name,
                 "--workers", str(self.spin_workers.value()),
                 "--max", str(self.spin_max.value()),
                 "--wait", str(self.spin_wait.value())]
        types = self.selected_types()
        if types and len(types) < 3:
            parts.append("--type")
            parts.append(",".join(types))
        if self.chk_mock.isChecked():
            parts.append("--mock")
        else:
            parts.append("--no-mock")
        if self.chk_verify.isChecked():
            parts.append("--verify")
        if self.chk_destroy_plugin.isChecked():
            parts.append("--destroy-via-plugin")
        return " ".join(parts)

    def remote_upload_files(self, name):
        """需要上传到远程的文件列表：脚本 + 公共模块 + 接口定义 + 数据文件"""
        rd = self.edit_remote_dir.text().strip()
        return [
            (os.path.join(BASE_DIR, "send_test.py"), f"{rd}/send_test.py"),
            (os.path.join(BASE_DIR, "mock_datahub.py"), f"{rd}/mock_datahub.py"),
            (os.path.join(INTERFACES_DIR, "_common.py"), f"{rd}/interfaces/_common.py"),
            (os.path.join(INTERFACES_DIR, f"{name}.py"), f"{rd}/interfaces/{name}.py"),
            (os.path.join(DATA_DIR, f"{name}.xlsx"), f"{rd}/data/{name}.xlsx"),
        ]

    def _save_ui_config(self):
        """把当前界面上的配置保存到 config.ini"""
        cfg = {
            "host": self.edit_host.text().strip(),
            "port": str(self.spin_ssh_port.value()),
            "username": self.edit_user.text().strip(),
            "password": self.edit_pass.text(),
            "remote_dir": self.edit_remote_dir.text().strip(),
            "workers": str(self.spin_workers.value()),
            "max": str(self.spin_max.value()),
            "wait": str(self.spin_wait.value()),
            "mock": "1" if self.chk_mock.isChecked() else "0",
            "verify": "1" if self.chk_verify.isChecked() else "0",
            "destroy_via_plugin": "1" if self.chk_destroy_plugin.isChecked() else "0",
            "download": "1" if self.chk_download.isChecked() else "0",
            "download_dir": self.edit_download_dir.text().strip() or DEFAULT_CONFIG["download_dir"],
        }
        save_config(cfg)

    def on_read_redis(self):
        """从远程拉取 DataHub.ini 的 [REDIS] 段显示到界面"""
        import paramiko
        try:
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c.connect(self.edit_host.text().strip(), port=self.spin_ssh_port.value(),
                      username=self.edit_user.text().strip(),
                      password=self.edit_pass.text(), timeout=15)
            sftp = c.open_sftp()
            path = f"{self.edit_remote_dir.text().strip()}/DataHub.ini"
            with sftp.open(path, "r") as fh:
                text = fh.read().decode("utf-8", "replace")
            sftp.close()
            c.close()
            vals = {}
            for line in text.splitlines():
                line = line.strip()
                for key in ("REDISHOST", "REDISPORT", "REDISPWD", "REDISSELECT"):
                    if line.startswith(key + "="):
                        vals[key] = line.split("=", 1)[1].strip()
            self.edit_r_host.setText(vals.get("REDISHOST", self.edit_r_host.text()))
            self.edit_r_port.setText(vals.get("REDISPORT", self.edit_r_port.text()))
            if vals.get("REDISPWD"):
                self.edit_r_pwd.setText(vals["REDISPWD"])
            try:
                self.spin_r_db.setValue(int(vals.get("REDISSELECT", "0")))
            except ValueError:
                pass
            self.append_log(f"[SSH] 已读取远程 Redis 配置: {vals}")
        except Exception as e:
            QMessageBox.warning(self, "提示", f"读取远程 Redis 配置失败: {e}")

    def on_save_redis(self):
        """把界面的 Redis 配置写入远程 DataHub.ini [REDIS] 段"""
        kv = {
            "REDISHOST": self.edit_r_host.text().strip(),
            "REDISPORT": self.edit_r_port.text().strip(),
            "REDISPWD": self.edit_r_pwd.text(),
            "REDISSELECT": str(self.spin_r_db.value()),
        }
        cfg_save = dict(load_config())
        cfg_save.update({"r_host": kv["REDISHOST"], "r_port": kv["REDISPORT"],
                         "r_pwd": kv["REDISPWD"], "r_db": kv["REDISSELECT"]})
        save_config(cfg_save)
        self._save_ui_config()
        worker = SshWorker(
            self.edit_host.text().strip(), self.spin_ssh_port.value(),
            self.edit_user.text().strip(), self.edit_pass.text(),
            self.edit_remote_dir.text().strip(), "echo 'Redis配置已更新'",
            ini_update={"kv": kv}, parent=self)
        worker.line.connect(self.append_log)
        worker.start()

    def on_upload_all(self):
        """批量上传所有接口数据(xlsx) + 接口定义(py)到远程"""
        if not self.chk_remote.isChecked():
            QMessageBox.warning(self, "提示", "请先勾选“启用远程执行”")
            return
        rd = self.edit_remote_dir.text().strip()
        files = []
        # 所有接口定义 py
        for f in sorted(os.listdir(INTERFACES_DIR)):
            if f.endswith(".py"):
                files.append((os.path.join(INTERFACES_DIR, f), f"{rd}/interfaces/{f}"))
        # 所有数据 xlsx
        if os.path.isdir(DATA_DIR):
            for f in sorted(os.listdir(DATA_DIR)):
                if f.endswith(".xlsx") and not f.startswith("~$"):
                    files.append((os.path.join(DATA_DIR, f), f"{rd}/data/{f}"))
        # 脚本文件
        for f in ("send_test.py", "mock_datahub.py", "make_excel.py"):
            files.append((os.path.join(BASE_DIR, f), f"{rd}/{f}"))

        self._save_ui_config()
        self.set_running(True)
        self.append_log(f"[SSH] 批量上传 {len(files)} 个文件到 {rd}...")
        self.worker = SshWorker(self.edit_host.text().strip(), self.spin_ssh_port.value(),
                                self.edit_user.text().strip(), self.edit_pass.text(),
                                rd, "echo '上传完成'", files, self)
        self.worker.line.connect(self.append_log)
        self.worker.finished.connect(lambda rc: self.set_running(False))
        self.worker.start()

    def on_send(self):
        """批量发送：对勾选的每个接口依次执行（远程或本地）"""
        names = self.selected_interfaces()
        if not names:
            QMessageBox.warning(self, "提示", "请至少勾选一个接口")
            return
        self._save_ui_config()
        self._batch_names = names
        self._batch_idx = 0
        self._batch_stopped = False
        self.set_running(True)
        if len(names) > 1:
            self.append_log(f"\n[BATCH] 共 {len(names)} 个接口待发送: {', '.join(names)}")
        self._run_next_batch_item()

    def _download_config_for(self, name):
        dl = None
        if self.chk_download.isChecked():
            dl = {
                "remote": self.edit_remote_dir.text().strip() + "/out/performance",
                "local": self.edit_download_dir.text().strip() or
                         os.path.join(BASE_DIR, "out", "performance"),
                "patterns": [f"{name}_*.xlsx", f"{name}_*.log"],
            }
        return dl

    def _run_next_batch_item(self):
        if self._batch_stopped:
            self.append_log("[BATCH] 已手动停止")
            self.set_running(False)
            return
        names = self._batch_names
        idx = self._batch_idx
        if idx >= len(names):
            self.append_log(f"[BATCH] 全部完成（共 {len(names)} 个接口）")
            self.set_running(False)
            return
        name = names[idx]
        if len(names) > 1:
            self.append_log(f"[BATCH] ({idx + 1}/{len(names)}) 接口 {name} 开始...")

        cmd_str = self.build_send_cmd(name)
        local_dl_dir = self.edit_download_dir.text().strip() or \
                       os.path.join(BASE_DIR, "out", "performance")
        dl = self._download_config_for(name) if self.chk_download.isChecked() else None

        if self.chk_remote.isChecked():
            self.worker = SshWorker(
                self.edit_host.text().strip(), self.spin_ssh_port.value(),
                self.edit_user.text().strip(), self.edit_pass.text(),
                self.edit_remote_dir.text().strip(), cmd_str,
                files_to_upload=self.remote_upload_files(name),
                download_config=dl, parent=self)
            self.worker.line.connect(self.append_log)
            self.worker.finished.connect(lambda rc: self.on_batch_item_done(rc))
            self.worker.start()
        else:
            # 本地模式（.so 在 Linux 时才有真实发送）
            args = cmd_str.split()[2:]   # 跳过 "python3 send_test.py"
            cmd = [PYTHON, os.path.join(BASE_DIR, "send_test.py")] + args
            self.worker = Worker(cmd, BASE_DIR, self)
            self.worker.line.connect(self.append_log)
            self.worker.finished.connect(lambda rc: self.on_batch_item_done(rc))
            self.worker.start()

    def on_batch_item_done(self, rc):
        name = self._batch_names[self._batch_idx]
        self.append_log(f"[BATCH] 接口 {name} 完成，退出码 {rc}")
        self._batch_idx += 1
        self._run_next_batch_item()

    def remote_upload_files(self, name):
        """需要上传到远程的文件列表：脚本 + 公共模块 + 接口定义 + 数据文件 + DataHub.ini"""
        rd = self.edit_remote_dir.text().strip()
        return [
            (os.path.join(BASE_DIR, "send_test.py"), f"{rd}/send_test.py"),
            (os.path.join(BASE_DIR, "mock_datahub.py"), f"{rd}/mock_datahub.py"),
            (os.path.join(BASE_DIR, "perf_stats.py"), f"{rd}/perf_stats.py"),
            (os.path.join(INTERFACES_DIR, "_common.py"), f"{rd}/interfaces/_common.py"),
            (os.path.join(INTERFACES_DIR, f"{name}.py"), f"{rd}/interfaces/{name}.py"),
            (os.path.join(DATA_DIR, f"{name}.xlsx"), f"{rd}/data/{name}.xlsx"),
        ]

    def on_stop(self):
        self._batch_stopped = True
        if self.worker:
            self.worker.stop()
            self.append_log("[STOP] 请求停止...")

    def closeEvent(self, event):
        self._save_ui_config()
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        event.accept()


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
