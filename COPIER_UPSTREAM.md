# copier 本体(upstream)への寄稿候補リスト

copier-org/copier に issue / PR を投げるために、本テンプレートの開発・利用で
遭遇した問題のうち「テンプレート側では解決できず copier 本体に起因するもの」を
まとめた。根拠はすべて copier **9.18.1**(本リポジトリ `.venv` 版)のソースで確認済み。
各項目には、そのまま issue に使える英語タイトル案を付けた。

**そのまま貼れる英語 issue 本文の草稿は `upstream-drafts/` に file 毎に用意済み**
(01〜09 が本書の項目 1〜9 に対応。再現手順と検証済みの出力を含む)。

先に結論: 動的 `choices` の誤パース(BUG.md #1 で報告された
`['README', 'sphinx']`)は **9.18.1 では再現しなかった**(最小再現テンプレートで
正常動作を確認)。テンプレート側も静的 choices 化済みのため、これは upstream
報告対象から外した。逆に、本テンプレートの bug 報告の大半(`--defaults` で止まる、
`--data-file` が効かない、に見えたもの)は copier の **unsafe features 拒否の
 UX** に起因しており、これが寄稿候補の筆頭。

---

## 1. unsafe features の拒否が「提案口調」で、何も生成されないことが伝わらない

**種別**: UX / bug 寄り。**難易度**: 小(文言のみ)。**優先度**: 高

- 英語タイトル案: `UnsafeTemplateError message should state that nothing was generated`
- 現状: `_jinja_extensions` / `_tasks` を持つテンプレートを `--trust` 無しで
  `copier copy` すると、stderr に
  `Template uses potentially unsafe feature(s): jinja_extensions, tasks. / If you trust this template, consider adding the --trust option ...`
  とだけ出て **exit code 4**(`0b100`)で終了する。
  根拠: `errors.py:157-166`(`UnsafeTemplateError`)、`_cli.py:88-92`
  (`return 0b100`)、raise 箇所は `_main.py:328`。
- 問題: 文言が「consider adding ...」という提案形のため、**生成が拒否され
  宛先には何も書き込まれていない**ことが伝わらない。実際、本リポジトリに寄せられた
  非インタラクティブ生成の bug 報告(bugs.md #10「`--defaults` でも質問が
  スキップされない」、BUG.md #2/#4)は、すべてこの拒否を別の問題と誤認したもの。
  生成成功と誤認して宛先ディレクトリを探し回る事態を何度も目撃した。
- 提案:
  - 文言を指示形に変え、状態を明示する。例:
    `Refusing to generate: the template uses potentially unsafe feature(s): jinja_extensions, tasks. Nothing was written to the destination. If you trust this template, re-run with --trust (or list it in the settings trust file).`
  - 宛先パスが分かるなら文面に含める。
- 既存関連: #1269(クローズ — この文言自体がその改善。一歩 further)、
  #1328(bitflag 由来の経緯)

## 2. CLI の exit code が未ドキュメント(4 が特に謎)

**種別**: docs。**難易度**: 小。**優先度**: 高(1 と同じ PR でよい)

- 英語タイトル案: `Document CLI exit codes (1 = error, 4 = unsafe template refused)`
- 現状: `_handle_exceptions` が `UserMessageError → 1`、`UnsafeTemplateError →
  0b100` を返す(`_cli.py:80-92`)。`0b100` は bitflag 時代の名残で、
  コード内の根拠が issue コメントへの URL コメントだけ
  (`# DOCS https://github.com/copier-org/copier/issues/1328#issuecomment-...`)。
  スクリプトからは「4 = テンプレートを trust せずに拒否された」を正式ドキュメント
  なしで判定できない。
- 提案: docs に exit code 一覧ページ(または README 節)を追加。
  `0b100` をそのままにするか、意味の分かる値へ移行するかはメンテナ判断。
  破壊的変更になるなら少なくとも docs 化だけでも。

## 3. テンプレートが「レンダリングに必要な pip パッケージ」を宣言できない

**種別**: feature + docs。**難易度**: 中〜大(feature)/ 小(docs 部分)。**優先度**: 高

- 英語タイトル案: `Allow templates to declare required packages for Jinja extensions (e.g. _pre_requirements), and document the uvx/pipx recipes`
- 現状: `_jinja_extensions` の実行には拡張パッケージが **copier 本体と同じ
  環境**に必要。隔離環境の `uvx copier copy` では
  `Copier could not load some Jinja extensions: No module named 'copier_template_extensions'. Make sure to install these extensions alongside Copier itself.`
  (`errors.py:125`、`_main.py:736-741`)で即死する。
  copier.yml には依存を宣言する key が存在しない(9.18.1 で確認:
  `_requirements` / `_pre_requirements` 相当は無し)。
  本テンプレートでは `uvx --with copier-template-extensions copier copy --trust ...`
  が唯一の隔離環境レシピで、これを README に明記する羽目になった。
- 提案(段階的に):
  1. docs の jinja_extensions 節に `uvx --with <ext> copier copy` と
     `pipx inject copier <ext>` のレシピを追記(小 PR)
  2. `ExtensionNotFoundError` の文面に上記コマンド例を追加(小 PR)
  3. 長期: `copier.yml` に `_pre_requirements: [pkg, ...]` を新設し、copier が
     未導入なら「この key で宣言された依存が足りない」と具体的に案内する
     (自動 pip install はコード実行なので `--trust` 必須にする等の設計は要議論)
- 既存関連: #851(クローズ — copier 自身のバージョン要件で別物)

## 4. `--answers-file` が絶対パスを受け付けず、エラーも無ヒント

**種別**: UX。**難易度**: 小。**優先度**: 中

- 英語タイトル案: `--answers-file: better error (or accept absolute paths)`
- 現状: 絶対パスを渡すと `ValueError: "/tmp/answers.yml" is not a relative path`
  (`errors.py:111-115`)。ヘルプには "relative to destination_path" とあるが、
  エラー単体では何をどう直せばいいか分からない。本テンプレートの bug 報告
  (BUG.md #3)の元ネタ。
- 提案: エラー文面を `"... is not a relative path (answers file must be
  relative to the destination directory)"` に。もしくは絶対パスを受け付けて
  宛先基準で解決する(破壊的な挙動変更になるので文面改善が安全)。

## 5. 非対話実行時に「足りない質問」を 1 個ずつしか報告しない

**種別**: DX。**難易度**: 中。**優先度**: 中

- 英語タイトル案: `Report all missing required answers at once in non-interactive mode`
- 現状: `--defaults` / `--data-file` の非対話実行で回答が足りないと
  `ValueError: Question "X" is required` が最初の 1 件で raise される
  (`_main.py:659`)。修正して再実行すると次の質問でまた落ちる。CI では
  1 回の実行で全欠落を知りたい。また `--defaults` を付けていても
  default を持たない質問はこれに当たる(default を全質問に付けることが
  テンプレート側のベストプラクティスだと、この挙動からは学べない)。
  本テンプレートでは「全質問に default があることを検証するテスト」を
  自前で書いて対策した。
- 提案: 非対話パスでは required 欠落を収集し、
  `Missing answers for: a, b, c` 形式で一度に報告する。
- 既存関連: #1475(クローズ)、#2436(open — `--defaults --skip-answered`
  でも TUI が出る件。同根の非対話系の不満)

## 6. ローカルパス指定のテンプレートで DirtyLocalWarning が毎回出る

**種別**: UX。**難易度**: 小。**優先度**: 低〜中

- 英語タイトル案: `Do not warn DirtyLocalWarning when the template path is an explicit local directory`
- 現状: `copier copy ./my-template dest` のように **ローカルパスを明示しただけ**
  で `Dirty template changes included automatically.`(DirtyLocalWarning、
  `_vcs.py:414`)が出る。ローカルパス指定は「今の作業状態を使え」という
  明示的な意図を伴うため、警告はノイズ(本リポジトリではテスト実行のたびに
  全件で出力される)。
- 提案: src_path が VCS 参照でなくローカルディレクトリの場合は警告しない。
  または Python API 利用者が category でフィルタできることを docs に明記。

## 7. settings の trust リストが発見しにくい(CLI 経路が無い)

**種別**: docs / 小 feature。**難易度**: 小(docs)/ 中(CLI)。**優先度**: 低〜中

- 英語タイトル案: `Make the settings trust list discoverable (docs and/or a CLI command)`
- 現状: `--trust` を毎回付けなくても、
  `user_config_path("copier") / "settings.yml"` に `trust: [repo-prefix, ...]`
  を書けば永続化できる(`_settings.py:106,134`、判定は `_main.py:313` の
  `is_trusted_repository`)。ただし CLI サブコマンドが無く、ドキュメントも
  目立たない。項目1の改善で「settings に書け」と案内するなら、その方法が
  発見可能でなくてはならない。
- 提案: (a) docs の trust 節に settings.yml の具体例を追記(小)、
  (b) 将来的に `copier settings trust add <url>` 相当の CLI(中)。

## 8. (docs) `--data-file` の値は「回答」として扱われることを明記

**種別**: docs。**難易度**: 小。**優先度**: 低

- 英語タイトル案: `Document that --data/--data-file values count as answers for skipped questions`
- 現状: `--data-file` の値は `answers.init` に入り、`when: false` で
  スキップされた質問にも値として採用される。validation は when が真のときのみ
  (`_user_data.py:289-294` に "intentionally not validated" のコメントあり)。
  9.18.1 の最小再現では動的 choices(jinja 文字列)も正しく render/parse された。
  挙動自体は合理的だが、非対話生成を書く人からすると驚きやすい点
  (skip された質問に値を渡すと出力に反映される)が未文書。
- 提案: 非対話生成の docs 節にこの挙動を明記。
- 既存関連: #1951(open — data-file の boolean 扱い)、
  #2142(open — プロセス置換非対応)

## 9. リモート URL 指定で「最新タグ」を使う挙動が、fork/改名リポジトリで無警告に古いテンプレートを掴む

**種別**: UX / docs。**難易度**: 中(警告)/ 小(docs)。**優先度**: 中
**(本テンプレートへの bug 報告3件の真の根因だったため記録に残す)**

- 英語タイトル案: `Warn when the selected ref is far behind the default branch (stale tag checkout)`
- 現状: `copier copy https://.../template.git dest` を `--vcs-ref` 無しで実行すると
  copier は**デフォルトブランチでなく最新 git tag** をチェックアウトする
  (公式 docs に記載はある)。fork を継承したリポジトリでは、その「最新タグ」が
  fork 前の古い上流テンプレートを指したままになり、ユーザーは**古い質問票・
  古い生成物**を現在のテンプレートだと信じて受取る。本テンプレートでは
  継承タグ 5.4.0(旧上流版)が最新タグのまま残っており、「docs_type に
  zensical が選べない」「存在しない component_owner を聞かれる」という
  2件の現実の bug 報告が両方この罠だった(`git show 5.4.0:copier.yml` で確認:
  旧版の docs_type choices は正確に `['README', 'sphinx']`、`component_owner`
  質問あり)。出力の `Copying from template version 5.4.0...` は表示されるが、
  それが「このリポジトリの現状ではない」ことは何も伝えない。
- 提案:
  - (a) docs: URL 指定時のタグ選択挙動を「Create a new project」系ガイドの
    目立つ位置に明記(小)
  - (b) UX: `--vcs-ref` 無しで checkout した ref がデフォルトブランチから
    N コミット以上遅れている場合に警告を出す(例: `Warning: using tag
    5.4.0, which is 44 commits behind the default branch main. Pass
    --vcs-ref=main to use the branch tip.`)。「遅れ」の検出は clone 済み
    なので `git rev-list --count` 1 回で済む
- 対応済み(テンプレート側): README / docs に `--vcs-ref=main` を追加。
  継承タグ自体は v1.0 fork 解除時に打ち直し(TODO 11)。

---

## 寄稿の進め方(メモ)

1. 投げる順番の推奨: **1+2(同じ PR で文言+docs)→ 4 → 3(a)(b)(docs レシピ)
   → 6 → 5 → 7 → 3(c)**。小さいものから実績を作り、design が要るものは
   Discussions で相談してから issue 化。
2. issue には本ドキュメントの「現状」のソース行参照(9.18.1)と、
   再現コマンド(`copier copy` を `--trust` 無しで実行して exit 4 を示す
   2 行スクリプト等)を添える。再現テンプレートは本リポジトリ自体が使える
   (`--trust` 無しで拒否される実例、`uvx --with ...` で通る実例の双方)。
3. PR 前に `CONTRIBUTING.md` 通りに upstream のテストを回す。
   文言系(1/2/4)は単発 PR として最も通りやすい。

## 2026-09-06 時点で確認済みのこと

- 検証 copier: 9.18.1(本リポジトリ `.venv`)
- 動的 choices の誤パース: 再現せず → 報告対象外(テンプレート側で静的化済み)
- upstream 重複確認済み: exit code ドキュメント / answers-file 絶対パス /
  DirtyLocalWarning(ローカルパス) / requirements 宣言の 4 点は既存 issue 無し。
  unsafe 文言は #1269 で一度改善済み(この先の改善として差し上げる)。
