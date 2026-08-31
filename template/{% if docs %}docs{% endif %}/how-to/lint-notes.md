# LINT / 型チェックの決定メモ

`~/dotfiles/template` の Python 規格（ruff ALL / basedpyright / pyrefly / task
runner / pre-commit 等）を適用した際に、「**直すコストが高く、全面適用が開発速度遅延になる**」
と判断して除外（ignore）したルール、および実際に起きた問題・ツール仕様を記録する。

> **学習用の解説（実コード例・実ログ・判断プロセス）は [`TOOLING_LESSONS.md`](./TOOLING_LESSONS.md) 参照。**
> ここは最終的な決定（WHYNOT 一覧）を管理する。

基本方針:
- **実バグを検出するルールは修正する**（未使用 import、未定義名、float 比較、tz なし datetime 等）
- **形式・意見が分かれるルール・日本語文書起因の誤検出**は WHYNOT コメント付きで除外
- 除外したものは必ず `pyproject.toml` の `extend-ignore` にコメント付きで残す
- **自動修正（--fix / --unsafe-fixes）は必ずテストで検証する**

## 現在の状態

| チェック | 結果 |
|---|---|
| `pixi run test` | 404 passed |
| `pixi run lint` (ruff) | All checks passed |
| `pixi run basedpyright` | 0 errors / 0 warnings |
| `pixi run pyrefly check` | 0 errors (preset=default) |
| `pixi run vulture` | clean |
| `pixi run deptry` | clean |
| `pixi run spell` (typos) | clean |
| `pixi run audit` (pip-audit) | clean |
| `pixi run check` | EXIT 0（上記すべて） |

## 実際に起きた問題とツール仕様

### 事例1: `--unsafe-fixes` が sqlite3.Row を dict と誤認して壊した

**起きたこと**: `ruff check --fix --unsafe-fixes` を実行したところ、
`features/projects.py` の `_calculate_priority` が

```python
# 修正前（safe）
importance = row["importance_pre"] if "importance_pre" in row.keys() else None
# ruff が unsafe-fix で自動変換
importance = row.get("importance_pre")
```

に書き換えられた。しかし `row` は `sqlite3.Row`（dict ではなく `.get()` を持たない）。
テスト実行で `AttributeError: 'sqlite3.Row' object has no attribute 'get'` が発生し、
**2 件のテストが失敗**した。

**原因**: ruff の unsafe-fix は `dict` 前提の最適化（`SIM` 系 / `FURB` 系）を、
`Mapping` プロトコルを満たすが `.get()` を持たない型にも適用する。`sqlite3.Row` は
`Mapping` に似ているが `.get()` が無い、という罠。

**対処**: 手動で `row.keys()` 判定に戻し、コメントを追加。
`pyproject.toml` の `unsafe-fixes = false` は既に設定済みだったが、明示的に
`--unsafe-fixes` を渡すと有効になる。

**教訓**:
- `--unsafe-fixes` は**挙動を変える**可能性がある。実行後は必ずテストを回す
- 自動修正の結果を無条件に信頼しない。`git diff` を確認する
- `sqlite3.Row` のように `dict` 互換でも `.get()` が無い型は、ツールが誤認しやすい

### 事例2: `raise ... from exc` の一括置換で二重適用（SyntaxError）

**起きたこと**: B904（except 内の raise に `from exc` を付ける）を修正する際、
`sed` / Python の `str.replace` で `raise click.ClickException(str(exc))` を
`raise click.ClickException(str(exc)) from exc` に一括置換した。

既に `from exc` が付いていた箇所にも適用され、
`raise click.ClickException(str(exc)) from exc from exc` という
**SyntaxError: invalid syntax** が発生。4 つのテストが ERROR になった。

**対処**: `from exc from exc` → `from exc` に置換して解消。

**教訓**: 一括置換は**冪等性を保証しない**。既に変換済みの行も再変換される。
- 事前に `grep -c "from exc"` で既存数を把握する
- 置換後に `python -m py_compile` で構文チェックを必ず行う

### 事例3: `# type: ignore` は basedpyright で「デフォルト無効」

**起きたこと**: `# type: ignore[attr-defined]` を付けたが basedpyright が
エラーを消さなかった（boto3 の `_resource.Table` が未型付けのため）。

**原因（検証で判明）**: `# type: ignore` 構文は pyright / basedpyright でも有効。
しかし **basedpyright は `enableTypeIgnoreComments` がデフォルトで無効**のため、
`# type: ignore` コメント自体を無視していた。加えて、`# type: ignore` は
「行の全エラーを無視」し、コード名の検証も行わない（`# type: ignore[asdf]` でも
効く）。これに対し `# pyright: ignore[RuleName]` は指定ルールのみ無視し、
コード名も検証される。

**このプロジェクトの対応**: `pyproject.toml` で有効化した:
```toml
[tool.basedpyright]
enableTypeIgnoreComments = true   # mypy 等とのコード共有を見込む
```

**正しい書き方（推奨）**:
```python
self._table = self._resource.Table(...)  # pyright: ignore[reportAttributeAccessIssue]
# # type: ignore も有効化済みだが、新規には使わない（コード名を検証しないため）
```

**教訓**: 
- 「対応していない」と「デフォルトで無効」は別物。まず設定を確認する
- pyright 系は `# pyright: ignore[report*]` が推奨（厳格）
- mypy とのコード共有が必要なら `enableTypeIgnoreComments = true` で `# type: ignore` も受け付ける
- ruff は `# noqa: CODE`

### 事例4: `pyrefly infer` は注釈付与が限定的（strict は 186→181 しか減らない）

**起きたこと**: pyrefly を strict にすると 186 件のエラー。テンプレートが
`pyrefly infer`（自動注釈付与）を想定しているか試したが、
**52 ファイル・1211 行追加 / 1044 行削除**という大規模な変更の割に、
strict エラーは 186 → 181 と 5 件しか減らなかった。

**原因**: infer が付与するのは「引数・戻り値の型注釈」のみで、残りの大半は
「呼び出し側の引数型不一致」「ライブラリ未型付け」など、infer では解決できない。
また infer は docstring の大文字化・改行の再フォーマットなど、型と無関係な
変更も大量に行う（ノイズが大きい）。

**対処**: infer の変更を破棄し（バックアップから復元）、pyrefly は
`preset = "default"` に落とした。実型チェックは basedpyright が担う。

**教訓**: 「自動生成で strict を達成する」は幻想になりやすい。
- 既存コードに型チェッカーの strict を後から適用するのは、自動ツールだけでは無理
- 生成ツールの変更はノイズが多い。適用前に必ずバックアップ
- 型チェッカーは 1 本に絞る（ここでは basedpyright）、もう 1 本は緩い preset で補助

### 事例5: basedpyright は警告でも終了コード 1（check 全体が失敗）

**起きたこと**: `pixi run check`（typecheck を含む）が EXIT 1 で失敗。原因は
basedpyright が **0 errors でも warnings があると終了コード 1** を返すこと。

basedpyright は警告の種類が多く、テンプレートの初期設定だけでは
`reportPrivateUsage` / `reportUnusedParameter` / `reportMissingParameterType` 等の
警告が残り、`check` タスク全体が失敗する。

**対処**: `pyproject.toml` の `[tool.basedpyright]` に追加で無効化した:
```toml
reportPrivateUsage = false              # ruff SLF001 と同様
reportUnusedParameter = false           # ruff ARG001 と同様
reportUnusedFunction = false            # vulture が担う
reportUnusedImport = false              # ruff F401 が担う
reportImplicitOverride = false          # オーバーライド注釈は形式
reportMissingParameterType = false      # ruff ANN001 と同様
reportImplicitStringConcatenation = false
```

**教訓**:
- 型チェッカーは「エラー 0 でも警告で落ちる」設定がある。CI で通すには warnings も 0 にする
- 重複検出（basedpyright の X と ruff の Y）は片方に寄せる
- `pixi run check` の EXIT CODE を確認してから「通った」と判断する

### 事例6: 別プロジェクト（gmail/）が全ツールに巻き込まれる

**起きたこと**: gmail/（Gemini-Inbox-Agent、GAS + Python の独立サブプロジェクト）が
リポジトリ内にあり、以下のツールが gmail/ まで走ってしまった:
- **ruff**: gmail/ の 610 件を検出
- **typos**: gmail/ のトークン JSON に `ya29.` 等を誤検出
- **deptry**: gmail/ の 93 件（未宣言依存）を検出

**対処**: 各ツールの exclude に gmail を追加:
- ruff: `[tool.ruff] extend-exclude = ["gmail"]`
- typos: `[tool.typos.files] extend-exclude = ["gmail"]`
- deptry: `[tool.deptry] extend_exclude = ["gmail"]`

**教訓**: モノレポ（複数プロジェクト同居）では、**各ツールの exclude 設定が必須**。
テンプレートは単一プロジェクト前提なので、この調整が必要。

## なぜ除外したか（WHYNOT 一覧）

### 日本語プロジェクト起因

| ルール | 内容 | 除外理由 |
|---|---|---|
| `RUF001/002/003` | 全角文字（（）：等） | 日本語コードベースでは全角文字は意図的。誤検出の嵐になる |
| `D400/D401/D415` | docstring 句読点 | 日本語 docstring にピリオドは不要 |

### プロトタイピングの速度を優先

| ルール | 内容 | 除外理由 |
|---|---|---|
| `ANN001/002/003/201/202/204/401` | 型注釈 | 部分注釈関数の残りを全部埋めるコストが大きい。実型チェックは basedpyright が担う |
| `C901` | 複雑度 | ディスパッチ関数（block action / cron）の分割リファクタは開発速度遅延。閾値 10 に緩和済み |
| `EM101/EM102` | 例外メッセージを変数に | ユーザーが「プロトタイプ中は煩い」と明示的に除外希望 |
| `DTZ011/DTZ001` | tz なし datetime | 全置換は挙動（JST/UTC）を変え得る。新規コードは `timeutil` を使う |
| `PLC0415` | import 位置 | Lambda コールドスタートの遅延 import が意図的 |
| `PLR0913/0912/0911` | 引数・分岐・return 過多 | Lambda ハンドラ・CLI コマンドの引数は構造由来 |
| `FBT001/002/003` | boolean 引数 | CLI / テストの boolean 引数は普通 |
| `ARG001-005` | 未使用引数 | コールバック・ハンドラの引数は構造上存在するだけの場合が多い |
| `SLF001` | private アクセス | テストが private を叩くのは正当。同パッケージ内の `_call` 参照も実用上問題ない |
| `N803` | 引数名が大文字 | boto3 の `Key` / `Bucket` 等は API 仕様 |
| `S101` | assert 使用 | 型チェッカーへの None 絞り込み目的の assert。`python -O` で消えても実害なし |

### 誤検出・個別判断

| ルール | 内容 | 除外理由 |
|---|---|---|
| `ERA001` | コメントアウトコード | 日本語コメントの末尾がコード風に誤検出される |
| `S404/S603/S607/PLW1510` | subprocess | `gh` CLI 呼び出し。`shell=False` でリスト渡しなので安全 |
| `S314/S405` | XML | 信頼ソースのフィード構造を読むだけ |
| `S311/S324` | 乱数・hash | セキュリティ用途ではない |
| `N818` | 例外名 suffix | `NotConfigured` 等は `Error` を足すと冗長 |
| `PT011/PT013/PT015` | pytest raises 広さ | ValueError の広さがテスト意図に合致 |

## pyrefly と basedpyright の役割分担

| | pyrefly | basedpyright |
|---|---|---|
| preset | `default` | `recommended` |
| エラー | 0 errors | 0 errors / 0 warnings |
| 役割 | 補助（動的型の追跡） | 主軸（実バグ検出） |

テンプレートは両方を strict で併用するが、既存コードには過剰。basedpyright を
主軸にし、pyrefly は default で補助に回す（詳細は事例4）。

## 今後コードを書くときの注意

1. 新規関数には型注釈を書く（basedpyright が recommended で検証）
2. 時刻は必ず `lifelog.core.timeutil` を使う（naive datetime を作らない）
3. 例外メッセージに f-string を直接使うのは現状許容（EM102 除外中）
4. 型絞り込みの `assert` は `# pyright: ignore[reportAttributeAccessIssue]` 等と併用
5. **自動修正（--fix / --unsafe-fixes）後は必ず `pixi run test` と `git diff` で確認**
6. `sqlite3.Row` 等の `dict` 互換型に `.get()` を使わない（ツールが誤認する）
7. ignore コメントは pyright 系では `# pyright: ignore[report*]` を推奨。
   `# type: ignore` は `enableTypeIgnoreComments = true` で有効化済みだが
   コード名を検証しないため新規には使わない
8. モノレポでは各ツールの exclude に別プロジェクトを必ず追加
