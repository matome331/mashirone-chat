#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
yt-dlp を使ったライブチャット取得テスト
yt-dlp は live_chat を字幕としてダウンロードできる
"""

import json
import sys
import os
import time
import subprocess
import glob

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "test_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# テスト動画 (比較的短いもの)
test_video = ["https://www.youtube.com/watch?v=EIVyL6x0bQo"]  # 30分 おはV朝活リレー

def download_live_chat(video_url, output_dir):
    """yt-dlpでライブチャットをJSON形式でダウンロード"""
    vid_id = video_url.split('v=')[1].split('&')[0]
    output_path = os.path.join(output_dir, f"chat_{vid_id}")
    
    cmd = [
        "yt-dlp",
        "--skip-download",        # 動画はDLしない
        "--write-subs",           # 字幕をダウンロード
        "--sub-langs", "live_chat",  # ライブチャットを対象
        "--sub-format", "json3",     # JSON形式
        "-o", output_path,
        video_url,
    ]
    
    print(f"  コマンド: {' '.join(cmd)}")
    print(f"  実行中...")
    
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    
    if result.returncode != 0:
        print(f"  エラー (exit {result.returncode}):")
        # stderr の最後の部分だけ表示
        stderr_lines = result.stderr.strip().split('\n')
        for line in stderr_lines[-10:]:
            print(f"    {line}")
        return None
    
    # 出力ファイルを探す
    pattern = os.path.join(output_dir, f"chat_{vid_id}*live_chat*")
    files = glob.glob(pattern)
    
    if not files:
        # 別パターンも試す
        pattern2 = os.path.join(output_dir, f"*{vid_id}*")
        files = glob.glob(pattern2)
    
    if files:
        print(f"  出力ファイル: {files[0]}")
        return files[0]
    else:
        print(f"  出力ファイルが見つかりません（パターン: {pattern}）")
        # output_dir の中身を表示
        all_files = os.listdir(output_dir)
        if all_files:
            print(f"  ディレクトリ内容: {all_files}")
        return None


def parse_live_chat_json(filepath):
    """yt-dlpのlive_chat JSON形式をパースしてメッセージリストに変換"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    messages = []
    
    # json3形式: eventsリストに格納
    events = data.get('events', [])
    
    for event in events:
        # segsにテキストが入っている
        segs = event.get('segs', [])
        if not segs:
            continue
        
        text = ''.join(seg.get('utf8', '') for seg in segs).strip()
        if not text:
            continue
        
        # タイムスタンプ (ミリ秒)
        start_ms = event.get('tStartMs', 0)
        
        msg = {
            'text': text,
            'time_ms': start_ms,
            'time_sec': start_ms / 1000,
        }
        messages.append(msg)
    
    return messages


def main():
    print("=" * 60)
    print("  yt-dlp ライブチャット取得テスト")
    print("=" * 60)
    
    # まずyt-dlpのバージョン確認
    ver = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True)
    print(f"  yt-dlp バージョン: {ver.stdout.strip()}")
    
    # まず動画情報だけ取得してライブチャットの有無を確認
    print(f"\n  動画: {test_video[0]}")
    print(f"  利用可能な字幕を確認中...")
    
    sub_check = subprocess.run(
        ["yt-dlp", "--list-subs", "--skip-download", test_video[0]],
        capture_output=True, text=True, encoding='utf-8'
    )
    
    # live_chatが含まれるか確認
    has_live_chat = 'live_chat' in sub_check.stdout
    print(f"  ライブチャットあり: {has_live_chat}")
    
    if not has_live_chat:
        print(f"\n  この動画にはライブチャットがありません。")
        print(f"  出力:")
        for line in sub_check.stdout.strip().split('\n')[-10:]:
            print(f"    {line}")
        
        # 別の動画で試す
        alt_videos = [
            "https://www.youtube.com/watch?v=nH6Wbr0QTu4",  # 雑談 6.7時間
            "https://www.youtube.com/watch?v=EvBQ16UxB9o",  # 朝活 3.4時間
            "https://www.youtube.com/watch?v=r6zN5P5eg0A",  # 雑談 4.3時間
        ]
        
        for alt_url in alt_videos:
            vid_id = alt_url.split('v=')[1].split('&')[0]
            print(f"\n  代替動画 {vid_id} を確認中...")
            alt_check = subprocess.run(
                ["yt-dlp", "--list-subs", "--skip-download", alt_url],
                capture_output=True, text=True, encoding='utf-8'
            )
            if 'live_chat' in alt_check.stdout:
                print(f"  → ライブチャットあり！ これを使います。")
                test_video[0] = alt_url
                has_live_chat = True
                break
            else:
                print(f"  → ライブチャットなし")
    
    if not has_live_chat:
        print("\nどの動画でもライブチャットが見つかりませんでした。")
        return
    
    # ダウンロード実行
    print(f"\n  チャットをダウンロード中...")
    filepath = download_live_chat(test_video[0], OUTPUT_DIR)
    
    if not filepath:
        print("ダウンロードに失敗しました。")
        return
    
    # ファイルサイズ
    file_size = os.path.getsize(filepath)
    print(f"\n  ファイルサイズ: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")
    
    # パースして中身を確認
    print(f"\n  JSONをパース中...")
    
    try:
        messages = parse_live_chat_json(filepath)
        print(f"  メッセージ数: {len(messages)}")
    except Exception as e:
        print(f"  パースエラー: {e}")
        # ファイルの先頭を確認
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read(2000)
        print(f"\n  ファイル先頭2000文字:")
        print(content[:2000])
        return
    
    # サンプル表示
    if messages:
        print(f"\n  最初の5件:")
        for msg in messages[:5]:
            t = msg['time_sec']
            mins = int(t // 60)
            secs = int(t % 60)
            print(f"    [{mins}:{secs:02d}] {msg['text'][:60]}")
        
        # 最小化サイズの計算
        slim = []
        for msg in messages:
            slim.append({
                'm': msg['text'],
                't': round(msg['time_sec']),
            })
        
        slim_path = os.path.join(OUTPUT_DIR, "slim_test.json")
        with open(slim_path, 'w', encoding='utf-8') as f:
            json.dump(slim, f, ensure_ascii=False, separators=(',', ':'))
        slim_size = os.path.getsize(slim_path)
        
        print(f"\n  サイズ比較:")
        print(f"    生データ: {file_size:,} bytes ({file_size/1024:.1f} KB)")
        print(f"    最小化: {slim_size:,} bytes ({slim_size/1024:.1f} KB)")
        
        print(f"\n  --- 全量見積もり (750動画) ---")
        print(f"    生データ推定: {file_size * 750 / 1024/1024/1024:.2f} GB")
        print(f"    最小化推定: {slim_size * 750 / 1024/1024/1024:.2f} GB")


if __name__ == '__main__':
    main()
