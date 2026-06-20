#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ミミィチャット検索 - データ収集パイプライン
yt-dlp を使って YouTube ライブチャットを収集・パースし、検索用JSONを生成する

GitHub Actions / ローカル両対応
"""

import json
import sys
import os
import subprocess
import glob
import time
import re
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# yt-dlp の出力を確実に UTF-8 にするための環境変数
def _utf8_env():
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    return env

# パス設定（リポジトリルート基準）
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/ の親
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
RAW_DIR = os.path.join(SCRIPTS_DIR, "raw_chats")
DATA_DIR = os.path.join(REPO_ROOT, "data")
CHUNKS_DIR = os.path.join(DATA_DIR, "chunks")
INDEX_FILE = os.path.join(DATA_DIR, "index.json")
PROGRESS_FILE = os.path.join(SCRIPTS_DIR, "progress.json")

# チャンネル情報
CHANNEL_URL = "https://www.youtube.com/@mashi_rone"

# 除外リスト（不備のある配信など、収集対象から永久に除外する動画ID）
EXCLUDED_IDS = {
    "rPgWLBgZfqE",  # 2024/05/09 配信 - データ不備
}

# メンバー限定配信のタイトルキーワード（チャット取得不可のため除外）
MEMBERS_ONLY_KEYWORDS = ["メン限", "Members Only", "members only", "Member Only", "member only"]

def is_members_only(title):
    """タイトルからメンバー限定配信かどうか判定"""
    return any(kw in title for kw in MEMBERS_ONLY_KEYWORDS)

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(CHUNKS_DIR, exist_ok=True)


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"completed": [], "failed": [], "video_list": []}


def save_progress(progress):
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def load_existing_index():
    """既存の index.json を読み込み、処理済み動画IDのセットを返す"""
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, 'r', encoding='utf-8') as f:
            index = json.load(f)
        return {entry['id'] for entry in index}, index
    return set(), []


def get_video_list_from_channel(limit=10):
    """yt-dlp でチャンネルの動画一覧を取得（ライブ配信 + 通常動画）"""
    print(f"  チャンネルから動画リスト取得中... ({CHANNEL_URL})")

    seen_ids = set()
    videos = []

    # /streams（ライブ配信）を優先し、/videos（通常動画）も取得
    for tab in ["/streams", "/videos"]:
        print(f"    {tab} タブ取得中...")
        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--encoding", "utf-8",
            "--print", "%(id)s\t%(title)s\t%(duration)s",
            CHANNEL_URL + tab,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace',
                                    timeout=300, env=_utf8_env())
        except subprocess.TimeoutExpired:
            print(f"    → {tab} タイムアウト、スキップ")
            continue

        tab_count = 0
        for line in result.stdout.strip().split('\n'):
            parts = line.split('\t')
            if len(parts) >= 3:
                vid_id, title, duration_str = parts[0], parts[1], parts[2]

                if vid_id in seen_ids:
                    continue
                seen_ids.add(vid_id)

                try:
                    duration = float(duration_str) if duration_str != 'NA' else 0
                except ValueError:
                    duration = 0

                # /videos タブのみ5分以上フィルタ（ショート除外）
                # /streams タブはライブ配信なので全て対象
                if tab == "/videos" and duration <= 300:
                    continue

                videos.append({
                    'id': vid_id,
                    'title': title,
                    'duration': duration,
                })
                tab_count += 1

        print(f"    → {tab_count}本")

    print(f"  取得動画合計: {len(videos)}本")
    return videos


def get_video_upload_date(video_id):
    """yt-dlp で動画の配信日を取得"""
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--print", "%(upload_date)s",
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding='utf-8', errors='replace',
                                timeout=30, env=_utf8_env())
        date_str = result.stdout.strip()
        if date_str and date_str != 'NA' and len(date_str) == 8:
            # YYYYMMDD → YYYY/MM/DD
            return f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:8]}"
    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"    日付取得失敗: {e}")
    return ""


def download_live_chat(video_id):
    """1つの動画のライブチャットをダウンロード"""
    output_path = os.path.join(RAW_DIR, f"chat_{video_id}")
    url = f"https://www.youtube.com/watch?v={video_id}"

    # 既にダウンロード済みか確認
    existing = glob.glob(os.path.join(RAW_DIR, f"chat_{video_id}*live_chat*"))
    if existing:
        return existing[0]

    cmd = [
        "yt-dlp",
        "--skip-download",
        "--write-subs",
        "--sub-langs", "live_chat",
        "--sub-format", "json3",
        "-o", output_path,
        url,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding='utf-8', errors='replace',
                            timeout=180, env=_utf8_env())

    if result.returncode != 0:
        return None

    files = glob.glob(os.path.join(RAW_DIR, f"chat_{video_id}*live_chat*"))
    return files[0] if files else None


def parse_live_chat(filepath):
    """yt-dlpのライブチャットJSONLをパースしてメッセージリストに変換"""
    messages = []

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            replay = data.get('replayChatItemAction', {})
            offset_ms = int(replay.get('videoOffsetTimeMsec', 0))

            for action in replay.get('actions', []):
                add_action = action.get('addChatItemAction', {})
                item = add_action.get('item', {})

                renderer = (
                    item.get('liveChatTextMessageRenderer') or
                    item.get('liveChatPaidMessageRenderer') or
                    item.get('liveChatMembershipItemRenderer')
                )
                if not renderer:
                    continue

                msg_runs = renderer.get('message', {}).get('runs', [])
                text_parts = []
                for run in msg_runs:
                    if 'text' in run:
                        text_parts.append(run['text'])
                    elif 'emoji' in run:
                        emoji = run['emoji']
                        shortcuts = emoji.get('shortcuts', [])
                        if shortcuts:
                            text_parts.append(shortcuts[0])
                        else:
                            label = (emoji.get('image', {})
                                    .get('accessibility', {})
                                    .get('accessibilityData', {})
                                    .get('label', ''))
                            text_parts.append(f":{label}:" if label else '')

                text = ''.join(text_parts).strip()
                if not text:
                    continue

                author = renderer.get('authorName', {}).get('simpleText', '')

                messages.append({
                    'a': author,
                    'm': text,
                    't': round(offset_ms / 1000),
                })

    return messages


def update_index(existing_index, new_entries):
    """既存のインデックスに新しいエントリを追加し、日付順にソート・ランク付与"""
    # 既存エントリをIDでマッピング
    index_map = {entry['id']: entry for entry in existing_index}

    # 新しいエントリを追加（既存なら上書き）
    for entry in new_entries:
        index_map[entry['id']] = entry

    # リストに変換してタイムスタンプ降順ソート
    combined = list(index_map.values())
    combined.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

    # ランク再付与（大きいほど新しい）
    for i, item in enumerate(combined):
        item['rank'] = len(combined) - i

    return combined


def collect_and_process(limit=10, sleep_sec=5):
    """メインの収集・処理パイプライン（差分収集）"""

    print("=" * 60)
    print("  ミミィチャット検索 - データ収集パイプライン")
    print("=" * 60)

    # 既存データ読み込み
    existing_ids, existing_index = load_existing_index()
    print(f"  既存データ: {len(existing_ids)}本")

    progress = load_progress()

    # チャンネルから動画リスト取得
    all_videos = get_video_list_from_channel(limit=None)  # 全件取得

    # 未処理の動画だけフィルタリング（除外リスト・メン限も除外）
    new_videos = [v for v in all_videos
                  if v['id'] not in existing_ids
                  and v['id'] not in progress.get('failed', [])
                  and v['id'] not in EXCLUDED_IDS
                  and not is_members_only(v.get('title', ''))]

    if not new_videos:
        print("  新しい動画はありません。")
        return

    # 最新の数本はチャットリプレイが未生成の可能性があるためスキップ
    # (yt-dlp は新しい順で返すので、先頭が最新)
    SKIP_RECENT = 3
    if len(new_videos) > SKIP_RECENT:
        skipped = new_videos[:SKIP_RECENT]
        new_videos = new_videos[SKIP_RECENT:]
        print(f"  直近{SKIP_RECENT}本はスキップ（チャットリプレイ未生成の可能性）")

    # limit 適用（新しい順のまま処理 → 最近の配信から優先的に収集）
    if limit:
        new_videos = new_videos[:limit]

    print(f"  新規収集対象: {len(new_videos)}本")

    new_entries = []
    total = len(new_videos)

    for i, video in enumerate(new_videos, 1):
        vid_id = video['id']
        print(f"\n  [{i}/{total}] {vid_id}: {video['title'][:50]}...")

        # 1. ダウンロード
        print(f"    チャットダウンロード中...")
        try:
            filepath = download_live_chat(vid_id)
        except subprocess.TimeoutExpired:
            print(f"    → タイムアウト")
            progress.setdefault('failed', []).append(vid_id)
            save_progress(progress)
            continue

        if not filepath:
            print(f"    → チャットなし or エラー")
            progress.setdefault('failed', []).append(vid_id)
            save_progress(progress)
            time.sleep(sleep_sec)
            continue

        # 2. パース
        print(f"    パース中...")
        messages = parse_live_chat(filepath)
        print(f"    → {len(messages)} メッセージ")

        if not messages:
            progress.setdefault('failed', []).append(vid_id)
            save_progress(progress)
            time.sleep(sleep_sec)
            continue

        # 3. チャンクファイル保存
        chunk_file = os.path.join(CHUNKS_DIR, f"{vid_id}.json")
        with open(chunk_file, 'w', encoding='utf-8') as f:
            json.dump(messages, f, ensure_ascii=False, separators=(',', ':'))

        chunk_size = os.path.getsize(chunk_file)
        print(f"    → 保存: {chunk_size/1024:.0f} KB")

        # 4. 日付取得
        print(f"    日付取得中...")
        date_str = get_video_upload_date(vid_id)
        timestamp = 0
        if date_str:
            try:
                dt = datetime.strptime(date_str, '%Y/%m/%d')
                timestamp = int(dt.timestamp())
            except ValueError:
                pass
        print(f"    → 配信日: {date_str or '不明'}")

        # 5. エントリ作成
        new_entries.append({
            'id': vid_id,
            'title': video['title'],
            'duration': video.get('duration', 0),
            'count': len(messages),
            'date': date_str,
            'timestamp': timestamp,
        })

        progress.setdefault('completed', []).append(vid_id)
        save_progress(progress)

        # レート制限回避
        if i < total:
            time.sleep(sleep_sec)

    # インデックス更新（既存 + 新規をマージ）
    if new_entries:
        print(f"\n  インデックス更新中...")
        combined_index = update_index(existing_index, new_entries)

        with open(INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(combined_index, f, ensure_ascii=False, indent=2)

        print(f"  インデックス更新完了: {len(combined_index)}動画 (+{len(new_entries)}本)")

    # サマリー
    print(f"\n{'=' * 60}")
    print(f"  完了サマリー")
    print(f"{'=' * 60}")
    print(f"  新規収集: {len(new_entries)}本")
    print(f"  合計: {len(existing_ids) + len(new_entries)}本")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='ミミィチャット検索 データ収集')
    parser.add_argument('--limit', type=int, default=10,
                       help='処理する動画数の上限 (default: 10)')
    parser.add_argument('--sleep', type=int, default=5,
                       help='動画間のスリープ秒数 (default: 5)')
    args = parser.parse_args()

    collect_and_process(
        limit=args.limit,
        sleep_sec=args.sleep,
    )
