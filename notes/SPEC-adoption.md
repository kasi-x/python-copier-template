# 仕様: 既存プロジェクトへの柔軟な展開(Adopt モード)

ステータス: **提案(未実装)** — 実装は下記フェーズに分割して TODO 経由で進める。
検証環境: copier 9.18.1(ソース参照は /tmp/copier クローンの実コード)。

## 1. 目的と背景

現状、既存プロジェクトへの適用は `copier copy --force`(全上書き)のみで、
README / pyproject.toml / LICENSE / .gitignore / src 構成など**既存資産を
壊すか、手動で戻すか**の二択。docs/tutorials/adopt-existing.md はこの
全上書きフローを案内している。

本仕様は「**壊さず採用し、欲しい部分だけ後から足せる**」適用フローを
一次機能として提供する。

## 2. ユースケース

| ID | ストーリー | 必要な動作 |
|----|-----------|-----------|
| U1 | 新規プロジェクト(現行) | 従来どおり全レンダー(後方互換) |
| U2 | **既存 repo に採用**: コードはそのまま、CI/hygiene/品質基盤だけ欲しい | 既存ファイルを保護し、欠けている基盤だけ追加 |
| U3 | **選択的採用**: 例えば docs サイトと MCP だけ | 既存保護 + 既存の include_* / docs_type レイヤーで取捨 |

## 3. 設計原則

1. **copier 標準機能のみ**(新規 pip 依存・フレームワークは持ち込まない)。
2. 本リポジトリの確立イディオムを踏襲: 条件付きファイル名
   (`{% if x %}name{% endif %}.jinja` = 空パスは非生成)でレンダー出力を制御。
3. 非対話(`--defaults` + `--data-file`)を完全サポート。
4. 採用後も `.copier-answers.yml` を書き出し、**`copier update` と相互運用**。
5. 既存ファイルの**破壊はデフォルトで起こさない**。全置換(U1)は
   `existing_project: false` の明示的回答で行う。

## 4. 検証済みの copier 機能と制約

| 機能 | 検証結果 | 仕様への影響 |
|------|---------|-------------|
| `_skip_if_exists` | **Jinja 非対応**(`_template.py` が config を生のまま返す) | 回答駆動の保護は **ファイル名条件イディオム**で実装する |
| CLI `--skip VALUE`(複数可) | 実行時に既存ファイルを skip に追加できる | フェーズ0: テンプレ無変更で `--skip` スペルを文書化 |
| ファイル名条件(空パス=非生成) | 本テンプレートの確立イディオム(mcp/ctf/docs 等で実績) | 採用モードの本体 |
| multiselect 質問 | 対応(`_user_data.py: multiselect`) | フェーズ2の `adopt_protect` |
| `.copier-answers.yml` 常時書き出し | copier 標準 | 採用後の `copier update` 互換 |
| 対話時の競合プロンプト | skip 外の既存ファイルは対話確認(`--overwrite` で全上書き) | U1 は対話で個別判断も可能 |

## 5. 新規回答

```yaml
existing_project:
    type: bool
    default: false
    help: |
        Apply this template to an EXISTING project?
        Yes: your README, LICENSE, pyproject.toml, .gitignore,
        CHANGELOG.md, .python-version and src/tests scaffolding are
        protected — only files you do not have yet are added, plus the
        CI / quality infrastructure. No: full scaffold (fresh project).
    when: なし(常に尋ねる。fresh はデフォルト yes の逆向きゲートにしない:
          U1 の全置換を「明示的な No」にしない本案では existing_project
          自体がオプトインのため)
```

フェーズ2(任意の精緻化):

```yaml
adopt_protect:
    type: multiselect
    default: [readme, license, pyproject, changelog, gitignore, python_version, scaffold]
    choices:
        readme: README.md
        license: LICENSE
        pyproject: pyproject.toml
        changelog: CHANGELOG.md
        gitignore: .gitignore
        python_version: .python-version
        scaffold: src/tests パッケージ足場
    when: "{{ existing_project }}"
```

フェーズ1では `existing_project` のみ(保護対象は固定セット、下記ティア)。

## 6. 保護ティアとレンダー条件

### T1 — 常時追加(競合リスク小、採用の主体)

`.github/workflows/*`(hygiene/lint/test/docs/dist)、`.github/actionlint.yaml`、
`.github/zizmor.yml`、`.gitleaks.toml`、`renovate.json`、`cliff.toml`、
`.editorconfig`、`.envrc`、`AGENTS.md`、`.gitlab-ci.yml`(gitlab 時)、
`{% if fair %}` 系(CITATION.cff / REUSE.toml)、`challenges/`(CTF)

- 既存 CI がある場合: 既存 workflow との競合は `docs/how-to/adopt` に
  ジョブ名の衝突回避を案内(ファイル名が違えば共存可能)。

### T2 — existing_project=true で保護(存在すれば skip)

| ファイル | レンダー条件(Phase 1) | Phase 2 の条件 |
|---|---|---|
| README.md | `{% if not existing_project %}` | `{% if not existing_project or 'readme' not in adopt_protect %}` |
| LICENSE | 同左 | `'license' not in adopt_protect` |
| pyproject.toml | 同左 | `'pyproject' not in adopt_protect` |
| .gitignore | 同左 | `'gitignore' not in adopt_protect` |
| .python-version | 同左 | `'python_version' not in adopt_protect` |
| src 足場 / tests / {{ pkg }} フラット / __main__ / logging_setup / agent・tools・prompts | `{% if not existing_project %}` を各ファイル名条件に追加 | `'scaffold' not in adopt_protect` |
| justfile / Taskfile / Makefile / tasks.py / duties.py | 同左(タスクランナー未導入の既存 repo 向け。上書きしない) | ランナー系は protect 選択肢に含めない(未導入なら追加・導入済みなら手動統合を案内) |

- `CHANGELOG.md`: 従来どおり `_skip_if_exists` で常時保護(変更なし)。
- `docs/`: Phase 1 では保護しない(docs ツリーは衝突が少なく、採用の
  主体になりやすい)。Phase 2 で `'docs' in adopt_protect` を検討。

### T3 — 対象外(やらないこと)

- 既存パッケージのリネーム・移動、既存 pyproject への自動マージ
  (deps の自動追記はしない。代わりに採用レポートで案内)。
- 既存 CI の解体。

## 7. 採用レポート(post-generation task)

`existing_project` 時のみ、生成後に次を出力する `_tasks`(上書きしない):

```
Adopt mode: protected files were not touched (README.md, pyproject.toml, ...).
To wire the quality tooling into your own pyproject.toml:
  uv add --dev ruff pytest pytest-cov typos deptry vulture basedpyright ...
Task entry points: see justfile / Taskfile.yml (copy the recipes you need).
CI: .github/workflows/ is ready as-is.
Update this project later with: copier update --trust --vcs-ref=main
```

(実装は `_tasks.jinja` の既存の `_tasks` 生成機構に `existing_project`
ゲートのエントリを1つ追加)

## 8. 導入フロー(ユーザーから見たコマンド)

### フェーズ0 — テンプレ無変更で今すぐ使えるスペル(`--skip` 利用)

```sh
git init --initial-branch=main /path/to/existing-project   # 既存 repo の場合 cd で可
cd /path/to/existing-project
uvx copier copy --trust --vcs-ref=main \
  --skip README.md --skip LICENSE --skip pyproject.toml --skip .gitignore \
  https://github.com/kasi-x/python-copier-template.git .
git add -A && git commit -m "chore: adopt python-copier-template (infra only)"
```

### フェーズ1 — `existing_project: true`(推奨フロー)

```sh
uvx copier copy --trust --vcs-ref=main \
  --data existing_project=true \
  https://github.com/kasi-x/python-copier-template.git /path/to/existing-project
```

### 採用後の更新

```sh
uvx copier update --trust --vcs-ref=main   # docs/tutorials/adopt-existing.md の
git diff                                   # 差分確認フローに従う
```

## 9. エッジケース

| ケース | 扱い |
|---|---|
| 既存パッケージ名が回答 package_name と不一致 | 保護モードでは src 足場を触らないため影響なし。U1(全置換)では従来どおり一致させる |
| 既存 pyproject に ruff/pytest が無い | 採用レポートが dev deps の追加コマンドを案内。タスク実行は自分の pyproject に依存 |
| LICENSE の二重化 | 保護対象。SPDX/REUSE は fair 選択時のみ生成で既存表記と干渉しない |
| monorepo のサブディレクトリ適用 | `copier copy` の dst にサブディレクトリを指定すれば可。answers ファイルはその配下に書かれる点を docs に記載 |
| `copier update` 時に保護ファイルが新規追加される | 意図的(テンプレ改良の享受)。`git diff` レビュー → 不要なら削除、を adopt-existing.md に追記 |
| docs_type=README 以外で docs/ 既存 | Phase 1 では非保護(docs ツリーは衝突が少ない)。競合時は対話プロンプト |

## 10. テスト計画

1. `existing_project=true` レンダー: 保護対象ファイルが1つも生成されない
   こと、T1 の基盤(.github/workflows、.gitleaks.toml、renovate.json、
   AGENTS.md 等)は生成されること(generated_lint matrix に adopt パス追加)。
2. 既存ファイル保護: 事前に README.md/pyproject.toml を配置した dst に
   レンダーし、内容が**1バイトも変わらない**こと。
3. 採用レポート: post-gen task の出力に保護対象と wiring コマンドが含まれる
   こと(--trust ランで capture)。
4. `copier update`: 採用レンダー → HEAD テンプレートで update → 差分が
   期待どおり(新規ファイル追加・既存保護ファイルは non-conflict)であること。
5. 全ランナー × adopt のタスクセット適合(test_task_runners と同一の保証)。

## 11. 実装フェーズ

- **P0(即時・無変更)**: adopt-existing.md に `--skip` スペル(§8 フェーズ0)を追記。
- **P1**: `existing_project` 回答 + T2 ファイル名条件 + 採用レポート task +
  テスト(§10 の1〜3)。
- **P2**: `adopt_protect` multiselect + docs 保護の検討 + update テスト(§10 の4)。

## 12. 非目標

- 既存 pyproject へのセクション自動マージ(TOML 編集は壊れやすい。レポート案内に留める)
- copier 以外の適用手段(cookiecutter 等)の対応
- 既存コードの解析による質問の自動回答
