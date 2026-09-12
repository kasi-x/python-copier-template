# PLAN: 劇的改善の作業分解（委託用）

対象リポジトリ: `kasi-x/python-copier-template`（HEAD = `e2a210e1`、2026-09-11）。
この文書は **そのまま他エージェントへ委託できる粒度**の作業パッケージ集。
既存の `TODO.md`（節1〜21）と重複する項目は、参照のみで再記述しない（二重管理の禁止）。

---

## 0. 診断（この計画の動機。2026-09-11 実測）

| # | 事実 | 実測根拠 |
|---|---|---|
| D1 | 最新タグ `5.4.0` は **upstream の内容**。fork の機能は 0 個、HEAD は 69 commits 先 | `git show 5.4.0:copier.yml` に `micropython\|online_judge\|web_django` が **0 回**（HEAD は 12 回）。`git rev-list --count 5.4.0..HEAD` = 69。`git diff --name-status 5.4.0 HEAD` で追加 328 ファイル |
| D2 | 既定 `copier copy` は**即失敗**する | `copier copy --trust --defaults --data-file example-answers.yml . out` → exit 1 `Invalid choice for 'docs_type': 'zensical' is not in ['README', 'sphinx']` |
| D3 | 最小 answers でも既定は失敗 | `--defaults --data-file <5行>` → exit 1 `Question "author_name" is required` |
| D4 | `--vcs-ref=main` なら成功 | exit 0 / 51 files / `_commit: 5.4.0-69-ge2a210e1` |
| D5 | 全テストが `vcs_ref="HEAD"` 固定なので D2/D3 を検出しない | `tests/test_example.py:27,59,272,1031,1086`、`tests/test_generated_lint.py:120,134,287` 他 |
| D6 | 実行検証は 10 構成のみ（質問空間は 9型×3PM×7ランナー×2layout ≳378） | pixi/poetry は install/run ゼロ、flat layout も実行ゼロ、`make/poe/invoke/duty` は `lint` のみ、ros2/script/kaggle/ctf/leetcode 等は render のみ |
| D7 | CI に `timeout-minutes` が **0 件**、キャッシュは Docker layer のみ | `grep -rl timeout-minutes .github/workflows \| wc -l` = 0 |
| D8 | `template/` 197 ファイル中 **188 がパス名に Jinja**、`{% if %}` 444 個、質問 108（user 62 / internal 46） | 偵察監査（agent://TemplateInternalsAudit） |
| D9 | src/flat の鏡像 11 ファイル、dev 依存 3 重複、python-version 三項が 6 ファイルに散在、raw/effective 混在 ≥10 箇所 | 同監査。例 `template/<README>.jinja:449,659` が raw `fair`、`_shared/pyproject-basedpyright.toml.jinja:8` と `.python-version.jinja:1` が同一三項を重複 |
| D10 | README 477 行中 61% が機能カタログ、最初のコマンドまで 410 行、TL;DR なし。`README.md:302` は「Task (default)」、`questions/_common_a.yml:75` は `default: just` | 直接確認済み |
| D11 | 生成 README は 681 行 / `if` 98 個 | 同監査 |

**目標**: 「broad に *生成できる*」を「broad に *動くと証明されている*」に一致させる。
そのために (a) 既定経路と update を壊れないようにし、(b) オプション空間とタスク定義をデータ化し、
(c) 網羅性を Z3 の証人として実行で証明する。

---

## 1. 全エージェント共通の規約（委託時に必ず渡す）

- **検証の形**: 文字列 assert の追加ではなく、**実行して観測**する。新規テストは
  「起こりうるバグで落ちる」ものだけ。実装詳細（レンダリング文言・内部変数・デフォルト値のコピー）を
  固定するテストは書かない。既存で文言を固定しているだけのテストは削除してよい。
- **mid-flight で lint / format / 全体テストを回さない**。担当 WP の該当テストのみ実行し、
  横断的な `task check` は統合担当が最後に 1 回だけ。
- **copier の呼び方（ローカル）**: `copier copy --trust --defaults --vcs-ref=HEAD --data-file <yml> . <dest>`。
  `--overwrite` は再生成時のみ。network（`uvx`, clone, PyPI 参照）に依存するテストを**新設しない**。
- **`template/` 配下は、担当 WP が所有権を持つファイル以外を触らない**（§4 の所有権表）。
- **生成物の byte-identical 検証**は W2 のリファクタでは必須（差分ゼロを確認してから振る舞いテストへ移行）。
- **記録**: 進捗は `TODO.md` 節22 のチェックボックスを更新する。仕様判断は本ファイルに追記し、
  別ファイルを新設しない。
- **言語**: コミットメッセージは Conventional Commits（CI で強制）。本文は日本語可。

---

## 2. 先に固定する共有コントラクト（エージェント間で交渉させない）

### C1. ref の意味論
- 利用者向け: タグ（W0 完了後は引数なし `copier copy` が正）。ドキュメントから `--vcs-ref=main` を撤去。
- テスト/CI: `--vcs-ref=HEAD`（ローカル作業ツリー）。
- **W0 完了まで、既存の `--vcs-ref=main` 記述は凍結**（W0 が一括更新する）。

### C2. 質問票モデル JSON（`tools/questionnaire.py` が出力、W3/W5 が消費）

```json
{
  "order": ["project_type", "existing_project", "..."],
  "questions": [
    {
      "name": "project_type",
      "type": "str",
      "when": null,
      "choices": ["library", "web_api", "cli", "data_science", "online_judge", "script", "web_django", "ros2", "micropython"],
      "default": "library",
      "help": "What kind of project is this? ...",
      "internal": false,
      "source": "copier.yml",
      "line": 31
    }
  ]
}
```

- `choices` は copier の mapping 形式（`label: value`）を **value の配列**に正規化する。
- `when` は raw 文字列（Jinja 評価しない）。`internal` は `when == false`（bool）のとき true。
- 順序は `!include` を解決した実質問順（`copier.yml` の document order）。

### C3. タスクモデル YAML（W2 が定義・生成元）

```yaml
# 単一の宣言的リスト。これが just/Taskfile/Makefile/poe/pixi/invoke/duty と
# AGENTS.md・CI(_tasks.yml) の唯一の生成元になる。
tasks:
  - name: lint
    desc: Check formatting and lint (ruff, check-only)
    when: null                 # raw 変数に対する Jinja 条件（省略時は常に出す）
    run:                       # 順に実行。シリアライザが && 連結する
      - "{{ run }}ruff format --check ."
      - "{{ run }}ruff check ."
    deps: []                   # run と排他。指定時は他タスクへの依存
    shell: null                # "bash" 等を明示したいときのみ（poe/pixi のヒューリスティック廃止）
```

- `run` は**実行順**を持つ配列。現行の「`&&` を含む 1 文字列をランナー毎に分割する」実装は廃止。
- タスク名の集合が各ランナーで一致することを構造比較でテストする（文字列比較ではない）。

### C4. 証人カバレッジ成果物（W3）

`tests/matrix/witnesses.json`（生成物・コミットする）:
```json
{"leaves": [{"id": "project_type=library/gate=recommended", "tier": "fast", "answers": {...}}],
 "coverage": {"total": 42, "executed_fast": 41, "executed_full": 12, "none": 1}}
```
`tier`: `fast`（render + ruff）/ `full`（+ uv sync + pytest + typecheck + docs）/ `none`（W4 が宣言する非サポート）。

### C5. サポート宣言（W4）

`support.yml`（人間が承認した組合せのみ）:
```yaml
tiers:
  supported:    # CI で実行保証
  best_effort:  # render のみ。壊れても CI を赤くしない
```

### C6. 実行エンジン（実装済み: `tools/batch.py`）

W3 の証人は **JSONL のリクエスト行**として `tools/batch.py` に渡す。1 行 =
1 リクエスト（`id` / `src` / `ref` / `answers` / `answers_file` / `dest` /
`update` / `commands` / `expect`）。ランナーは 1 行ずつ実行して
`expect` を判定し、`0`（全通過）/ `1`（期待値の失敗）/ `2`（リクエスト列が不正）
を返す。`--json` の stdout は JSON のみ（copier の出力は stderr）。
仕様は `docs/how-to/batch.md`、例は `batches/smoke.jsonl`。

W3 が生成する成果物はこの形式に合わせる（`tests/matrix/witnesses.jsonl` を
出力し、既存の `tests/matrix/witnesses.json` はカバレッジ集計に使う）。

### C7. 適用前の判定（実装済み: `tools/detect.py`）

モード判定と既存資産の棚卸しは `tools/detect.py` が行う（`docs/how-to/detect.md`）。
`detect(target, template_dir) -> Detection` をライブラリとして呼べる。

- `mode`: `fresh` / `adopt` / `update` / `foreign`（`update` は `.copier-answers.yml` の
  `_src_path` が本テンプレートを指す場合のみ。ローカル clone は origin で照合する）。
- 保護条件は `template/` のパス名条件（`existing_project` / `adopt_protect`）から
  **実行時に導出**する。ハードコードしない（HEAD と作業ツリーで条件が異なっても正しい）。
- `collisions`: テンプレートが書く出力のうち既に存在するもの。
  `skip` はこの同名リストで、そのまま `copier copy --skip <path>` に渡すと既存ファイルが無傷になる
  （レポートは実行可能なコマンドとして印字する）。
- `suggested_answers`: 一意に決まるものだけ。`project_type` / `include_*` などの形状質問は
  **推測しない**（SPEC §12）。テンプレートが宣言していない質問は出力しない。

W6 の wrapper CLI は `detect` の結果でモードを選び、`--answers` の生成物をそのまま使う。

### C8. エージェント向け面（実装済み: `tools/mcp_server.py` / `tools/questionnaire.py`）

| 層 | 入口 | 用途 |
|---|---|---|
| 質問票 | `tools/questionnaire.py`（`load_questions()`） | `!include` を解決した実質問順、`type`/`default`（Jinja のまま）/`when`/`help`/`choices`、`_` 設定は分離 |
| 判定 | `tools/detect.py` | モード・既存資産・COLLISIONS |
| 実行と判定 | `tools/batch.py` | JSONL → 合否（`--prepare` で環境構築、`--shell` で調査） |
| MCP | `tools/mcp_server.py` | 上記を tool として公開（stdio / streamable-http） |

- stdio の stdout は**プロトコル路**なので、render は必ず
  `batch.report_stream_only()`（fd 1 → fd 2）の中で行う。テストが `capfd` で固定。
- tool の docstring はモデルが読む説明文なので、コストと返り値の形を書く（無いと落ちるテストあり）。
- 形状質問（`project_type` / `include_*`）は MCP 経由でも**推測しない**（SPEC §12）。
- `list_questions` の 2 問（`package_manager` / `oj_kind`）は block scalar の
  `choices_template` を返す（回答依存で選択肢が狭まるため解決不能）。

W-P のうち読み取り側はこれで実装済み。残りは `test_copier_structure.py` の
`_load_questions` をこれへ委譲する重複排除。

W9（テスト実行コスト）は下記。

### C9. トランザクション付き adopt（実装済み: `tools/adopt.py`）

`copier copy` 単体では守れない 3 点を 1 コマンドで塞ぐ（すべて copier 9.18.1 で実測）:

| 失敗 | copier 単体の挙動 |
|---|---|
| テンプレも持つ既存ファイル（`ci.yml` / `renovate.json` …） | `conflict` → `Interactive session required` → exit 1。**描画済みファイルは残る**（before でも after でもない） |
| `--overwrite` で回避 | 未検出の衝突まで置換 |
| `--vcs-ref` 無し | 最新**タグ**を展開（fork では祖先の別テンプレートを指しうる） |

- **衝突ゼロ**: `detect.skip` を `skip_if_exists` に渡す。`overwrite` は使わない。
- **ロールバック**: 描画後に「既存ファイルが内容ごと変わっていないか」「消えていないか」を
  ファイル集合と**ディレクトリ集合**で検証し、破れていれば元を復元 + 生成物（空ディレクトリ含む）を削除。
  実測: 未カバーの衝突で失敗させると、ツリーが**バイト一致かつディレクトリ一致**で元に戻る。
- **正しいリビジョン**: 最新タグが HEAD と同じ質問集合を持つときだけタグを使い、
  そうでなければ既定ブランチ + 理由を報告（実測: `5.4.0` は 93 問欠け → `main` を選択）。
  `--ref HEAD` は作業ツリー（未コミット含む）を展開する。

**依存関係は加算マージする**（`tools/pyproject_deps.py`、2026-09-13 追加）: テンプレートが
生成するはずの deps を一時ディレクトリにレンダーして読み、既存 `pyproject.toml` へ
**無い名前だけ**追加する。既存の specifier は書き換えず、差があれば `differing` として報告。
tomlkit でコメント・レイアウトは保持、冪等、`[project]` / `[tool.poetry]` が無ければ報告のみ、
extras/markers は推測せず報告。`--no-deps` で無効化。マージは同じトランザクション内で検証され、
破れれば adopt 全体をロールバックする。

やらないこと（SPEC §12 の非目標として維持）: セクション単位の TOML 再編成、`[tool.*]` の書き換え、
タスクランナーファイルのマージ。

---

## 3. 作業パッケージ

各 WP は `# Target / # Change / # Acceptance` 形式でそのまま `task` に渡せる。

---

### W-P（前提・最初に直列で実行）— 質問票パーサの抽出

- **依存**: なし。**他 WP の前提**。
- **所有**: `tools/questionnaire.py`（新規）、`tests/test_copier_structure.py`（`_load_questions` の置換のみ）。
- **Target**: `tests/test_copier_structure.py:87` の `_load_questions()` と `:323` の `_fragment_questions()`。
- **Change**:
  1. `tools/questionnaire.py` を新設。`copier.yml` の `!include` を順に解決し、
     §C2 のモデルを返す `load_questions() -> dict` と、`--json` を出す `main()` を実装。
     `!include` のネスト（`questions/*.yml` は 1 include = 1 document）を再現する。
  2. `test_copier_structure.py` の `_load_questions` / `_fragment_questions` を
     `tools.questionnaire` への薄い委譲に置換（テスト側にロジックを残さない）。
  3. `tests/test_qa.py:53` の「`tools/` の import は stdlib か dev 依存のみ」規約を守る（追加依存なし）。
- **Acceptance**:
  - `uv run --locked python tools/questionnaire.py --json | jq '.questions | length'` が **108**。
  - `uv run --locked pytest tests/test_copier_structure.py tests/test_qa.py` が全緑。
  - 出力 JSON の `order` が `copier.yml` の document order と一致（Z3 テストが依存する順序を壊さない）。
- **非目標**: Z3 エンコーダの移植、docs 生成（それぞれ W3/W5）。

---

### W0（最優先・直列）— fork detach と既定経路の是正

- **依存**: なし。**W1/W3/W5/W6 が暗黙に依存**。
- **所有**: git タグ（リモート含む）、`README.md`（`--vcs-ref` 関連の削除のみ）、
  `docs/tutorials/adopt-existing.md`、`docs/tutorials/create-new.md`、`tests/test_generation_docs.py`、
  `copier.yml`（`_migrations` のみ）、`CHANGELOG.md`。
- **Target**: D1〜D5、`copier.yml:131-136`、`tests/test_generation_docs.py:1-43`。
- **Change**:
  1. **タグ番号は PEP440 で必ず `5.4.0` より大きくする（例: `6.0.0`）。`1.0.0` は不可。**
     理由（copier 9.18.1 で**実測再現済み**）:
     - `_template.py:649-672` が `dunamai`/`git describe` から template version を PEP440 に変換する。
       現 HEAD の answers は `_commit: 5.4.0-69-ge2a210e1` → version は
       **`5.4.0.post69.dev0+e2a210e1`**（実測）。
     - `_main.py:1368-1371` は `subproject.version > template.version` のとき
       `UserMessageError` を **raise**（警告ではない）する。`1.0.0` を打った場合の実測出力:
       ```
       You are downgrading from 5.4.0.post69.dev0+e2a210e1 to 1.0.0. Downgrades are not supported.
       ```
     - 正しい手順の実測: 継承タグを消して HEAD に **`6.0.0` ただ 1 つ**を打つと
       `copier update --vcs-ref=6.0.0` は成功し、answers は `_commit: 6.0.0` に前進する。
     - **追加の罠（実測）**: 同一起点 commit に複数のバージョンタグ（例 `1.0.0` と `6.0.0`）を
       残すと dunamai が低い方を選び、偽のダウングレードになる。**継承タグは必ず削除し、
       HEAD のバージョンタグは 1 つだけにする。**
     - `_template.py:421` の migration 選択は `new >= migration.version > old` なので、
       既存の `_migrations: version: 2.0.0` は `old = 5.4.0.post69…` のユーザーには
       発火しない（正常）。`before/after` 形式は deprecated（`DeprecationWarning`）なので、
       新形式へ移すか pre-2.0.0 向けとして残す判断を本ファイルに記録する。
     - 再現手順（委託先がそのまま実行して確認する）:
       ```sh
       git clone -q . /tmp/pct-probe && cd /tmp/pct-probe
       git checkout -q -b future && echo x >> README.md && git add -A && git commit -qm wip
       git tag -f 1.0.0                      # ← 意図的に悪い番号
       copier copy  --trust --defaults --vcs-ref=e2a210e1 --data-file /tmp/min.yml "$PWD" /tmp/dg
       (cd /tmp/dg && git init -q -b main . && git add -A && git commit -qm init)
       copier update --trust --defaults --vcs-ref=1.0.0 /tmp/dg
       # → You are downgrading from 5.4.0.post69.dev0+e2a210e1 to 1.0.0.
       git tag -d 1.0.0 && git tag -f 6.0.0   # ← 正しい番号は 1 つだけ
       copier update --trust --defaults --vcs-ref=6.0.0 /tmp/dg   # → 成功、_commit: 6.0.0
       ```
  2. 継承タグ（`3.0.0`〜`5.4.0` 系）を fork のリモートから削除し、HEAD に新タグを打つ。
     `git tag -l > /tmp/tags.before` を保存し、削除前に一覧を本ファイルへ追記する。
  3. `tests/test_generation_docs.py` の「docs の `copier copy` に `--vcs-ref=` を強制する」テストを撤去し、
     代わりに**タグ整合のテスト**を置く: `git describe --tags --abbrev=0` が HEAD の祖先で、
     その ref の `copier.yml` の質問名集合が HEAD と一致すること（network 不要・ローカル git のみ）。
  4. `README.md:417-422` の `--vcs-ref` 説明、`docs/tutorials/adopt-existing.md:4-9,21-44` の矛盾
     （`--vcs-ref=1.0.0` と「v1.0 未到達」の同居）を削除/一本化。`--trust` の説明は残す。
  5. `CHANGELOG.md` に「fork detach: 既定 ref が fork の最新タグに変わった」を追記。
- **Acceptance**（上から順に実測。すべてコマンド出力で示すこと）:
  1. **ダウングレード例外が出ない**: HEAD で生成したプロジェクト
     （`copier copy --trust --defaults --vcs-ref=HEAD --data-file example-answers.yml . /tmp/u1`、
     `git -C /tmp/u1 init` 済み）に対し、新タグで
     `copier update --trust --defaults --vcs-ref=<新タグ>` を実行 → exit 0 で
     `You are downgrading` が出ない。**これが通るタグ番号を選ぶ**（`1.0.0` では必ず落ちる）。
  2. **旧 upstream 経路の update も壊さない**: `--vcs-ref=4.0.0`（継承タグ）で生成したプロジェクトを
     削除前に確保しておき、新タグへ update して exit 0（必要なら `_migrations` を追記）。
  3. 引数なしで fork の質問票が出る:
     `git clone -q . /tmp/probe && cd /tmp/probe && copier copy --trust --defaults --data-file /path/example-answers.yml . /tmp/o1` → exit 0。
  4. 最小 answers: `project_type: library` 等 5 行で exit 0（D3 の `author_name` エラーが再現しない）。
  5. `grep -rn 'vcs-ref=main' README.md docs/` が 0 件。
  6. `uv run --locked pytest tests/test_generation_docs.py` が緑。
- **非目標**: README の Features 節の書き換え（W5）、`_migrations` の全面再設計（必要なら別 WP 化）。
- **見積**: 小（半日）。ただしタグ削除は不可逆なので、実行前にユーザー承認を取ること。

---

### W1（並列可）— `copier update` 適合マトリクスと質問票 diff ガード

- **依存**: W0（タグが確定していること）。
- **所有**: `tests/test_update_path.py`（新規）、`tools/check_questionnaire_diff.py`（新規）、
  `copier.yml`（`_migrations` 追記時のみ）、`.github/workflows/update-path.yml`（新規）。
- **Target**: `tests/test_example.py:1863-1900`（network 依存の `test_example_repo_updates`）。
- **Change**:
  1. `tools/check_questionnaire_diff.py`: 最新リリースタグの `copier.yml`（`!_include` 解決後）と
     HEAD の質問名/`when`/`default` を比較し、**削除・改名・default 変更**があれば
     `_migrations` に該当 version のエントリが無い限り exit 1。出力は `[MISSING MIGRATION] <name>`。
  2. `tests/test_update_path.py`: fixture answers（`example-answers.yml` + `tests/test_recommended_path.py:43` の `FAST_PATHS` の代表 3 件）について、
     旧 ref で生成 → HEAD に `copier update` → (a) conflict なし、(b) `git diff --check` クリーン、
     (c) answers の `_commit` が前進、を検証。旧 ref のレンダリングは tmp にキャッシュして 2 回目以降を速くする。
  3. network 依存の `test_example_repo_updates` は削除し、同等の検証を 2 に置換。
  4. CI: `update-path.yml`（`pull_request` + `workflow_dispatch`）で 1 と 2 を実行。`timeout-minutes: 30`。
- **Acceptance**:
  - 質問名を 1 つ改名した状態で `python tools/check_questionnaire_diff.py` が exit 1 になり、
    `_migrations` を足すと exit 0（両方の実行結果を示す）。
  - `uv run --locked pytest tests/test_update_path.py` が緑で、network を使わない（`--vcs-ref=HEAD` のみ）。
- **非目標**: `_migrations` の全面再設計。

---

### W2（並列可・最大）— タスク定義の宣言的モデル化

- **依存**: なし（W0 と並列可）。
- **所有**: `_tasks.jinja`、下記 5 つのランナーファイル
  （`template/{% if not existing_project and task_runner_effective == '<r>' %}<file>{% endif %}.jinja`
  の `<r>`/`<file>` = `just/justfile`, `task/Taskfile.yml`, `make/Makefile`, `invoke/tasks.py`, `duty/duties.py`）、
  `template/{% if not existing_project and not ros2_cpp %}pyproject.toml{% endif %}.jinja`（タスク表のみ）、
  `.github/workflows/_tasks.yml`、`tests/test_task_runners.py`、`tests/test_recommended_path.py`（タスク名 assert のみ）。
- **Target**: `_tasks.jinja:1-176`（`{% set tasks = tasks + [...] %}` が 8 ブロック）、
  `tests/test_task_runners.py:90-107`。
- **Change**:
  1. §C3 のモデルを `_tasks.jinja` 内で**単一の宣言リスト**として構築（8 回の mutation を廃止）。
     条件は各タスクの `when` に移す。
  2. ランナー別シリアライザを macro に集約し、`&&` 分割ヒューリスティックを廃止（`run` 配列を順に連結）。
  3. `pyproject.toml.jinja:43-131`（`dev = [` 〜 `]`、`strictness == 'none'` / `'basic'` / else の 3 分岐）を
     「base + `{% if strictness in ['recommended','full'] %}` append」に。
  4. `tests/test_task_runners.py` を「7 ランナーそれぞれでタスク名集合 == モデル」の構造比較に変更。
     実行テストは `make/poe/invoke/duty` の `lint` に加え、`test` と `check` も 1 ランナーずつ実走させる。
  5. `AGENTS.md.jinja` のコマンド表と `.github/workflows/_tasks.yml` の task 入力をモデルから導出。
- **Acceptance**:
  - **リファクタ前後で生成物が byte-identical**（`example-answers.yml` と `FAST_PATHS` の各 render を diff）。
    これが確認できるまでテストの書き換えに進まない。
  - `uv run --locked pytest tests/test_task_runners.py tests/test_recommended_path.py` が緑。
  - `make -n lint` / `poe --dry-run` 相当で `run` 配列の順序が保たれる（`&&` の欠落が無い）。
- **非目標**: ランナーの削減（W4）、タスクの追加/削除。

---

### W3（並列可・看板）— Z3 の証人で質問票の全葉を実行検証

- **依存**: W-P（パーサ）、W0（ref 確定）。
- **所有**: `tests/test_witness_matrix.py`（新規）、`tests/matrix/`（新規）、`tools/z3_witnesses.py`（新規）、
  `.github/workflows/witness.yml`（新規）。`tests/test_copier_structure.py` の Z3 関数は**呼ぶだけ**（改変しない）。
- **Target**: `tests/test_copier_structure.py:483-625`（`_when_expr_satisfiable` とパーサ）、
  `tests/test_generated_lint.py:35-85`（`RENDERED_PATHS`）。
- **Change**:
  1. `tools/z3_witnesses.py`: 既存 Z3 エンコーダを再利用し、ゲート変数の充足モデルを
     blocking clause（`solver.add(z3.Not(model))` を繰り返す）で列挙。各モデルを §C4 の answers に写像。
     全直積は爆発するので、対象は「`use_recommended_*` と `project_type`/`include_*`/`oj_kind`」の葉に限定。
  2. `tests/test_witness_matrix.py`:
     - 証人は `tests/matrix/witnesses.jsonl`（§C6 の形式）に出力し、実行は
       `tools/batch.py` に委ねる（`python tools/batch.py tests/matrix/witnesses.jsonl --json`）。
       テスト本体はランナーの終了コードとカバレッジ集計だけを見る。
     - `fast` tier: render（`skip_tasks=True`）→ 例外なし・ファイル集合の不変条件（§C3 の契約）→ `ruff format --check` / `ruff check`。
     - `full` tier: `uv sync` → `pytest` → `basedpyright` → docs build。`@pytest.mark.timeout(550)` を付ける。
     - カバレッジを `tests/matrix/witnesses.json` に書き出し、**未実行の葉が 1 つでもあれば fail**（W4 が `none` を宣言した葉は除外）。
  3. `pyproject.toml` に `markers = ["fast", "full", "slow"]` を登録（現在 `markers` 未登録）。
  4. CI: `witness.yml`。PR は `-m fast` のみ、nightly（`schedule`）で `-m full`。`timeout-minutes` を付ける。
- **Acceptance**:
  - `uv run --locked python tools/z3_witnesses.py --json | jq '.leaves|length'` が 1 以上、かつ全葉が一意。
  - モデルを 1 つ**意図的に壊した** `when`（例: `docs_type` を常に false にする）を入れると、
    未カバーの葉が増えて `test_witness_matrix.py` が fail する（ガードのガードを実演）。
  - `uv run --locked pytest tests/test_witness_matrix.py -m fast` が緑。実行時間を PR コメントに記載。
  - 既存 4,303 行のテストのうち、**文言を固定しているだけの assert** を洗い出し、
    挙動テストに置換 or 削除した件数を報告（削除は W3 の裁量。ただし `test_example.py` の実行テストは残す）。
- **非目標**: Z3 エンコーダの書き換え（バグを見つけたら別途報告のみ）。

---

### W4（W3 の後）— サポートマトリクスの宣言と長尾の整理

- **依存**: W2、W3（カバレッジ結果が出ていること）。
- **所有**: `support.yml`（新規）、`docs/reference/support.md`（新規）、
  `tests/matrix/witnesses.json`（`tier: none` の付与のみ）。
  **`README.md` は触らない**（サポート表は `support.yml` から W5 の `tools/gen_docs.py` が生成する）。
- **Change**:
  1. W3 のカバレッジと実行コストを根拠に `support.yml` を作成。
     第一候補の降格対象: `make`/`poe`/`invoke`/`duty`（`lint` しか実走していない）、`poetry`、
     `loguru`/`picologging`、`pyrefly`/`ty` の片方。
  2. 降格対象は削除ではなく `best_effort` として明記（既存ユーザーの回答を壊さない）。
     削除する場合は `_migrations` と W1 の diff ガードに従う。
  3. `docs/reference/support.md` にサポート表を書き、README 側の表は W5 の生成器に委ねる
     （`support.yml` を入力にする）。
- **Acceptance**:
  - `support.yml` の `supported` に載る全組合せが W3 の `full` tier で実行されている。
  - `docs/reference/support.md` の表と `support.yml` が一致することをテストで担保（W1 の仕組みを流用してよい）。
- **非目標**: 新規 project_type の追加（凍結中。TODO 節16 の方針を維持）。

---

### W5（W-P/W0 の後）— ドキュメントを質問票から生成

- **依存**: W-P（モデル）、W0（README の `--vcs-ref` 削除が済んでいること）。
- **所有**: `README.md`（Features/quickstart 節）、`docs/reference/questionnaire.md`、
  `tools/gen_docs.py`（新規）、`docs/explanations.md`。
- **Target**: D10、`README.md:302`（`Task (default)` の矛盾）、`docs/reference/questionnaire.md`。
- **Change**:
  1. `tools/gen_docs.py`: §C2 のモデルから (a) `docs/reference/questionnaire.md`、
     (b) README の Features 節と mermaid（ゲートの Yes/No 分岐）、(c) サポート表（W4）を生成。
     `--check` で「生成物 == コミット済み」を検査（CI で `--check` を回す）。
  2. README の先頭 10 行以内に TL;DR（`uv init` 不要・`git init` と `copier copy` の 2 コマンド、
     前提: `uv` / `git`）を置き、機能カタログは docs に移して README は ~120 行にする。
  3. `docs/explanations/structure.md` を `docs/explanations.md` の index に追加。
  4. 生成 README の `{{docs_url}}/how-to/run-container` リンクを**実測**する:
     docker + docs の生成物で `docs/how-to/run-container.md` が ship されることは確認済み。
     404 が再現するのは「Pages 未公開時」だけなら**バグではない**ので、その場合は
     TODO 節20 の該当項を「再現せず」と記録して閉じる。生成 `zensical.toml` の `nav` に
     how-to ページが 1 つも入っていない点は別の小修正として直す。
- **Acceptance**:
  - `uv run --locked python tools/gen_docs.py --check` が exit 0。
  - `grep -n 'Task (default)' README.md` が 0 件（`just` が default と一致）。
  - README の `copier copy` 例が W0 後の姿（`--vcs-ref` なし）になっている。
  - mermaid に CTF / scraping / `license_check` が反映されている（現行 `docs/reference/questionnaire.md` と一致）。
- **非目標**: 生成 README（681 行）の削減。これは別 WP とする（W5 では触らない）。

---

### W6（W0 の後・並列可）— 導入のワンコマンド化

- **依存**: W0。
- **所有**: `tools/cli.py`（新規）、`pyproject.toml`（script エントリのみ）、`presets/*.yml`（新規）、
  `docs/tutorials/installation.md`、`docs/tutorials/create-new.md`。
- **Change**:
  1. `python-copier-template new <dir> [--preset <name>] [--ref <ref>]` を実装。
     内部で `tools/detect.py` の `detect()` によりモード（fresh / adopt / update / foreign）を判定し、
     adopt なら `existing_project: true` と `adopt_protect` を、`collisions` があれば警告を出す。
     その後 `copier` を `--trust` 付きで呼ぶ。`--ref` の既定は「最新の fork タグ」。
  2. `presets/` に代表形（library / cli / web-api / data-science / ros2 / micropython / online-judge-*）を用意。
     `example-answers.yml` は全ゲート off の網羅 fixture として残す。
  3. `questions/_common_a.yml:66-72` の `choices` から `web_django` を削除（選択すると abort する罠）。
     削除は W1 の diff ガードを通すこと。
- **Acceptance**:
  - `uv run --locked python tools/cli.py new /tmp/probe --preset library` が対話なしで exit 0。
  - `--preset` 全種で render が成功し、`web_django` が選択肢に存在しない。
- **非目標**: PyPI への実公開（人間の作業。手順のみ docs に書く）。

---

### W9（並列可）— テスト実行コストの削減

- **依存**: W3（`witness.yml` と fast/heavy の分割方針を共有）。**所有権の注意**:
  本 WP は `tests/test_example.py`（現在ユーザーが編集中）に触るため、着手は
  その編集が落ち着いてから。それまで `task test-fast` / `task test-heavy`（実装済み）で凌ぐ。
- **根拠（実測 2026-09-13、16 コア・warm）**: フル 37s / `task test-fast`（`test_example.py` と
  `test_generated_typecheck.py` を除外）17s / `batch --only` 1 ケース 2s。`--durations=25` の上位は
  すべて venv 構築つきテスト:
  `test_template_defaults` 24.3s / `test_template_include_scraping_runs` 20.7s /
  `test_template_web_api_runs_in_process` 16.3s / `test_template_mcp_runs_in_process` 14.8s /
  `test_example_repo_updates` 13.4s（network）。
- **Change**:
  1. `pyproject.toml` に `markers = ["heavy", "network"]` を登録し、`make_venv` /
     `uv sync` / network を使うテストへ `@pytest.mark.heavy` を付ける（`-m "not heavy"` が
     `task test-fast` の file 除外より正確になる）。
  2. **レンダ結果のキャッシュ**: `(answers のハッシュ, テンプレートの指紋)` をキーに
     セッション共有の一時ディレクトリへ render し、複数テストが同じ組合せを再レンダーしない
     （`test_generated_lint.py` / `test_pyproject_fmt.py` は 23 組合せを別々に render している）。
     テンプレートの指紋はファイル名+内容のハッシュ（dirty な作業ツリーを正しく無効化する）。
  3. **venv の再利用**: 生成物の dev 依存は組合せ間でほぼ同一なので、`uv sync` を
     `UV_PROJECT_ENVIRONMENT` 共有 + `--inexact` で 1 つに寄せられないか計測してから決める
     （安易な共有は依存差で偽陽性を生む）。
  4. `task test` は現状維持（フル）。CI は PR で `-m "not heavy"`、nightly でフル。
- **Acceptance**:
  - `uv run --locked pytest -m "not heavy"` が `task test-fast` と同じ集合を選ぶ（件数一致）。
  - キャッシュ導入後、`test_generated_lint.py` + `test_pyproject_fmt.py` の wall time が
    半減以上（前後を `--durations` で示す）。
  - ヘビー tier を外しても、レンダー内容の検証は 1 件も失われない（`--collect-only` の差分で示す）。
- **非目標**: `test_example.py` の実行テスト（venv + 実走）を render のみに置換すること。
  それは検証の意味を落とす。削るのはコストであって被覆ではない。

---

### W8（解決済み）— adopt モードの T1 衝突ポリシー

**決着（2026-09-13、実測に基づく）**: テンプレート側に質問を増やさず、copier の
`--skip`（= API の `skip_if_exists`、"既存なら書かない"）で解く。`tools/detect.py` が
`collisions` を `skip` として返し、そのまま実行できるコマンドをレポートに印字する。
`--overwrite` は使わない（未検出の衝突まで置換するため）。

実測（copier 9.18.1、自前の `.github/workflows/ci.yml` + `renovate.json` を持つプロジェクトへ adopt）:

| レシピ | 結果 |
|---|---|
| フラグ無し | `conflict` → `Interactive session required: Consider using --overwrite`、exit 1。**描画済みのファイルは残る**（half-written） |
| `--overwrite` | 置換される |
| `--skip <path>`（`--overwrite` なし） | 既存は無傷、他は追加。`--overwrite --skip` と**同一のファイル集合**（41 files、diff なし） |

受け入れ済み: `tests/test_detect.py::test_skip_recipe_keeps_existing_files_and_adds_the_rest`
がレポート印字のレシピを実走し、既存 `ci.yml`/`renovate.json` が無傷・README/pyproject が保護・
`.gitleaks.toml` と `_hygiene.yml` が追加、を検証する。

残る任意項目（テンプレート側で保護したい場合のみ。今は不要と判断）:
既存ファイルの存在は copier の描画時に知り得ないため、`--skip` に代わる手段は
「グループ単位の質問を足してファイル名条件で分岐する」しかない
（`_skip_if_exists` は Jinja 非対応 = SPEC §4 で検証済み）。安全性は `--skip` で足りているので、
質問を増やすコストに見合うのは「adopt 利用者が多い」と分かってから。

- **依存**: なし（W0/W-P と並列可）。
- **所有**: `template/{% if git_platform=="github.com" %}.github{% endif %}/**`、
  `template/{% if git_platform == 'gitlab.com' %}.gitlab-ci.yml{% endif %}.jinja`、
  `questions/adoption.yml`、`tests/test_example.py` の adopt テスト。
- **根拠（実測 2026-09-13）**: 自前の `.github/workflows/ci.yml` を持つ既存プロジェクトに
  `copier copy --trust --defaults --overwrite --vcs-ref=HEAD --data-file <detect --answers>` を実行すると、
  `ci.yml` は**テンプレート内容に置換**され、README.md / pyproject.toml は byte-identical のまま保護された。
  つまり SPEC §6 T1 の想定（「ファイル名が違えば共存可能」）と実装（正準名を常時レンダー）が食い違っている。
  `tools/detect.py` はこれを `COLLISIONS` として事前に列挙する（`docs/how-to/detect.md`）。
- **Change**（人間の判断が要る。a+c が既定案）:
  1. (a) 文書化: `docs/tutorials/adopt-existing.md` と detect の `COLLISIONS` で「置換される」ことを明示（実装済み）。
  2. (b) 保護する場合の実装手段は限られる: copier の `_skip_if_exists` は **Jinja 非対応**
     （SPEC §4 で検証済み）なので、「既存なら skip」を条件付きで実現するには質問を足すしかない
     （例 `adopt_keep_existing_ci: bool` を `existing_project` の下に置き、T1 ファイル名を条件化する）。
     質問を増やすコストと、既存 CI を失うコストを比較して決める。
  3. (c) 採用レポート（`_tasks` の `existing_project` 分岐）に「置換された T1 ファイル」を列挙する。
- **Acceptance**:
  - (a) の場合: `tests/test_example.py` に「既存 `ci.yml` が置換される」ことを固定する adopt テストを追加
    （現状の意図を明示。detect の `COLLISIONS` と一致すること）。
  - (b) の場合: `adopt_keep_existing_ci=true` で既存 `ci.yml` が byte-identical のまま残るテスト。
- **非目標**: 既存 CI の解体、既存 workflow へのジョブ単位マージ。

---

### W7（並列可・小）— CI 衛生（timeout とキャッシュ）

- **依存**: なし。
- **所有**: `.github/workflows/*.yml` のうち `_tasks.yml` を**除く**全ファイル、`Taskfile.yml`。
- **Target**: D7。
- **Change**:
  1. 全 workflow に `timeout-minutes` を付与（test 60 / docs 20 / hygiene 10 / それ以外 15）。
  2. `astral-sh/setup-uv` の `enable-cache: true`、`.venv` の `actions/cache`、
     `_docs.yml` の `apt-get install graphviz` と `uvx` 冷起動のキャッシュ。
  3. `_docs.yml:30` の `sleep 60` を `concurrency` で置換。
- **Acceptance**:
  - `grep -rl timeout-minutes .github/workflows | wc -l` が全ファイル数と一致。
  - `uv run --locked pytest tests/test_workflow_security.py` が緑（SHA pin / permissions の既存規約を壊さない）。
- **非目標**: workflow の分割（fast/heavy）は W3 の `witness.yml` と競合するため W3 完了後に検討。

---

## 4. ファイル所有権（同時編集の衝突防止）

| ファイル/領域 | 所有者 | 他 WP の扱い |
|---|---|---|
| git タグ | W0 | 触らない |
| `README.md` | Wave A は W0（`--vcs-ref` 記述の削除のみ）、Wave C は W5（Features/quickstart/サポート表） | **W4 は README を触らない**。表は `support.yml` から W5 の生成器が出す |
| `copier.yml` | W0（`_migrations`）→ W1（追記） | W6 は `choices` 変更を W1 のガード経由で |
| `tools/questionnaire.py` | W-P | W3/W5 は import のみ |
| `tools/z3_witnesses.py`, `tests/matrix/`, `tests/test_witness_matrix.py` | W3 | W4 は `tier: none` の付与のみ |
| `_tasks.jinja`, ランナー生成物, `template/pyproject.toml.jinja`, `.github/workflows/_tasks.yml`, `tests/test_task_runners.py` | W2 | 他は触らない |
| `tests/test_copier_structure.py` | W-P（`_load_questions` のみ） | W3 は Z3 関数を呼ぶだけ |
| その他の `.github/workflows/*.yml` | W7 | W1/W3 は新規ファイルのみ追加 |
| `docs/`, `tools/gen_docs.py` | W5 | W4 は `docs/reference/support.md` のみ、W7 は docs を触らない |
| `support.yml` | W4 | W5 は読むだけ |
| `tools/detect.py`, `tests/test_detect.py` | 実装済み | W6 は import して使う。W8 は参照のみ |
| `tools/adopt.py`, `tests/test_adopt.py` | 実装済み | W6 の wrapper CLI はこれを呼ぶ（`--ref` 判断とロールバックを再実装しない） |
| `tools/pyproject_deps.py`, `tests/test_pyproject_deps.py` | 実装済み | adopt の依存マージ専用。W5 の docs 生成とは独立 |
| `tools/questionnaire.py`, `tools/mcp_server.py` と各テスト | 実装済み | W-P の残り（`_load_questions` 委譲）、W5 は `load_questions()` を使う |
| `Taskfile.yml` の test-fast / test-heavy / mcp | 実装済み | W9 は marker 化のみ |
| adopt の T1 ファイル（`.github` 系 / `.gitlab-ci.yml`）と `questions/adoption.yml` | 変更不要（W8 は `--skip` 方式で決着。触るなら質問追加時のみ） | W6 の `choices` 変更とは別ファイル |

## 5. 実行順（wave）

| Wave | 並列で走らせる WP | 各 WP の前提 |
|---|---|---|
| A | **W0**（直列・ユーザー承認必須）、**W-P** | W0: なし / W-P: なし |
| B | **W1**、**W2**、**W3**、**W7** | W1: W0 / W2: なし / W3: W-P + W0 / W7: なし |
| — | ~~W8~~ 完了（`--skip` 方式） | — |
| C | （追加）**W9** | `tests/test_example.py` の編集が落ち着いてから（W3 と分割方針を共有） |
| C | **W4**、**W5**、**W6** | W4: W2 + W3 / W5: W-P + W0 / W6: W0 |

同一 Wave 内はファイル所有権が排他なので同時に流してよい（README は W5 が単独所有）。
`task check`（root の lint/type-check/test/docs）は Wave ごとに 1 回、統合担当が実行する。

## 6. 委託プロンプトの雛形

```
# Goal
notes/PLAN-improvements.md の <WP-ID> を実装する。

# Constraints
- notes.md §1 の共通規約と §2 の共有コントラクトに従う。
- 触ってよいのは §4 の所有権表で <WP-ID> が所有するファイルのみ。
- mid-flight で formatter / linter / 全体テストを回さない。
- network 依存テストを新設しない。

# Contract
- 受け入れ条件は notes/PLAN-improvements.md の <WP-ID> の Acceptance をそのまま使う。

# Target / Change / Acceptance
（本ファイルの該当節をそのまま貼る）
```

## 7. この計画の完了条件

1. D2/D3 が再現しない（引数なし `copier copy` が exit 0）。
2. 質問票の充足可能な全葉が `tests/matrix/witnesses.json` に登録され、
   `tier != "none"` の全葉に実行済みの証人がある（未実行 0 件。`none` は W4 が宣言した非サポートのみ）。
3. タスク名集合が全ランナーでモデルと一致し、`lint` 以外の `test`/`check` も 1 ランナーで実走している。
4. `copier update` が全 fixture ref で conflict なし、生成物の check が緑。
5. README が <130 行で TL;DR を持ち、`gen_docs.py --check` が緑（ドリフトゼロ）。
6. 全 workflow に `timeout-minutes` があり、`task check` が通る。
7. ~~adopt モードの T1 衝突~~ → **解決済み（W8）**: `detect.skip` を `--skip` に渡すレシピで
   既存ファイルを無傷にしたまま追加できる（実測 + 回帰テスト）。
8. `-m "not heavy"` がフル CI からヘビー tier を正しく外し、レンダー被覆を失っていない（W9）。
