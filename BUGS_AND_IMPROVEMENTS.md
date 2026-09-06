# python-copier-template 改善メモ

copier-python-template v5.4.0 を animetor_eval に適用際の問題点・改善案を記録する。

---

## 1. `use_recommended_*` フラグが `default: true` でも詳細質問が表示される

**深刻度**: 高

**現象**:
`use_recommended_toolchain: true` を設定しても `package_manager` や `task_runner` の質問がスキップされない。
テンプレートの `when` 条件が意図通り動作しない。

**原因推測**:
- `_common_a.yml` の `package_manager.when` は `not use_recommended_toolchain` で正しいが、
  `--defaults` 使用時に `when: false` の内部変数が先に評価され、デフォルト値が上書きされる可能性
- `task_runner_pixi` の条件分岐が `package_manager` の選択に依存するため、初期評価で undefined になる

**回避策**:
全回答をデータファイルで明示的に指定した。

**テンプレート改善案**:
```yaml
# 現状
package_manager:
    when: "{{ not use_recommended_toolchain and not (project_type == 'ros2' and ros2_package_manager == 'pixi') }}"

# 改善案: デフォルト値を use_recommended_toolchain に連動
package_manager:
    type: str
    when: "{{ not use_recommended_toolchain and not (project_type == 'ros2' and ros2_package_manager == 'pixi') }}"
    default: "{{ 'pixi' if project_type == 'ros2' and ros2_package_manager == 'pixi' else 'uv' }}"
```

---

## 2. `docs_type` の選択肢にバージョン依存の不整合

**深刻度**: 中

**現象**:
`web_api` プロジェクトで `use_recommended_docs: false` にした場合、`docs_type` の選択肢に
`zensical` が含まれない。`sphinx` か `README` のみ。

**原因**:
`_common_b.yml` の `docs_type.when` に `web_api` 用の分岐がない。
`zensical` は `library` / `cli` デフォルトの推奨ツールだが、`web_api` では選べない。

**テンプレート改善案**:
```yaml
docs_type:
    choices: |
        {%- if micropython_pkg %}
        - README
        - zensical
        - great-docs
        {%- elif project_type == 'web_api' %}
        - README
        - zensical
        - sphinx
        {%- else %}
        - README
        - zensical
        - sphinx
        - great-docs
        {%- endif %}
```

---

## 3. `type_checker` の選択肢が `pyrefly` / `ty` ではなく `pyright` / `mypy`

**深刻度**: 低 (選択肢名の変更)

**現象**:
README では「basedpyright + pyrefly」と「basedpyright + ty」が謨われているが、
実際の `type_checker.choices` は `pyright` / `my mypy` となっている。

**原因**:
README と `copier.yml` の選択肢名が同期していない。

**テンプレート改善案**:
- README の記述を `pyright` / `mypy` に合わせる
- または `copier.yml` の選択肢を `pyrefly` / `ty` に統一

---

## 4. pixi プロジェクトで `_test.yml` の `uv run --locked tox` が使用不能

**深刻度**: 中 (pixi ユーザーへの影響大)

**現象**:
テンプレートの GitHub Actions ワークフローは `uv` と `tox` に依存している。
`pixi` を選択したプロジェクトでも `_test.yml` 等は `uv` ベースのまま。

**該当ファイル**:
- `.github/workflows/_test.yml` — `uv run --locked tox -e tests`
- `.github/workflows/_tox.yml` — `uv run --locked tox -e ${{ inputs.tox }}`
- `.github/workflows/_dist.yml` — `uvx --from build pyproject-build`

**回避策**:
animetor_eval では既存の CI (`ci.yml`, `quality.yml`) を維持し、テンプレートの CI は採用しない。

**テンプレート改善案**:
```yaml
# package_manager == 'pixi' の場合の分岐
{% if package_manager == 'pixi' %}
- name: Setup pixi
  uses: prefix-dev/setup-pixi@v0.8.1
- name: Run tests
  run: pixi run test
{% else %}
- name: Install uv
  uses: astral-sh/setup-uv@v10.0.0
- name: Run tests
  run: uv run --locked tox -e tests
{% endif %}
```

---

## 5. `renovate.json` の `matchPackageNames` がテンプレート専用の Action に依存

**深刻度**: 低

**現象**:
`renovate.json` の `matchPackageNames` に `actions/checkout`, `astral-sh/setup-uv` など
テンプレートGitHub Actions で使われるパッケージがハードコードされている。

**問題**:
- 別の CI provider を選んだプロジェクトでも除外設定が残る
- 新しい GitHub Action を追加したときに Renovate 更新を手動で再有効化する必要がある

**テンプレート改善案**:
`_release.yml` 等でしか使わない `softprops/action-gh-release` は `matchDepTypes: [action]` で
一括除外するか、逆に「テンプレート管理外の Action のみ更新」ホワイトリスト方式にする。

---

## 6. `.vscode/settings.json` が `uv` / `tox` に依存

**深刻度**: 低

**現象**:
生成された `.vscode/settings.json` に `python.testing.pytestPath` が `uv` ベースの
パス想定で含まれる場合がある。

**テンプレート改善案**:
`package_manager` に応じて VSCode 設定を切り替える jinja 条件を追加。

---

## 7. `_dist.yml` の `python -m $(ls --hide='*.egg-info' src | head -1)` が不安定

**深刻度**: 中

**現象**:
`src/` 直下の最初のディレクトリ名をパッケージ名と仮定して `--version` テストを行う。
この `ls | head -1` は:
- ディレクトリが複数ある場合に最初が意図しないパッケージになる可能性
- `.egg-info` 以外に `_version.py` 等のファイルが最初に来る可能性

**テンプレート改善案**:
```yaml
- name: Test module --version works
  run: python -m {{ import_pkg }} --version
```
`import_pkg` 内部変数 (`_internal.yml` で定義済み) を使用する。

---

## 8. `package_name` バリデーションが `src` を拒否

**深刻度**: 中 (web_api プロジェクト)

**現象**:
`package_name` の正規表現 `^[a-zA-Z][a-zA-Z_0-9]+$` は `src` を有効とするが、
`web_api` では `pkg_dir` 内部変数が `app` になり、`package_name` は単なる識別子として使われる。

**ユーザーの混乱**:
- `web_api` でパッケージ名を求められる意図が不明
- 生成後の `src/app/` と `package_name=app` の関係が分かりにくい

**テンプレート改善案**:
`web_api` の場合は `package_name` 質問をスキップし、内部で `app` に固定する。
またはヘルプテキストで「web_api では app に固定されます」と明示。

---

## 9. `.vscode/tasks.json` が `tox` にハードコード

**深刻度**: 中

**現象**:
テンプレートの `.vscode/tasks.json` に `tox -p` がハードコードされている。
`pixi` パッケージマネージャや `task` タスクランナーを選択したプロジェクトでは使用不能。

```json
{
    "type": "shell",
    "label": "Tests, lint and docs",
    "command": "tox -p",
    ...
}
```

**テンプレート改善案**:
```json
{% if task_runner == 'make' %}
"command": "make"
{% elif task_runner == 'just' %}
"command": "just"
{% elif task_runner == 'task' %}
"command": "task"
{% elif package_manager == 'pixi' %}
"command": "pixi run"
{% else %}
"command": "tox -p"
{% endif %}
```

---

## 10. `periodic.yml` ワークフローが `tox` 専用

**深刻度**: 低 (docs がある場合のみ影響)

**現象**:
リンクチェックワークフローが `tox -e docs -- -b linkcheck` に依存。
Sphinx を使っていないプロジェクトでは無意味。

**テンプレート改善案**:
```yaml
# tox または sphinx docs がある場合のみ生成
{% if task_runner == 'tox' or docs_type == 'sphinx' %}
name: Periodic
...
{% endif %}
```

---

## 11. `make_switcher.py` が `gh-pages` ブランチに依存

**深刻度**: 低

**現象**:
ドキュメントバージョン切り替えスクリプトが `origin/gh-pages` をハードコード。
GitLab Pages や Netlify 等では使用不能。

**テンプレート改善案**:
```python
parser.add_argument(
    "--ref",
    default="origin/gh-pages",
    help="Git ref to list versions from (default: origin/gh-pages)",
)
```

---

## 12. CI ワークフローに `concurrency` 設定がない

**深刻度**: 中

**現象**:
テンプレートの `ci.yml` に `concurrency` グループ設定がない。
同じブランチへの複数プッシュで古いワークフローが実行され続け、リソースを浪費。

**テンプレート改善案**:
```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

---

## 13. CI ワークフローに `permissions` 最小化がない

**深刻度**: 中 (セキュリティ)

**現象**:
デフォルトの `permissions: write-all` のまま。
Supply chain attack のリスクが高まる。

**テンプレート改善案**:
```yaml
permissions:
  contents: read

jobs:
  release:
    permissions:
      contents: write  # 必要なジョブでのみ付与
```

---

## 14. `.github/CONTRIBUTING.md` が Diamond Light Source 固定

**深刻度**: 低

**現象**:
テンプレートの CONTRIBUTING.md に `Diamond Light Source` とDiamond Light Source の Copier テンプレートへのリンクがハードコード。

```markdown
This project was created using the [Diamond Light Source Copier Template](https://github.com/DiamondLightSource/python-copier-template)
```

**テンプレート改善案**:
```
This project was created using the [python-copier-template](https://github.com/kasi-x/python-copier-template).
```
または jinja 変数でカスタマイズ可能にする。

---

## 15. `_release.yml` が `dist/` ではなく `html/` を圧縮

**深刻度**: 低 (動作はするが混乱)

**現象**:
`_release.yml` が `mv html $GITHUB_REF_NAME` として `html/` ディレクトリを圧縮。
`_docs.yml` は `build/html/` をアップロードしているが、`_release.yml` は `html/` を期待。

```yaml
- name: Zip up docs
  run: |
    set -vxeuo pipefail
    if [ -d html ]; then
      mv html $GITHUB_REF_NAME
      zip -r docs.zip $GITHUB_REF_NAME
```

**問題**:
- `_docs.yml` は `build/` をアップロード
- `_release.yml` は `html/` を探す (実際は `build/html/`)

**テンプレート改善案**:
```yaml
- name: Zip up docs
  run: |
    set -vxeuo pipefail
    if [ -d build/html ]; then
      mv build/html $GITHUB_REF_NAME
      zip -r docs.zip $GITHUB_REF_NAME
```

---

## 16. `docs/conf.py` が Diamond Light Source ロゴをハードコード

**深刻度**: 低 (外観)

**現象**:
```python
html_logo = "images/dls-logo.svg"
html_favicon = html_logo
```
Diamond Light Source のロゴがハードコード。

**テンプレート改善案**:
```python
html_logo = "images/logo.svg"
html_favicon = html_logo
```
または jinja 変数 `{{ logo_path }}` にする。

---

## 17. `docs/conf.py` で `requests.get()` を import 時に実行

**深刻度**: 中 (CI での問題)

**現象**:
```python
import requests
...
switcher_json = f"https://{github_user}.github.io/{github_repo}/switcher.json"
switcher_exists = requests.get(switcher_json).ok
```

import 時に HTTP リクエストが発生。オフライン環境やネットワーク制限のある CI でコケる。

**テンプレート改善案**:
```python
import urllib.request
try:
    urllib.request.urlopen(switcher_json, timeout=5)
    switcher_exists = True
except Exception:
    switcher_exists = False
```
または lazy evaluation にする。

---

## 18. `docs/conf.py` が `app.__version__` に依存

**深刻度**: 中 (web_api 以外)

**現象**:
```python
import app
release = app.__version__
```

`library` / `cli` では `app` モジュールが存在しない。`import_pkg` 内部変数を使うべき。

**テンプレート改善案**:
```python
import {{ import_pkg }} as app
```
または `__version__.py` を直接読み込む。

---

## 19. `import app` で `sys.path` 操作がない

**深刻度**: 中

**現象**:
```python
import app
```
だけだが、`sys.path` に `src/` が追加されていない。

**テンプレート改善案**:
```python
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import {{ import_pkg }} as app
```

---

## 20. `_test.yml` で `codecov-action` が毎回実行

**深刻度**: 低

**現象**:
PR ごとに Codecov にアップロード。noisy なコメントが発生。

**テンプレート改善案**:
```yaml
- name: Upload coverage
  if: github.event_name == 'push' && github.ref == 'refs/heads/main'
```

---

## 21. `tox` と `pixi` の環境変数競合

**深刻度**: 中 (pixi ユーザー)

**現象**:
テンプレートは `tox` で `passenv = ["*"]` している。
`pixi` ユーザーが tox を使うと、大量の環境変数が渡されデバッグ困難。

**テンプレート改善案**:
pixi 選択時は tox を使わない (Taskfile 等で置換)。

---

## 22. `_dist.yml` で `python -m $(ls ...)` が sh シェル依存

**深刻度**: 低

**現象**:
```yaml
run: python -m $(ls --hide='*.egg-info' src | head -1) --version
```
Windows の GitHub Actions runner で `ls` が使えない (デフォルトは PowerShell)。

**テンプレート改善案**:
```yaml
run: python -m {{ import_pkg }} --version
```

---

## 23. テンプレートの `docs/` が Sphinx 専用構成

**深刻度**: 中

**現象**:
`zensical` や `great-docs` を選択しても、生成される `docs/` ディレクトリは Sphinx 用。
`docs/conf.py`, `docs/_templates/`, `docs/explanations.md` 等。

**問題**:
- `zensical` は MkDocs fork なのに Sphinx conf.py が生成される
- `great-docs` は Quarto なのに Sphinx 構造が生成される

**テンプレート改善案**:
```jinja
{#- 各 docs_type に応じたディレクトリ構造を生成 #}
{% if docs_type == 'zensical' %}
    {% include 'docs/zensical/' %}
{% elif docs_type == 'great-docs' %}
    {% include 'docs/great-docs/' %}
{% elif docs_type == 'sphinx' %}
    {% include 'docs/sphinx/' %}
{% else %}
    {#- README only - no docs/ directory #}
{% endif %}
```

---

## 24. `README.md.jinja` が未確認

**深刻度**: 未確認

**現象**:
`template/README.md.jinja` の中身を確認していないが、Diamond Light Source への言及がないか要確認。

---

## 25. `.python-version` ファイルが `uv` 専用

**深刻度**: 低

**現象**:
```
template/.python-version  # "3.12" 等
```
`pixi` では使用されない (pixi.toml で Python バージョンを指定)。

**テンプレート改善案**:
```jinja
{% if package_manager == 'uv' %}
# .python-version
3.12
{% endif %}
```

---

## まとめ: 優先度高の改善

### 高優先度 (機能障害)
1. `use_recommended_*` フラグの動作修正 — テンプレートのコア機能
2. `.vscode/tasks.json` の `tox` ハードコード — UX 問題
3. Sphinx 以外の docs_type で Sphinx 構造が生成される問題

### 中優先度 (互換性・セキュリティ)
4. pixi パッケージマネージャ対応 (CI workflows)
5. `docs_type` 選択肢の `web_api` 追加
6. `import_pkg` 変数の `_dist.yml` 活用
7. CI `concurrency` 設定追加
8. CI `permissions` 最小化
9. `docs/conf.py` の `requests.get()` import 時実行

### 低優先度 (改善)
10. `renovate.json` のハードコード
11. `periodic.yml` の tox 依存
12. `make_switcher.py` の gh-pages 固定
13. CONTRIBUTING.md の Diamond Light Source 固定
14. `_release.yml` の html/ パス問題
15. `docs/conf.py` の DLS ロゴハードコード
16. `.python-version` の uv 専用問題

---

*更新: 2026-09-05 — 25件の問題を記録*

---

*更新: 2026-09-05*

---

# 2026-09-06 検証結果(全25項目を現行テンプレートで再確認)

このファイルは animetor_eval への適用時(2026-09-05)のレポート。全項目を
現行 HEAD で再確認した結果、多くは**すでに解決済み**または upstream 由来の
共有ワークフローの誤認だった。以下が現状。

## 解決済み(コード修正済み — 適用時より前に直っていたもの)

- **#4 (pixi で CI が uv/tox 前提)**: 解決済み。`_test.yml` / `_dist.yml` は
  `hashFiles('pixi.lock'/'poetry.lock')` で setup-pixi / setup-uv / poetry を
  出し分け、テストは `task_runner` input(`pixi run -e dev --locked test` 等)
  で駆動する。`_tox.yml` は廃止済み。
- **#9 (`.vscode/tasks.json` の `tox -p` ハードコード)**: 解決済み。
  `task check` を実行する汎用タスクになっている。
- **#10 (periodic.yml が tox 専用)**: 解決済み。lychee によるリンクチェックに
  置き換わり、docs ツール非依存。
- **#12 (CI concurrency 無し)**: 解決済み。`ci.yml` に
  `concurrency: group: ${{ github.workflow }}-${{ github.ref }}` あり。
- **#13 (CI permissions 未最小化)**: 解決済み。全 workflow が
  `permissions: contents: read` で、write は release/docs job のみ。
  `tests/test_workflow_security.py` が強制。
- **#14 (CONTRIBUTING.md が DLS 固定)**: 解決済み。`{{ repo_url }}` ベースに
  書き換わり、docs リンクもこのテンプレートのもの。
- **#15 (`_release.yml` の html/ パス)**: 解決済み。`html/` と `site/` の
  どちらかを拾う分岐 + コメント付き。
- **#16 (DLS ロゴのハードコード)**: 解決済み。テキストロゴ既定、画像ロゴは
  設置手順のコメントのみ。
- **#23 (docs が Sphinx 専用構成)**: 解決済み。`{% if sphinx %}` /
  `{% if zensical %}` / `{% if great_docs %}` で docs ツリー全体が出し分け
  される。zensical は zensical.toml + modules.md(import root は `import_pkg`)。
- **#2 (docs_type に web_api 分岐が無い)**: 解決済み。choices は静的リスト
  `[README, zensical, sphinx, great-docs]` で全 project_type 共通
  (検証に `--data-file` を使う場合、Jinja choices は validation 前に評価され
  ないため静的が正解。micropython で sphinx を選ぶと zensical に
  フォールバックするよう render 側で保護)。

## 今回修正(2026-09-06)

- **#7 (`_dist.yml` の `ls | head -1` 推測)**: 修正。`_dist.yml` に
  `version-command` input を追加し、生成側 `ci.yml` が `import_pkg` から
  正確なコマンド(`python -m <pkg> --version`、web_api は import チェック)を
  渡す。web_api(パッケージが `app`)や data_science(src/ 直下にパッケージが
  無い)で旧ヒューリスティックが壊れていた問題も同時に解消。
- **#17 (`docs/conf.py` が import 時に `requests.get`)**: 修正。
  `except requests.RequestException` で offline ビルドでも docs が落ちない。
- **#18 (`docs/conf.py` が `app.__version__` 依存)**: 修正。
  `{{ import_pkg }}` を使うようになり、library / web_api 両方で正しい
  モジュールを import する。`_api.rst` / `reference.md` も同様。
- **#20 (codecov が毎回実行)**: 修正。`_test.yml` の upload は
  push to main のみに制限。
- **#11 (`make_switcher.py` の gh-pages 固定)**: 修正。`--ref` オプションを
  追加(既定 `origin/gh-pages`、後方互換)。
- **#8 (`package_name` 質問の web_api での意味)**: 対応。
  生成物 README / AGENTS.md に「web_api では `app/` が本体、`package_name`
  は識別子として使われる」旨のガイドを追加(#9 の app/src 関係と同時に)。

## 誤認・該当なし

- **#1 (`use_recommended_*: true` でも詳細質問が出る)**: 現行では再現しない。
  `when: not use_recommended_*` は通常どおり機能し、`--data-file` + 
  `--defaults` の非インタラクティブ生成も全 project_type で検証済み
  (適用時の失敗は #2 の docs_type choices 問題と `--trust` 漏れによるもの)。
- **#3 (type_checker の選択肢名)**: 現行は `pyrefly` / `ty` で README と一致。
  (basedpyright が常時 primary、選択肢は「追加の静的解析チェッカー」。)
- **#5 (renovate.json の matchPackageNames)**: 意図的設計。テンプレートが
  生成・管理する action のみ更新停止するルールで、生成物側の workflow 構成と
  パリティテストで同期している。
- **#6 (`.vscode/settings.json` の uv/tox 依存)**: 該当する設定は存在しない。
- **#19 (docs/conf.py の sys.path 操作)**: 不要。docs ビルド環境にはプロジェクト
  自体が editable install され、conf.py は `{{ import_pkg }}`(今回修正)を
  import する。
- **#21 (tox `passenv = ["*"]`)**: tox 設定は廃止済み(task_runner ベースに移行)。
- **#22 (`_dist.yml` の sh 依存)**: #7 の修正で廃止。
- **#24 (README.md.jinja の DLS 言及)**: 無し(grep で確認)。
- **#25 (`.python-version` が uv 専用)**: 意図的。uv が読むファイルで、pixi は
  `pixi.lock` / `[tool.pixi.workspace]` を使う。 ros2 では distro に応じて
  3.10/3.12 を出し分ける(テストで固定)。

## 見送り(設計判断)

- **#9' (pyproject.toml のコメント量)**: comments は「なぜこの設定か」を
  生成物だけで完結させる意図的なスタイル。外部ドキュメントへの追い出しは
  テンプレート本体と生成物のパリティテストを壊すためしない。
