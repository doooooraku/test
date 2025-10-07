# test

test

## Codex CLIでGitHub MCPを使ってGitHub Flowを動かす手順

### 用語のミニ辞書
- **Codex CLI**: OpenAIが提供するコマンドライン版のエージェント。自然言語で指示を出すと、必要なコマンドを自動で実行してくれる。
- **MCP (Model Context Protocol)**: エージェントと外部ツールをつなぐ共通規格。ここではGitHub用サーバーを介してリポジトリ操作を行う。
- **MCPサーバー**: MCPに対応した外部サービス。`github-mcp-server` はGitHubのIssue/PR/リポジトリAPIを代わりに呼び出してくれる。
- **PAT (Personal Access Token)**: GitHubの個人用アクセストークン。パスワード代わりに使う秘密鍵で、`.codex/mcp.env` に保存する。
- **GitHub Flow**: `main` ブランチから機能ブランチを切り、変更をコミット → Push → Pull Request(PR) → レビュー → マージという一連の開発手順。
- **Branch（ブランチ）**: 作業用の分岐。変更を隔離して安全に開発できる。
- **Commit（コミット）**: 変更内容のスナップショット。履歴として残される。
- **Pull Request / PR**: 他の人に変更をレビューしてもらうための申請。GitHub Flowのゴール。

### 1. 設定ファイルを確認する
1. `cat ~/.codex/config.toml` — `cat` はファイルの中身をそのまま表示するコマンド。MCPサーバーが正しく登録されているかを確認する。
2. `cat ~/.codex/mcp.env` — GitHubのPATが設定されているかを確認する。`#` で始まる行はコメントなので無視してよい。
3. `codex mcp list` — Codex CLIに登録されたMCPサーバーを一覧表示する。`github` サーバーが `docker ... stdio` で動く設定になっていればOK。

### 2. MCPの接続テストを行う
- `codex exec --skip-git-repo-check --json 'List the branches for the repository doooooraku/test on GitHub. Use the github MCP server to fetch the branches and then stop.'`
  - `codex exec` は非対話モードでCodexを走らせるサブコマンド。
  - `--skip-git-repo-check` は「実行ディレクトリがGitリポジトリかどうか」のチェックをスキップするオプション。
  - `--json` は応答をJSON Lines形式で出力させるオプション。途中で `tool":"list_branches"` のようにGitHub MCPが呼ばれていることが確認できる。
  - プロンプトでリポジトリ名を指定すれば、CodexがMCP経由でGitHub APIを呼び、ブランチ一覧を表示してくれる。

### 3. GitHub Flow をCodexとMCPで実践する
1. `git clone https://github.com/doooooraku/test.git` — リポジトリをローカルに複製する。`git` はバージョン管理ツール、`clone` はダウンロードして `.git` 履歴ごと取得するコマンド。
2. `cd test` — 作業ディレクトリをリポジトリ内に移動する。`cd` は “change directory” の略。
3. `git checkout -b docs/add-codex-mcp-guide` — `docs/add-codex-mcp-guide` という新しいブランチを作って切り替える。`-b` は「ブランチを作成しながらチェックアウトする」という意味。
4. `nano README.md` など好みのエディタでREADMEを編集し、手順メモを追記する。今回の例ではこのファイルに上記の内容を追加した。
5. `git status` — 変更されたファイルの一覧を確認する。ステージングされていない変更（赤色表示）が見えればOK。
6. `git add README.md` — 変更内容をステージングエリアに追加する。`add` はコミット候補に含めるという意味。
7. `git commit -m "Add Codex MCP walkthrough"` — ステージされた変更を履歴として確定する。`-m` はコミットメッセージをその場で指定するフラグ。
8. `set -a && source ~/.codex/mcp.env && git push origin docs/add-codex-mcp-guide`
   - `set -a` は以降に読み込んだ変数を自動で環境変数に昇格させるシェル機能。
   - `source ~/.codex/mcp.env` でPATを環境変数として読み込む。
   - `git push origin ブランチ名` でリモートリポジトリ（origin）へ変更を送信する。PATがあるので認証も自動で完了する。
9. `codex exec --skip-git-repo-check 'Create a pull request in doooooraku/test from docs/add-codex-mcp-guide into main with the title "Add Codex MCP walkthrough" and summarize the diff.'`
   - Codex CLIがGitHub MCPサーバーを使ってPR作成APIを叩いてくれる。
   - 応答には作成されたPR番号やURLが表示されるので、そのままレビュー依頼に進める。

これらを順番に実施することで、Codex CLIがMCP経由でGitHubの操作を肩代わりし、初心者でも安全にGitHub Flowを回せる。加えて、各コマンドが何を意味するのかを理解しておくと、トラブルシューティングも容易になる。
