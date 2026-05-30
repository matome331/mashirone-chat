#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ミミィチャット検索 - アーカイブ公開チェック
index.json の全動画IDについて、非公開/削除済みかを確認し、
該当する動画をインデックスとチャンクデータから削除する

GitHub Actions で月次実行を想定
"""

import json
import sys
import os
import subprocess
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# パス設定（リポジトリルート基準）
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
CHUNKS_DIR = os.path.join(DATA_DIR, "chunks")
INDEX_FILE = os.path.join(DATA_DIR, "index.json")

# チェック間のスリープ（レート制限回避）
CHECK_SLEEP = 2  # 秒


def check_video_availability(video_id):
    """
    yt-dlp で動画が公開中かチェック。
    戻り値: True=公開中, False=非公開/削除済み/アクセス不可
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--print", "%(availability)s",
        "--no-warnings",
        url,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=30)

        availability = result.stdout.strip()

        # "public" or "unlisted" → OK, それ以外 → 非公開/削除
        if availability in ("public", "unlisted"):
            return True

        # returncode 0 でも availability が空や "private" ならNG
        if result.returncode != 0:
            stderr = result.stderr.lower()
            # "private video" / "video is unavailable" / "removed" 等
            if any(kw in stderr for kw in ['private', 'unavailable', 'removed', 'not exist']):
                return False
            # その他のエラー（ネットワーク等）は判断保留
            return None

        return False

    except subprocess.TimeoutExpired:
        return None  # タイムアウトは判断保留
    except Exception as e:
        print(f"    チェックエラー: {e}")
        return None


def main(dry_run=False, sleep_sec=CHECK_SLEEP):
    print("=" * 60)
    print("  ミミィチャット検索 - アーカイブ公開チェック")
    print("=" * 60)

    # index.json 読み込み
    if not os.path.exists(INDEX_FILE):
        print("  index.json が見つかりません。")
        return

    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        index = json.load(f)

    total = len(index)
    print(f"  チェック対象: {total}本")

    unavailable = []  # 非公開/削除された動画
    errors = []       # チェックできなかった動画

    for i, entry in enumerate(index, 1):
        vid_id = entry['id']
        title_short = entry.get('title', '')[:40]
        print(f"  [{i}/{total}] {vid_id}: {title_short}...", end=" ")

        status = check_video_availability(vid_id)

        if status is True:
            print("✓ 公開中")
        elif status is False:
            print("✗ 非公開/削除済み")
            unavailable.append(entry)
        else:
            print("? チェック不能（スキップ）")
            errors.append(entry)

        if i < total:
            time.sleep(sleep_sec)

    # 結果サマリー
    print(f"\n{'=' * 60}")
    print(f"  チェック結果")
    print(f"{'=' * 60}")
    print(f"  公開中: {total - len(unavailable) - len(errors)}本")
    print(f"  非公開/削除: {len(unavailable)}本")
    print(f"  チェック不能: {len(errors)}本")

    if not unavailable:
        print("\n  非公開動画はありませんでした。更新不要です。")
        return

    # 非公開動画のリスト表示
    print(f"\n  非公開になった動画:")
    for entry in unavailable:
        print(f"    - {entry['id']}: {entry.get('title', '')[:60]}")

    if dry_run:
        print(f"\n  [DRY RUN] 実際の削除はスキップされました。")
        return

    # index から除去
    unavailable_ids = {e['id'] for e in unavailable}
    new_index = [e for e in index if e['id'] not in unavailable_ids]

    # ランク再付与
    new_index.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
    for i, item in enumerate(new_index):
        item['rank'] = len(new_index) - i

    # index.json 書き込み
    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_index, f, ensure_ascii=False, indent=2)
    print(f"\n  index.json 更新: {len(index)} → {len(new_index)}本")

    # チャンクファイル削除
    deleted_chunks = 0
    for vid_id in unavailable_ids:
        chunk_file = os.path.join(CHUNKS_DIR, f"{vid_id}.json")
        if os.path.exists(chunk_file):
            os.remove(chunk_file)
            deleted_chunks += 1
            print(f"    削除: chunks/{vid_id}.json")

    print(f"  チャンクファイル削除: {deleted_chunks}件")
    print(f"\n  完了！")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='アーカイブ公開チェック')
    parser.add_argument('--dry-run', action='store_true',
                       help='チェックのみ実行し、実際の削除は行わない')
    parser.add_argument('--sleep', type=int, default=CHECK_SLEEP,
                       help=f'チェック間のスリープ秒数 (default: {CHECK_SLEEP})')
    args = parser.parse_args()

    main(dry_run=args.dry_run, sleep_sec=args.sleep)
