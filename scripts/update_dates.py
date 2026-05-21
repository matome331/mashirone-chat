import json
from datetime import datetime

dates_file = r'c:\Users\grave\yt-comments\video_dates_full.json'
index_file = r'site\data\index.json'

with open(dates_file, 'r', encoding='utf-8') as f:
    vid_dates = json.load(f)

with open(index_file, 'r', encoding='utf-8') as f:
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
# 同じ日付の場合は、既存の並び順（通常はduration等の降順）を維持
index_data.sort(key=lambda x: x['timestamp'], reverse=True)

# 一意なランクを付与（大きいほど新しい。これで動画が混ざるのを防ぐ）
for i, item in enumerate(index_data):
    item['rank'] = len(index_data) - i

with open(index_file, 'w', encoding='utf-8') as f:
    json.dump(index_data, f, ensure_ascii=False, indent=2)

print("Updated dates and added ranks successfully.")
