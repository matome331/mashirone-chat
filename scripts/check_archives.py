#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ミミィチャット検索 - 全件公開状態チェック。

data/index.json に登録済みの全動画をローカルPCから確認し、
「公開中 / 非公開候補 / 確認不能」に分類する。

重要:
- index/chunkは削除・変更しない
- 途中経過を保存し、中断後は続きから再開
- bot判定や通信失敗は「非公開」と断定しない
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_FILE = os.path.join(REPO_ROOT, "data", "index.json")
STATE_FILE = os.path.join(REPO_ROOT, "scripts", "archive_check_state.json")
REPORT_FILE = os.path.join(REPO_ROOT, "scripts", "archive_check_report.json")

DEFAULT_SLEEP = 2.0
UNKNOWN_STREAK_LIMIT = 8

STATUS_PUBLIC = "public"
STATUS_CANDIDATE = "unavailable_candidate"
STATUS_UNKNOWN = "unknown"


def utf8_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def atomic_json_write(path: str, data: object) -> None:
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def load_index() -> list[dict]:
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("data/index.json の形式が不正です")
    return data


def new_state(total: int) -> dict:
    return {
        "version": 2,
        "started_at": now_iso(),
        "last_updated_at": now_iso(),
        "complete": False,
        "total_at_start": total,
        "results": {},
    }


def load_or_create_state(total: int, restart: bool) -> tuple[dict, bool]:
    if restart or not os.path.exists(STATE_FILE):
        state = new_state(total)
        atomic_json_write(STATE_FILE, state)
        return state, False

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError):
        state = new_state(total)
        atomic_json_write(STATE_FILE, state)
        return state, False

    if (
        not isinstance(state, dict)
        or state.get("version") != 2
        or not isinstance(state.get("results"), dict)
        or state.get("complete")
    ):
        state = new_state(total)
        atomic_json_write(STATE_FILE, state)
        return state, False

    return state, True


def classify_result(
    returncode: int,
    stdout: str,
    stderr: str,
) -> tuple[str, str]:
    output = stdout.strip()
    availability = output.splitlines()[-1].strip().lower() if output else ""
    err = stderr.lower()

    if returncode == 0:
        if availability in {"public", "unlisted"}:
            return STATUS_PUBLIC, availability

        if availability in {"private", "subscriber_only"}:
            return STATUS_CANDIDATE, availability

        if availability:
            return STATUS_UNKNOWN, f"availability={availability}"

    access_block_tokens = (
        "sign in to confirm you're not a bot",
        "sign in to confirm you’re not a bot",
        "po token",
        "http error 403",
        "http error 429",
        "too many requests",
    )
    if any(token in err for token in access_block_tokens):
        return STATUS_UNKNOWN, "youtube_access_blocked"

    strong_unavailable_tokens = (
        "private video",
        "this video is private",
        "video has been removed",
        "this video has been removed",
        "this video is no longer available",
        "account associated with this video has been terminated",
        "members-only content",
        "members only",
        "join this channel",
    )
    for token in strong_unavailable_tokens:
        if token in err:
            return STATUS_CANDIDATE, token

    if returncode != 0:
        tail = " | ".join(stderr.strip().splitlines()[-3:])
        return STATUS_UNKNOWN, tail[:500] or f"yt-dlp exit {returncode}"

    return STATUS_UNKNOWN, "availabilityを判定できませんでした"


def check_video(video_id: str) -> tuple[str, str]:
    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--skip-download",
        "--no-warnings",
        "--encoding",
        "utf-8",
        "--print",
        "%(availability)s",
        url,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
            env=utf8_env(),
        )
    except subprocess.TimeoutExpired:
        return STATUS_UNKNOWN, "timeout"
    except Exception as exc:
        return STATUS_UNKNOWN, f"{type(exc).__name__}: {exc}"

    return classify_result(
        result.returncode,
        result.stdout,
        result.stderr,
    )


def summarize(index: list[dict], state: dict) -> dict:
    current_ids = {entry.get("id") for entry in index}
    results = {
        video_id: result
        for video_id, result in state["results"].items()
        if video_id in current_ids
    }

    public = []
    candidates = []
    unknown = []

    for entry in index:
        video_id = entry.get("id")
        result = results.get(video_id)
        if not result:
            continue

        item = {
            "id": video_id,
            "title": entry.get("title", ""),
            "date": entry.get("date", ""),
            "status": result.get("status"),
            "reason": result.get("reason", ""),
            "checked_at": result.get("checked_at", ""),
        }

        if item["status"] == STATUS_PUBLIC:
            public.append(item)
        elif item["status"] == STATUS_CANDIDATE:
            candidates.append(item)
        else:
            unknown.append(item)

    return {
        "version": 1,
        "generated_at": now_iso(),
        "total_indexed": len(index),
        "checked": len(results),
        "public_count": len(public),
        "candidate_count": len(candidates),
        "unknown_count": len(unknown),
        "public": public,
        "candidates": candidates,
        "unknown": unknown,
    }


def print_summary(report: dict) -> None:
    print("\n" + "=" * 60)
    print("  全件公開状態チェック 結果")
    print("=" * 60)
    print(f"  登録動画: {report['total_indexed']}本")
    print(f"  確認済み: {report['checked']}本")
    print(f"  公開中: {report['public_count']}本")
    print(f"  非公開候補: {report['candidate_count']}本")
    print(f"  確認不能: {report['unknown_count']}本")

    if report["candidates"]:
        print("\n  [非公開候補]")
        for item in report["candidates"]:
            print(
                f"  - {item['id']} | {item['date']} | "
                f"{item['title'][:70]}"
            )
            print(f"    理由: {item['reason']}")

    if report["unknown"]:
        print("\n  [確認不能]")
        for item in report["unknown"][:30]:
            print(
                f"  - {item['id']} | {item['date']} | "
                f"{item['title'][:60]}"
            )
            print(f"    理由: {item['reason']}")
        if len(report["unknown"]) > 30:
            print(f"  ... 他 {len(report['unknown']) - 30}本")

    print(f"\n  結果保存: {REPORT_FILE}")
    print("  ※ 非公開候補は自動削除していません。")


def main(*, sleep_sec: float, restart: bool) -> int:
    if not os.path.exists(INDEX_FILE):
        print("❌ data/index.json が見つかりません。", file=sys.stderr)
        return 1

    index = load_index()
    state, resumed = load_or_create_state(len(index), restart)

    valid_ids = {entry.get("id") for entry in index}
    state["results"] = {
        video_id: value
        for video_id, value in state["results"].items()
        if video_id in valid_ids
    }

    checked_ids = set(state["results"])
    pending = [entry for entry in index if entry.get("id") not in checked_ids]

    print("=" * 60)
    print("  ミミィチャット検索 - 全件公開状態チェック")
    print("=" * 60)
    print(f"  登録動画: {len(index)}本")
    if resumed:
        print(f"  前回の途中結果から再開: {len(checked_ids)}本確認済み")
    else:
        print("  新しい全件チェックを開始")
    print(f"  残り: {len(pending)}本")
    print("  ※ index/chunkの削除・変更は行いません。")
    print()

    consecutive_unknown_ids: list[str] = []

    try:
        for number, entry in enumerate(pending, start=len(checked_ids) + 1):
            video_id = entry.get("id", "")
            title = entry.get("title", "")
            print(
                f"  [{number}/{len(index)}] {video_id}: "
                f"{title[:45]}...",
                flush=True,
            )

            status, reason = check_video(video_id)

            if status == STATUS_PUBLIC:
                symbol = "✓"
                label = "公開中"
                consecutive_unknown_ids.clear()
            elif status == STATUS_CANDIDATE:
                symbol = "!"
                label = "非公開候補"
                consecutive_unknown_ids.clear()
            else:
                symbol = "?"
                label = "確認不能"
                consecutive_unknown_ids.append(video_id)

            print(f"    {symbol} {label} ({reason})", flush=True)

            state["results"][video_id] = {
                "status": status,
                "reason": reason,
                "checked_at": now_iso(),
            }
            state["last_updated_at"] = now_iso()
            atomic_json_write(STATE_FILE, state)

            if len(consecutive_unknown_ids) >= UNKNOWN_STREAK_LIMIT:
                # YouTube側の一時ブロックの可能性が高いので、直近の確認不能は
                # 未確認へ戻して後日resume時に再試行する。
                for unknown_id in consecutive_unknown_ids:
                    state["results"].pop(unknown_id, None)
                state["last_updated_at"] = now_iso()
                atomic_json_write(STATE_FILE, state)

                print(
                    "\n⚠ 確認不能が連続したため一旦停止します。\n"
                    "  YouTube側の制限や通信問題の可能性があります。\n"
                    "  時間を空けて同じボタンを押すと続きから再開します。",
                    file=sys.stderr,
                )
                report = summarize(index, state)
                atomic_json_write(REPORT_FILE, report)
                print_summary(report)
                return 2

            if sleep_sec > 0:
                time.sleep(sleep_sec)

    except KeyboardInterrupt:
        print(
            "\n中断しました。途中結果は保存済みです。"
            "次回は続きから再開します。"
        )
        report = summarize(index, state)
        atomic_json_write(REPORT_FILE, report)
        return 130

    state["complete"] = True
    state["completed_at"] = now_iso()
    state["last_updated_at"] = now_iso()
    atomic_json_write(STATE_FILE, state)

    report = summarize(index, state)
    atomic_json_write(REPORT_FILE, report)
    print_summary(report)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="登録済み動画の全件公開状態チェック"
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=DEFAULT_SLEEP,
        help=f"動画間の待機秒数 (default: {DEFAULT_SLEEP})",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="途中結果を破棄して最初から確認する",
    )
    args = parser.parse_args()

    raise SystemExit(
        main(
            sleep_sec=max(0.0, args.sleep),
            restart=args.restart,
        )
    )
