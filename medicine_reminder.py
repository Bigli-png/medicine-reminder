import json
import os
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk

try:
    import winsound
except ImportError:
    winsound = None

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "medicines.json")
SNOOZE_MINUTES = 10
REPEAT_LABELS = {"daily": "每天", "once": "仅一次"}


def load_items():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            items = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    # 兼容旧数据：补齐新增字段
    for it in items:
        if it.get("repeat") not in ("daily", "once"):
            it["repeat"] = "daily"
        it.setdefault("dose", "")
        it.setdefault("last_done", None)
        it.setdefault("created", None)
    return items


def save_items(items):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def normalize_time(text):
    try:
        return datetime.strptime(text.strip(), "%H:%M").strftime("%H:%M")
    except ValueError:
        return None


def today_str():
    return datetime.now().strftime("%Y-%m-%d")


class App:
    def __init__(self, root):
        self.root = root
        self.items = load_items()
        self.popup = None
        self.editing_index = None
        root.title("吃药提醒")
        root.geometry("660x460")
        root.minsize(620, 400)
        self.build_ui()
        self.refresh_list()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.tick()

    def build_ui(self):
        form = ttk.LabelFrame(self.root, text="添加药物提醒", padding=10)
        form.pack(fill="x", padx=12, pady=(12, 6))

        ttk.Label(form, text="药名").grid(row=0, column=0, sticky="w")
        ttk.Label(form, text="剂量").grid(row=0, column=1, sticky="w")
        ttk.Label(form, text="时间 (HH:MM)").grid(row=0, column=2, sticky="w")
        ttk.Label(form, text="重复").grid(row=0, column=3, sticky="w")

        self.name_var = tk.StringVar()
        self.dose_var = tk.StringVar()
        self.time_var = tk.StringVar(value="08:00")
        self.repeat_var = tk.StringVar(value="每天")
        ttk.Entry(form, textvariable=self.name_var, width=16).grid(
            row=1, column=0, padx=(0, 8)
        )
        ttk.Entry(form, textvariable=self.dose_var, width=12).grid(
            row=1, column=1, padx=(0, 8)
        )
        ttk.Entry(form, textvariable=self.time_var, width=10).grid(
            row=1, column=2, padx=(0, 8)
        )
        ttk.Combobox(
            form,
            textvariable=self.repeat_var,
            values=("每天", "仅一次"),
            width=8,
            state="readonly",
        ).grid(row=1, column=3, padx=(0, 8))
        self.add_btn = ttk.Button(form, text="添加", command=self.add_item)
        self.add_btn.grid(row=1, column=4, padx=(0, 8))
        ttk.Button(form, text="清空", command=self.clear_form).grid(row=1, column=5)

        columns = ("time", "name", "dose", "repeat", "status")
        wrap = ttk.Frame(self.root)
        wrap.pack(fill="both", expand=True, padx=12, pady=6)
        self.tree = ttk.Treeview(wrap, columns=columns, show="headings", height=10)
        for col, title, width in (
            ("time", "时间", 70),
            ("name", "药名", 170),
            ("dose", "剂量", 90),
            ("repeat", "重复", 60),
            ("status", "今日状态", 90),
        ):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor="w")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(bar, text="编辑选中", command=self.edit_item).pack(side="left")
        ttk.Button(bar, text="删除选中", command=self.delete_item).pack(side="left", padx=8)
        ttk.Button(bar, text="标记今日已服用", command=self.mark_taken).pack(
            side="left", padx=8
        )
        self.clock_var = tk.StringVar()
        ttk.Label(bar, textvariable=self.clock_var).pack(side="right")

    def refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        today = today_str()
        order = sorted(range(len(self.items)), key=lambda i: self.items[i]["time"])
        for i in order:
            it = self.items[i]
            status = self.status_of(it, today)
            self.tree.insert(
                "",
                "end",
                iid=str(i),
                values=(
                    it["time"],
                    it["name"],
                    it.get("dose", ""),
                    REPEAT_LABELS.get(it.get("repeat", "daily"), "每天"),
                    status,
                ),
            )

    def status_of(self, it, today):
        repeat = it.get("repeat", "daily")
        if repeat == "once":
            if it.get("last_done"):
                return "已完成"
            if it.get("created") and it.get("created") != today:
                return "已过期"
            return "待服用"
        return "已服用" if it.get("last_done") == today else "待服用"

    def clear_form(self):
        self.editing_index = None
        self.add_btn.config(text="添加")
        self.name_var.set("")
        self.dose_var.set("")
        self.time_var.set("08:00")
        self.repeat_var.set("每天")

    def add_item(self):
        name = self.name_var.get().strip()
        t = normalize_time(self.time_var.get())
        if not name:
            messagebox.showwarning("提示", "请输入药名")
            return
        if t is None:
            messagebox.showwarning("提示", "时间格式应为 HH:MM，例如 08:30")
            return
        repeat = "once" if self.repeat_var.get() == "仅一次" else "daily"

        if self.editing_index is not None:
            it = self.items[self.editing_index]
            it.update(
                {
                    "name": name,
                    "dose": self.dose_var.get().strip(),
                    "time": t,
                    "repeat": repeat,
                }
            )
            if repeat == "once" and not it.get("created"):
                it["created"] = today_str()
        else:
            item = {
                "name": name,
                "dose": self.dose_var.get().strip(),
                "time": t,
                "repeat": repeat,
                "last_done": None,
            }
            if repeat == "once":
                item["created"] = today_str()
            self.items.append(item)

        save_items(self.items)
        self.clear_form()
        self.refresh_list()

    def edit_item(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中要编辑的提醒")
            return
        if len(sel) > 1:
            messagebox.showinfo("提示", "一次只能编辑一条，请只选中一条")
            return
        i = int(sel[0])
        it = self.items[i]
        self.editing_index = i
        self.name_var.set(it["name"])
        self.dose_var.set(it.get("dose", ""))
        self.time_var.set(it["time"])
        self.repeat_var.set(REPEAT_LABELS.get(it.get("repeat", "daily"), "每天"))
        self.add_btn.config(text="保存修改")

    def delete_item(self):
        sel = self.tree.selection()
        if not sel:
            return
        for idx in sorted((int(s) for s in sel), reverse=True):
            del self.items[idx]
        save_items(self.items)
        self.clear_form()
        self.refresh_list()

    def mark_taken(self):
        for s in self.tree.selection():
            self.items[int(s)]["last_done"] = today_str()
        save_items(self.items)
        self.refresh_list()

    def tick(self):
        now = datetime.now()
        self.clock_var.set(now.strftime("当前时间 %H:%M:%S"))
        if self.popup is None:
            due = self.find_due(now)
            if due is not None:
                self.show_popup(due)
        self.root.after(1000, self.tick)

    def find_due(self, now):
        today = today_str()
        hhmm = now.strftime("%H:%M")
        for i, it in enumerate(self.items):
            repeat = it.get("repeat", "daily")
            if repeat == "once":
                if it.get("last_done"):
                    continue
                if it.get("created") and it.get("created") != today:
                    continue
            else:
                if it.get("last_done") == today:
                    continue
            snooze = it.get("snooze_until")
            if snooze:
                if now >= datetime.fromisoformat(snooze):
                    return i
                continue
            if it["time"] <= hhmm and it.get("last_alerted") != today:
                return i
        return None

    def show_popup(self, idx):
        it = self.items[idx]
        it["last_alerted"] = today_str()
        it.pop("snooze_until", None)
        save_items(self.items)

        win = tk.Toplevel(self.root)
        self.popup = win
        win.title("该吃药了")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.geometry(
            "340x180+%d+%d"
            % (
                self.root.winfo_screenwidth() // 2 - 170,
                self.root.winfo_screenheight() // 2 - 90,
            )
        )
        text = "该吃药了！\n\n%s  %s\n（预定时间 %s）" % (
            it["name"],
            it.get("dose", ""),
            it["time"],
        )
        ttk.Label(win, text=text, justify="center", font=("Microsoft YaHei", 12)).pack(
            pady=18
        )

        btns = ttk.Frame(win)
        btns.pack()
        ttk.Button(
            btns, text="已服用", command=lambda: self.close_popup(idx, taken=True)
        ).pack(side="left", padx=6)
        ttk.Button(
            btns,
            text="%d 分钟后再提醒" % SNOOZE_MINUTES,
            command=lambda: self.close_popup(idx, taken=False),
        ).pack(side="left", padx=6)
        win.protocol("WM_DELETE_WINDOW", lambda: self.close_popup(idx, taken=False))

        if winsound:
            for _ in range(3):
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        win.lift()
        win.focus_force()
        win.wait_visibility()
        win.grab_set()

    def close_popup(self, idx, taken):
        it = self.items[idx]
        if taken:
            it["last_done"] = today_str()
            it.pop("snooze_until", None)
        else:
            it["snooze_until"] = (
                datetime.now() + timedelta(minutes=SNOOZE_MINUTES)
            ).isoformat()
        save_items(self.items)
        if self.popup is not None:
            self.popup.destroy()
            self.popup = None
        self.refresh_list()

    def on_close(self):
        if messagebox.askyesno("退出", "退出后将不再提醒吃药，确定退出吗？"):
            self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
