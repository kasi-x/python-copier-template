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
- **✅ 対応 (2026-09-06)**: 生成物 AGENTS.md の Commands 節にチェック実行の案内を追記
  （エージェントがまっ先に読む場所に置く。スキップするレシピは「check が静かに縮む」
  問題を生むため作らない）。
- **✅ 根本解決 (2026-09-07)**: そもそも**生成直後の非 git ワークスペースで
  `uv sync` が setuptools_scm エラーで即死**するのが本当の原因だった
  （pre-commit 廃止で lint は git 不要になったが、sync が残っていた）。
  生成 pyproject の `[tool.setuptools_scm]` に `fallback_version = "0.0.0"` を
  追加し、git metadata が無くてもプレースホルダバージョンで環境が構築できるように。
  「生成 → check → git init → 単一コミット → push」の PIPELINE 順序が
  どの順でも動くようになった。回帰テスト
  `test_template_works_outside_git`（git init 無しレンダー + 実際の uv sync）で固定。

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

---

# 2026-09-08 新規報告（fake_detector 生成セッションから）

`fake_detector` (data_science) を `copier copy` で生成した際、3 ステップ連鎖で失敗した。
失敗の全体像: **(1) タグ既定で古い設問定義にヒット → (2) HEAD を指定しても trust 無しで
無言終了 → (3) trust を足して初めて拡張不足が判明**。各ステップの切り分けに
余計な試行錯誤が発生した。最終的に成功したコマンド:

```sh
uv tool install copier --with copier-template-extensions --force
copier copy --defaults --vcs-ref=HEAD --trust --data-file answers.yml \
    ~/dev/python-copier-template ~/dev/fake_detector
```

## 11. 最新タグと HEAD で質問定義が乖離しており、タグ既定の copier で HEAD 時代の回答が通らない

- **現象**: `copier copy --defaults --data-file answers.yml`（回答は最小限）で
  生成すると、HEAD の README / questionnaire を読んで書いたはずの回答セットが
  タグ側で検証に落ち、2 通りのエラーが発生した。
  - 最小限の回答セット → `ValueError: Question "docker" is required`
  - `example-answers.yml` と同型のフル回答セット（`docs_type: zensical` を含む）→
    `ValueError: Invalid choice for 'docs_type': 'zensical' is not in ['README', 'sphinx']`
- **原因**: copier はローカル git リポジトリのテンプレートを**最新タグ (5.4.0)** で解決する
  （`--vcs-ref` 未指定時）。5.4.0 時点の copier.yml を `git show 5.4.0:` で確認すると:
  - `docker` は `default` を持たない無条件質問で、`use_recommended_integrations`
    ゲートはまだ存在しない → `--defaults` でも埋められず "required" で死ぬ
  - `docs_type` の choices は `[README, sphinx]` のまま → `zensical` は choices 検証で落ちる
  一方 HEAD は `5.4.0-55-g5b28f449`（タグから 55 コミット先行、うち questions 関係が 18 コミット）で、
  integrations ゲート導入・zensical/great-docs 追加済み。README や questionnaire の記述は
  HEAD ベースなので、「ドキュメントどおりの回答を書いたユーザーほどタグで失敗する」状態。
- **提案**:
  - 回帰テスト: example-answers.yml（+ 最小回答セット）を**最新タグ**に対してレンダーし、
    タグ側の設問定義が古くなったら drift issue を出す CI（upstream drift チェックの質問版）
  - README の生成コマンド例（クイックスタート節）に、ローカル開発中テンプレートから
    生成する場合は `--vcs-ref=HEAD` を付ける旨を明記
  - タグの更新頻度を上げる（あるいは HEAD ベース生成を公式に案内する）
- **回避策の実績**: `--vcs-ref=HEAD` で解決。このとき `DirtyLocalWarning` が出て
  未コミット変更（当時 `template/pyproject.toml.jinja` と `tests/test_example.py`）も
  自動取り込みされる点は挙動として把握しておく必要があった（意図的仕様だが、
  生成物がワークツリーの途中状態を含み得ることを警告文言だけから読み取るのは難しい）。

## 12. unsafe feature による無言終了が Jinja 拡張不足より先に起き、切り分けが 2 段階になる

- **現象**: `--vcs-ref=HEAD` を付けても出力は `DirtyLocalWarning` と
  「Template uses potentially unsafe features」の notice だけで dest は空のまま。
  `--trust` を足して初めて本当の原因
  `Copier could not load some Jinja extensions: No module named 'copier_template_extensions'`
  （exit 1）が見えた。
- **原因**: 積み重なった 2 つの問題。
  1. 環境の copier が bare `uv tool install copier` で、`copier-template-extensions` が
     無かった（#10 対応済みの README 記載 `uvx --with copier-template-extensions` を
     今回は踏まなかった）
  2. copier 本体の挙動として、trust 未指定の unsafe-feature 終了（#10 記載の exit 4・無言）が
     拡張チェックより先に走るため、拡張不足のエラーメッセージが最後まで表面化しない
- 加えて `| tail` 経由で確認していたため exit code が消え、
  「エラー無しで dest が空」という誤解を招く見た目になった。
- **提案**:
  - README: 非インタラクティブ節だけでなく、生成手順の最初の 1 コマンド目から
    `uvx --with copier-template-extensions` + `--trust` を含む形で提示する
    （#10 の修正が非インタラクティブ節に留まっているため、素通りする利用者がいる）
  - FAQ / トラブルシューティングに「dest が空で終わる場合、
    unsafe features (--trust) と Jinja 拡張の 2 点を順に確認」の項を足す

さらに、生成が通った後でも気になった仕様を 3 〜 5 件。いずれも fake_detector
(data_science + allow_japanese + torch/f_vec 系依存) での実測に基づく。

## 13. `allow_japanese: true` でも pydocstyle の句点ルール (D400/D403/D415) が無効化されない

- **現象**: 生成直後の `ruff check` が 87 errors で、うち約 70 が日本語 docstring
  の句点「。」起因（missing-terminal-punctuation D415 / missing-trailing-period
  D400 / first-word-uncapitalized D403）。`allow_japanese` は line-length と
  max-doc-length しか緩めておらず、pydocstyle は ASCII の `.` 前提のまま。
- **傍証**: テンプレート自身が生成する `logging_setup.py` も「。」終わりの日本語
  docstring だが、こちらは per-file-ignores で `D` 全免除して回避している
  （=テンプレート内部でも同じ問題を個別免責で握りつぶしている）。
- **提案**: `allow_japanese: true` のときは extend-ignore に D400/D403/D415 を
  加えて生成する（line-length 緩和と同じ文脈で適用）。現状は「文字幅は緩めるが
  文末スタイルは ASCII 前提」という半端な仕様に見える。
- **fake_detector 側で暫定対応済み**: extend-ignore に 3 ルールを理由コメント付きで追加。

## 14. setuptools-scm 生成物 `_version.py` が ruff 対象で、生成直後から ruff が失敗する

- **現象**: 初回 `ruff check` で `src/fake_detector/_version.py` に
  unsorted-dunder-all と bad-quotes-inline-string。ユーザーが書かないファイルで、
  `uv sync` のたびに再生成されるため手直ししても消えない。
- **提案**: テンプレート既定の ruff extend-exclude に
  `src/{{ package_name }}/_version.py` を追加（生成物は lint 対象外が自然）。
- **fake_detector 側で暫定対応済み**: extend-exclude に追加。

## 15. data_science / GPU を謳いながら torch wheel (CPU vs CUDA) の選択をテンプレートが面倒見ない

- **現象**: data_science は GPU Dockerfile / GPU devcontainer を生成するのに、
  torch の入れ方には一切関与しない。uv で `torch` を足すと Linux は PyPI 既定の
  CUDA ビルド（nvidia 依存が大量・数 GB）になり、CPU 固定には
  `[[tool.uv.index]]` + `[tool.uv.sources]` をユーザーが手書きする必要がある。
  逆に CPU 固定にすると `Dockerfile.gpu` の `uv sync --locked` が GPU コンテナに
  CPU wheel を入れる不整合が起きる（lock が CPU に張り付くため）。
- **提案**: data_science 詳細質問に「torch: 使わない / CPU wheel / CUDA (cu126 など)」
  を追加し、index/sources ブロックと Dockerfile.gpu の整合をテンプレート側で担保する。
  torch はデータ系プロジェクトでほぼ必ず絡むので、罠を質問に事前吸收する価値が高い。
- **fake_detector 側で暫定対応済み**: CPU index 固定 + README に CUDA への差し替え手順を注記。

## 16. data_science の `src/{data,features,models,visualization}` スケルトンが src/<pkg> パッケージ構成と並存する

- **現象**: data_science 生成物の `src/` に、`.gitkeep` だけの
  `data/ features/ models/ visualization/`（Kedro / cookiecutter-data-science 由来の
  スクリプト置き場）がインストール可能パッケージ `src/<pkg>/` と並んで生成される。
  使い道の説明がどこにもなく、ここに分析スクリプトを置き始めると
  deptry / ruff の対象になって依存宣言エラー (DEP001 等) で怒られる。
- **提案**: (a) README / AGENTS.md に使い道と依存宣言の注意を注記する、
  (b) 質問で on/off を選べるようにする、の少なくとも一方。
  パッケージ本体 (src layout) とスクリプト置き場 (flat src) は慣習が混在するので、
  分離（scripts/ など）も検討の価値あり。

## 17. 生成 pyproject の deptry `per_rule_ignores` に web_api 系の依存名が data_science でも大量に混入する

- **現象**: 生成 pyproject の `per_rule_ignores` が
  `DEP002=alembic|asgi-correlation-id|asyncpg|click|fastapi|...|wandb` と長大で、
  data_science プロジェクトが依存しない alembic / slowapi / sqlalchemy / loguru 等も
  並ぶ。機能への影響はないが、設定の意図が読み取りにくく diff も太る。
- **提案**: 機能ゲート（web_api / mcp / scraping / sentry / experiment）に応じて
  ignore リストを組み立て、選択していない機能の名前は生成しない。
