#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ミミィチャット検索 - Windows GUI 更新ランチャー。

既存の collect_chats.py / health_check.py を子プロセスとして実行し、
進捗ログをTkinter画面内へ表示する。
"""

from __future__ import annotations

import importlib.util
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
COLLECT_SCRIPT = os.path.join(REPO_ROOT, "scripts", "collect_chats.py")
HEALTH_SCRIPT = os.path.join(REPO_ROOT, "scripts", "health_check.py")


class ChatUpdateApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("ミミィチャット検索 - 更新ツール")
        self.root.geometry("820x640")
        self.root.minsize(720, 540)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.current_process: subprocess.Popen[str] | None = None
        self.running = False
        self.action_buttons: list[ttk.Button] = []

        self.status_var = tk.StringVar(value="起動準備中…")
        self.video_var = tk.StringVar()

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._drain_events)
        self.root.after(250, self._check_environment)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)

        title_row = ttk.Frame(outer)
        title_row.pack(fill="x")

        ttk.Label(
            title_row,
            text="ミミィチャット検索",
            font=("", 17, "bold"),
        ).pack(side="left")
        ttk.Label(
            title_row,
            text="コメントログ更新",
            font=("", 11),
        ).pack(side="left", padx=(10, 0), pady=(5, 0))

        status_frame = ttk.Frame(outer)
        status_frame.pack(fill="x", pady=(12, 12))

        self.progress = ttk.Progressbar(status_frame, mode="indeterminate", length=170)
        self.progress.pack(side="right", padx=(12, 0))

        ttk.Label(
            status_frame,
            textvariable=self.status_var,
            font=("", 10, "bold"),
        ).pack(side="left")

        button_frame = ttk.LabelFrame(outer, text="更新メニュー", padding=12)
        button_frame.pack(fill="x")

        normal_btn = ttk.Button(
            button_frame,
            text="通常更新",
            command=self._normal_update,
        )
        normal_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=4)

        full_btn = ttk.Button(
            button_frame,
            text="全件棚卸し",
            command=self._full_scan,
        )
        full_btn.grid(row=0, column=1, sticky="ew", padx=8, pady=4)

        health_btn = ttk.Button(
            button_frame,
            text="データ健康診断",
            command=self._health_check,
        )
        health_btn.grid(row=0, column=2, sticky="ew", padx=(8, 0), pady=4)

        failures_btn = ttk.Button(
            button_frame,
            text="失敗動画を見る",
            command=self._show_failures,
        )
        failures_btn.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=4)

        self.clear_btn = ttk.Button(
            button_frame,
            text="ログを消す",
            command=self._clear_log,
        )
        self.clear_btn.grid(row=1, column=1, sticky="ew", padx=8, pady=4)

        self.stop_btn = ttk.Button(
            button_frame,
            text="実行を停止",
            command=self._stop_current,
            state="disabled",
        )
        self.stop_btn.grid(row=1, column=2, sticky="ew", padx=(8, 0), pady=4)

        for col in range(3):
            button_frame.columnconfigure(col, weight=1)

        self.action_buttons.extend(
            [normal_btn, full_btn, health_btn, failures_btn]
        )

        single_frame = ttk.LabelFrame(
            outer,
            text="1配信だけ再取得",
            padding=12,
        )
        single_frame.pack(fill="x", pady=(12, 0))

        ttk.Label(
            single_frame,
            text="YouTube URL / 動画ID",
        ).pack(anchor="w")

        single_row = ttk.Frame(single_frame)
        single_row.pack(fill="x", pady=(6, 0))

        self.video_entry = ttk.Entry(
            single_row,
            textvariable=self.video_var,
        )
        self.video_entry.pack(side="left", fill="x", expand=True)

        single_btn = ttk.Button(
            single_row,
            text="この配信を再取得",
            command=self._single_video,
        )
        single_btn.pack(side="left", padx=(8, 0))
        self.action_buttons.append(single_btn)

        log_frame = ttk.LabelFrame(outer, text="実行ログ", padding=8)
        log_frame.pack(fill="both", expand=True, pady=(12, 0))

        self.log = scrolledtext.ScrolledText(
            log_frame,
            wrap="word",
            height=18,
            font=("Consolas", 9),
            state="disabled",
        )
        self.log.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="※ update_chat.bat は非常用として残しています。",
            foreground="#666666",
        ).pack(anchor="w", pady=(8, 0))

    def _check_environment(self) -> None:
        missing = []
        for path in (COLLECT_SCRIPT, HEALTH_SCRIPT):
            if not os.path.exists(path):
                missing.append(os.path.relpath(path, REPO_ROOT))

        if missing:
            self.status_var.set("必要ファイルが見つかりません")
            self._append_log(
                "[ERROR] 必要ファイルがありません: " + ", ".join(missing) + "\n"
            )
            self._set_actions_enabled(False)
            return

        if importlib.util.find_spec("yt_dlp") is None:
            self.status_var.set("yt-dlp が未インストールです")
            self._set_actions_enabled(False)
            install = messagebox.askyesno(
                "yt-dlp が必要です",
                "yt-dlp がPython環境に見つかりません。\n"
                "今インストールしますか？",
            )
            if install:
                self._run_sequence(
                    "yt-dlp をインストール",
                    [[sys.executable, "-m", "pip", "install", "-U", "yt-dlp"]],
                    run_health=False,
                    environment_setup=True,
                )
            else:
                self._append_log(
                    "yt-dlp は未インストールです。\n"
                    "update_chat.bat からもインストールできます。\n"
                )
            return

        self.status_var.set("準備OK")
        self._append_log(
            f"Python: {sys.version.split()[0]}\n"
            "yt-dlp: 利用可能\n"
            "準備OK。操作を選んでください。\n\n"
        )

    def _normal_update(self) -> None:
        self._run_sequence(
            "通常更新",
            [[
                sys.executable,
                COLLECT_SCRIPT,
                "--limit",
                "10",
                "--sleep",
                "5",
            ]],
            run_health=True,
        )

    def _full_scan(self) -> None:
        if not messagebox.askyesno(
            "全件棚卸し",
            "古い取りこぼしを含めてチャンネル全件を確認します。\n"
            "通常更新より時間がかかります。実行しますか？",
        ):
            return

        self._run_sequence(
            "全件棚卸し",
            [[
                sys.executable,
                COLLECT_SCRIPT,
                "--full-scan",
                "--limit",
                "0",
                "--sleep",
                "5",
            ]],
            run_health=True,
        )

    def _single_video(self) -> None:
        video_ref = self.video_var.get().strip()
        if not video_ref:
            messagebox.showwarning(
                "入力がありません",
                "YouTube URL または11文字の動画IDを入力してください。",
            )
            self.video_entry.focus_set()
            return

        self._run_sequence(
            "1配信だけ再取得",
            [[sys.executable, COLLECT_SCRIPT, "--video", video_ref]],
            run_health=True,
        )

    def _show_failures(self) -> None:
        self._run_sequence(
            "失敗動画台帳",
            [[sys.executable, COLLECT_SCRIPT, "--show-failures"]],
            run_health=False,
        )

    def _health_check(self) -> None:
        self._run_sequence(
            "データ健康診断",
            [[sys.executable, HEALTH_SCRIPT]],
            run_health=False,
        )

    def _run_sequence(
        self,
        label: str,
        commands: list[list[str]],
        *,
        run_health: bool,
        environment_setup: bool = False,
    ) -> None:
        if self.running:
            messagebox.showinfo("実行中", "現在の処理が終わってから実行してください。")
            return

        self.running = True
        self._set_actions_enabled(False)
        self.stop_btn.configure(state="normal")
        self.progress.start(12)
        self.status_var.set(f"{label} 実行中…")
        self._append_log("\n" + "=" * 62 + "\n")
        self._append_log(f"{label}\n")
        self._append_log("=" * 62 + "\n")

        thread = threading.Thread(
            target=self._worker,
            args=(label, commands, run_health, environment_setup),
            daemon=True,
        )
        thread.start()

    def _worker(
        self,
        label: str,
        commands: list[list[str]],
        run_health: bool,
        environment_setup: bool,
    ) -> None:
        return_code = 0

        try:
            for command in commands:
                return_code = self._run_process(command)
                if return_code != 0:
                    break

            if return_code == 0 and run_health:
                self.events.put(("log", "\n--- 自動健康診断 ---\n"))
                return_code = self._run_process([sys.executable, HEALTH_SCRIPT])
        except Exception as exc:  # GUI側の予期しない失敗もログへ出す
            self.events.put(("log", f"\n[GUI ERROR] {exc}\n"))
            return_code = 1

        self.events.put(
            (
                "done",
                {
                    "label": label,
                    "return_code": return_code,
                    "environment_setup": environment_setup,
                },
            )
        )

    def _run_process(self, command: list[str]) -> int:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        creationflags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW

        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
            creationflags=creationflags,
        )
        self.current_process = process

        assert process.stdout is not None
        for line in process.stdout:
            self.events.put(("log", line))

        return_code = process.wait()
        self.current_process = None
        return return_code

    def _stop_current(self) -> None:
        process = self.current_process
        if not self.running or process is None:
            return

        if not messagebox.askyesno(
            "実行を停止",
            "現在の処理を停止しますか？\n"
            "停止した動画は次回更新で再試行できます。",
        ):
            return

        self._append_log("\n[停止要求] 実行中の処理を終了します…\n")
        try:
            self._terminate_process_tree(process)
        except OSError as exc:
            self._append_log(f"[ERROR] 停止できませんでした: {exc}\n")

    def _drain_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()

                if event == "log":
                    self._append_log(str(payload))
                elif event == "done":
                    self._finish_run(payload)
        except queue.Empty:
            pass

        self.root.after(100, self._drain_events)

    def _finish_run(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        label = str(data.get("label", "処理"))
        return_code = int(data.get("return_code", 1))
        environment_setup = bool(data.get("environment_setup"))

        self.running = False
        self.current_process = None
        self.progress.stop()
        self.stop_btn.configure(state="disabled")

        if environment_setup and return_code != 0:
            self._set_actions_enabled(False)
        else:
            self._set_actions_enabled(True)

        if return_code == 0:
            self.status_var.set(f"{label} 完了")
            self._append_log(f"\n✅ {label}: 完了\n")
            if environment_setup:
                self._append_log("yt-dlp の準備ができました。\n")
            elif label == "1配信だけ再取得":
                self.video_var.set("")
        else:
            self.status_var.set(f"{label} エラー")
            self._append_log(f"\n❌ {label}: エラー終了 (code {return_code})\n")
            messagebox.showerror(
                "処理に失敗しました",
                f"{label} がエラー終了しました。\n"
                "実行ログを確認してください。",
            )

    def _set_actions_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in self.action_buttons:
            button.configure(state=state)
        self.video_entry.configure(state=state)

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _on_close(self) -> None:
        if self.running:
            if not messagebox.askyesno(
                "終了",
                "処理を実行中です。GUIを終了しますか？",
            ):
                return
            process = self.current_process
            if process is not None:
                try:
                    self._terminate_process_tree(process)
                except OSError:
                    pass

        self.root.destroy()

    def _terminate_process_tree(self, process: subprocess.Popen[str]) -> None:
        """Windowsでは子プロセスも含めて停止する。"""
        if process.poll() is not None:
            return

        if os.name == "nt":
            subprocess.run(
                [
                    "taskkill",
                    "/PID",
                    str(process.pid),
                    "/T",
                    "/F",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                    if hasattr(subprocess, "CREATE_NO_WINDOW")
                    else 0
                ),
            )
        else:
            process.terminate()


def main() -> int:
    root = tk.Tk()
    app = ChatUpdateApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
