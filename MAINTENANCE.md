# コメントログ収集・メンテナンス

## 現在の正規ルート

YouTubeコメント/ライブチャットの取得は、GitHub ActionsではなくローカルPCで実行します。

通常はリポジトリ直下の `update_chat.bat` をダブルクリックして実行します。

メニュー:

1. 通常更新
2. 全件棚卸し
3. 1配信だけ再取得
4. 失敗動画台帳を見る
5. 終了

バッチを使わずコマンドで通常更新する場合:

```bat
python scripts\collect_chats.py --limit 10 --sleep 5
```

通常更新では `/streams` と `/videos` の各タブ最新100件だけ確認し、
`data/index.json` にまだ存在しない動画IDだけを収集対象にします。

古い取りこぼしを含めて全件確認したい場合:

```bat
python scripts\collect_chats.py --full-scan --limit 0 --sleep 5
```

一覧確認件数を変えたい場合:

```bat
python scripts\collect_chats.py --scan-limit 200
```

特定の1配信だけ再取得したい場合:

```bat
python scripts\collect_chats.py --video "https://www.youtube.com/watch?v=XXXXXXXXXXX"
```

動画IDだけでも指定できます。

```bat
python scripts\collect_chats.py --video XXXXXXXXXXX
```

単一動画モードは通常の取得済み判定や直近スキップを無視して、その動画だけを再取得します。
再取得・パースに失敗した場合は既存のchunk/indexを変更しません。

GitHub Pagesの公開処理はそのまま利用します。

## GitHub Actionsでのyt-dlp自動収集をやめる理由

GitHub-hosted runner上では、YouTube側のbot判定・共有データセンターIP・取得制限の影響で、yt-dlpによるライブチャット取得が安定しません。

2026-08-24 / 08-31 / 09-07 / 09-14 の Weekly Chat Collection は、ワークフロー自体は成功扱いでしたが、確認できた新規候補をすべて「チャットなし or エラー」としてスキップし、新規収集は0本でした。

2026-09-01 の Monthly Archive Check でも、753本中752本が「チェック不能」でした。

このため、以下のGitHub Actionsは廃止します。

- Weekly Chat Collection
- Monthly Archive Check

## 現在のデータ状態

健康診断時点:

- `data/index.json`: 763動画
- `data/chunks/`: 763ファイル
- indexにあるのにchunkがない動画: 0
- indexにない孤立chunk: 0
- 重複動画ID: 0

`data/index.json` の動画IDが、現状の「取得済み配信」の判定に使われています。

## 現在分かっている改善点

今後は順番に以下を整備します。

1. 取得済み判定を明文化・安定化 — 完了
2. 新規配信だけを差分収集する更新モード — 完了
3. 特定動画の再取得モード — 完了
4. 失敗動画・失敗理由を記録する台帳 — 完了
5. Windowsでワンクリック実行できる更新バッチ — 完了
6. 取得後のデータ健康診断

## 取得済み判定

収集済み判定の正本は `data/index.json` です。

- indexに動画IDがある → 取得済み
- indexに動画IDがない → 新規候補
- `data/chunks/<video_id>.json` は実際の検索用チャットデータ

通常更新ではこの判定だけで差分収集します。
古い未取得動画を探すときだけ `--full-scan` を使います。

## エラー時の扱い

チャンネル一覧のyt-dlp取得自体に失敗した場合は、更新処理をエラー終了します。
「一覧取得失敗」を「新しい動画なし」と誤判定しません。

## 特定動画の再取得

`--video` は次の形式を受け付けます。

- 11文字のYouTube動画ID
- `youtube.com/watch?v=...`
- `youtu.be/...`
- `youtube.com/live/...`
- `youtube.com/shorts/...`
- `youtube.com/embed/...`

再取得時は:

1. 動画メタデータを取得
2. 既存rawを残したまま一時rawへチャットを再取得
3. 1件以上のメッセージをパースできたことを確認
4. chunk/indexを一時ファイルへ生成
5. 既存chunk/indexをバックアップして差し替え
6. 正常完了後だけrawも新しいデータへ差し替え
7. 途中で失敗した場合はchunk/indexを元に戻す

既存indexにない動画を指定した場合は、取得成功時に新規動画としてindexへ追加されます。

## 失敗動画台帳

収集に失敗した動画は `scripts/collection_failures.json` に記録します。

記録内容:

- 動画ID
- タイトル
- 失敗種別
- エラー詳細（最大1000文字）
- 試行回数
- 初回失敗時刻
- 最終失敗時刻

主な失敗種別:

- `timeout` — yt-dlp取得タイムアウト
- `youtube_access_blocked` — bot判定 / PO Token / 403 / 429など
- `chat_replay_unavailable` — ライブチャットリプレイなし
- `private_or_members_only` — 非公開・メンバー限定
- `video_unavailable` — 削除・利用不可
- `empty_parse` — rawは取れたがメッセージ0件
- `yt_dlp_error` — その他のyt-dlpエラー

台帳だけ確認する場合:

```bat
python scripts\collect_chats.py --show-failures
```

同じ動画が再び失敗した場合は `attempts` を加算します。
通常収集または `--video` 再取得で成功した動画は、失敗台帳から自動的に削除します。

直近配信をチャットリプレイ待ちで保留しただけの場合や、
`EXCLUDED_IDS` / メン限タイトル判定で意図的に除外した動画は失敗台帳へ入れません。

## Windows更新バッチ

リポジトリ直下の `update_chat.bat` をダブルクリックすると更新メニューを開きます。

起動時に:

- Python 3 が利用可能か確認
- `yt-dlp` Pythonモジュールが利用可能か確認
- yt-dlpが無い場合は、確認後に `pip install -U yt-dlp` を実行可能

収集スクリプトは `yt-dlp.exe` のPATHに依存せず、現在使用中のPythonから
`python -m yt_dlp` として実行します。

通常更新は最大10本を収集します。
全件棚卸しは時間がかかるため、バッチ内で実行確認を挟みます。

## デスクトップショートカット

Windowsでは、リポジトリ直下の `create_desktop_shortcut.bat` を1回だけダブルクリックすると、
現在のユーザーのデスクトップに「ミミィチャット検索 更新」ショートカットを作成します。

ショートカットのリンク先は同じフォルダの `update_chat.bat` です。
リポジトリの保存場所を移動した場合は、`create_desktop_shortcut.bat` をもう一度実行してください。
