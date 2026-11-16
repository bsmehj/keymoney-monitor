"""KeyMoney Monitor - 桌面悬浮球，监控百炼 Token Plan 额度与硅基流动余额。"""

import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
from datetime import datetime

APP_NAME = "KeyMoney Monitor"
BALL_SIZE = 96
TRANSPARENT_KEY = "#010203"
STATUS_KEYS = ("ok", "warn", "err", "idle")
SINGLE_INSTANCE_PORT = 57321


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def asset_path(name):
    base = getattr(sys, "_MEIPASS", None) or app_dir()
    return os.path.join(base, "assets", name)


CONFIG_PATH = os.path.join(app_dir(), "config.json")

DEFAULT_CONFIG = {
    "siliconflow_api_key": "",
    "siliconflow_base_url": "https://api.siliconflow.cn",
    "bailian_enabled": True,
    "refresh_interval_seconds": 300,
    "siliconflow_low_balance": 10.0,
    "bailian_low_percent": 20.0,
    "ball_x": None,
    "ball_y": None,
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except (OSError, json.JSONDecodeError):
            pass
    else:
        save_config(cfg)
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def fetch_siliconflow(cfg):
    key = cfg.get("siliconflow_api_key", "").strip()
    if not key:
        return {"ok": False, "skipped": True, "error": "未配置 API Key（右键→设置）"}
    base = cfg.get("siliconflow_base_url", "https://api.siliconflow.cn").rstrip("/")
    req = urllib.request.Request(
        base + "/v1/user/info",
        headers={"Authorization": "Bearer " + key, "User-Agent": APP_NAME},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    data = body.get("data") or {}
    return {
        "ok": True,
        "total": float(data.get("totalBalance", "0")),
        "charge": float(data.get("chargeBalance", "0")),
        "gift": float(data.get("balance", "0")),
    }


def fetch_bailian(cfg):
    if not cfg.get("bailian_enabled", True):
        return {"ok": False, "skipped": True, "error": "已在配置中禁用"}
    bl = shutil.which("bl")
    if not bl:
        return {"ok": False, "error": "未找到 bl CLI，请先安装 bailian-cli"}
    env = dict(os.environ)
    env.update(
        {
            "BAILIAN_CALLER_TYPE": "script",
            "BAILIAN_CALLER_NAME": "qoder",
            "NO_COLOR": "1",
        }
    )
    proc = subprocess.run(
        [bl, "usage", "token-plan", "--output", "json"],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if proc.returncode != 0:
        hint = ""
        try:
            hint = json.loads(proc.stdout).get("error", {}).get("hint", "")
        except (json.JSONDecodeError, AttributeError):
            pass
        if "console" in (proc.stdout + proc.stderr).lower():
            hint = hint or "请运行 bl auth login --console 重新登录"
        return {"ok": False, "error": hint or "bl 查询失败（退出码 %d）" % proc.returncode}
    data = json.loads(proc.stdout)
    used_pct = float(data.get("per1MonthPercentage", 0)) * 100
    reset_ms = data.get("per1MonthResetTime")
    reset_str = (
        datetime.fromtimestamp(reset_ms / 1000).strftime("%Y-%m-%d") if reset_ms else "未知"
    )
    return {"ok": True, "remaining_pct": 100 - used_pct, "reset": reset_str}


def refresh_worker(cfg, result_queue, stop_event):
    while not stop_event.is_set():
        results = {}
        for name, fn in (("siliconflow", fetch_siliconflow), ("bailian", fetch_bailian)):
            try:
                results[name] = fn(cfg)
            except Exception as exc:
                results[name] = {"ok": False, "error": str(exc)}
        results["updated_at"] = datetime.now().strftime("%H:%M:%S")
        result_queue.put(results)
        interval = max(30, int(cfg.get("refresh_interval_seconds", 300)))
        stop_event.wait(interval)


class FloatingBall:
    def __init__(self, root, cfg):
        self.root = root
        self.cfg = cfg
        self.results = None
        self.result_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.tip = None
        self.hide_job = None
        self.drag_offset = None

        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-transparentcolor", TRANSPARENT_KEY)
        root.configure(bg=TRANSPARENT_KEY)
        root.geometry("%dx%d" % (BALL_SIZE, BALL_SIZE))
        self.place_ball()

        self.canvas = tk.Canvas(
            root, width=BALL_SIZE, height=BALL_SIZE, bg=TRANSPARENT_KEY, highlightthickness=0
        )
        self.canvas.pack()
        self.images = {
            key: tk.PhotoImage(file=asset_path("ball_%s.png" % key)) for key in STATUS_KEYS
        }
        self.ball_img = self.canvas.create_image(
            BALL_SIZE / 2, BALL_SIZE / 2, image=self.images["idle"]
        )
        self.text = self.canvas.create_text(
            BALL_SIZE / 2,
            BALL_SIZE * 0.44,
            text="--",
            fill="white",
            font=("Microsoft YaHei UI", 12, "bold"),
        )
        self.subtext = self.canvas.create_text(
            BALL_SIZE / 2,
            BALL_SIZE * 0.61,
            text="",
            fill="white",
            font=("Microsoft YaHei UI", 7),
        )

        for widget in (root, self.canvas):
            widget.bind("<Enter>", self.on_enter)
            widget.bind("<Leave>", self.on_leave)
            widget.bind("<ButtonPress-1>", self.on_press)
            widget.bind("<B1-Motion>", self.on_drag)
            widget.bind("<ButtonRelease-1>", self.on_release)
            widget.bind("<Double-Button-1>", lambda e: self.trigger_refresh())
            widget.bind("<Button-3>", self.show_menu)

        self.menu = tk.Menu(root, tearoff=0)
        self.menu.add_command(label="立即刷新", command=self.trigger_refresh)
        self.menu.add_command(label="设置（打开配置文件）", command=self.open_config)
        self.menu.add_separator()
        self.menu.add_command(
            label="百炼·阿里云费用中心（查现金余额）",
            command=lambda: self.open_url("https://billing-cost.console.aliyun.com/"),
        )
        self.menu.add_command(
            label="硅基流动·控制台（查余额/充值）",
            command=lambda: self.open_url("https://cloud.siliconflow.cn/"),
        )
        self.menu.add_separator()
        self.menu.add_command(label="退出", command=self.quit)

        self.worker = threading.Thread(
            target=refresh_worker, args=(self.cfg, self.result_queue, self.stop_event), daemon=True
        )
        self.worker.start()
        self.poll_results()

    def place_ball(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = self.cfg.get("ball_x")
        y = self.cfg.get("ball_y")
        if x is None or y is None:
            x, y = sw - BALL_SIZE - 40, sh - BALL_SIZE - 120
        x = max(0, min(int(x), sw - BALL_SIZE))
        y = max(0, min(int(y), sh - BALL_SIZE))
        self.root.geometry("+%d+%d" % (x, y))

    def on_press(self, event):
        self.drag_offset = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def on_drag(self, event):
        if self.drag_offset:
            x = event.x_root - self.drag_offset[0]
            y = event.y_root - self.drag_offset[1]
            self.root.geometry("+%d+%d" % (x, y))
            self.hide_tip()

    def on_release(self, event):
        if self.drag_offset:
            self.cfg["ball_x"] = self.root.winfo_x()
            self.cfg["ball_y"] = self.root.winfo_y()
            save_config(self.cfg)
        self.drag_offset = None

    def trigger_refresh(self):
        self.canvas.itemconfig(self.text, text="…")
        threading.Thread(
            target=self._one_shot_refresh, daemon=True
        ).start()

    def _one_shot_refresh(self):
        results = {}
        for name, fn in (("siliconflow", fetch_siliconflow), ("bailian", fetch_bailian)):
            try:
                results[name] = fn(self.cfg)
            except Exception as exc:
                results[name] = {"ok": False, "error": str(exc)}
        results["updated_at"] = datetime.now().strftime("%H:%M:%S")
        self.result_queue.put(results)

    def poll_results(self):
        try:
            while True:
                self.results = self.result_queue.get_nowait()
                self.update_display()
        except queue.Empty:
            pass
        self.root.after(500, self.poll_results)

    def status_key(self):
        r = self.results
        if not r:
            return "idle"
        sf, bl = r.get("siliconflow", {}), r.get("bailian", {})
        active = [v for v in (sf, bl) if not v.get("skipped")]
        if any(not v.get("ok") for v in active):
            return "err"
        if not active:
            return "idle"
        if sf.get("ok") and sf["total"] < self.cfg.get("siliconflow_low_balance", 10):
            return "warn"
        if bl.get("ok") and bl["remaining_pct"] < self.cfg.get("bailian_low_percent", 20):
            return "warn"
        return "ok"

    def ball_label(self):
        r = self.results
        if not r:
            return "--", ""
        sf, bl = r.get("siliconflow", {}), r.get("bailian", {})
        if sf.get("ok"):
            total = sf["total"]
            label = ("¥%.0f" % total) if total >= 100 else ("¥%.1f" % total)
            return label, "硅基"
        if bl.get("ok"):
            return "%.0f%%" % bl["remaining_pct"], "百炼"
        return "!", "异常"

    def update_display(self):
        label, sub = self.ball_label()
        self.canvas.itemconfig(self.ball_img, image=self.images[self.status_key()])
        self.canvas.itemconfig(self.text, text=label)
        self.canvas.itemconfig(self.subtext, text=sub)
        if self.tip and self.tip.winfo_exists():
            self.fill_tip()

    def tip_text(self):
        r = self.results
        lines = [APP_NAME, ""]
        if not r:
            lines.append("正在查询…")
            return "\n".join(lines)
        sf = r.get("siliconflow", {})
        lines.append("【硅基流动 SiliconFlow】")
        if sf.get("ok"):
            lines.append("  总余额：¥%.2f" % sf["total"])
            lines.append("  充值余额：¥%.2f    赠送：¥%.2f" % (sf["charge"], sf["gift"]))
        else:
            lines.append("  " + sf.get("error", "未知错误"))
        lines.append("")
        bl = r.get("bailian", {})
        lines.append("【百炼 Token Plan】")
        if bl.get("ok"):
            lines.append("  本月剩余额度：%.1f%%" % bl["remaining_pct"])
            lines.append("  额度重置日期：%s" % bl["reset"])
        else:
            lines.append("  " + bl.get("error", "未知错误"))
        lines.append("")
        lines.append("更新于 %s（双击刷新 / 右键菜单）" % r.get("updated_at", "--"))
        return "\n".join(lines)

    def fill_tip(self):
        self.tip_label.config(text=self.tip_text())
        self.tip.update_idletasks()
        w = self.tip.winfo_reqwidth()
        h = self.tip.winfo_reqheight()
        bx, by = self.root.winfo_x(), self.root.winfo_y()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = bx - w - 10 if bx > w + 20 else bx + BALL_SIZE + 10
        y = max(10, min(by + BALL_SIZE - h, sh - h - 10))
        self.tip.geometry("+%d+%d" % (x, y))

    def show_tip(self):
        if self.tip and self.tip.winfo_exists():
            self.fill_tip()
            return
        self.tip = tk.Toplevel(self.root)
        self.tip.overrideredirect(True)
        self.tip.attributes("-topmost", True)
        self.tip.configure(bg="#2c3e50")
        self.tip_label = tk.Label(
            self.tip,
            text="",
            bg="#2c3e50",
            fg="#ecf0f1",
            font=("Microsoft YaHei UI", 9),
            justify="left",
            padx=12,
            pady=10,
        )
        self.tip_label.pack()
        self.tip.bind("<Enter>", self.cancel_hide)
        self.tip.bind("<Leave>", self.on_leave)
        self.fill_tip()

    def hide_tip(self):
        if self.tip and self.tip.winfo_exists():
            self.tip.destroy()
        self.tip = None

    def on_enter(self, event):
        self.cancel_hide()
        self.show_tip()

    def on_leave(self, event):
        self.schedule_hide()

    def cancel_hide(self, event=None):
        if self.hide_job:
            self.root.after_cancel(self.hide_job)
            self.hide_job = None

    def schedule_hide(self):
        self.cancel_hide()
        self.hide_job = self.root.after(200, self.hide_if_outside)

    def hide_if_outside(self):
        self.hide_job = None
        px, py = self.root.winfo_pointerxy()
        for w in (self.root, self.tip):
            if w and w.winfo_exists():
                wx, wy = w.winfo_rootx(), w.winfo_rooty()
                if wx <= px < wx + w.winfo_width() and wy <= py < wy + w.winfo_height():
                    return
        self.hide_tip()

    def show_menu(self, event):
        self.hide_tip()
        self.menu.tk_popup(event.x_root, event.y_root)

    def open_config(self):
        # os.startfile 在 PyInstaller + Python 3.14 下会触发 GIL 致命错误崩溃
        subprocess.Popen(["explorer.exe", CONFIG_PATH])

    def open_url(self, url):
        subprocess.Popen(["explorer.exe", url])

    def quit(self):
        self.stop_event.set()
        self.root.destroy()


def ensure_single_instance():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", SINGLE_INSTANCE_PORT))
        s.listen(1)
        return s
    except OSError:
        return None


def main():
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    guard = ensure_single_instance()
    if guard is None:
        sys.exit(0)
    cfg = load_config()
    root = tk.Tk()
    root.title(APP_NAME)
    FloatingBall(root, cfg)
    root.mainloop()
    guard.close()


if __name__ == "__main__":
    main()