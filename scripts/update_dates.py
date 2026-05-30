#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ミミィチャット検索 - 日付・ランク付与ユーティリティ
index.json に配信日、タイムスタンプ、ランクを追加する

使用法: python update_dates.py --dates-file <日付JSONファイル> --index-file <index.json>
"""

import json
import os
import argparse
from datetime import datetime

# パス設定（リポジトリルート基準）
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_INDEX = os.path.join(REPO_ROOT, "data", "index.json")


def main():
    parser = argparse.ArgumentParser(description='index.json に日付・ランクを付与')
    parser.add_argument('--dates-file', required=True,
                       help='動画日付データのJSONファイルパス')
    parser.add_argument('--index-file', default=DEFAULT_INDEX,
                       help='index.json のパス (default: data/index.json)')
    args = parser.parse_args()

    with open(args.dates_file, 'r', encoding='utf-8') as f:
        vid_dates = json.load(f)

    with open(args.index_file, 'r', encoding='utf-8') as f:
        index_data = json.load(f)

    for item in index_data:
        vid_id = item['id']
        date_str = vid_dates.get(vid_id, '')
        item['date'] = date_str

        if date_str:
            try:
                dt = datetime.strptime(date_str, '%Y/%m/%d')
                item['timestamp'] = int(dt.timestamp())
            except ValueError:
                item['timestamp'] = 0
        else:
            item['timestamp'] = 0

    # 新しい順にソート（タイムスタンプ降順）
    index_data.sort(key=lambda x: x['timestamp'], reverse=True)

    # 一意なランクを付与（大きいほど新しい）
    for i, item in enumerate(index_data):
        item['rank'] = len(index_data) - i

    with open(args.index_file, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    print("Updated dates and added ranks successfully.")


if __name__ == '__main__':
    main()
