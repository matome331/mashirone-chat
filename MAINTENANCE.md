# コメントログ収集・メンテナンス

## 現在の正規ルート

YouTubeコメント/ライブチャットの取得は、GitHub ActionsではなくローカルPCで実行します。

通常更新:

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
3. 特定動画の再取得モード
4. 失敗動画・失敗理由を記録する台帳
5. Windowsでワンクリック実行できる更新バッチ
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
