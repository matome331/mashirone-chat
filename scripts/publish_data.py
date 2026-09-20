#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ローカルで取得したチャットデータだけを安全にGitHubへ公開する。

対象:
- data/index.json
- data/chunks/
- scripts/collection_failures.json

それ以外の変更はstage/commitしない。
mainがorigin/mainよりbehindの場合や、未公開の非データcommitがある場合は中断する。
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEALTH_SCRIPT = os.path.join(REPO_ROOT, "scripts", "health_check.py")

ALLOWED_EXACT = {
    "data/index.json",
    "scripts/collection_failures.json",
}
ALLOWED_PREFIXES = (
    "data/chunks/",
,)


def creation_flags() -> int:
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        return subprocess.CREATE_NO_WINDOW
    return 0


def run_git(
    *args: str,
    capture: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    cmd = ["git", *args]
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        creationflags=creation_flags(),
    )

    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            f"git {' '.join(args)} に失敗しました"
            + (f"\n{detail}" if detail else "")
        )
    return result


def is_allowed_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    return (
        normalized in ALLOWED_EXACT
        or any(normalized.startswith(prefix) for prefix in ALLOWED_PREFIXES)
    )


def split_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def run_health_check() -> None:
    print("=" * 60)
    print("  公開前データ健康診断")
    print("=" * 60)
    result = subprocess.run(
        [sys.executable, HEALTH_SCRIPT],
        cwd=REPO_ROOT,
        check=False,
        creationflags=creation_flags(),
    )
    if result.returncode != 0:
        raise RuntimeError(
            "健康診断がNGのため公開を中止しました。"
            "データを修正してから再実行してください。"
        )


def ensure_git_available() -> None:
    result = subprocess.run(
        ["git", "--version"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        creationflags=creation_flags(),
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Gitが見つかりません。Git for Windowsをインストールしてください。"
        )
    print(result.stdout.strip())


def ensure_main_and_sync_state() -> None:
    branch = run_git("branch", "--show-current").stdout.strip()
    if branch != "main":
        raise RuntimeError(
            f"現在のブランチは {branch or '(detached HEAD)'} です。"
            "公開はmainブランチでだけ実行できます。"
        )

    remote_url = run_git("remote", "get-url", "origin").stdout.strip()
    print(f"origin: {remote_url}")

    print("origin/main の状態を確認中...")
    run_git("fetch", "origin", "main", capture=False)

    counts = run_git(
        "rev-list",
        "--left-right",
        "--count",
        "HEAD...origin/main",
    ).stdout.strip().split()

    if len(counts) != 2:
        raise RuntimeError("origin/mainとの同期状態を判定できませんでした")

    ahead, behind = (int(counts[0]), int(counts[1]))

    if behind > 0:
        raise RuntimeError(
            f"ローカルmainがorigin/mainより {behind} commit古いです。"
            "先に git pull してから公開してください。"
        )

    if ahead > 0:
        ahead_paths = split_lines(
            run_git("diff", "--name-only", "origin/main..HEAD").stdout
        )
        unsafe = [path for path in ahead_paths if not is_allowed_path(path)]
        if unsafe:
            joined = "\n  - ".join(unsafe)
            raise RuntimeError(
                "origin/mainへ未公開のコード変更があります。"
                "データ公開と一緒にはpushしません。\n"
                f"  - {joined}"
            )
        print(
            f"前回のデータ公開commitが未pushの可能性があります "
            f"({ahead} commit)。今回のpushで再試行します。"
        )


def ensure_no_unrelated_staged_files() -> None:
    staged = split_lines(run_git("diff", "--cached", "--name-only").stdout)
    unsafe = [path for path in staged if not is_allowed_path(path)]
    if unsafe:
        joined = "\n  - ".join(unsafe)
        raise RuntimeError(
            "公開対象外のファイルがすでにstageされています。"
            "誤commit防止のため公開を中止します。\n"
            f"  - {joined}"
        )


def stage_publish_data() -> None:
    run_git(
        "add",
        "-A",
        "--",
        "data/index.json",
        "data/chunks",
        "scripts/collection_failures.json",
        capture=False,
    )


def get_staged_publish_files() -> list[str]:
    staged = split_lines(run_git("diff", "--cached", "--name-only").stdout)
    return [path for path in staged if is_allowed_path(path)]


def commit_if_needed() -> bool:
    staged = get_staged_publish_files()
    if not staged:
        print("新しくcommitするデータ変更はありません。")
        return False

    print("公開対象:")
    for path in staged:
        print(f"  - {path}")

    message = "Update chat data " + datetime.now().astimezone().strftime(
        "%Y-%m-%d %H:%M"
    )
    run_git("commit", "-m", message, capture=False)
    print(f"commit: {message}")
    return True


def push_main() -> None:
    counts = run_git(
        "rev-list",
        "--left-right",
        "--count",
        "HEAD...origin/main",
    ).stdout.strip().split()
    ahead = int(counts[0]) if len(counts) == 2 else 0

    if ahead <= 0:
        print("GitHubへ送る新しいcommitはありません。")
        return

    print(f"GitHubへ {ahead} commit push中...")
    run_git("push", "origin", "main", capture=False)
    print("✅ GitHubへ公開しました。")
    print("GitHub Pagesの反映には少し時間がかかる場合があります。")


def main() -> int:
    try:
        ensure_git_available()
        run_health_check()
        ensure_main_and_sync_state()
        ensure_no_unrelated_staged_files()
        stage_publish_data()
        commit_if_needed()
        push_main()
        return 0
    except Exception as exc:
        print(f"\n❌ 公開中止: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
