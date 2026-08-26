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
    """本地子进程执行，实时回传输出"""
    line = Signal(str)
    finished = Signal(int)

    def __init__(self, cmd, cwd, parent=None):
        super().__init__(parent)
        self.cmd = cmd
        self.cwd = cwd
        self._proc = None

    def run(self):
        try:
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"
            self._proc = subprocess.Popen(
                self.cmd, cwd=self.cwd, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                errors="replace", bufsize=1, env=env)
            for out in self._proc.stdout:
                self.line.emit(out.rstrip("\n"))
            self._proc.wait()
            self.finished.emit(self._proc.returncode)
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
                 files_to_upload=None, parent=None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.remote_dir = remote_dir
        self.command = command
        self.files_to_upload = files_to_upload or []
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
    "init_wait": "15.0",
    "mock": "1",
    "verify": "1",
    "destroy_via_plugin": "0",
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
        self.setWindowTitle("多线程压测工具")
        self.resize(820, 720)
        self.worker = None
        self.cfg = load_config()
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        # ---- 接口选择 + 生成 Excel ----
        grp1 = QGroupBox("1. 测试数据 (Excel)")
        g1 = QGridLayout(grp1)
        g1.addWidget(QLabel("接口:"), 0, 0)
        self.cmb_interface = QComboBox()
        self.cmb_interface.addItems(list_interfaces())
        g1.addWidget(self.cmb_interface, 0, 1)
        self.btn_make = QPushButton("生成 Excel")
        self.btn_make.clicked.connect(self.on_make)
        g1.addWidget(self.btn_make, 0, 2)
        self.lbl_excel = QLabel("")
        g1.addWidget(self.lbl_excel, 0, 3)
        root.addWidget(grp1)

        # ---- 发送参数 ----
        grp2 = QGroupBox("2. 发送参数")
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

        g2.addWidget(QLabel("初始化超时秒数:"), 1, 2)
        self.spin_init = QDoubleSpinBox()
        self.spin_init.setRange(1, 300)
        self.spin_init.setValue(float(self.cfg.get("init_wait", "15.0")))
        g2.addWidget(self.spin_init, 1, 3)

        self.chk_mock = QCheckBox("模拟数据中台应答器 (mock)")
        self.chk_mock.setChecked(self.cfg.get("mock", "1") == "1")
        g2.addWidget(self.chk_mock, 2, 0, 1, 2)

        self.chk_verify = QCheckBox("发送后验证 Redis")
        self.chk_verify.setChecked(self.cfg.get("verify", "1") == "1")
        g2.addWidget(self.chk_verify, 2, 2, 1, 2)

        self.chk_destroy_plugin = QCheckBox("破坏数据走插件 (默认直写 Redis)")
        self.chk_destroy_plugin.setChecked(self.cfg.get("destroy_via_plugin", "0") == "1")
        g2.addWidget(self.chk_destroy_plugin, 3, 0, 1, 3)
        root.addWidget(grp2)

        # ---- 远程 Linux ----
        grp3 = QGroupBox("3. 远程 Linux (发送测试在其上执行)")
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
    def update_excel_label(self):
        name = self.cmb_interface.currentText()
        path = os.path.join(DATA_DIR, f"{name}.xlsx")
        self.lbl_excel.setText(f"data/{name}.xlsx" if os.path.exists(path) else "未生成")

    def append_log(self, text):
        self.log.append(text)
        self.log.moveCursor(QTextCursor.MoveOperation.End)

    def run_local(self, cmd, on_done=None):
        """本地子进程"""
        self.set_running(True)
        self.append_log("$ " + " ".join(cmd))
        self.worker = Worker(cmd, BASE_DIR, self)
        self.worker.line.connect(self.append_log)
        self.worker.finished.connect(lambda rc: self.on_done(rc, on_done))
        self.worker.start()

    def run_remote(self, command, files_to_upload=None, on_done=None):
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
                                files_to_upload, self)
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

    # ---------- 操作 ----------
    def on_make(self):
        name = self.cmb_interface.currentText()
        cmd = [PYTHON, os.path.join(BASE_DIR, "make_excel.py"),
               "--interface", name]
        self.run_local(cmd, on_done=lambda rc: self.update_excel_label())

    def build_send_cmd(self, name):
        """构造 send_test.py 的命令行"""
        parts = ["python3", "send_test.py", "--interface", name,
                 "--workers", str(self.spin_workers.value()),
                 "--max", str(self.spin_max.value()),
                 "--wait", str(self.spin_wait.value()),
                 "--init-wait", str(self.spin_init.value())]
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
            "init_wait": str(self.spin_init.value()),
            "mock": "1" if self.chk_mock.isChecked() else "0",
            "verify": "1" if self.chk_verify.isChecked() else "0",
            "destroy_via_plugin": "1" if self.chk_destroy_plugin.isChecked() else "0",
        }
        save_config(cfg)

    def on_send(self):
        self._save_ui_config()
        name = self.cmb_interface.currentText()
        cmd_str = self.build_send_cmd(name)
        if self.chk_remote.isChecked():
            self.run_remote(cmd_str, files_to_upload=self.remote_upload_files(name))
        else:
            # 本地：用 venv python 跑，但 .so 在 Linux 时才有真实发送
            cmd = [PYTHON, os.path.join(BASE_DIR, "send_test.py"),
                   "--interface", name,
                   "--workers", str(self.spin_workers.value()),
                   "--max", str(self.spin_max.value()),
                   "--wait", str(self.spin_wait.value()),
                   "--init-wait", str(self.spin_init.value())]
            if self.chk_mock.isChecked():
                cmd.append("--mock")
            else:
                cmd.append("--no-mock")
            if self.chk_verify.isChecked():
                cmd.append("--verify")
            if self.chk_destroy_plugin.isChecked():
                cmd.append("--destroy-via-plugin")
            self.run_local(cmd)

    def on_stop(self):
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
