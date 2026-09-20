#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""承認済みのYouTube動画を公開検索除外リストへ追加する。

通常はChatで非公開/削除を確認した後に使う。
index/chunk自体は削除しない。
"""

import argparse
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCLUDED_FILE = os.path.join(REPO_ROOT, "excluded_videos.txt")
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def extract_video_id(value):
    value = value.strip()
    if VIDEO_ID_RE.fullmatch(value):
        return value

    patterns = [
        r"[?&]v=([A-Za-z0-9_-]{11})",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"/(?:shorts|live|embed)/([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return match.group(1)

    return None


def load_ids():
    if not os.path.exists(EXCLUDED_FILE):
        return set()

    ids = set()
    with open(EXCLUDED_FILE, "r", encoding="utf-8") as f:
        for raw_line in f:
            video_id = raw_line.split("#", 1)[0].strip()
            if video_id:
                ids.add(video_id)
    return ids


def main():
    parser = argparse.ArgumentParser(
        description="承認済み動画を公開検索除外リストへ追加します。"
    )
    parser.add_argument("video", help="YouTube URL または11文字の動画ID")
    parser.add_argument(
        "--reason",
        default="Chat確認済み",
        help="行末へ残す理由メモ",
    )
    args = parser.parse_args()

    video_id = extract_video_id(args.video)
    if not video_id:
        print("[ERROR] YouTube動画IDを判別できませんでした。")
        return 1

    excluded = load_ids()
    if video_id in excluded:
        print(f"[INFO] {video_id} はすでに除外済みです。")
        return 0

    reason = re.sub(r"[\r\n]+", " ", args.reason).strip()
    with open(EXCLUDED_FILE, "a", encoding="utf-8") as f:
        if os.path.getsize(EXCLUDED_FILE) > 0:
            f.write("\n")
        f.write(video_id)
        if reason:
            f.write(f"  # {reason}")
        f.write("\n")

    print(f"[SUCCESS] {video_id} を公開検索除外リストへ追加しました。")
    print("index/chunkは削除していません。")
    print("「GitHubへ公開」でサイトへ反映できます。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
