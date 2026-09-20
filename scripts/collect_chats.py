#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ミミィチャット検索 - データ収集パイプライン
yt-dlp を使って YouTube ライブチャットを収集・パースし、検索用JSONを生成する

ローカル実行専用。
GitHub-hosted Actions では YouTube / yt-dlp の取得が安定しないため、収集はPC上で実行する。
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
DEFAULT_SCAN_LIMIT = 100
DEFAULT_SKIP_RECENT = 3

# チャンネル情報
CHANNEL_URL = "https://www.youtube.com/@mashi_rone"

# 除外リスト（チャットリプレイなし・データ不備等、収集対象から除外する動画ID）
EXCLUDED_IDS = {
    "cI8yaCSXOEU",  # ノロイヅキ - チャットリプレイなし
    "TNIS-orv9TM",  # 朝活(2025/02/24) - チャットリプレイなし
    "bB727Jk2cfU",  # 復帰最初の朝活(2025/02/23) - チャットリプレイなし
    "lbFl-iYnQSY",  # バレンタイン(2025/02/14) - チャットリプレイなし
    "Eas56ISi4YI",  # メンシ1周年(2025/02/12) - チャットリプレイなし
    "ylu_xCKvd4Y",  # 朝活(2025/02/02) - チャットリプレイなし
    "9IvnmocUM6I",  # ワンちゃんお別れ - 実質メン限
    "OLpbjKJTFXw",  # Re≒Connect(2024/05/26) - チャットリプレイなし
    "D8n7BX8rMhA",  # バーチャル物産展(2024/04/05) - チャットリプレイなし
    "WL43rULdieQ",  # 朝活(2025/09/30) - 非公開化(2026-09-01確認)
}

# メンバー限定配信のタイトルキーワード（チャット取得不可のため除外）
MEMBERS_ONLY_KEYWORDS = ["メン限", "Members Only", "members only", "Member Only", "member only"]

def is_members_only(title):
    """タイトルからメンバー限定配信かどうか判定"""
    return any(kw in title for kw in MEMBERS_ONLY_KEYWORDS)

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(CHUNKS_DIR, exist_ok=True)


def load_existing_index():
    """既存の index.json を読み込み、処理済み動画IDのセットを返す"""
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, 'r', encoding='utf-8') as f:
            index = json.load(f)
        return {entry['id'] for entry in index}, index
    return set(), []


def get_video_list_from_channel(scan_limit=DEFAULT_SCAN_LIMIT):
    """yt-dlp でチャンネルの動画一覧を取得（ライブ配信 + 通常動画）。

    scan_limit=None のときだけ全件取得する。通常更新では最新側だけ確認する。
    """
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
        ]
        if scan_limit is not None:
            cmd.extend(["--playlist-end", str(scan_limit)])
        cmd.append(CHANNEL_URL + tab)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace',
                                    timeout=300, env=_utf8_env())
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"{tab} の動画一覧取得がタイムアウトしました") from exc

        if result.returncode != 0:
            stderr_tail = "\n".join(result.stderr.strip().splitlines()[-8:])
            raise RuntimeError(
                f"{tab} の動画一覧取得に失敗しました (exit {result.returncode})"
                + (f"\n{stderr_tail}" if stderr_tail else "")
            )

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


def normalize_video_id(value):
    """YouTube URL または11文字の動画IDから動画IDを取り出す。"""
    value = value.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
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

    raise ValueError(f"YouTube動画IDを取得できません: {value}")


def get_video_metadata(video_id):
    """単一動画のタイトル・長さ・配信日をyt-dlpから取得する。"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--encoding", "utf-8",
        "--print", "%(id)s",
        "--print", "%(title)s",
        "--print", "%(duration)s",
        "--print", "%(upload_date)s",
        url,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=60,
            env=_utf8_env(),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"動画情報の取得がタイムアウトしました: {video_id}") from exc

    if result.returncode != 0:
        stderr_tail = "\n".join(result.stderr.strip().splitlines()[-8:])
        raise RuntimeError(
            f"動画情報の取得に失敗しました: {video_id}"
            + (f"\n{stderr_tail}" if stderr_tail else "")
        )

    lines = result.stdout.splitlines()
    if len(lines) < 4:
        raise RuntimeError(f"動画情報を解析できませんでした: {video_id}")

    resolved_id, title, duration_raw, upload_date_raw = lines[-4:]
    if resolved_id != video_id:
        video_id = resolved_id

    try:
        duration = float(duration_raw) if duration_raw != 'NA' else 0
    except ValueError:
        duration = 0

    date_str = ""
    if re.fullmatch(r"\d{8}", upload_date_raw):
        date_str = (
            f"{upload_date_raw[:4]}/{upload_date_raw[4:6]}/{upload_date_raw[6:8]}"
        )

    return {
        "id": video_id,
        "title": title,
        "duration": duration,
        "date": date_str,
    }


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


def download_live_chat(video_id, force=False):
    """1つの動画のライブチャットをダウンロード。

    force=True の場合は既存rawを残したまま一時ファイルへ再取得し、
    呼び出し側が内容確認後に差し替えられるようにする。
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    existing = glob.glob(os.path.join(RAW_DIR, f"chat_{video_id}*live_chat*"))

    if existing and not force:
        return existing[0]

    if force:
        output_path = os.path.join(
            RAW_DIR,
            f"chat_{video_id}_refresh_{time.time_ns()}",
        )
    else:
        output_path = os.path.join(RAW_DIR, f"chat_{video_id}")

    cmd = [
        "yt-dlp",
        "--skip-download",
        "--write-subs",
        "--sub-langs", "live_chat",
        "-o", output_path,
        url,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding='utf-8', errors='replace',
                            timeout=180, env=_utf8_env())

    # yt-dlp は DL 成功でも returncode!=0 を返す場合があるため、
    # 実ファイルの存在で成否を判定する。
    if force:
        files = glob.glob(output_path + "*live_chat*")
    else:
        files = glob.glob(os.path.join(RAW_DIR, f"chat_{video_id}*live_chat*"))

    if files:
        return files[0]

    if result.stderr.strip():
        stderr_tail = "\n".join(result.stderr.strip().splitlines()[-8:])
        print(f"    yt-dlp: {stderr_tail}")
    return None


def promote_raw_chat(video_id, refreshed_path):
    """検証済みの再取得rawを正式なrawファイルへ差し替える。"""
    canonical_path = os.path.join(RAW_DIR, f"chat_{video_id}.live_chat.json")

    # 先に新しいrawをatomic replaceし、成功後に古い別名rawを掃除する。
    # replaceに失敗した場合は既存rawを消さない。
    os.replace(refreshed_path, canonical_path)

    old_files = glob.glob(os.path.join(RAW_DIR, f"chat_{video_id}*live_chat*"))
    for old_path in old_files:
        if os.path.abspath(old_path) == os.path.abspath(canonical_path):
            continue
        try:
            os.remove(old_path)
        except FileNotFoundError:
            pass

    return canonical_path


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


def recollect_single_video(video_ref):
    """指定した1動画だけライブチャットを再取得して安全に差し替える。"""
    video_id = normalize_video_id(video_ref)
    print("=" * 60)
    print("  ミミィチャット検索 - 単一動画再取得")
    print("=" * 60)
    print(f"  対象動画ID: {video_id}")

    _, existing_index = load_existing_index()
    existing_entry = next(
        (entry for entry in existing_index if entry.get('id') == video_id),
        None,
    )

    metadata = get_video_metadata(video_id)
    title = metadata.get('title') or (
        existing_entry.get('title', '') if existing_entry else ''
    )
    duration = metadata.get('duration') or (
        existing_entry.get('duration', 0) if existing_entry else 0
    )
    date_str = metadata.get('date') or (
        existing_entry.get('date', '') if existing_entry else ''
    )

    print(f"  タイトル: {title}")
    print(f"  既存登録: {'あり' if existing_entry else 'なし'}")
    if existing_entry:
        print(f"  既存メッセージ数: {existing_entry.get('count', 0)}")

    print("  ライブチャットを再ダウンロード中...")
    refreshed_path = None
    try:
        refreshed_path = download_live_chat(video_id, force=True)
        if not refreshed_path:
            raise RuntimeError(
                "ライブチャットを再取得できませんでした。"
                "既存のchunk/indexは変更していません。"
            )

        messages = parse_live_chat(refreshed_path)
        print(f"  再取得メッセージ数: {len(messages)}")
        if not messages:
            raise RuntimeError(
                "再取得データからメッセージを抽出できませんでした。"
                "既存のchunk/indexは変更していません。"
            )

        timestamp = 0
        if date_str:
            try:
                dt = datetime.strptime(date_str, '%Y/%m/%d')
                timestamp = int(dt.timestamp())
            except ValueError:
                pass
        elif existing_entry:
            timestamp = existing_entry.get('timestamp', 0)

        new_entry = {
            'id': video_id,
            'title': title,
            'duration': duration,
            'count': len(messages),
            'date': date_str,
            'timestamp': timestamp,
        }

        # chunk / index は両方を一時ファイルへ書いた後、バックアップを
        # 作って差し替える。途中失敗時は元ファイルへロールバックする。
        chunk_file = os.path.join(CHUNKS_DIR, f"{video_id}.json")
        chunk_tmp = chunk_file + ".tmp"
        index_tmp = INDEX_FILE + ".tmp"
        chunk_backup = chunk_file + ".recollect.bak"
        index_backup = INDEX_FILE + ".recollect.bak"

        with open(chunk_tmp, 'w', encoding='utf-8') as f:
            json.dump(messages, f, ensure_ascii=False, separators=(',', ':'))

        combined_index = update_index(existing_index, [new_entry])
        with open(index_tmp, 'w', encoding='utf-8') as f:
            json.dump(combined_index, f, ensure_ascii=False, indent=2)

        for backup in (chunk_backup, index_backup):
            if os.path.exists(backup):
                os.remove(backup)

        had_chunk = os.path.exists(chunk_file)
        if had_chunk:
            os.replace(chunk_file, chunk_backup)
        os.replace(INDEX_FILE, index_backup)

        try:
            os.replace(chunk_tmp, chunk_file)
            os.replace(index_tmp, INDEX_FILE)
            promote_raw_chat(video_id, refreshed_path)
            refreshed_path = None
        except Exception:
            if os.path.exists(chunk_file):
                os.remove(chunk_file)
            if had_chunk and os.path.exists(chunk_backup):
                os.replace(chunk_backup, chunk_file)

            if os.path.exists(INDEX_FILE):
                os.remove(INDEX_FILE)
            if os.path.exists(index_backup):
                os.replace(index_backup, INDEX_FILE)
            raise
        else:
            for backup in (chunk_backup, index_backup):
                if os.path.exists(backup):
                    os.remove(backup)

        print("  ✅ 再取得完了")
        print(f"  chunk: data/chunks/{video_id}.json")
        print(f"  index: {len(combined_index)}動画")
    finally:
        # 検証前に失敗した一時rawは消し、既存rawを残す。
        if refreshed_path and os.path.exists(refreshed_path):
            try:
                os.remove(refreshed_path)
            except OSError:
                pass


def collect_and_process(
    limit=10,
    sleep_sec=5,
    scan_limit=DEFAULT_SCAN_LIMIT,
    full_scan=False,
    skip_recent=DEFAULT_SKIP_RECENT,
):
    """メインの収集・処理パイプライン（差分収集）"""

    print("=" * 60)
    print("  ミミィチャット検索 - データ収集パイプライン")
    print("=" * 60)

    # 既存データ読み込み
    existing_ids, existing_index = load_existing_index()
    print(f"  既存データ: {len(existing_ids)}本")

    # チャンネルから動画リスト取得
    effective_scan_limit = None if full_scan else scan_limit
    if full_scan:
        print("  一覧走査: 全件モード")
    else:
        print(f"  一覧走査: 各タブ最新{scan_limit}件まで")
    all_videos = get_video_list_from_channel(scan_limit=effective_scan_limit)

    # 未処理の動画だけフィルタリング（除外リスト・メン限も除外）
    new_videos = [v for v in all_videos
                  if v['id'] not in existing_ids
                  and v['id'] not in EXCLUDED_IDS
                  and not is_members_only(v.get('title', ''))]

    if not new_videos:
        print("  新しい動画はありません。")
        return

    # 最新の数本はチャットリプレイが未生成の可能性があるためスキップ
    # (yt-dlp は新しい順で返すので、先頭が最新)
    if skip_recent > 0 and new_videos:
        skip_count = min(skip_recent, len(new_videos))
        new_videos = new_videos[skip_count:]
        print(
            f"  直近{skip_count}本はスキップ"
            "（チャットリプレイ未生成の可能性）"
        )

    if not new_videos:
        print("  収集対象はありません（直近スキップ分のみ）。")
        return

    print(f"  新規収集対象: {len(new_videos)}本（成功{limit}本で終了）")

    new_entries = []
    collected = 0  # 成功カウント
    total = len(new_videos)

    for i, video in enumerate(new_videos, 1):
        # limit は成功数でカウント（失敗はカウントしない）
        if limit and collected >= limit:
            print(f"\n  収集上限{limit}本に到達、終了")
            break

        vid_id = video['id']
        print(f"\n  [{i}/{total}] {vid_id}: {video['title'][:50]}...")

        # 1. ダウンロード
        print(f"    チャットダウンロード中...")
        try:
            filepath = download_live_chat(vid_id)
        except subprocess.TimeoutExpired:
            print(f"    → タイムアウト（スキップ）")
            time.sleep(sleep_sec)
            continue

        if not filepath:
            print(f"    → チャットなし or エラー（スキップ）")
            time.sleep(sleep_sec)
            continue

        # 2. パース
        print(f"    パース中...")
        messages = parse_live_chat(filepath)
        print(f"    → {len(messages)} メッセージ")

        if not messages:
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

        collected += 1

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
    parser.add_argument('--scan-limit', type=int, default=DEFAULT_SCAN_LIMIT,
                       help=f'通常更新で各タブの最新何件を見るか (default: {DEFAULT_SCAN_LIMIT})')
    parser.add_argument('--full-scan', action='store_true',
                       help='復旧・棚卸し用。チャンネル一覧を全件確認する')
    parser.add_argument('--skip-recent', type=int, default=DEFAULT_SKIP_RECENT,
                       help=f'チャットリプレイ待ちで直近何本を保留するか (default: {DEFAULT_SKIP_RECENT})')
    parser.add_argument('--video',
                       help='指定したYouTube URLまたは動画IDだけを再取得する')
    args = parser.parse_args()

    if args.video:
        recollect_single_video(args.video)
    else:
        collect_and_process(
            limit=args.limit,
            sleep_sec=args.sleep,
            scan_limit=args.scan_limit,
            full_scan=args.full_scan,
            skip_recent=args.skip_recent,
        )
