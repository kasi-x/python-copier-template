# Strategy: エラー検知・追従の仕組み

このドキュメントは「copierテンプレートの完成度を継続的に保つための検知・追従の仕組み」を
実装可能な粒度まで具体化したものです。**別セッション/別エージェントがこのファイルだけを読んで
再現できる**ことを目的に、対象ファイル・関数名・コマンド・完了条件まで明記します。

## 実装ステータス（2026-09-05 更新・commit a82f9a46）

①②③④-a④-b は実装済み。仕様からの差分と、実装時に判明したことを以下に記す。

- **②**: `git remote add/remove` ではなく URL 直 fetch（`git fetch <URL> main` →
  `HEAD..FETCH_HEAD`）で実装。名付きリモートを触らないので、まっさらなチェックアウトから
  毎回実行できる。
- **①**: 「現時点未確認」だった `_docs.yml` の publish 挙動は `publish` 入力（既定 true、
  CI は変更なし）を追加して解決。`scheduled-check.yml` は `publish: false` で build のみ。
- **③**: pip-audit は 1 workflow 1 関心の方針どおり、独立した `dependency-audit.yml`
  （木曜 07:00）にした。
- **④-a**: 実装時に RENDERED_PATHS の大半（12パス）で実 drift を検出し、テンプレート
  ソース 9 ファイルを修正した（`test_qa.py.jinja` / `test_flake8.py.jinja` の幅依存
  assert メッセージ、web_api の jinja ブロック由来の空行と settings.py の URL 結合、
  ctf のパス結合と subprocess 呼び出し、`explore.py` の空行）。原因は example-answers
  （重いテスト層）が `allow_japanese: true`（幅120）しか通っていなかったこと。
  RENDERED_PATHS は allow_japanese を跨がないため、`JAPANESE_VARIANTS` を別途追加した。
  両幅で安定させる手法: 短縮（≤88 行）か、magic trailing comma、暗黙結合の部分間コメント。
- **計画外の追加修正**（緑ベースライン復元のため実施）: check-yaml に copier.yml を除外
  （multi-document YAML で lint job が既に赤だった）、extensions.py の `github_username()`
  本体復旧（docstring のみで本体が欠損 → type-check エラー + author/org 既定値機能が
  死んでいた）。

背景となる調査（2026-09、このセッションで実施）は本文中に埋め込んであります。ここに書かれた
現状認識（ファイルパス・行番号・既存の挙動）は調査時点のものなので、実装前に該当ファイルを
読み直して前提が変わっていないか確認してください。

## MECEフレームワーク（前提）

エラー・ズレの発生源は5分類、検知タイミングは4分類。両者は独立な軸。

**発生源**
- A. テンプレート内部の静的品質（jinja構文・YAML・質問票ロジック）
- B. レンダリング〜生成物の動的正しさ（render成功・lint・型・テスト・build）
- C. 外部パッケージ・ツールチェーンの経年劣化（バージョンpin、ツール自体の挙動変化）
- D. 上流フォーク（DiamondLightSource/python-copier-template）の追従
- E. メタ事故（開発ツールチェーン自体がテンプレート規約を壊す。例: pre-commitフックの誤爆）

**検知タイミング**
1. コミット前（pre-commit）
2. push/PR時CI
3. 定期実行（スケジュール。コード変更ゼロでも発火する唯一の経路）
4. 論理的検証（Z3。コード実行なしで数学的に充足可能性を証明）

現状のマッピング（詳細は各セクション。✅ = 2026-09-05 実装済み）:

| | 1: pre-commit | 2: push/PR CI | 3: 定期実行 | 4: Z3 |
|---|---|---|---|---|
| A | ruff/typos | `test_machine_gate.py` | — | `test_copier_structure.py` |
| B | — | `test_example.py`(重)/`test_generated_lint.py`(軽=ruff check + format)/`test_generated_typecheck.py`(deps込み) | ✅ `scheduled-check.yml`(火曜) | — |
| C | — | renovate PR時のみ | `check-upstream.yml`(月)/`lockFileMaintenance`/✅ `dependency-audit.yml`(木)/✅ copier ceiling | — |
| D | — | — | ✅ `check-upstream-fork.yml`(火曜) | — |
| E | `.jinja`/`copier.yml` 除外 | — | — | — |

かつての**穴①（B×3）、②（D）、③（Cの未カバー: copier pin / pip-audit）、
④（Bの軽量検査の拡充）はすべて実装済み**。⑤（Z3充足可能性×テストカバレッジの突き合わせ）と
⑥（pre-commitフック事故の一般的な再発防止テスト）は別途・専門性が高いためこのドキュメントの
対象外（着手時は新しい `Strategy-*.md` か本ファイルへの追記で扱う。TODO.md セクション15 も参照）。

---

## ① 定期フル検証（B×3）

### 目的
コードを一切変更していなくても、外部ツールチェーン（ruff / basedpyright / pyrefly / FastAPI /
SQLAlchemy 等）の進化で生成物が壊れることがある。今のCIは push/PR でしか走らないため、
「誰も気づかないまま何ヶ月も壊れている」状態が起こりうる。今日実際に見つけた
`test_qa.py.jinja` の regex 幅依存バグ（ruff-formatが `line-length` によって挙動を変える）も
この種の drift の一種で、コードは触っていないのに `allow_japanese` の値次第で通ったり
落ちたりしていた。

### 現状
- `.github/workflows/ci.yml` は `on: push (main, tags) / pull_request` のみ。
  `lint`(→`_tasks.yml` task=lint,type-check) / `test`(→`_test.yml`) / `docs`(→`_docs.yml`) の
  3ジョブを実行している。これがそのまま「フル検証」の中身。
- スケジュールトリガーを持つのは `check-upstream.yml`（週次、hardcoded pin専用）、
  `periodic.yml`（週次、リンクチェックのみ）、`scorecard.yml`（週次、セキュリティ姿勢）、
  `new_python.yml`（年次、GitHub issueを開くだけ）の4本。**「ci.ymlと同じ検証を定期的に回す」
  ワークフローは存在しない。**

### 実装手順
1. 新規ワークフロー `.github/workflows/scheduled-check.yml` を作る。中身は `ci.yml` の
   `lint` / `test` / `docs` ジョブをそのまま `workflow_call` 経由で再利用する（`_tasks.yml` /
   `_test.yml` / `_docs.yml` は既に `on: workflow_call` なのでそのまま呼べる）。
   `example` / `release` ジョブは push/tag前提のロジックなので含めない。
   `required-checks-passed` もPRゲートなので不要。

   ```yaml
   name: Scheduled full check

   permissions:
     contents: read

   on:
     workflow_dispatch:
     schedule:
       # ci.yml相当をコード変更なしで週次再実行し、外部ツールチェーンの
       # drift（ruff新ルール・basedpyright挙動変化・依存メジャー更新等）を
       # 拾う。check-upstream.yml(月曜6:00)・periodic.yml(水曜8:00)・
       # scorecard.yml(土曜1:30)と曜日を分けて、失敗時にどのワークフローが
       # 何を検知したか区別しやすくする。
       - cron: "0 7 * * TUE"

   jobs:
     lint:
       uses: ./.github/workflows/_tasks.yml
       with:
         task_runner: task
         task: lint,type-check

     test:
       uses: ./.github/workflows/_test.yml
       with:
         runs-on: ubuntu-latest
         task_runner: task

     docs:
       uses: ./.github/workflows/_docs.yml
       with:
         task_runner: task
       permissions:
         contents: write

     open-drift-issue:
       name: Open issue on drift
       needs: [lint, test, docs]
       if: always() && contains(needs.*.result, 'failure')
       runs-on: ubuntu-latest
       permissions:
         issues: write
       steps:
         - env:
             GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
             GH_REPO: ${{ github.repository }}
             RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
           run: |
             existing=$(gh issue list --search "Scheduled full check failed" \
               --state open --json number --jq 'length')
             if [ "$existing" -eq 0 ]; then
               gh issue create \
                 --title "Scheduled full check failed (no code change involved)" \
                 --body "The weekly full check (lint/type-check/test/docs, same jobs as ci.yml) failed with no repo changes involved. This usually means an external toolchain (ruff, basedpyright, a pinned dependency's latest release, ...) changed behaviour. See: $RUN_URL"
             else
               echo "An issue for this drift is already open; skipping."
             fi
   ```

2. `docs`ジョブは `permissions: contents: write` を要求する（gh-pagesへのpush権限。
   `ci.yml`の`docs`ジョブが同じ権限を持つのを踏襲）。**スケジュール実行でdocsを実際にpublish
   したくない場合**は、`_docs.yml`が`publish`のような入力を取れるか確認し、なければ
   `docs`ジョブは「buildのみ・publishしない」ように`_docs.yml`側にオプションを足すか、
   `scheduled-check.yml`では`docs`ジョブを外して`lint`+`test`のみにするかを判断する
   （どちらを選ぶかは実装時に`_docs.yml`の中身を読んで決める。現時点未確認）。

### 検証方法
- `workflow_dispatch`で手動実行し、GitHub Actions上で3ジョブがpush/PR時と同じ内容を
  実行することを確認する。
- 意図的に生成物を壊す変更（例: `template/pyproject.toml.jinja`のruff line-lengthを
  一時的に変える）をローカルで試し、`task test`が失敗することを確認してから戻す
  （＝このワークフローが検知すべき失敗パターンを再現できることの確認。実際にpushはしない）。

### 完了条件
- `scheduled-check.yml`が週次でGitHub Actions上に登録され、`workflow_dispatch`で
  手動発火できる。
- 失敗時に重複しないissueが1件だけ立つ（`check-upstream.yml`の`gh issue list --search`パターンを
  踏襲済みなので、同じロジックで担保される）。

### 見積規模
- 小〜中。新規ワークフローファイル1つ。既存の`_tasks.yml`/`_test.yml`/`_docs.yml`をそのまま
  呼ぶだけなので新規ロジックは「失敗時issue作成」部分のみ。

---

## ② 上流フォーク追従（D）

### 目的
`kasi-x/python-copier-template`（このリポジトリ、`origin`）は
`DiamondLightSource/python-copier-template`（`upstream`）のフォークで、大きく発展・分岐している
（web_api再設計、online_judge、scraping、CTF等、本家に無い機能が多数）。本家がバグ修正や
セキュリティ修正をmainに積んだとき、それに気づく仕組みが現状ゼロ。

### 現状（調査時点の事実）
- `git remote -v` で `upstream` が `DiamondLightSource/python-copier-template` を指すよう
  既に登録されている。
- 調査時点（2026-09）では `git log --oneline main..upstream/main` が0件（本家に追従できている）。
  ただしこれは「たまたま追いついている」だけで、仕組みとして保証されていない。
- 紛らわしい点: 既存の `.github/workflows/check-upstream.yml` という名前のワークフローが
  **既に存在する**が、これは`tools/check_upstream.py`（ハードコードpinのバージョン照合。
  micropython/CUDA/ROS2 EOL/Python floor/Postgres/Ubuntu）専用で、**gitのフォーク追従とは
  無関係**。名前だけ見ると誤解しやすいので、新設するワークフローには明確に別名を付けること。

### 実装手順
1. `tools/check_upstream_fork.py` を新設する（`tools/check_upstream.py`とは別ファイル。
   後者の内部関数を流用する必要はない — gitコマンドの薄いラッパーで十分）。

   ```python
   #!/usr/bin/env python3
   """Check whether upstream (DiamondLightSource/python-copier-template) has
   commits on main that this fork hasn't reviewed yet.

   This is a *different* concern from tools/check_upstream.py (which tracks
   hardcoded version pins like MicroPython/CUDA/ROS2 EOL): this script
   tracks the git history of the upstream fork relationship itself. Exits 1
   when upstream/main has commits not reachable from HEAD (see .github/
   workflows/check-upstream-fork.yml, which opens an issue on drift).
   """

   from __future__ import annotations

   import subprocess
   import sys

   UPSTREAM_URL = "https://github.com/DiamondLightSource/python-copier-template.git"


   def run(*args: str) -> str:
       return subprocess.run(args, check=True, capture_output=True, text=True).stdout


   def main() -> None:
       run("git", "remote", "remove", "upstream-check")  # ignore if absent; wrap in try below
       try:
           run("git", "remote", "add", "upstream-check", UPSTREAM_URL)
       except subprocess.CalledProcessError:
           pass
       run("git", "fetch", "upstream-check", "main", "--quiet")
       commits = run("git", "log", "--oneline", "HEAD..upstream-check/main").strip()
       if commits:
           print("Upstream has new commits not yet reviewed:\n")
           print(commits)
           print(
               "\nReview with: git fetch https://github.com/DiamondLightSource/"
               "python-copier-template.git main && git log HEAD..FETCH_HEAD"
           )
           sys.exit(1)
       print("Up to date with upstream/main.")


   if __name__ == "__main__":
       main()
   ```

   （実装時の注意: `git remote remove` の失敗を握りつぶす雑な実装例。実際に書くときは
   `git remote add` が既に存在するリモート名でも安全に再実行できるよう、素直に
   `git ls-remote` + 一時ディレクトリでの `git fetch` にするか、`try/except` を整理すること。
   要件は「毎回まっさらな状態から実行できる」ことだけ。）

2. 新規ワークフロー `.github/workflows/check-upstream-fork.yml`:

   ```yaml
   name: Check upstream fork

   permissions:
     contents: read

   on:
     workflow_dispatch:
     schedule:
       # DiamondLightSource/python-copier-template の新規コミットを検知。
       # check-upstream.yml(pin追従、月曜)とは別物 — 名前の混同注意。
       - cron: "0 6 * * TUE"

   jobs:
     check:
       runs-on: ubuntu-latest
       permissions:
         issues: write
         contents: read
       steps:
         - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
           with:
             persist-credentials: false
             fetch-depth: 0
         - id: check
           run: python3 tools/check_upstream_fork.py
         - if: failure() && steps.check.outcome == 'failure'
           env:
             GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
             GH_REPO: ${{ github.repository }}
           run: |
             body=$(python3 tools/check_upstream_fork.py 2>&1 || true)
             existing=$(gh issue list --search "Upstream has new commits" \
               --state open --json number --jq 'length')
             if [ "$existing" -eq 0 ]; then
               gh issue create --title "Upstream has new commits to review" --body "$body"
             else
               echo "An issue for this drift is already open; skipping."
             fi
   ```

3. （任意・将来拡張。今回のMVPには含めない）issueだけでなく draft PR
   （`git merge upstream/main --no-commit --no-ff` の結果をpushしてPRを開く）まで自動化する案は、
   このフォークが構造的に大きく分岐している（web_apiのtop-level app/化等）ため
   コンフリクトが常態化しやすく、ノイズになる可能性が高い。まずはissue通知のみで運用し、
   実際のマージはレビュー担当者が `git fetch upstream main && git log HEAD..upstream/main` を
   手動で見て判断する。

### 検証方法
- ローカルで `python3 tools/check_upstream_fork.py` を実行し、`Up to date with upstream/main.`
  と出ること（調査時点で確認済み: `main..upstream/main` は0件）。
- 意図的に `HEAD~5` をチェックアウトした状態で実行し、drift検知（exit 1 + コミット一覧表示）が
  機能することを確認する。

### 完了条件
- `check_upstream_fork.py` がローカル・CI両方で実行できる。
- `check-upstream-fork.yml` が週次で登録され、drift時に重複しないissueを1件作る。
- 既存の `check-upstream.yml`（pin専用）と名前・役割が明確に区別されている
  （README/TODO.mdへの一言注記も推奨）。

### 見積規模
- 小。既存の`check-upstream.yml`のissue作成パターンをほぼそのまま踏襲できる。

---

## ③ copier自体のpin + pip-auditのルート適用（Cの未カバー項目）

### 目的その1: copierのバージョン制約
`pyproject.toml`の`dev`グループに `"copier",` とだけ書かれており、**バージョン制約が一切ない**。
copierは過去に破壊的変更を経験してきたツールで（このセッション中にも
`copier.errors.UserMessageError` / `_user_data.py`の内部実装を実際に確認している）、
`renovate`の`lockFileMaintenance`が`uv.lock`を定期的に最新へ更新する設定になっているため、
**ある日いきなりメジャーバージョンが上がったcopierで全テストが壊れる**リスクがある。
既存の `mcp[cli]>=2.0,<3`（TODO.md項目5、「v1→v2事故の再発防止」）と同じ考え方を適用する。

- 調査時点の解決バージョン: `copier==9.18.1`（`uv.lock`より）。PyPI最新も同じく9.18.1。

### 実装手順（pin）
1. `pyproject.toml`の該当行を変更:
   ```diff
   -    "copier",
   +    "copier>=9,<10",
   ```
2. `docs/explanations/template-dev.md`（または`TODO.md`の該当箇所）に一言、
   「copierは`<10`でメジャー更新を止めている。上げるときは`tests/`全体（特に
   `run_copy`のシグネチャ・`copier.errors`の例外クラス）を必ず再検証してから」という注記を残す。

### 目的その2: copierのメジャー更新をdrift検知に載せる
`tools/check_upstream.py`は現状、`template/pyproject.toml.jinja`（＋`_shared/pyproject-*.toml.jinja`）
に書かれた**生成物側**のPyPI floorしか見ておらず、**ルートリポジトリ自身の`dev`依存**
（copier含む）は対象外。

### 実装手順（drift検知への追加）
1. `tools/check_upstream.py`の`extract_pins()`（155行目付近）に、ルート`pyproject.toml`の
   `copier>=9,<10`のような制約を読んで`Pin`を追加するブロックを足す:
   ```python
   # copier itself: this repo's own dev dependency, not a template floor.
   # Unlike the PyPI-floor pins above (which check the *floor* still
   # exists), this checks whether a newer *major* than our ceiling has
   # shipped -- that's the drift signal worth a human look, since a copier
   # major bump can change run_copy()'s signature / exception types (see
   # docs/explanations/template-dev.md).
   root_pyproject_src = (TOP / "pyproject.toml").read_text()
   copier_m = re.search(r'"copier>=(\d+),<(\d+)"', root_pyproject_src)
   if copier_m:
       floor, ceiling = copier_m.group(1), copier_m.group(2)
       pins.append(Pin(name="copier ceiling (root pyproject.toml)", current=f">={floor},<{ceiling}", checkable=True))
   ```
2. `_resolve_one()`（333行目付近）に分岐を追加:
   ```python
   if name.startswith("copier ceiling"):
       return pypi_latest("copier")
   ```
3. `_is_drift()`（357行目付近）の`triggers`辞書に追加。「latestのメジャーが`ceiling`以上」を
   drift条件にする（文字列比較ではなくメジャー番号の数値比較にすること。既存の
   `_parse_version`ヘルパー、234行目付近、が使えるはず — 実装時に確認）:
   ```python
   if name.startswith("copier ceiling"):
       ceiling = int(current.split("<")[1])
       latest_major = _parse_version(upstream)[0] if upstream else None
       drift = latest_major is not None and latest_major >= ceiling
       msg = (
           f"[DRIFT]  {name}: ceiling <{ceiling} but latest is {upstream}"
           if drift
           else f"[ok]     {name}: {current} (latest {upstream})"
       )
       return drift, msg
   ```
   （`_is_drift`は現状「exact_match」と「triggers（文字列包含）」の2パターンで分岐しており、
   数値比較が必要なcopierのケースはどちらにも綺麗に嵌らない。上記のように専用の早期return
   ブロックを`_is_drift`の先頭付近に足すのが素直。実装時に既存コードの構造を見て調整すること。）

### 目的その3: ルートリポジトリ自身へのpip-audit適用
生成物向けの`_tasks.jinja`には`audit`タスク（pip-audit、network依存のため`check`から独立、
TODO.md項目7で意図的に分離済み）があるが、**テンプレート本体（ルート）のTaskfile.ymlには
`audit`タスクが存在しない**。`pip-audit`自体はルートの`dev`依存に既に入っている
（`pyproject.toml`の`dev`グループに`"pip-audit>=2.9.0,<3.0",`が存在——依存はあるのに
未使用）。renovateの`vulnerabilityAlerts`はGitHub Advisory経由でカバーしているが、
OSVベースのpip-auditとは情報源が異なるため、生成物向けと同じ理由でルート自身にも適用する
価値がある。

### 実装手順（pip-audit）
1. `Taskfile.yml`に生成物の`_tasks.jinja`と同じ発想のタスクを追加:
   ```yaml
     audit:
       desc: Audit dependencies for known vulnerabilities (network; not part of check)
       cmd: uv run --locked pip-audit
   ```
2. ①で作る`scheduled-check.yml`（または独立した新規ワークフロー。1ワークフロー1関心の
   既存方針に従うなら独立ファイル`dependency-audit.yml`が望ましい）に週次で`task audit`を
   実行するジョブを追加。失敗時のissue作成パターンは①・②と同じものを踏襲する。

### 検証方法
- `uv run --locked pip-audit` をローカルで実行し、正常終了することを確認。
- `uv run pytest`が`copier>=9,<10`のpin変更後も全件green（このセッションで確認した
  `222 passed, 1 xfailed`から退行しないこと）。

### 完了条件
- `pyproject.toml`の`copier`にバージョン制約が入っている。
- `tools/check_upstream.py --offline`の出力に「copier ceiling」の行が追加され、
  `--offline`無しで実行するとPyPI最新版と比較したdrift判定が出る。
- `task audit`がルートで実行できる。

### 見積規模
- 小。3つとも既存パターンの横展開。

---

## ④ Bの軽量検査の拡充（test_generated_lint.pyの拡張）

### 目的
`test_generated_lint.py`は現状 `ruff check`のみを`RENDERED_PATHS`（`FAST_PATHS`+`EXTRA_PATHS`、
`skip_tasks=True`で`uv sync`なし）に対して実行している。今日実際に踏んだ
`test_qa.py.jinja`のバグ（`ruff format`が`line-length`次第で挙動を変える）は、**この軽量層に
`ruff format --check`が無かったせいで、重い`task_example.py`のテスト（一部の組み合わせのみ）
まで到達しないと検出できなかった**。同様に`basedpyright`/`pyrefly`も軽量層には存在せず、
広い組み合わせでの型ドリフトは重いテストの狭いカバレッジでしか拾えない。

この節は2段階に分ける。コストと価値が異なるため。

### ④-a: `ruff format --check` の追加（低コスト・即着手可）
`ruff format`は依存解決不要（importが実際に存在するか気にしない、純粋に構文・スタイル）。
`ruff check`と全く同じ条件（`skip_tasks=True`、依存インストール無し）で追加できる。

1. `tests/test_generated_lint.py`に新しいテスト関数を追加（既存の
   `test_generated_project_is_ruff_clean`のすぐ下、同じ`RENDERED_PATHS`
   パラメトライズを使う):
   ```python
   @pytest.mark.parametrize("answers", RENDERED_PATHS, ids=[_id(a) for a in RENDERED_PATHS])
   def test_generated_project_is_ruff_format_clean(tmp_path: Path, answers: dict[str, object]):
       """The rendered tree must already match `ruff format`'s output.

       A .jinja source whose static content only happens to match one
       line-length setting's formatting (e.g. allow_japanese=True's 120 vs
       False's 88) breaks `task check` for the other setting on every run.
       ruff format doesn't need the project's dependencies installed (it's
       pure syntax/style), so this runs in the same skip_tasks=True tier as
       test_generated_project_is_ruff_clean.
       """
       run_copy(
           src_path=str(TOP),
           dst_path=tmp_path,
           data={**BASE, **answers},
           vcs_ref="HEAD",
           defaults=True,
           unsafe=True,
           overwrite=True,
           skip_tasks=True,
       )
       ruff = _ruff_bin()
       proc = subprocess.run(
           [str(ruff), "format", "--check", "--no-cache", "."],
           cwd=tmp_path,
           capture_output=True,
           text=True,
           check=False,
       )
       assert proc.returncode == 0, (
           f"generated project is not ruff-format-clean under its own [tool.ruff]:\n{proc.stdout}{proc.stderr}"
       )
   ```
2. **重要**: `RENDERED_PATHS`は`allow_japanese`の両方の値（line-length 88/120）を
   またいでいない可能性が高い（`BASE`の値を確認すること — `tests/test_recommended_path.py`の
   `BASE`辞書に`allow_japanese`が無ければ質問のdefault値1本しか通らない）。今日のバグを
   本当に再現・防止できる形にするには、`RENDERED_PATHS`とは別に
   `{"project_type": "cli", "allow_japanese": True}` / `{"project_type": "cli", "allow_japanese": False}`
   の両方を明示的にパラメータへ加えるか、既存`RENDERED_PATHS`の代表1パスに
   `allow_japanese`違いのバリエーションを追加する。実装時に`BASE`の中身を確認してから
   このテストのパラメータリストを決めること。

### ④-b: 依存インストールを伴う軽量型チェック層の新設（中コスト・別PRでも可）
`basedpyright`/`pyrefly`は対象パッケージの依存が解決できないと`reportMissingImports`だらけに
なり、意味のある検査にならない。つまり`skip_tasks=True`のままでは使えず、**`uv sync`相当は
避けられない**。ただし`test_example.py`の最重量テスト（pytest本体・`pyproject-build`・
`twine check`・docsビルドまで含む）ほどの重さは不要。

1. 新規ファイル`tests/test_generated_typecheck.py`を作る。`test_generated_lint.py`と
   同じ`RENDERED_PATHS`（`from test_recommended_path import FAST_PATHS`、
   `from test_generated_lint import EXTRA_PATHS`のように再利用するか、循環import回避のため
   `EXTRA_PATHS`を`test_recommended_path.py`側に移すか——既存の`test_generated_lint.py`冒頭の
   docstringにある「なぜEXTRA_PATHSがここにあるか」を読んで、循環しない置き場所を選ぶこと）
   を使い、各パスで:
   - `run_copy(..., skip_tasks=True)`
   - `uv sync`相当（`subprocess.run(["uv", "sync"], cwd=tmp_path)`。generated projectには
     `uv.lock`が無い状態からのsyncになるため初回は依存解決が走る。CI/ローカルの実行時間への
     影響を事前に計測すること — 全`RENDERED_PATHS`数 × sync時間 が許容範囲か確認してから
     マージする）
   - `uv run basedpyright` / `uv run pyrefly check` を実行し、returncode 0を assert
   - pytest本体・docsビルド・build/twineは**含めない**（それらは既存の`test_example.py`の
     役割のまま残す）

2. 実行時間が許容できない場合の代替案: 全`RENDERED_PATHS`ではなく、
   `test_example.py`が現状カバーしていない project_type だけに絞る（重複を避けてCI時間を
   節約する）。どの組み合わせが未カバーかは、`test_example.py`内で`make_venv`/`task check`を
   呼んでいる関数の`copy_project`/`copy_project_recommended`引数を洗い出して突き合わせる。

### 検証方法
- ④-aは`uv run pytest tests/test_generated_lint.py -k ruff_format`で単体実行し、
  全パラメータがpassすることを確認。
- ④-aを追加した状態で、意図的に`_shared/`配下の`.jinja`に幅依存の1行を仕込み、
  テストが実際にFAILすることを手元で確認してから戻す（＝今日の実バグを再現できることの検証）。
- ④-bは実行時間を計測し、CIのタイムアウト設定（`pytest-timeout`、現状550秒目安）内に
  収まるか確認する。

### 完了条件
- ④-a: `test_generated_lint.py`に`ruff format --check`のテストが追加され、
  `allow_japanese`の両方の値が最低1つのパスでカバーされている。
- ④-b: `test_generated_typecheck.py`が新設され、`RENDERED_PATHS`（または明示的に選んだ
  サブセット）に対して`basedpyright`/`pyrefly`がdeps込みで走る。

### 見積規模
- ④-a: 小。既存テストのコピー+微修正。
- ④-b: 中。新規ファイル1つ、CI時間への影響を要計測。

---

## 実装順序の推奨（2026-09-05 完了）

依存関係は無い（4つとも独立）。着手コストの低い順（✅ = 実行済み。実際にはこの順で実施した）:
1. ✅ ③のcopier pin（1行変更 + drift検知1ブロック追加）
2. ✅ ④-a（既存テストの拡張。予想どおり実バグを12件検出し、ソース修正を伴った）
3. ✅ ②（新規ファイル2つ。URL直fetch方式で草案より簡潔になった）
4. ✅ ①（新規ワークフロー1つ。publish挙動は `_docs.yml` への `publish` 入力追加で解決）
5. ✅ ④-b（deps込みで6経路、warm 4.3秒。torch同期の data_science/kaggle は除外）

## スコープ外（別セッションで扱う）

- ⑤ Z3充足可能性 × テストカバレッジの突き合わせ（`test_copier_structure.py`のZ3ソルバーが
  「充足可能」と証明した葉が、実際に`RENDERED_PATHS`等で最低1回テストされているかを機械的に
  検証する仕組み）
- ⑥ pre-commitフックの事故再発防止の一般化（`pre-commit run --all-files`実行後に
  `git diff --exit-code`で無変更をassertする回帰テスト。今回end-of-file-fixerが
  `.jinja`を壊した事故の教訓の一般化。なお2026-09-05時点で、check-yaml×copier.yml の
  既存赤がローカルでもCIでも数日気づかれないままだった — 「赤を放置しない運用」の
  観点で TODO.md セクション15 も参照）
