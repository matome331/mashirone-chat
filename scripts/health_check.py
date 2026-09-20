#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ミミィチャット検索 - 公開データ健康診断

YouTubeへアクセスせず、リポジトリ内の index / chunks / failure ledger の
整合性だけを検証する。エラーが1件でもあれば終了コード1。
"""

import json
import os
import re
import sys
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
CHUNKS_DIR = os.path.join(DATA_DIR, "chunks")
INDEX_FILE = os.path.join(DATA_DIR, "index.json")
FAILURE_LEDGER_FILE = os.path.join(
    REPO_ROOT, "scripts", "collection_failures.json"
)
EXCLUDED_VIDEOS_FILE = os.path.join(REPO_ROOT, "excluded_videos.txt")

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
DATE_RE = re.compile(r"^\d{4}/\d{2}/\d{2}$")


class HealthReport:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.checked_messages = 0

    def error(self, message):
        self.errors.append(message)

    def warn(self, message):
        self.warnings.append(message)


def load_json(path, report, label):
    if not os.path.exists(path):
        report.error(f"{label} が見つかりません: {path}")
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        report.error(
            f"{label} のJSONが壊れています: "
            f"{path} (line {exc.lineno}, column {exc.colno})"
        )
    except OSError as exc:
        report.error(f"{label} を読めません: {path} ({exc})")
    return None


def validate_index(report):
    index = load_json(INDEX_FILE, report, "data/index.json")
    if index is None:
        return [], {}

    if not isinstance(index, list):
        report.error("data/index.json のトップレベルが配列ではありません")
        return [], {}

    by_id = {}
    total = len(index)

    for position, entry in enumerate(index):
        label = f"index[{position}]"
        if not isinstance(entry, dict):
            report.error(f"{label} がオブジェクトではありません")
            continue

        video_id = entry.get("id")
        if not isinstance(video_id, str) or not VIDEO_ID_RE.fullmatch(video_id):
            report.error(f"{label}.id が不正です: {video_id!r}")
            continue

        if video_id in by_id:
            report.error(f"重複動画ID: {video_id}")
        else:
            by_id[video_id] = entry

        title = entry.get("title")
        if not isinstance(title, str) or not title.strip():
            report.error(f"{video_id}: title が空または文字列ではありません")

        duration = entry.get("duration")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool):
            report.error(f"{video_id}: duration が数値ではありません")
        elif duration < 0:
            report.error(f"{video_id}: duration が負数です: {duration}")

        count = entry.get("count")
        if not isinstance(count, int) or isinstance(count, bool):
            report.error(f"{video_id}: count が整数ではありません")
        elif count <= 0:
            report.error(f"{video_id}: count が0以下です: {count}")

        date_str = entry.get("date")
        if not isinstance(date_str, str):
            report.error(f"{video_id}: date が文字列ではありません")
        elif date_str:
            if not DATE_RE.fullmatch(date_str):
                report.error(f"{video_id}: date 形式が不正です: {date_str!r}")
            else:
                try:
                    datetime.strptime(date_str, "%Y/%m/%d")
                except ValueError:
                    report.error(f"{video_id}: 実在しない日付です: {date_str}")

        timestamp = entry.get("timestamp")
        if not isinstance(timestamp, int) or isinstance(timestamp, bool):
            report.error(f"{video_id}: timestamp が整数ではありません")
        elif timestamp < 0:
            report.error(f"{video_id}: timestamp が負数です: {timestamp}")

        expected_rank = total - position
        rank = entry.get("rank")
        if rank != expected_rank:
            report.error(
                f"{video_id}: rank 不整合 "
                f"(expected {expected_rank}, actual {rank!r})"
            )

    return index, by_id


def validate_chunks(index_by_id, report):
    if not os.path.isdir(CHUNKS_DIR):
        report.error(f"chunksディレクトリが見つかりません: {CHUNKS_DIR}")
        return

    chunk_names = [
        name for name in os.listdir(CHUNKS_DIR)
        if name.endswith(".json") and os.path.isfile(os.path.join(CHUNKS_DIR, name))
    ]
    chunk_ids = {name[:-5] for name in chunk_names}
    index_ids = set(index_by_id)

    for video_id in sorted(index_ids - chunk_ids):
        report.error(f"chunk欠損: data/chunks/{video_id}.json")

    for video_id in sorted(chunk_ids - index_ids):
        report.error(f"孤立chunk: data/chunks/{video_id}.json")

    for video_id in sorted(index_ids & chunk_ids):
        path = os.path.join(CHUNKS_DIR, f"{video_id}.json")
        messages = load_json(path, report, f"chunk {video_id}")
        if messages is None:
            continue

        if not isinstance(messages, list):
            report.error(f"{video_id}: chunkのトップレベルが配列ではありません")
            continue

        if not messages:
            report.error(f"{video_id}: chunkが0件です")
            continue

        expected_count = index_by_id[video_id].get("count")
        if len(messages) != expected_count:
            report.error(
                f"{video_id}: count不整合 "
                f"(index {expected_count}, chunk {len(messages)})"
            )

        duration = index_by_id[video_id].get("duration", 0)

        for i, message in enumerate(messages):
            report.checked_messages += 1
            prefix = f"{video_id}[{i}]"

            if not isinstance(message, dict):
                report.error(f"{prefix}: メッセージがオブジェクトではありません")
                continue

            author = message.get("a")
            text = message.get("m")
            offset = message.get("t")

            if not isinstance(author, str):
                report.error(f"{prefix}: a が文字列ではありません")

            if not isinstance(text, str):
                report.error(f"{prefix}: m が文字列ではありません")
            elif not text.strip():
                report.error(f"{prefix}: m が空です")

            if not isinstance(offset, (int, float)) or isinstance(offset, bool):
                report.error(f"{prefix}: t が数値ではありません")
            else:
                if offset < 0:
                    report.error(f"{prefix}: t が負数です: {offset}")
                if (
                    isinstance(duration, (int, float))
                    and duration > 0
                    and offset > duration + 120
                ):
                    report.warn(
                        f"{prefix}: t={offset} が duration={duration} を"
                        "120秒超えているため要確認"
                    )


def validate_excluded_videos(report):
    if not os.path.exists(EXCLUDED_VIDEOS_FILE):
        report.error("excluded_videos.txt が見つかりません")
        return set()

    excluded = set()
    with open(EXCLUDED_VIDEOS_FILE, "r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, start=1):
            video_id = raw_line.split("#", 1)[0].strip()
            if not video_id:
                continue

            if not VIDEO_ID_RE.fullmatch(video_id):
                report.error(
                    f"excluded_videos.txt line {line_no}: "
                    f"動画ID形式が不正です: {video_id!r}"
                )
                continue

            if video_id in excluded:
                report.error(
                    f"excluded_videos.txt line {line_no}: 重複ID {video_id}"
                )
                continue

            excluded.add(video_id)

    return excluded


def validate_failure_ledger(report):
    ledger = load_json(
        FAILURE_LEDGER_FILE,
        report,
        "scripts/collection_failures.json",
    )
    if ledger is None:
        return

    if not isinstance(ledger, dict):
        report.error("失敗台帳のトップレベルがオブジェクトではありません")
        return

    if ledger.get("version") != 1:
        report.warn(f"失敗台帳のversionが想定外です: {ledger.get('version')!r}")

    failures = ledger.get("failures")
    if not isinstance(failures, dict):
        report.error("失敗台帳の failures がオブジェクトではありません")
        return

    for key, item in failures.items():
        if not VIDEO_ID_RE.fullmatch(str(key)):
            report.error(f"失敗台帳の動画IDキーが不正です: {key!r}")
            continue

        if not isinstance(item, dict):
            report.error(f"失敗台帳 {key}: 値がオブジェクトではありません")
            continue

        if item.get("video_id") != key:
            report.error(
                f"失敗台帳 {key}: video_idがキーと一致しません "
                f"({item.get('video_id')!r})"
            )

        attempts = item.get("attempts")
        if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 1:
            report.error(f"失敗台帳 {key}: attempts が不正です: {attempts!r}")

        reason = item.get("reason")
        if not isinstance(reason, str) or not reason:
            report.error(f"失敗台帳 {key}: reason が空です")

        for field in ("first_failed_at", "last_failed_at"):
            value = item.get(field)
            if not isinstance(value, str) or not value:
                report.error(f"失敗台帳 {key}: {field} が空です")
                continue
            try:
                datetime.fromisoformat(value)
            except ValueError:
                report.error(
                    f"失敗台帳 {key}: {field} がISO日時ではありません: {value!r}"
                )


def main():
    report = HealthReport()

    print("=" * 60)
    print("  ミミィチャット検索 - データ健康診断")
    print("=" * 60)

    index, index_by_id = validate_index(report)
    validate_chunks(index_by_id, report)
    excluded_ids = validate_excluded_videos(report)
    validate_failure_ledger(report)

    print(f"  index動画数: {len(index_by_id)}")
    print(f"  公開除外動画数: {len(excluded_ids)}")
    print(f"  検証メッセージ数: {report.checked_messages:,}")
    print(f"  warning: {len(report.warnings)}")
    print(f"  error: {len(report.errors)}")

    if report.warnings:
        print("\n[WARNINGS]")
        for warning in report.warnings[:50]:
            print(f"  - {warning}")
        if len(report.warnings) > 50:
            print(f"  ... 他 {len(report.warnings) - 50}件")

    if report.errors:
        print("\n[ERRORS]")
        for error in report.errors[:100]:
            print(f"  - {error}")
        if len(report.errors) > 100:
            print(f"  ... 他 {len(report.errors) - 100}件")

        print("\n  ❌ 健康診断: NG")
        return 1

    print("\n  ✅ 健康診断: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
