# TODO

このテンプレートの開発・拡張メモ。各項目は作業時に個別のissue/PRへ分割してよい。
未公開（pre-publication）のため、後方互換・移行案内・CHANGELOG は考慮しない。

## 設計原則（2026-09 合意・更新: AGENTS.md / online_judge / kaggle 再編を反映）

以下の原則に従って、オプションの追加・削除・再編を判断する。原則に反する提案は
肥大化のもとなので、このTODOに載せる前に再考する。

- **project_type = 実行環境 / ビルドが根本から異なるもの、または「競技」という
  明確な利用規約の軸があるものだけ**
  - 例: library（import）、web_api（HTTP+Docker）、cli（即終了）、data_science、
    script、online_judge（競技。AI 利用の可否が大会ごとに異なる）、ros2（colcon/
    rosdep）、micropython（デバイス+firmware 特殊ビルド）。
    将来 vfx（DCC内Python）が加わる場合もこの根拠による。
- **実行環境が同じでも「AI 利用の可否」という規約の軸が明確なら project_type にできる**
  - online_judge は実行環境としては script/cli と同じだが、大会ごとに
    「AI コーディングエージェントの利用可否」が異なり、生成物に AGENTS.md を
    置く/置かないが変わる。これは実行環境軸とは独立した第一級の違い。
  - 逆に、実行環境も AI 規約も同じなら project_type を増やさない。
    CTF、botter（discord/slack）、data_science の拡充、SRE、FastHTML 等は
    「既存 project_type の上に載るレイヤー / 亜種」として扱う。増やしたい要求は
    必ず「既存の何の上に載るか」を答えてから設計する。
- **AI コーディングエージェント向けの指示（AGENTS.md）は、デフォルトで全プロジェクトに置く**
  - library / cli / web_api / data_science / script / kaggle には常時生成。
  - AI 利用 NG の online_judge タイプには置かない（規約遵守のため）。
  - 個別の ON/OFF 質問は作らない（内蔵の初期構成とする）。
- **対象外の領域は web_django 方式で明示的に拒否する**
  - このテンプレートの守備範囲外（Ansible の IaC、Terraform/K8s、Django 等）は
    project_type の選択肢として「NOT supported。生成を abort して代替を案内」する。
    黙って無視する選択肢を増やさない。
- **選択肢は「推奨1本 + No でカスタム」を保つ**
  - 現行の `use_recommended_*` 方式。詳細な選択肢（ORM 5種、GraphQL/REST 等）を
    一度に並べるカタログ型（例: s3rius/FastAPI-template）にはしない。

## 前提: 現状の構造的問題（このTODOの動機）

- **AI コーディングエージェント向けの指示がどこにも無い**: 生成物に AGENTS.md が
  無く、AI エージェントが「どうテストを回し、どこを編集してよいか」を README /
  CONTRIBUTING.md から推測するしかない。CONTRIBUTING.md は人間向けの詳細版であり、
  エージェント向けの簡潔な作業手順が無い。
- **kaggle（competition）が data_science の亜種として誤って配置されている**:
  Kaggle は「競技」であり、AI 利用 OK という点で online_judge の一種。
  data_science（分析）と competition（競技）は実行のされ方が違い、GPU 前提の
  競技特化レイアウト（src/utils, submission）が data_science に混在している。

（web_api が scaffold として未完成だった問題と「生成物が動く検証テストが無い」問題は
2026-09 に解消済み。web_api はトップレベル app/ の動く scaffold になり、
test_example / test_generated_lint / test_recommended_path が生成物を実走・lint 検証する。
履歴は項目6 と「このセッションで解決した項目」に残してある）

## 1. AI コーディングエージェント向け指示（AGENTS.md）の生成

- [ ] `AGENTS.md.jinja` を新設し、生成物の設定（task_runner / strictness / docs /
      project_type）に応じた開発フローを自動生成する
      - 内容: テスト・lint・type-check・docs の実行コマンド、編集してよい範囲
        （src/<pkg>/, tests/）、commit 規約（conventional）、CI の構成
      - 生成: library / cli / web_api / data_science / script / kaggle
        （online_judge の AI-NG タイプでは生成しない）
- [ ] README.md.jinja に「See AGENTS.md for AI-agent guidance」を追記する
      （Development setup 付近。docs 生成時は docs にも反映）
- [ ] .gitignore / renovate / pre-commit への影響を確認する
      （AGENTS.md は通常の md として扱い、typos / markdown lint / docs 取込の
      対象にするか決める）
- [ ] CONTRIBUTING.md との住み分けを docs に明記する
      （AGENTS.md = エージェント向け簡潔版、CONTRIBUTING.md = 人間向け詳細版）
- [ ] AGENTS.md の有無を検証するテストを追加する
      （各 project_type と online_judge の AI 可否で、ファイルの有無が正しいこと）

## 2. online_judge project_type の新設（競技用。AI 可否は種類による）

- [x] copier.yml の project_type に `online_judge` を追加する
      - help: 競技用プロジェクト。種類（kaggle / atcoder / leetcode）により
        AI コーディングエージェント利用の可否が異なり、AGENTS.md の有無が変わる
      - 実装メモ: AI 可否と AGENTS.md 有無の配線は項目1（AGENTS.md）着手時に
        oj_allow_ai 質問として追加する（今回は質問・変数とも未導入）
- [x] `oj_kind` 質問を新設する（online_judge 選択時のみ）
      - kaggle / atcoder / leetcode の3種で開始し、**2026-09 に yukicoder / aoj を
        追加して5種**に拡張（oj 対応サイト + 教育的OJ優先の方針。ユーザー指示）
      - yukicoder / aoj は既存の oj_code（コード提出型・空ワークスペース）側に載せ、
        生成物の分岐変更なし。README の導入手順だけサイト別に切替:
        atcoder = oj + acc / yukicoder = oj（submit まで対応）/ aoj = aoj-cli 主軸
        （oj は AOJ に submit 不可）/ leetcode = LeetCode エディタ（oj 非対応）
      - atcoder / leetcode では AI 可否をさらに質問する（項目1 で追加予定）
- [ ] `oj_allow_ai` 質問を新設する（atcoder / leetcode 選択時のみ）
      - AI 利用 OK → AGENTS.md を生成（+ README に AI 向け言及）
      - AI 利用 NG → AGENTS.md を生成しない（規約遵守）
      - （項目1 の AGENTS.md 設計と一体で導入。今回のコミットでは見送り）
- [x] online_judge の生成物（最小構成・追加依存なし・stdlib のみ）
      - **設計変更（oj 実測ベース）**: solutions/ は事前生成しない。oj はカレントに
        `test/`（sample-N.in/.out）を作り、acc はコンテスト/問題ディレクトリを
        作るため、「空の作業リポジトリ」を生成し oj / atcoder-cli に全て任せる
      - atcoder/leetcode はルートが空（src/ も package も無い）。lint は競技向けに
        緩和（A001 / N802 / N806 / RUF059 / ARG / F841 / PLC0415 等を oj_code 全体に
        適用）、pytest は tests/ のみ、型チェックは vulture スキップ、CI は dist 無し
      - README に oj / acc の導入手順と提出フロー（oj download → main.py →
        oj test → oj submit）を記載
- [x] online_judge では `use_recommended_agent`（pydantic-ai scaffold）を出さない
      （online_judge では use_recommended_agent 質問自体が出ないことを確認）
- [x] online_judge のテスト: 生成物の有無（src 無し・deps 空・CI に dist 無し）+
      空ワークスペースで task check が通ること + kaggle に solutions が無いこと
- [ ] **将来拡張**: oj_kind を世界基準の主要 OJ 9種 + 「その他」（選ぶと更に
      選択肢が出る2段階方式）へ拡張する。**2026-09 に yukicoder / aoj を追加して
      5種**（kaggle / atcoder / leetcode / yukicoder / aoj）。残り候補は
      Codeforces / CodeChef 等（oj 対応だが教育的OJを優先して今回見送り）。
      サイト数が増えたら2段階 UI（competitive coder / result competition の
      2系統 + サイト列挙）へ移行する
      - 対象外の整理（調査済み）: Project Euler（oj 非対応・数値回答のみ）、
        ML コンペ系（DrivenData / AIcrowd / 天池 / Analytics Vidhya。kaggle の
        コンペレイアウトに載せられるが日本話者の実利用は低く見送り）、
        CTF（pwntools の pwn template 等は下記項目8 の「亜種レイヤー検討」と統合）

## 3. kaggle の data_science 分離 → online_judge の内部タイプへ統合

- [x] copier.yml から data_science 配下の `competition` 質問を削除する
      （kaggle = oj_kind=='kaggle' として online_judge 側に移す）
- [x] 内部変数を張り替える: competition 条件を kaggle 条件に変更
      - data_science_layout / pkg_dir（'src/utils'）/ use_gpu_effective / duo / care /
        _tasks.jinja の competition 分岐 等
      - oj_code（= online_judge and oj_kind != 'kaggle'）内部変数も追加
- [x] kaggle 用の生成物を移設する（既存 competition のものをほぼそのまま）
      - src/{configs,data,input,output,features,logs,models,notebook,scripts,utils}/
      - utils パッケージ（config/dataset/features/modeling/plots）
      - Dockerfile.gpu + devcontainer.gpu.json + uv の pytorch-cu124 インデックス
      - marimo notebook（src/notebook/explore.py）
      - 依存セットはユーザー判断で「既存 competition を完全維持」（duckdb/polars/
        pyarrow と experiment extra も kaggle に残す）
- [x] data_science を純粋な分析型に純化する
      - competition / GPU 質問を外す（notebooks / data / models / reports / paper）
      - **DUO / CARE 質問は data_science に残す**（competition の when 条件を外す）
      - polars/duckdb/pyarrow 等の data_science 初期依存は維持する
- [ ] kaggle には AGENTS.md を生成する（AI 利用 OK のため。kaggle 固有の指示:
      GPU の使い方・submission の作り方・データ境界を含める）
      - （項目1 の AGENTS.md 設計で、kaggle / atcoder(AI可) は生成、
        AI NG の online_judge では生成しない一元管理を実装）
- [x] 既存テストを移設する: test_template_kaggle_competition → kaggle タイプ用に
      書き換え、test_template_data_science_layout は competition 無しの純化後仕様に
      更新。example-answers.yml / questionnaire.md / README の competition 言及を更新
      （未公開なので移行案内は不要。単に competition を撤去して kaggle に置き換える）

## 4. 「常駐する実行可能物」の実行形態を新設する（bot / MCP server の受け皿）

- [x] project_type に `daemon` / `service`（常駐実行物: bot、MCP server、長命 worker）を
      追加するか、既存 project_type の上に載るレイヤーとして独立起動モジュールを持つ
      設計にするか決定する → **既存の上に載るレイヤー方式** に決定
      - 判断基準は設計原則1（実行環境が根本から違うか）。bot/MCP は「イベントループ +
        トークン/env で起動する長命プロセス」だが、library / cli / web_api と同じ
        CPython + uv 実行環境に載る。マイクロPython / VFX（ビルド・実行対象が根本から
        違う）と違い、実行環境軸で project_type を増やす根拠が無い
      - 「cli / web_api の上に bot 実行モジュールを置く」レイヤーとして扱う
        （bot / MCP server は「ホストやイベントループに起動される実行可能物」であり、
        import される側の library には載せない）。**2026-09 に include_mcp を cli 限定へ
        変更**（web_api は top-level app/ 化で <pkg> を無くし、mcp_server.py の置き場が
        消えたため。常駐レイヤーの実装例は cli + include_mcp のみになった）。
        既存の `include_mcp`（cli 上に mcp_server.py + `mcp-server-<name>` console
        script を生成して常駐起動する）がこのレイヤーの実装例
- [x] `__main__.py` を「常駐起動（トークン必須、環境変数チェック）」に置き換える分岐を
      設計する（CLI と衝突させない） → **独立起動モジュール方式** に決定
      - `__main__.py`（CLI: `python -m <pkg>` / `scripts.<name>`）は即終了コマンドの
        まま維持し、常駐物は別モジュール（例: mcp_server.py）の `main()` を
        `python -m <pkg>.mcp_server` で起動する
      - 理由: `__main__.py` にトークン必須・env チェックの分岐を足すと、Docker の
        ENTRYPOINT（`scripts.<name>` = CLI）や既存テスト（`python -m <pkg> --version`）
        と衝突する。常駐物ごとに独立モジュール + 専用 `[project.scripts]` を持つ方が
        CLI / 常駐の二重起動を構造的に防げる
- [ ] botter 向け（discord / slack）: 新設した常駐レイヤーの platform として
      discord / slack を実装する
      - discord.py / nextcord / py-cord と slack-sdk / bolt のどれを推奨1本にするか
      - .env.example のトークン管理、structlog 連携、Docker での常駐/再起動方針
      - （「常駐レイヤー」の設計と MCP の実装例は docs/explanations と docs/how-to に
        文書化済み。discord/slack はこの受け皿に載せる platform の実装として将来着手）
- [x] 既存の `include_mcp` をこの常駐レイヤーへ統合する（下記5と一体で整理）
      → 既存 include_mcp（mcp_server.py 生成）を常駐レイヤーの最初の実装例と位置づけ、
      docs（how-to / explanations）にその位置づけを文書化した
- [x] **複数要素の同時展開（base + layer）**（2026-09。data_science + web_api、
      web_api + MCP 等の要望に対応）
      - `project_type`（単一）は **base** のまま残し、追加要素は `include_*` bool
        質問で opt-in する（既存 `include_mcp` と同じ発想）。`project_type` 自体の
        multiselect 化はしない（`.copier-answers.yml` 非互換・Z3/list 対応等の
        コストに見合う恩恵が無い）
      - 新設 `questions/_combo.yml`（`include_data_science` / `include_web_api` +
        `combinable` ガード + `has_*` effective）。デフォルト全 false で単体
        render は byte-identical（全単体ケースで HEAD と比較検証済み）
      - `web_api` / `data_science` は `questions/_internal.yml` の同名 internal を
        effective 化（template 側の参照はそのまま効く）。`mcp_effective` も
        `web_api` 含有時に効くよう拡張
      - MCP 本体は `_shared/mcp_server.py.jinja` に集約し 3 wrapper
        （src / flat / `app/`）から include。web_api 含有時は
        `app/mcp_server.py` + `from app import mcp_server`（console script も
        `app.` 起点）。`test_mcp_server.py` / console script は `import_pkg` 化
      - 教訓2件を `docs/explanations/template-dev.md` に規約化:
        wrapper 単行化（2行 wrapper は先頭空行を生む）、`_internal.yml` 内の
        定義順（`when: false` も定義順に評価される。後方 internal 参照は
        Undefined/falsy になる）+ 後者を検出する
        `test_internal_variable_references_are_forward_only` を新設
      - ros2 / micropython / oj_code / script は単独のまま（ビルド・実行形態が
        根本的に違うため）。`combinable` ガードで強制 data の leak も防ぐ

## 5. MCP の整理（include_mcp と mcp_server の分裂解消）

- [x] `include_mcp`（mcp_server.py 生成 + mcp SDK 依存）と旧 specialty の mcp_server
      （inspector のみ）の2系統を1つに統合する
      - 旧 specialty='mcp_server' を撤去し、inspector 実行方法を include_mcp 生成の
        mcp_server.py docstring / README に移植した。これにより
        「片方だけ選ぶと exclude されない生成コードができる」不整合も構造的に消えた
- [x] **MCP Python SDK v2 移行**（2026-09。`pip install mcp` が 2.x になったことに伴い、
      生成物が import エラーで壊れていた問題を修正）
      - `FastMCP`（`mcp.server.fastmcp`）→ `MCPServer`（`mcp.server`）。v1 の import パスは
        v2 で消失しており、無指定の `"mcp"` 依存では新規生成プロジェクトが壊れる
      - 依存を `mcp[cli]>=2.0,<3` に変更（cli extra は `mcp dev/run/install` を提供。
        `<3` 上限は v1→v2 事故の再発防止）
      - SSE transport を撤去し **streamable-http** に置き換え（`--transport streamable-http`。
        SSE はプロトコル上 deprecated で「新規構築するな」の位置づけ）
      - `run()` は `if __name__ == "__main__":` ガード内でのみ呼ぶ（v2 要件。import で起動しない）
      - v2 SDK は完全な型スタブを同梱するため、mcp_server.py の basedpyright/pyrefly
        exclude を**撤去**（v1 時代の「stubs が無い」理由は消滅。argparse 起因の reportAny は
        `cast(Literal[...])` で回避）
- [x] mcp_server の実装例を「型付きツールの登録」まで拡充する（ツール定義・引数スキーマ・
      エラー処理）。テストは in-process client でツール呼び出しを検証する
      - `add(a: int, b: int)` / `divide(...)` の型付きツール（スキーマは型ヒントから自動生成）
        + `ToolError`（0 除算）の例 + `project://about` resource の例
      - `tests/test_mcp_server.py` を生成: SDK の `Client(mcp)` による **in-memory 接続**
        （サブプロセス・ポート不要）。anyio（`@pytest.mark.anyio`）+ `anyio_backend` fixture。
        dev 依存に anyio を追加（mcp SDK の推移的依存だが明示する）。このテストが
        「client としての利用コード」の見本を兼ねる
      - **「開発と利用は分けない」判断**: SDK は1パッケージで server/client 両対応。
        ホスト登録や `uvx` での既製サーバ利用はコード生成の対象外（設定+コマンド）のため
        how-to の1節でカバーし、質問は増やさない
- [x] streamable HTTP（リモートMCP）と docker での運用まで含めるかは、
      常駐レイヤーの設計（4）に合わせて決める
      - **streamable-http は scaffold の transport として採用**（`--transport streamable-http`、
        起動は `python -m <pkg>.mcp_server`）
      - **Docker でのリモート運用**（compose service 化・HEALTHCHECK・認証）と
        **配布前提スタンドアロンサーバ**（reference servers 型: PyPI 公開 + `uvx` + `.mcp.json`
        でのホスト登録レシピ）は将来TODOとして明記する（下記6の web_api Docker 拡充と一体で検討）
- [x] **include_mcp の対象を cli に絞る**（library / web_api は対象外に）
      - 理由: library は「import される側」であり、実行可能サーバを載せる動機が薄い。
        **web_api は 2026-09 の top-level app/ 化で <pkg> を無くしたため対象外に**。
        cli = stdio ローカルサーバ（+ streamable-http は cli でも起動可能）
      - **console script `mcp-server-<name>` を追加**（`[project.scripts]`）。ローカルでは
        MCP ホストが `uv run mcp-server-<name>` で起動、公開後は `uvx mcp-server-<name>` で利用
      - data_science / script / online_judge / ros2 / micropython / library / web_api では
        質問を出さず、data 強制でも orphan 依存が付かないよう内部変数 `mcp_effective` で
        render を一元化（既存 `security_policy_effective` 方式）
      - **2026-09 の同時展開対応で web_api が復帰**: `include_mcp` は
        cli / web_api base と `include_web_api` layer で質問され、`app/` 配置で
        生成される（上記項目4 の同時展開メモを参照）
- [x] **MCP scaffold へのセキュリティ実装**（2026-09。「実際にしこむ」対応）
      - docs の指針をコードに反映: `mcp_server.py` に **`--host` / `--port`** フラグを追加し、
        **非ローカルバインド（--host 0.0.0.0 等）には `MCP_ALLOWED_HOSTS` を必須化**
        （SDK は localhost 以外で DNS-rebinding protection を自動無効化するため、allowlist 無しの
        公開バインドは起動を拒否して構造的に防ぐ）。`MCP_ALLOWED_ORIGINS` も任意対応
      - `GET /health` を `@server.custom_route` で登録（無認証・allowlist 対象外は SDK 仕様。
        Docker / オーケストレータの liveness 用）
      - docker=true && include_mcp の時だけ **`mcp-serve` タスク**（docker build + run）を
        全タスクランナーに追加。Dockerfile に EXPOSE 8000 + 起動コメント
      - README / run-container / .env.example / docs に MCP_ALLOWED_HOSTS と Docker 起動例を追記。
        生成テストに health ルート・_allowed_hosts の in-process 検証を追加
      - 生成物の文字列連結は **ruff デフォルト（複数行は暗黙連結が標準）を明示的に固定**:
        `lint.flake8-implicit-str-concat.allow-multiline = true` を記載し、
        ISC003（複数行 `+` 連結の禁止）を有効のままにする。basedpyright の
        `reportImplicitStringConcatenation = false` で暗黙連結を許可
      - スモーク検証済み: allowlist 無しの 0.0.0.0 バインドは拒否、allowlist 有りで起動し
        悪意 Host は /mcp で 421、/health は 200。uv sync + pytest 9本 + ruff/basedpyright/
        pyrefly/deptry/vulture 全クリーン
- [ ] **将来拡張: 配布前提スタンドアロン MCP サーバのレシピ**（reference servers 型）
      - cli + include_mcp は console script（`mcp-server-<name>`）まで生成済み。残りは
        PyPI 公開（既存 `pypi` 質問 + CI release job）後の `uvx mcp-server-<name>` 利用案内と、
        `.mcp.json` / `claude mcp add` でのホスト登録レシピの docs 拡充
      - 「自作サーバを library として配る」要求は cli 形状の配布アプリとして扱う
        （import される library ではなく、起動される console script が配布単位）
- [ ] **将来拡張: MCP server の本番運用**（残作業）
      - 調査メモ（2026-09）: MCP SDK 公式に Docker レシピは無い。SDK はプロセス管理を
        提供せず（`mcp.run()` は単一 uvicorn）、デプロイで MCP が関与するのは
        `TransportSecuritySettings`（Host allowlist。実装済み）のほか、
        マルチワーカー時の `RequestStateSecurity` 共有鍵と `SubscriptionBus` の2点。
        認証（OAuth 等）とプロセス管理は利用者側の仕事
      - streamable-http を **compose service 化**し、HEALTHCHECK（`/health` は実装済み）・
        認証（OAuth / reverse proxy）をどう載せるか。項目6（web_api の Docker 拡充）と一体で設計する
      - 最小権限・外部入力（prompt injection / SSRF）・ToolError の意図・公開時の
        transport_security 必須は docs/how-to/mcp.md の Security for server developers /
        users and operators 節に文書化済み。OWASP Agentic Skills Top 10 はスキル配布レイヤー
        （SKILL.md 等）向けで MCP server 開発の直接参照にはならない
        （OWASP Agentic AI Top 10 / LLM Top 10 が対応する領域）

## 6. web_api を「動く FastAPI scaffold」へ拡充する（s3rius/FastAPI-template 参考）

- [x] まず現状の欠落を解消する（どのオプションを選んでも効く土台）
      - FastAPI + uvicorn[standard] + pydantic-settings の依存追加と、動く `app` オブジェクト
        （`app/main.py` の create_app factory + module-level `app`、`app/settings.py`、
        `app/db.py`（async engine/session/Base）、`app/routers/{health,items}.py`、
        `app/schemas.py`、`app/models.py`（デモ Item））
      - Dockerfile ENTRYPOINT / compose command を CLI（--version）から
        `uvicorn {{ package_name }}.app.main:app` に変更（HEALTHCHECK は python urllib で
        /health を叩く）。compose api にも healthcheck + postgres の service_healthy 依存
      - pydantic-settings で .env.example の DATABASE_URL / HOST / PORT を読む
      - docs の「Add fastapi + uvicorn yourself」を廃止し、生成物に含める
- [x] `use_recommended_web_api` ゲートを新設する（既存の use_recommended_* 方式に乗せる。
      設計原則5）
      - 推奨: FastAPI + async SQLAlchemy 2.0 + alembic + asyncpg + Postgres + demo router/model +
        httpx(ASGITransport) テスト + asgi-correlation-id（リクエストID常時）+
        BackgroundTasks デモ（常時・依存追加なし）
      - No を選ぶと下記の詳細質問が出る
      - **DB 戦略**: CI は _test.yml が自動で DATABASE_URL を postgres サービス用に組み立てて
        渡す（実 DB を検証）。ローカルは sqlite+aiosqlite フォールバック（.test.db は gitignore）。
        テストは Base.metadata.create_all を使用（alembic はスキーマ進化専用）
- [x] 詳細質問の候補（s3rius の機能一覧から、このテンプレートで採用するものを絞る）
      - **認証**: **不採用**（docs に「後で足せる」+ 理由を明記）。fastapi-users は
        メンテナンスモード（セキュリティ更新のみ・後継開発中）のため、模範として焼き込まない。
        自作 JWT デモはセキュリティ責任が乗るため不採用。OIDC/SSO 連携や JWT ライブラリを
        docs で案内
      - **Redis**: 不採用（「後で足せる」に記載）
      - **バックグラウンドタスク**: FastAPI 標準 BackgroundTasks を常時デモ。taskiq/arq は
        docs の「後で足せる」に
      - **オブザーバビリティ**: **prometheus-client 直接の薄いミドルウェア**（約20行）で
        /metrics を実装。prometheus-fastapi-instrumentator は現行 fastapi/starlette
        （0.137+ / 1.x）と非互換（_IncludedRouter 問題）が繰り返しているため不採用
      - **demo 生成**: 常時生成（モデル + CRUD ルーター + テスト）
      - **DB**: Postgres 固定。テスト用 sqlite+aiosqlite は dev 依存として採用
      - **ORM**: SQLAlchemy 2.0 の1本固定（s3rius の 5種選択は取らない）
      - **採用した詳細質問（No 後）**: prometheus / rate_limit(slowapi) / cors — 3つのみ
- [x] 各オプションは「空ディレクトリ + 依存」で終わらせない（specialty 解体の教訓）:
      採用した項目（prometheus / rate_limit / cors / request-id / backgroundtasks）はすべて
      app 配線・テスト付きで「動く」状態。uv sync + pytest + ruff + basedpyright で実動検証済み
- [x] 取り込まない機能を明記する: GraphQL / REST 選択、Kafka / RabbitMQ、ORM 複数選択、
      gunicorn（uvicorn で足りる）、self-hosted swagger（FastAPI 内蔵で足りる）、
      traefik ラベル、piccolo ORM、SQLAdmin / FastCRUD、taskiq/arq。docs/how-to/web-api.md に
      「後で足せる」と理由付きで明記
- [x] **web_api をトップレベル app/ パッケージへ再設計**（2026-09）
      - FastAPI アプリを src/<pkg>/app から **top-level `app/`** へ（`uvicorn app.main:app`）。
        ライブラリ <pkg> を廃止し、src/flat で2重化していた app/（byte-identical）を1本化
      - CLI（`__main__.py`）/ test_cli / test_qa を web_api では生成しない
        （uvicorn 起動が本流。テストは tests/test_app.py のみ）
      - MCP は cli 限定へ（web_api に <pkg>/mcp_server.py の置き場が無くなった。項目5）
      - layout 質問から web_api を除外し、`pkg_dir` / `import_pkg` 内部変数で
        「import ルート = app」を一元化。logging_setup は _shared/ の共通 partial にし
        <pkg> と app の両方から include（詳しくは docs/explanations/template-dev.md）
      - **「複雑な web_api が欲しい場合は upstream full-stack-fastapi-template を案内」**
        と help / docs に明記（web_django 方式。フロント・認証等はスコープ外）
- [ ] **将来拡張: app 構造を選べるようにする**（2026-09 相談で保留 → 結論: 追加しない）
      - 現状は top-level `app/` のレイヤード構造（`app/models.py` + `app/schemas.py` +
        `app/routers/`）固定。benavlabs/FastAPI-boilerplate のような **vertical-slice**
        （機能ごとの `modules/<feature>/{model,schema,router}.py`）は**詳細質問に追加しない**
        と決定（2026-09）。web_api は「シンプルな API のみ」に限定し、複雑な要求は
        upstream full-stack-fastapi-template を案内する。vertical-slice が欲しい場合は
        その案内先で実現する
      - デモ Item 1つでは両構造の差がほぼ出ない、という理由付けも残る
- [ ] **将来拡張: SQLAdmin（管理画面）/ FastCRUD を詳細質問に追加**（2026-09 相談で保留）
      - benavlabs は SQLAdmin ベースの admin + FastCRUD を採用。用途が違う
        （SQLAdmin = 人間がブラウザで CRUD、FastCRUD = API コードのボイラープレート削減）ため
        両方載せる場合は独立質問になる
      - 各オプションは「動く見本 + テスト」必須（デモ Item 前提）。現状は docs の
        「後で足せる」に記載のみ

## 7. VFX 分野（マイクロPython型の特殊 project_type として検討）

- [ ] VFX は「特殊ビルド/実行対象」という点で micropython と同型と判断。
      ただし1つの巨大 project_type にせず、まず**単一DCC（Houdini）の最小実装**から
      始める（micropython が esp32 から始まったのと同様）
      - DCC内Python（hython / mayapy）は CPython と非互換の実行環境で、
        pip 配布より DCC プラグイン/シーン資産として展開する
      - 依存は pixi / conda（USD、OpenImageIO、OpenColorIO 等の native deps）
- [ ] micropython の実装（firmware/ 特殊レイアウト、専用ビルド、専用テスト、専用 CI）を
      「特殊 project_type の青写真」として参照する
- [ ] Maya / Nuke / アセット管理 / ocio 設定はスコープ外（後続TODO）と明記する

## 8. セキュリティ / CTF の扱い

- [ ] CTF を project_type に**追加しない**（実行環境は既存 library/cli と同じ。
      設計原則2）。online_judge とも別物（CTF に AI 可否の大会規約は無い）と整理する
- [ ] セキュリティ基盤は既に実装済みであることを docs に明記する:
      zizmor（CI 監査）、pip-audit（脆弱性スキャン）、Sentry（任意）
- [ ] 本当に欲しいのが CTF のファイルレイアウト（challenges/、solvers/）や依存
      （pwntools / z3）なら、library/cli の「亜種」として最小レイヤーを別TODOで検討
      - 参考（2026-09 調査）: pwntools の `pwn template`（exploit 雛形の自動生成。
        参加者側）、mhtoribio/pwn-scaffold（Docker + socat + gdb + solve.py の単一
        pwn 問題 scaffold。問題作成者側）、b01lers/rich-ctf-template と
        CTFd/ctfcli（CTF コンペ全体の構成・運営。問題作成者側）。参加者側の
        「問題別フォルダ + pwntools 初期化」は online_judge の空ワークスペースに
        近いので、そちらへの載せ方も含めて検討する

## 9. SRE / Ansible / IaC の扱い

- [ ] Ansible を project_type に**追加しない**（YAML プロジェクトであり Python の
      実行環境と噛み合わない。設計原則3: web_django 方式で拒否・案内する）
- [ ] Terraform / K8s / Ansible 等の IaC は「アプリの隣に置く別リポジトリの仕事」と
      位置づけ、このテンプレートでは生成しない
- [ ] SRE は「web_api の運用強化」に限定して進める:
      healthcheck、非root実行、read-only filesystem、resource limit を Dockerfile /
      compose に追加。otel / prometheus のメトリクスは上記6の「取り込まない機能」に
      従い、まず初期質問にしない

## 10. 初期ライブラリの設定（project_type / レイヤー別の初期依存マトリクス）

- [ ] project_type ごとに「初期依存セット」を一覧表（マトリクス）に整理する
      - 例: web_api → fastapi/uvicorn/sqlalchemy/alembic/pydantic-settings、
        data_science → polars/duckdb 等、online_judge → なし（stdlib のみ）。
        推奨1本 + No でカスタムの形
- [ ] 生成される pyproject.toml の初期設定を充実させる
      - ruff / basedpyright の生成先への展開がテンプレート本体と一致しているか確認
      - `[project.scripts]` の entry point と、上記4の常駐起動（daemon）の関係を整理
- [ ] 初期依存の更新（下記12のバージョン追従）と整合するよう、生成先 renovate.json の
      packageRules を依存カテゴリごとに整理する

## 11. data-science / kaggle の整理（AGENTS.md / online_judge 再編後の整合）

- [ ] data_science の純化後仕様を再確認する: notebooks / data / models / reports /
      paper の分析型として、competition 残骸（_tasks.jinja の dataset/train/predict 等
      の競技タスク、README の competition 言及、.gitignore の input//exp/ 等）を掃除する
- [ ] kaggle（online_judge 内）の初期依存を整理する: torch/lightgbm/xgboost 等の
      競技用依存、wandb、GPU/CUDA バージョン追従
- [ ] online_judge（atcoder / leetcode）と kaggle で、AI 可否の扱いが一貫しているかを
      AGENTS.md 生成ロジックで担保する（一元管理のテスト）

## 12. バージョン追従

- [ ] テンプレート本体の renovate.json の運用を点検する
      - lockFileMaintenance / pre-commit / vulnerabilityAlerts は有効。
        テンプレートが固定するバージョン（micropython_version 等）の追従方針を一元化
- [ ] `tools/check_micropython_upstream.py` のような上流確認ツールを他分野へ拡張する
      （ROS 2 distro の EOL、CUDA、python サポート一覧 等）
- [ ] 生成先 renovate.json（template/renovate.json.jinja）とテンプレート本体の同期確認
- [ ] periodic.yml の linkcheck に加え、copier.yml の default / README 記載の固定バージョン
      が古くならないかの定期チェックを検討する

## 13. セキュリティ / コンプライアンス基盤の整備（OpenSSF Scorecard / OSPS 準拠）

ルート（テンプレ自体）と生成物の両層に、OpenSSF Scorecard の検証項目とリポジトリ配置
（SECURITY.md / CODEOWNERS / ISSUE_TEMPLATE / REUSE / CITATION.cff / codemeta.json /
Scorecard workflow / zizmor SAST / Aqua.jl 風 test_qa.py）を実装した。

### 実施済み

- [x] ルート workflow の権限最小化: 全 `.github/workflows/*.yml` に
      `permissions: contents: read` と checkout `persist-credentials: false`
      （例外は push 用 `_example.yml`）。生成物側はルートへの symlink のため自動反映
- [x] ルートに SECURITY.md / LICENSE(Apache-2.0) / LICENSES/ / REUSE.toml /
      CITATION.cff / codemeta.json / .github/CODEOWNERS / .github/ISSUE_TEMPLATE/ を新設
- [x] `.github/workflows/scorecard.yml`（SHA固定・publish_results）と
      `security.yml`（zizmor-action CI）を新設
- [x] renovate に `helpers:pinGitHubActionDigests` を追加（ルートと生成物両方）
- [x] copier.yml に `use_recommended_security` ゲート + `security_policy` / `scorecard`
      詳細質問を追加。SECURITY.md / scorecard.yml は GitHub プロジェクト限定
      （effective 変数で render 時に git_platform 判定）
- [x] 生成物に SECURITY.md.jinja / security.yml.jinja / scorecard.yml.jinja /
      test_qa.py.jinja を追加（online_judge では test_qa を生成しない）
- [x] ルート tests/test_qa.py + 生成物 test_qa.py.jinja（Aqua.jl 風）
- [x] tests/test_workflow_security.py（permissions / persist-credentials / 分岐参照の静的検査）
- [x] docs/explanations/security.md + README バッジ（Scorecard）追加

### 残タスク（今回のセッションで対応）

- [x] **全アクションの SHA 固定**（ルート + 生成物）:
      ルート `.github/workflows/*.yml` の全 `uses:` を手動で 40桁SHA + `# vX.Y.Z`
      コメントに変換（renovate の pinning PR を待たず実施）。テンプレの実体ファイル
      （ci.yml.jinja / fair-software.yml.jinja / security.yml.jinja / scorecard.yml.jinja）
      も手動固定。生成物の reusable はルートへの symlink なのでルートの変換で反映。
      例外: `pypa/gh-action-pypi-publish@release/v1` のみ upstream 推奨ブランチ運用のため
      非固定（zizmor.yml に ignore で明記）。
      なお、ルートが参照していた `actions/upload-artifact@v8` は実在しないタグで
      （v8 は download-artifact のみ）、テンプレ ci.yml.jinja を v7.0.1 に修正
- [x] zizmor の全ルール有効化 + 意図的例外を ignore で明記（ルートと生成物の両方）:
      unpinned-uses（_pypi.yml の release/v1）/ artipacked（_example.yml の push 用
      credentials）/ superfluous-actions（_release.yml と ci.yml の softprops）/
      template-injection（ci.yml の toJSON(needs)）を ignore 化。disable は全廃
- [x] tests/test_workflow_security.py を全 SHA 必須に強化:
      `DELIBERATE_BRANCH_REFS`（pypi publish のみ）を例外として、それ以外の `uses:` は
      40桁SHA を必須化
- [x] 生成物 renovate.json.jinja の無効化 packageRules に新規アクションを追加:
      zizmorcore/zizmor-action（常時）/ ossf/scorecard-action + github/codeql-action
      （scorecard 有効時）をテンプレ管理対象として renovate の更新停止
- [x] ルート .pre-commit-config.yaml に `validate-cff` / `reuse` フックを追加
      （CITATION.cff / REUSE.toml の検証を本体でも実施。ともに Passed 確認）

### 残タスク（外部・手動依存）

- [ ] renovate の digest 更新を確認（SHA 固定済み参照の新バージョン追随は renovate の
      digest PR が担う。初回実行で pinning/digest PR が開くのを確認する）
- [ ] example リポジトリ（kasi-x/python-copier-template-example）を copier update で
      再生成し、test_example_repo_updates のパリティを通す
      （main push で _example.yml が自動実行）
- [ ] リポジトリ公開後に Scorecard のスコア・バッジを確認（private では機能しない）
- [ ] ブランチ保護/ルールセット（署名コミット・線形履歴・必須チェック・レビュー）は
      GitHub 設定で有効化（コードでは強制不可）

## 14. 質問票・テンプレートソースの保守性向上（2026-09）

肥大化した copier.yml（940行）と、jinja の頻出バグ（末尾改行）への対処。

- [x] **copier.yml を questions/ フラグメントへ !include 分割**（2026-09）
      - copier.yml は project_type + include 連鎖 + underscore 設定のみ（~110行）。
        questions/{ros2,micropython,online_judge,data_science,web_api}.yml（ジャンル）と
        _common_{a,b,c}.yml（横断ゲート）、_internal.yml（when:false 派生変数）
      - 各 `!include` は独立した YAML ドキュメント（同一ドキュメント内で2つ置くと
        同名キー衝突で後勝ちになる）
      - **後方参照バグ修正**: 質問が参照する内部変数（micropython_pkg / online_judge /
        kaggle）を、参照する質問より前のジャンルフラグメントに配置
        （docs_type の micropython 分岐が常に sphinx 側に落ちるバグ。テストは data 全指定の
        ため隠れていた）
      - 分割後も生成結果は byte-identical（全8タイプで HEAD と比較検証）
- [x] **質問票の完備性を機械検証するテスト群**（2026-09）
      - フラグメント union 整合（重複なし・漏れなし）
      - 質問参照の前方 DAG 性（後方参照を検出）
      - **Z3 充足検査**: 全 when 条件の充足可能性を z3-solver で検査（死んだ質問・タイポ検出）。
        z3-solver を dev 依存に追加
      - test_copier_structure.py は copier の load_template_config で !include を解決
- [x] **生成物の末尾改行を検証するテスト**（2026-09）
      - test_generated_files_end_with_single_newline: 全レンダーパスのテキストファイルが
        「末尾ちょうど1改行」であることを強制（jinja の include / 条件タグが末尾空行を
        生む頻出バグへの対処）
      - 検出・修正: pyproject.toml.jinja（poetry ブロック後の空行）、web_api の
        test_app.py.jinja（末尾 endif 後）
- [x] **テンプレートソース作成規約を docs に蓄積**（2026-09）
      - docs/explanations/template-dev.md を新設: 末尾改行制御 / _shared/ include 共有 /
        questions/ 順序・前方参照 / Z3 充足維持。各規約に強制テストをリンク
- [ ] **将来拡張: ジャンル別サブディレクトリ（_subdirectory 切替）は不採用**
      - template/ をジャンル別ツリーに分け `_subdirectory: template/{{ project_type }}` で
        切替える案は調査・実験の結果**不採用**（2026-09）。全8ジャンル共通ファイルが64あり、
        各ツリーへの symlink 共有が過大。質問票の !include 分割（上記）で主目的
        （肥大化解消）は達成済み
- [ ] **将来拡張: AGENTS.md / oj_allow_ai の設計と実装**（項目1・2 の残り。AGENTS.md は
      library / cli / web_api / data_science / script / kaggle に常時生成し、AI NG の
      online_judge 種に置かない。項目1 のチェックリストを参照）
- [ ] **残存するテスト失敗2件の解消**（2026-09 combo 対応時に発覚。いずれも HEAD でも
      失敗する既存の問題で、combo の退行ではない）
      - `test_template_with_extra_code_and_api_docs`: 生成物の sphinx docs ビルドが
        失敗する。原因切り分けから着手
      - `test_example_repo_updates`: example リポジトリとの parity 不一致。main push で
        _example.yml が example repo を再生成した後に通す（項目13 の外部依存と同型）
