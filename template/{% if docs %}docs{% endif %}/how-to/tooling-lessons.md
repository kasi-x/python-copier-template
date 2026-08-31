# ツールとの向き合い方 — 実例で学ぶ解釈の育て方

この文書は、`~/dotfiles/template` の規格を実コードへ適用したときに実際に起きた
問題を、**実コード例・実ログ・解釈**の3点セットで記録したもの。
「ルールをなぜ除外したか」の最終形は `LINT_NOTES.md`、ここでは「どう解釈して
判断に至ったか」のプロセスを残す。

---

## 1. basedpyright の警告は「exit 1」で check 全体を落とす

### 実ログ（7ルールを無効化する前）

```
$ pixi run basedpyright
0 errors, 106 warnings, 0 notes     # ← エラーは0なのに…
$ echo $?
1                                    # ← exit code 1
```

### 実コード（警告の実体）

**reportPrivateUsage** — private（`_` 始まり）を他クラス/他モジュールから参照:

```python
# cli.py:756 — Store._table を CLI から直接触る
for t in garbage:
    store._table.delete_item(Key={"pk": f"THREAD#{t.thread_id}", "sk": "META"})

# cli.py:1628 — SlackClient._call を別モジュールから呼ぶ
resp = client._call("conversations.list", payload)
```

**reportUnusedParameter** — 引数が未使用:

```python
# conflicts.py:72 — store が関数内で使われていない
def detect_conflicts(
    threads: list[Thread], available_h: float | None = None, store: Store | None = None
) -> ConflictReport:
```

**reportMissingParameterType** — 引数に型注釈がない:

```python
# cli.py:82 — click コマンドの ctx に注釈がない
def invoke(self, ctx):
```

### 解釈

basedpyright は「警告」を「エラーではないが、デフォルトで exit code 1」として
扱う。テンプレートは `pixi run check` が depends-on で typecheck を含むため、
**警告1件でも check 全体が失敗**する。

「エラー0なら通る」と思い込むと、CI が警告で落ち続けて混乱する。
ここでは2つの選択肢があった:
- **A. 警告を全部コード修正で消す** → 既存の click コマンド全量に型注釈を
  書くコストが大きい
- **B. 重複検出を無効化する** → `reportUnusedParameter` は ruff の `ARG001`、
  `reportUnusedImport` は ruff の `F401`、`reportPrivateUsage` は ruff の
  `SLF001` と重複している。**片方に寄せる**のが自然

→ **B を選んだ**。未使用検出は ruff / vulture が担い、basedpyright は
「型の実バグ」だけ見る。この整理で `0 errors, 0 warnings` になり check が通った。

---

## 2. `--unsafe-fixes` は「辞書っぽい型」を壊す

### 実ログ（テスト失敗）

```
$ pixi run test
FAILED tests/test_projects.py::test_sync_tasks_creates_and_updates
E   AttributeError: 'sqlite3.Row' object has no attribute 'get'
```

### 実コード（ruff が自動変換した内容）

```python
# 変換前（手書き・正しい）
importance = row["importance_pre"] if "importance_pre" in row.keys() else None

# ruff --unsafe-fixes が自動変換（間違い）
importance = row.get("importance_pre")   # ← sqlite3.Row には .get() が無い
```

`row` は `sqlite3.Row`（DB の行）。`dict` に似ているが `.get()` を持たない。
ruff の unsafe-fix は「dict 前提の最適化」を `Mapping` 風の型にも適用してしまう。

### 解釈

- **safe-fix は挙動を変えない**（`--fix` だけで通るものは安全）
- **unsafe-fix は挙動を変える可能性がある**（`--unsafe-fixes` で明示的に有効化）
- この事故は「`--unsafe-fixes` を渡した」ことではなく、
  「**`--unsafe-fixes` の結果を無条件に信頼した**」ことが原因

判断: `pyproject.toml` の `unsafe-fixes = false` を守り、自動修正は safe-fix に
限定。修正後は必ず `pixi run test` と `git diff` で確認する。
`sqlite3.Row` のような「dict 互換だが `.get()` が無い型」は、ツールが誤認する
代表例として覚えておく。

---

## 3. `# type: ignore` は basedpyright で「デフォルト無効」だった

### 実ログ（最初に効かなかった）

```
/home/.../src/lifelog/core/store.py:37:38 - error: Cannot access attribute "Table" for class "_"
```

`# type: ignore[attr-defined]` を付けたのに消えない。

### 実コード（最初は効かなかった ignore）

```python
# 最初に書いたもの（効かない）
self._table = self._resource.Table(...)  # type: ignore[attr-defined]

# 正しい書き方（このセッションで採用）
self._table = self._resource.Table(...)  # pyright: ignore[reportAttributeAccessIssue]
```

### 検証で判明した真実

`# type: ignore` が効かないのは「pyright が対応していないから」ではない。
**basedpyright は `enableTypeIgnoreComments` がデフォルトで無効**のため、
`# type: ignore` コメント自体を無視する。`pyproject.toml` で有効化すると効く:

```toml
[tool.basedpyright]
enableTypeIgnoreComments = true   # # type: ignore を有効化
```

さらに、`# type: ignore` は「行の全エラーを無視」する（コード名の検証もしない）:
```python
1 + ""  # type: ignore[asdf]   ← 無効なコード名でもエラーが消える
```

これに対して `# pyright: ignore[RuleName]` は:
- 指定したルールだけを無視（他のエラーは残る）
- コード名の検証をする（`report*` の正式名でないと警告）

### 解釈

basedpyright がデフォルトで `# type: ignore` を無効にしているのは、
「無効なコード名でも黙って全部無視する緩さ」を避けるため。
`# pyright: ignore[Rule]` はルールを明示でき、検証もされるので、**basedpyright
の推奨は `# pyright: ignore`**。

このプロジェクトではユーザー判断で `enableTypeIgnoreComments = true` を採用した
（mypy 等とのコード共有を見込む）。ただし:
- **新規に書く ignore は `# pyright: ignore[report*]` を使う**（厳格さを保つ）
- `# type: ignore` は「既存の mypy スタイルのコードをそのまま持ってきた」時の
  互換用と割り切る

### 教訓

- 型チェッカーの「対応していない」と「デフォルトで無効」は別物。
  まず設定を確認する
- ignore コメントはツールの推奨形式を使うのが安全
  （pyright 系: `# pyright: ignore[report*]`、ruff: `# noqa: CODE`）

---

## 4. `pyrefly infer` は「既存コードの strict 化」を救わない

### 実ログ（strict 適用の現実）

```
$ pixi run pyrefly check   # preset=strict
INFO 186 errors

$ pixi run pyrefly infer src/lifelog   # 自動注釈付与を試す
# 52ファイル・1211行追加/1044行削除 という大変更

$ pixi run pyrefly check   # 再チェック
INFO 181 errors            # ← 5件しか減っていない
```

`infer` が付与するのは「引数・戻り値の型注釈」。残る 181 件は
「呼び出し側の引数型不一致」「ライブラリ未型付け」など、**注釈を足しても
解決しない問題**。加えて infer は docstring の大文字化・改行整形など
型と無関係な変更を大量に行う（ノイズ）。

### 解釈

- strict は「新規プロジェクトの規律」には効くが、
  「既存コードへの後付け」には効かない
- 「自動生成ツールで strict を達成する」は幻想に近い。生成量に対して
  解決できる問題が少ない
- 判断: 実型チェックは basedpyright（recommended）に一本化し、pyrefly は
  `preset = "default"` で補助に回す。**型チェッカーは1本を主軸に**、
  もう1本は緩い設定で併用する

このとき `git stash create` でバックアップを取り、`git checkout -- src/` +
バックアップ復元で infer の変更を巻き戻した。**生成ツールの大規模変更は
適用前に必ずバックアップ**。

---

## 5. 別プロジェクト（モノレポ）が全ツールに巻き込まれる

### 実ログ

```
$ pixi run spell   # typos
error: `ot` should be `to`...    ← gmail/tokens/*.json（OAuthトークン）に誤検出

$ pixi run lint    # ruff
Found 610 errors   ← gmail/ の別プロジェクトコードを走査
```

gmail/（Gemini-Inbox-Agent = 独立プロジェクト）をリポジトリ内に置いたことで、
ruff / typos / deptry が全部 gmail/ まで走ってしまった。typos は
トークンの文字列（`ya29.` 等）を typo と誤検出した。

### 解釈

テンプレートは**単一プロジェクト前提**。モノレポ（複数プロジェクト同居）では
各ツールに exclude 設定が必要:

```toml
[tool.ruff]
extend-exclude = ["gmail"]
[tool.typos.files]
extend-exclude = ["gmail"]
[tool.deptry]
extend_exclude = ["gmail"]
```

「別プロジェクトのコードを混ぜる」ことは、それだけで全ツールの設定変更を
要求する。**置くなら最初から exclude を設定する**。実データ（トークン・CSV）は
`.gitignore` とツール exclude の両方で守る。

---

## 6. 一括置換は「冪等性」を持たない

### 実ログ（SyntaxError）

```
$ pixi run pytest
E   SyntaxError: invalid syntax
E       raise click.ClickException(str(exc)) from exc from exc
```

### 実コード（二重適用された箇所）

```python
# str.replace で「raise X」→「raise X from exc」を一括置換した結果、
# 既に from exc があった行も再変換された
raise click.ClickException(str(exc)) from exc from exc   # ← 二重
```

### 解釈

`sed` / `str.replace` による一括置換は「既に変換済み」を検出しない。
今回のケースは構文エラーで即検出されたから良かったが、**意味論的に壊れていて
構文が正しい**場合は検出が遅れる。

対処法:
- 置換前に `grep -c "from exc"` で既存数を把握
- 置換後は必ず `python -m py_compile` で構文検証
- 正規表現で「`from` が続かない場合のみ」を条件にする

---

## 結論：ツールへの向き合い方（原則）

1. **自動修正（--fix）は安全、--unsafe-fixes は危険**。結果をテストと diff で必ず検証
2. **型チェッカーは1本を主軸に**（ここでは basedpyright）。複数併用は警告の重複と
   無効化の調整コストが増える
3. **strict は新規プロジェクト専用**。既存コードには緩い preset で適用
4. **ignore コメントはツールの推奨形式を使う**（pyright 系は `# pyright: ignore[report*]`）。
   `# type: ignore` は basedpyright ではデフォルト無効で、有効化してもコード名を
   検証しない緩さがある（事例3）
5. **警告も exit code に含まれる**ツールがある（basedpyright）。「0 errors だから OK」
   ではなく `echo $?` を確認
6. **一括置換・自動生成はバックアップ前提**。`git stash create` で巻き戻せる状態に
7. **モノレポは exclude 設定が前提**。別プロジェクトを混ぜたら全ツールに伝播する
8. **重複検出は片方に寄せる**（ruff F401 = basedpyright reportUnusedImport 等）

## 付録：この文書の作り方

- 実ログは `/tmp/opencode/warnings-before.txt`（basedpyright の警告全件）に保存
- 実コードは `src/lifelog/` の該当行をそのまま引用
- 「解釈」は判断に至った思考を書く。結果だけの LINT_NOTES.md と違い、
  ここは「なぜ A でなく B を選んだか」を残す
