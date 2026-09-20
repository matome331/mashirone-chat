# コメントログ収集・メンテナンス

## 現在の正規ルート

YouTubeコメント/ライブチャットの取得は、GitHub ActionsではなくローカルPCで実行します。

通常はリポジトリ直下の `launch_update_chat_gui.bat` をダブルクリックしてGUIを起動します。

GUI機能:

- 通常更新
- 全件棚卸し
- 1配信だけ再取得（URL / 動画ID入力）
- 失敗動画台帳の表示
- データ健康診断
- GitHubへ公開（公開データだけcommit/push）
- 全件公開状態チェック
- 実行ログの画面内表示
- 実行中の停止

従来の `update_chat.bat` も非常用・トラブル時用として残します。

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
6. 取得後のデータ健康診断 — 完了

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

## Windows GUI更新ツール

リポジトリ直下の `launch_update_chat_gui.bat` をダブルクリックすると
Tkinter製の更新GUIを起動します。

GUI本体は `update_chat_gui.py` です。
既存の `scripts/collect_chats.py` / `scripts/health_check.py` を子プロセスとして呼ぶため、
収集ロジックをGUI側へ重複実装していません。

通常更新・全件棚卸し・1配信だけ再取得が成功した場合は、自動で健康診断まで実行します。
取得成功後は「完了（未公開）」と表示されます。サイトへ反映するには「GitHubへ公開」を実行します。
処理中の標準出力・エラー出力はGUI内のログ欄へ表示します。

Tkinterが利用できない環境やGUI側のトラブル時は、従来の `update_chat.bat` を利用できます。

## Windows更新バッチ（非常用）

リポジトリ直下の `update_chat.bat` をダブルクリックすると従来のコンソールメニューを開きます。

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

ショートカットのリンク先は同じフォルダの `launch_update_chat_gui.bat` です。
リポジトリの保存場所を移動した場合は、`create_desktop_shortcut.bat` をもう一度実行してください。

## データ健康診断

ローカルで手動実行:

```bat
python scripts\health_check.py
```

`update_chat.bat` では、通常更新・全件棚卸し・1配信だけ再取得が成功した直後に
自動で健康診断を実行します。メニューの「データ健康診断」から単独実行もできます。

主なチェック項目:

- `data/index.json` が正しいJSON配列か
- 動画IDの形式と重複
- title / duration / count / date / timestamp / rank の基本形式
- indexにある動画のchunkが存在するか
- indexにない孤立chunkがないか
- chunkが正しいJSON配列か
- indexの `count` とchunkの実メッセージ数が一致するか
- 各メッセージの `a` / `m` / `t` 形式
- 0件chunkがないか
- `scripts/collection_failures.json` の形式

エラーが1件でもあれば終了コード1、問題なければ0です。
durationを大きく超えるチャット時刻など、即破損とは断定できないものはwarning扱いにします。

## GitHub Actionsでの健康診断

`.github/workflows/health-check.yml` はPR、mainへのpush、手動実行で動きます。

このActionはYouTubeやyt-dlpへアクセスしません。
リポジトリ内のデータ整合性とPython構文だけを確認します。
`update_chat_gui.py` の構文もチェック対象です。

## GitHub Pagesへの公開

ローカル収集したデータは、取得しただけではGitHub Pagesへ反映されません。

GUIの「GitHubへ公開」は `scripts/publish_data.py` を実行し、次の公開データだけを
commit / pushします。

- `data/index.json`
- `data/chunks/`

`scripts/collection_failures.json` や、その他のコード・設定ファイルは自動公開しません。

公開前には次を確認します。

- データ健康診断がOK
- 現在のブランチが `main`
- `origin/main` よりローカルが古くない
- 公開対象外のファイルがstageされていない
- 未pushのcommitがある場合、その変更が公開データだけである

安全確認に失敗した場合はcommit / pushせず中止します。

コマンド単体でも実行できます。

```bat
python scripts\publish_data.py
```

## 公開サイトのデータキャッシュ

固定の `?v=13` は廃止しました。

- `data/index.json` は `cache: no-store` で毎回最新版を取得
- chunkは `cache: no-cache` でブラウザキャッシュを再検証

これにより、公開後に古いindex/chunkを掴み続ける問題を避けつつ、
全chunkを無条件に毎回再ダウンロードする方式にはしていません。

## 全件公開状態チェック

GUIの「全件公開状態チェック」は、`data/index.json` に登録済みの全配信について
現在もYouTubeで確認できるかをローカルPCから順番に確認します。

想定用途は3〜6か月に1回程度の手動メンテナンスです。

分類:

- 公開中 — public / unlisted
- 非公開候補 — private / members-only / 明示的な削除メッセージなど
- 確認不能 — bot判定、403/429、タイムアウト、通信エラー、曖昧なエラー

重要:

- 非公開候補を見つけても `index.json` / chunk は自動削除しません
- bot判定や通信エラーを「非公開」とは扱いません
- 動画間は標準2秒待機します
- 途中経過は `scripts/archive_check_state.json` にローカル保存します
- 途中停止した場合、次回同じボタンから続きへ再開します
- 全件完了後にもう一度実行すると、新しい全件チェックとして最初から確認します
- 結果は `scripts/archive_check_report.json` にローカル保存します
- state/reportはGit管理対象外です

確認不能が8本連続した場合は、YouTube側の一時制限の可能性を考えて自動停止します。
その8本は未確認へ戻すため、時間を空けて再実行するとそこから再試行できます。

コマンドから実行する場合:

```bat
python scripts\check_archives.py --sleep 2
```

途中結果を無視して最初からやり直す場合:

```bat
python scripts\check_archives.py --restart --sleep 2
```

## 承認済み非公開動画の共通除外

公開検索から外す動画IDの正本は、リポジトリ直下の `excluded_videos.txt` です。

方針:

- 元の `data/index.json` / `data/chunks/` は削除しない
- サイト起動時に `excluded_videos.txt` を読み、該当動画を検索対象から外す
- 除外解除はリストから動画IDを外すだけで復帰可能
- `excluded_videos.txt` は「GitHubへ公開」の対象に含める
- 誤読まとめ側も同じ動画IDリストを参照する

標準運用:

1. GUIで「全件公開状態チェック」
2. 非公開候補をこのChatで確認
3. 明確に非公開・削除・検索除外対象と確認できたIDだけ承認
4. 承認済みIDを `excluded_videos.txt` へ追加
5. 「GitHubへ公開」
6. チャット検索と誤読まとめの両方から検索対象外になることを確認

ローカルで承認済みIDを追加する場合:

```bat
python scripts\exclude_video.py VIDEO_ID --reason "非公開化をChatで確認"
```

YouTube URLも指定できます。

この操作はindex/chunkを削除しません。
