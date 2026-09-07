# bugs / フィードバック(生成側セッションから)

生成セッション(2026-09-05、`transrecord` を `copier copy --trust --defaults --vcs-ref=HEAD --data ...` で生成)で発見。各項目は issue 化してよい。

> **2026-09-05 対応済み**（3件とも修正 + テスト追加。修正内容の決定事項は各節末尾）。
> **2026-09-06 対応**（#4, #5, #6, #7, #10。各節末尾の ✅ を参照。#8, #9 は本文末尾に追記）。

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

---

# 2026-09-05 新規報告（kasi-x publish pipeline から）

## 4. `just check` が git repository 必須でパイプラインと矛盾

- **現象**: `just check` は `pre-commit` を実行するが、pre-commit は `.git` ディレクトリが存在する必要がある。パイプライン（PIPELINE.md）は「チェックを先に通してから `git init` → 単一コミット → push」という順序のため、鶏と卵の矛盾が起きる。
- **エラーメッセージ**:
  ```
  uv run --locked pre-commit run --all-files --show-diff-on-failure
  An error has occurred: FatalError: git failed. Is it installed, and are you in a Git repository directory?
  ```
- **回避策**: 一時的に `git init -q -b main && git add -A && git commit -q -m "temp"` してから `just check` を実行し、最終的にコミットを amend または reset して単一コミットにする。
- **提案**:
  - パイプライン文書にこのワークアラウンドを明記する
  - `just check` を `.git` 未存在時は pre-commit をスキップするようにする
  - `just check-no-git` のような別レシピを用意する
- **✅ 対応 (2026-09-06)**: 生成物 AGENTS.md の Commands 節に「check/lint は
  pre-commit を経由するため git リポジトリ外では実行不可。新規ワークスペースは
  先に `git init`」と明記（エージェントがまっ先に読む場所に置く。スキップする
  レシピは「check が静かに縮む」問題を生むため作らない）。

## 5. 日本語テキストで E501 (line-too-long) が多発

- **現象**: テンプレートの `line-length = 88` は日本語テキストには短すぎる。日本語は情報密度が高く、88文字では収まらない文が頻出する。
- **具体例**（discord_calender_bot）:
  ```python
  f"🗓️ {start.strftime('%Y-%m-%d %H:%M')}〜（{duration}分 / JST）\n"
  "⚠️ 日時の形式が正しくありません。`date` は `2026-07-01`、`time` は `19:00` の形式で。",
  ```
- **回避策**: 各ファイルに `per-file-ignores` で `E501` を追加。
- **提案**:
  - デフォルトの line-length を 100-120 に引き上げる
  - copier に「日本語テキストを含むか」の質問を追加し、line-length を調整する
  - 日本語プロジェクト向けのドキュメントを用意する
- **✅ 対応 (2026-09-06)**: すでに `allow_japanese` 質問が存在
  （`use_recommended_polish: false` で顕在化。true で line-length 88→120、
  max-doc-length 150→200 に緩和、E501/D は multibyte を考慮した計算になる）。
  提案の質問はこの質問が担うため新設せず、questionnaire.md に追記済み。

## 6. `@pytest.fixture()` が自動修正されない

- **現象**: 生成されたテストファイルに `@pytest.fixture()` が含まれるが、ruff が `@pytest.fixture` に自動修正してくれない（手動修正が必要）。
- **具体例**:
  ```python
  @pytest.fixture()
  def signing_key(monkeypatch: pytest.MonkeyPatch) -> SigningKey:
  ```
- **回避策**: 手動で括弧を削除するか、`per-file-ignores` に `PT006` を追加。
- **提案**: テンプレートの ruff 設定で `PT006` を auto-fix 対象に含める。
- **✅ 対応 (2026-09-06)**: 該当ルールは PT001（`fixture-parentheses`）。テンプレートは
  括弧なし `@pytest.fixture` を正とするスタイルで、ruff の実効デフォルトも同方向。
  `lint.flake8-pytest-style.fixture-parentheses = false` を明示固定し、ruff の
  デフォルト変更で生成物のスタイルが静かに反転しないようにした。修正は
  `ruff check --fix` で自動適用される（`--fix` なしの `ruff check` は指摘のみ）。

## 7. DTZ007 (call-datetime-strptime-without-zone) が厳しすぎる

- **現象**: `datetime.strptime()` でパースして `.replace(tzinfo=...)` でタイムゾーンを後付する一般的なパターンが DTZ007 に引っかかる。
- **具体例**:
  ```python
  dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
  return dt.replace(tzinfo=config.TZ)
  ```
- **回避策**: `per-file-ignores` に `DTZ007` を追加。
- **提案**:
  - デフォルトの `extend-ignore` に `DTZ007` を追加する
  - またはドキュメントに「日時パターンでは per-file-ignores が必要」と記載する
- **✅ 対応 (2026-09-06)**: recommended strictness の `extend-ignore` に
  `DTZ007` を追加（理由コメント付き: naive な入力をパースして
  `.replace(tzinfo=...)` で tz を後付する一般的な正しいパターンを
  DTZ007 は見分けられない。フォーマットが %z を持つなら ignore を外せばよい）。

## 8. 生成されたテストに未使用引数がある (ARG001)

- **現象**: テンプレートが生成したテストフィクスチャのうち、テスト本体で使われていない引数が ruff の ARG001 に引っかかる。
- **具体例**:
  ```python
  def test_invalid_signature_rejected(
      client: FlaskClient, signing_key: SigningKey  # signing_key 未使用!
  ) -> None:
  ```
- **回避策**: 未使用引数を削除するか `_` プレフィックスを付ける。
- **提案**: テスト生成で実際に使用されるフィクスチャのみを含める。

## 9. pyproject.toml のコメントが長すぎる

- **現象**: ruff の `per-file-ignores` に詳細な説明コメントが付いており、pyproject.toml が 300+ 行になる。
- **問題**:
  - 設定ファイルが見づらい
  - 実際の設定がコメントに埋もれる
- **提案**:
  - 詳細な説明は `RUFF.md` や `CONTRIBUTING.md` に移動する
  - インラインは最小限のコメントにする

## 10. copier `--defaults` でも質問がスキップされない

- **現象**: `copier copy --defaults` を実行しても、デフォルト値があるはずの質問が表示されてしまう。
- **問題**: 自動バッチ処理が中断する
- **提案**:
  - 全質問を `--defaults` でテストし、スキップされるか確認する
  - 「デフォルトでも聞かれる質問」をドキュメントに記載する
  - 完全非インタラクティブモード（`--force` 等）を用意する
- **✅ 対応 (2026-09-06)**: 根本原因は `--trust` 漏れ — copier は unsafe feature
  （jinja_extensions/tasks）を持つテンプレートを trust 無しでは生成せず、
  **exit 4 で何も出力せず終了**する（`_cli.py` の `0b100`）。加えて
  `gitlab_group` だけ default が無く `--defaults` + gitlab.com で止まり得たため
  default を追加した。全質問に default が付いたことを機械検証するテスト
  （test_every_asked_question_has_a_default）を新設。README の非インタラクティブ節を
  `--trust` 必須・`uvx --with copier-template-extensions` 付きで書き直した。

---

# 2026-09-06 検証結果(残り2件)

- **#8 (生成テストの未使用引数 ARG001)**: テンプレート生成物には再現しない。
  報告の例(`client`, `signing_key`)は Flask 固有のコードで、テンプレートは
  Flask を生成しない。生成物は `test_generated_lint.py` が全レンダーパスで
  ruff を実走させており ARG001 は出ない。生成コードを copy した後の
  ユーザー編集で起きたものと判断(対応不要)。
- **#9 (pyproject.toml のコメントが長い)**: **見送り(設計判断)**。コメントは
  「なぜこの ignore なのか」を生成物だけで完結させるための意図的なスタイルで、
  詳細を外部ドキュメントへ追い出すと copier update 時のパリティテスト
  (テンプレート本体と生成物の設定一致)が壊れる。コンフィグの教訓は
  docs/explanations/template-dev.md に文書化済み。
