# bugs / フィードバック(生成側セッションから)

生成セッション(2026-09-05、`transrecord` を `copier copy --trust --defaults --vcs-ref=HEAD --data ...` で生成)で発見。各項目は issue 化してよい。

> **2026-09-05 対応済み**（3件とも修正 + テスト追加。修正内容の決定事項は各節末尾）。

## 1. `use_recommended_agent` の意味が三重に矛盾し、誤レンダリングする

- **現象**: plain library が欲しくて `--data use_recommended_agent=false` を渡したら、逆に pydantic-ai scaffold(`agent.py` / `tools/` / `prompts/agent.md` / `tests/test_agent.py` + `pydantic-ai` 依存)が生成された。`--data` を外して再生成する無駄が発生。
- **原因**: ファイル名条件が二重否定形 — `{% if not use_recommended_agent and project_type in ['library', 'cli'] %}agent.py{% endif %}.jinja`。
- **矛盾点は3つ**:
  1. 変数名 `use_recommended_agent` は「推奨エージェント(pydantic-ai)を足す?」に読める。実際は「推奨設定(=エージェント無し)にする?」の意味。
  2. 質問文 "Add an LLM agent (pydantic-ai) scaffold?" は Yes で scaffold 追加に読めるが、Yes(=true, 既定)では scaffold は出ない。
  3. help 冒頭 "Recommended: no — a plain library" と `default: true` が衝突して見える(true が「agent 無し=推奨」の意味だと分かるまで数秒要る)。
- **提案**: 変数を肯定形(`include_agent_scaffold` 等)にリネームするか、質問文と help を実際の gating に合わせて書き直す。`tests/test_example.py` の present/absent テストは変数値を直接渡すため、この語彙のねじれは検知できない。
- **✅ 対応**: 質問文を gate 形式に修正 — "Use the recommended agent setup (no agent tooling)? / Recommended: yes ..."（矛盾点 2, 3 を解消。他の `use_recommended_*` ゲートと同一の文面パターン）。変数名のリネームは**見送り**: TODO 設計原則の「推奨1本 + No でカスタム（`use_recommended_*` 統一）」に反するため。ゲートなので中間の詳細質問は持たない設計も既定のまま。

## 2. `Dockerfile` が `docker: false` でも常に生成される

- `template/Dockerfile.jinja` は無条件レンダリング。`{% if docker %}` でゲートされているのは `.dockerignore` のみ。library + `docker: false` でも Dockerfile が出る。
- かつ内容は `FROM ghcr.io/kasi-x/ubuntu-devcontainer:resolute`(devcontainer 用ベース)。fork 元は `ghcr.io/diamondlightsource/...` なので、**GHCR に `kasi-x/ubuntu-devcontainer` パッケージが存在しないと devcontainer ビルドが即 404 する**。要確認: パッケージを公開済みならこの行は不要。
- **提案**: devcontainer 用 Dockerfile を `docker` 質問とは別軸(devcontainer を使うか)に分離。GHCR イメージ参照は `github_org` から動的にしているなら、実在チェックを `scheduled-check.yml` 系に足す。
- **✅ 対応**:
  - 実在確認の結果、`kasi-x/ubuntu-devcontainer` は**未公開**（GHCR 404）→ ベースを実在する `ghcr.io/diamondlightsource/ubuntu-devcontainer:resolute` に戻した（renovate.json のトラッキング対象も同時修正）。
  - Dockerfile 自体は **devcontainer の基底**（`.devcontainer/devcontainer.json` が `../Dockerfile` を参照）のため `docker` ゲートは入れない（upstream と同設計。「devcontainer を使うか」の別軸質問は将来課題）。
  - 代わりに `tools/check_upstream.py` に **Devcontainer base pin** を追加: 匿名トークンで GHCR manifest を実在チェックし、404 なら週次 drift issue。実データで `[ok] present` を確認済み。

## 3. (軽微) 依存ゼロの library にも `.env.example` / `.envrc` が生成される

- `dependencies = []`・env 変数を使わない library でも env ファイル一式と README の "Environment variables" セクションが出る。ノイズ。
- **提案**: env ファイル群は web_api / data_science / cloud_provider != none のときだけ生成するのが自然。
- **✅ 対応**: `.env.example` と README の "Environment variables" セクションを、**env 変数を消費する機能が1つでもあるときだけ**生成するようにゲート（`web_api or mcp_effective or scraping_effective or include_sentry or agent scaffold`。提案の cloud_provider は .env.example に該当セクションが無いため条件から除外し、代わりに mcp/scraping/sentry/agent を採用 — 中身の条件分岐に基づく）。data_science/kaggle も専用セクションが無いため対象外。**`.envrc` は常に生成**（中身は env 変数ではなく venv/pixi の自動アクティベーションで、依存ゼロの library でも機能するため）。`test_library_no_web_api_extras` を negativeケースへ更新し、agent ケースの positive アサーションを追加。
