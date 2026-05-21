#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ミミィチャット検索 - データ収集パイプライン
yt-dlp を使って YouTube ライブチャットを収集・パースし、検索用JSONを生成する
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

# パス設定
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(PROJECT_ROOT, "raw_chats")       # yt-dlp生データ
DATA_DIR = os.path.join(PROJECT_ROOT, "site", "data")    # サイト用JSON
PROGRESS_FILE = os.path.join(PROJECT_ROOT, "progress.json")

# チャンネル情報
CHANNEL_URL = "https://www.youtube.com/@mashironemimiy"

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"completed": [], "failed": [], "video_list": []}


def save_progress(progress):
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def get_video_list(channel_url=None, from_file=None, limit=None):
    """チャンネルの動画一覧を取得（既存リストファイルまたはyt-dlpで取得）"""
    
    if from_file and os.path.exists(from_file):
        print(f"  既存リストから読み込み: {from_file}")
        with open(from_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        videos = []
        for vid_id, info in data.items():
            dur = info.get('duration')
            if dur and dur > 300:  # 5分以上の動画のみ（短尺動画を除外）
                videos.append({
                    'id': vid_id,
                    'title': info.get('title', ''),
                    'duration': dur,
                })
        
        # 長い配信から優先（チャットが多い順に処理）
        videos.sort(key=lambda x: x['duration'], reverse=True)
        
        if limit:
            videos = videos[:limit]
        
        print(f"  対象動画: {len(videos)}本")
        return videos
    
    # yt-dlpでリスト取得
    print(f"  チャンネルから動画リスト取得中...")
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--print", "%(id)s\t%(title)s\t%(duration)s",
        channel_url + "/videos",
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    videos = []
    for line in result.stdout.strip().split('\n'):
        parts = line.split('\t')
        if len(parts) >= 3:
            vid_id, title, duration_str = parts[0], parts[1], parts[2]
            try:
                duration = float(duration_str) if duration_str != 'NA' else 0
            except ValueError:
                duration = 0
            
            if duration > 300:
                videos.append({
                    'id': vid_id,
                    'title': title,
                    'duration': duration,
                })
    
    if limit:
        videos = videos[:limit]
    
    print(f"  取得動画: {len(videos)}本")
    return videos


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
    
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                          timeout=120)
    
    if result.returncode != 0:
        return None
    
    # 出力ファイルを探す
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
                
                # テキスト組み立て
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
                    't': round(offset_ms / 1000),  # 秒単位
                })
    
    return messages


def build_site_data(videos, progress):
    """全動画のチャットデータをサイト用JSONに変換"""
    
    index = []  # 動画インデックス
    
    for video in videos:
        vid_id = video['id']
        if vid_id not in progress['completed']:
            continue
        
        # パース済みデータを読み込み
        chunk_file = os.path.join(DATA_DIR, "chunks", f"{vid_id}.json")
        if not os.path.exists(chunk_file):
            continue
        
        with open(chunk_file, 'r', encoding='utf-8') as f:
            messages = json.load(f)
        
        index.append({
            'id': vid_id,
            'title': video['title'],
            'duration': video.get('duration', 0),
            'count': len(messages),
        })
    
    # インデックスを保存
    index_file = os.path.join(DATA_DIR, "index.json")
    with open(index_file, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    
    print(f"  インデックス生成: {len(index)}動画")
    return index


def collect_and_process(video_list_file=None, limit=5, sleep_sec=3):
    """メインの収集・処理パイプライン"""
    
    print("=" * 60)
    print("  ミミィチャット検索 - データ収集パイプライン")
    print("=" * 60)
    
    progress = load_progress()
    
    # 動画リスト取得
    videos = get_video_list(
        channel_url=CHANNEL_URL,
        from_file=video_list_file,
        limit=limit
    )
    progress['video_list'] = [v['id'] for v in videos]
    save_progress(progress)
    
    # チャンクディレクトリ作成
    chunks_dir = os.path.join(DATA_DIR, "chunks")
    os.makedirs(chunks_dir, exist_ok=True)
    
    # 各動画を処理
    total = len(videos)
    for i, video in enumerate(videos, 1):
        vid_id = video['id']
        
        if vid_id in progress['completed']:
            print(f"  [{i}/{total}] {vid_id} - スキップ（処理済み）")
            continue
        
        if vid_id in progress['failed']:
            print(f"  [{i}/{total}] {vid_id} - スキップ（前回失敗）")
            continue
        
        print(f"\n  [{i}/{total}] {vid_id}: {video['title'][:40]}...")
        
        # 1. ダウンロード
        print(f"    チャットダウンロード中...")
        try:
            filepath = download_live_chat(vid_id)
        except subprocess.TimeoutExpired:
            print(f"    → タイムアウト")
            progress['failed'].append(vid_id)
            save_progress(progress)
            continue
        
        if not filepath:
            print(f"    → チャットなし or エラー")
            progress['failed'].append(vid_id)
            save_progress(progress)
            time.sleep(sleep_sec)
            continue
        
        # 2. パース
        print(f"    パース中...")
        messages = parse_live_chat(filepath)
        print(f"    → {len(messages)} メッセージ")
        
        if not messages:
            progress['failed'].append(vid_id)
            save_progress(progress)
            time.sleep(sleep_sec)
            continue
        
        # 3. チャンクファイル保存
        chunk_file = os.path.join(chunks_dir, f"{vid_id}.json")
        with open(chunk_file, 'w', encoding='utf-8') as f:
            json.dump(messages, f, ensure_ascii=False, separators=(',', ':'))
        
        chunk_size = os.path.getsize(chunk_file)
        print(f"    → 保存: {chunk_size/1024:.0f} KB")
        
        # 4. 進捗更新
        progress['completed'].append(vid_id)
        save_progress(progress)
        
        # レート制限回避
        if i < total:
            time.sleep(sleep_sec)
    
    # インデックス生成
    print(f"\n  インデックス生成中...")
    index = build_site_data(videos, progress)
    
    # サマリー
    print(f"\n{'=' * 60}")
    print(f"  完了サマリー")
    print(f"{'=' * 60}")
    print(f"  処理済み: {len(progress['completed'])}本")
    print(f"  失敗: {len(progress['failed'])}本")
    
    total_size = 0
    for f in glob.glob(os.path.join(chunks_dir, "*.json")):
        total_size += os.path.getsize(f)
    print(f"  チャンクデータ合計: {total_size/1024/1024:.2f} MB")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='ミミィチャット検索 データ収集')
    parser.add_argument('--from-file', default=r'c:\Users\grave\yt-comments\channel_video_list.json',
                       help='既存の動画リストファイル')
    parser.add_argument('--limit', type=int, default=5,
                       help='処理する動画数の上限')
    parser.add_argument('--sleep', type=int, default=3,
                       help='動画間のスリープ秒数')
    args = parser.parse_args()
    
    collect_and_process(
        video_list_file=args.from_file,
        limit=args.limit,
        sleep_sec=args.sleep,
    )
