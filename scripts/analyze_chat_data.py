#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
yt-dlp ライブチャットデータ分析
ダウンロード済みのJSONLファイルをパースして構造・サイズを確認
"""

import json
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

CHAT_FILE = os.path.join(
    os.path.dirname(__file__), "test_output",
    "chat_EIVyL6x0bQo.live_chat.json"
)

def parse_live_chat_jsonl(filepath):
    """yt-dlpのlive_chat JSONL形式をパース"""
    messages = []
    skipped = 0
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            
            # replayChatItemAction -> actions -> addChatItemAction -> item
            replay = data.get('replayChatItemAction', {})
            offset_ms = int(replay.get('videoOffsetTimeMsec', 0))
            
            for action in replay.get('actions', []):
                add_action = action.get('addChatItemAction', {})
                item = add_action.get('item', {})
                
                # テキストメッセージを抽出
                renderer = item.get('liveChatTextMessageRenderer')
                if not renderer:
                    # スパチャ等の他の種類
                    if 'liveChatPaidMessageRenderer' in item:
                        renderer = item['liveChatPaidMessageRenderer']
                    elif 'liveChatMembershipItemRenderer' in item:
                        renderer = item['liveChatMembershipItemRenderer']
                    else:
                        continue
                
                # メッセージテキストを組み立て
                msg_runs = renderer.get('message', {}).get('runs', [])
                text_parts = []
                for run in msg_runs:
                    if 'text' in run:
                        text_parts.append(run['text'])
                    elif 'emoji' in run:
                        # カスタム絵文字はショートカット名を使用
                        emoji = run['emoji']
                        shortcuts = emoji.get('shortcuts', [])
                        if shortcuts:
                            text_parts.append(shortcuts[0])
                        else:
                            label = emoji.get('image', {}).get('accessibility', {}).get('accessibilityData', {}).get('label', '')
                            text_parts.append(f":{label}:" if label else "🔲")
                
                text = ''.join(text_parts).strip()
                if not text:
                    continue
                
                # 投稿者名
                author_name = renderer.get('authorName', {}).get('simpleText', '不明')
                
                messages.append({
                    'author': author_name,
                    'message': text,
                    'time_ms': offset_ms,
                    'time_sec': offset_ms / 1000,
                })
    
    return messages, skipped


def main():
    print("=" * 60)
    print("  ライブチャットデータ分析")
    print("=" * 60)
    
    if not os.path.exists(CHAT_FILE):
        print(f"ファイルが見つかりません: {CHAT_FILE}")
        return
    
    raw_size = os.path.getsize(CHAT_FILE)
    print(f"  ファイル: {os.path.basename(CHAT_FILE)}")
    print(f"  生ファイルサイズ: {raw_size:,} bytes ({raw_size/1024/1024:.2f} MB)")
    
    # 行数を数える
    with open(CHAT_FILE, 'r', encoding='utf-8') as f:
        line_count = sum(1 for _ in f)
    print(f"  行数: {line_count:,}")
    
    # パース
    print(f"\n  パース中...")
    messages, skipped = parse_live_chat_jsonl(CHAT_FILE)
    print(f"  抽出メッセージ: {len(messages):,}")
    print(f"  スキップ行: {skipped}")
    
    if not messages:
        print("メッセージが抽出できませんでした。")
        return
    
    # サンプル表示
    print(f"\n  最初の10件:")
    for msg in messages[:10]:
        t = msg['time_sec']
        mins = int(t // 60)
        secs = int(t % 60)
        print(f"    [{mins:02d}:{secs:02d}] {msg['author']}: {msg['message'][:50]}")
    
    print(f"\n  最後の5件:")
    for msg in messages[-5:]:
        t = msg['time_sec']
        mins = int(t // 60)
        secs = int(t % 60)
        print(f"    [{mins:02d}:{secs:02d}] {msg['author']}: {msg['message'][:50]}")
    
    # 投稿者統計
    author_counts = {}
    for msg in messages:
        a = msg['author']
        author_counts[a] = author_counts.get(a, 0) + 1
    
    print(f"\n  ユニーク投稿者数: {len(author_counts)}")
    top_authors = sorted(author_counts.items(), key=lambda x: -x[1])[:10]
    print(f"  上位投稿者:")
    for author, count in top_authors:
        print(f"    {author}: {count}件")
    
    # サイズ計算
    output_dir = os.path.join(os.path.dirname(__file__), "test_output")
    
    # フル版（投稿者付き）
    full = []
    for msg in messages:
        full.append({
            'a': msg['author'],
            'm': msg['message'],
            't': round(msg['time_sec']),
        })
    
    full_path = os.path.join(output_dir, "parsed_full.json")
    with open(full_path, 'w', encoding='utf-8') as f:
        json.dump(full, f, ensure_ascii=False, separators=(',', ':'))
    full_size = os.path.getsize(full_path)
    
    # テキストのみ（検索用に最小化）
    text_only = []
    for msg in messages:
        text_only.append({
            'm': msg['message'],
            't': round(msg['time_sec']),
        })
    
    text_path = os.path.join(output_dir, "parsed_textonly.json")
    with open(text_path, 'w', encoding='utf-8') as f:
        json.dump(text_only, f, ensure_ascii=False, separators=(',', ':'))
    text_size = os.path.getsize(text_path)
    
    print(f"\n{'=' * 60}")
    print(f"  サイズ比較 (この動画: 30分配信)")
    print(f"{'=' * 60}")
    print(f"  生データ (yt-dlp出力): {raw_size:,} B ({raw_size/1024:.0f} KB)")
    print(f"  投稿者付き最小化:     {full_size:,} B ({full_size/1024:.0f} KB)")
    print(f"  テキストのみ最小化:   {text_size:,} B ({text_size/1024:.0f} KB)")
    print(f"  圧縮率: {full_size/raw_size*100:.1f}% (投稿者付き)")
    
    # 全量見積もり
    # 750動画で、平均配信時間を推定
    # この動画は30分で {len(messages)} メッセージ
    # ミミィさんの平均配信時間は約4時間なので、約8倍
    avg_multiplier = 4 * 60 / 30  # 4時間 / 30分 = 8倍
    
    print(f"\n{'=' * 60}")
    print(f"  全量見積もり")
    print(f"{'=' * 60}")
    print(f"  この動画: 30分 / {len(messages)} メッセージ")
    print(f"  平均配信時間を4時間と仮定 (×{avg_multiplier:.0f})")
    
    est_msgs_per_video = len(messages) * avg_multiplier
    est_full_per_video = full_size * avg_multiplier
    est_text_per_video = text_size * avg_multiplier
    
    print(f"  推定メッセージ/動画: {est_msgs_per_video:.0f}")
    print(f"  推定サイズ/動画: {est_full_per_video/1024:.0f} KB (投稿者付き)")
    
    total_videos = 750
    total_full = est_full_per_video * total_videos
    total_text = est_text_per_video * total_videos
    total_raw = raw_size * avg_multiplier * total_videos
    
    print(f"\n  --- 全{total_videos}動画 ---")
    print(f"  生データ合計: {total_raw/1024/1024/1024:.2f} GB")
    print(f"  投稿者付き合計: {total_full/1024/1024/1024:.2f} GB")
    print(f"  テキストのみ合計: {total_text/1024/1024/1024:.2f} GB")
    
    # GitHub Pages制約との比較
    print(f"\n  --- GitHub Pages 制約チェック ---")
    gh_limit_gb = 1.0  # 推奨上限
    if total_full / 1024/1024/1024 > gh_limit_gb:
        print(f"  ⚠️ 投稿者付きデータは推奨上限({gh_limit_gb}GB)を超えます")
        # 何ヶ月分なら収まるか計算
        months_fit = gh_limit_gb / (total_full / 1024/1024/1024) * 30  # 約30ヶ月分ある想定
        print(f"     → 約{months_fit:.0f}ヶ月分なら収まります")
    else:
        print(f"  ✅ 推奨上限({gh_limit_gb}GB)内に収まります！")

if __name__ == '__main__':
    main()
