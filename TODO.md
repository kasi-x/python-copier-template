# TODO

> 2026-09-07: バグ台帳(BUG.md / bugs.md / BUGS_AND_IMPROVEMENTS.md)・
> Strategy.md・copier 本体への寄稿候補(COPIER_UPSTREAM.md / upstream-drafts/)は
> ルート整理のため `notes/` へ移動しました。本文中の言及は移動前のパス表記です。

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
- **実行環境が同じでも「AI 利用の可否」という規約の軸が明確なら project_type にできる**
  - online_judge は実行環境としては script/cli と同じだが、大会ごとに
    「AI コーディングエージェントの利用可否」が異なり、生成物に AGENTS.md を
    置く/置かないが変わる。これは実行環境軸とは独立した第一級の違い。
  - 逆に、実行環境も AI 規約も同じなら project_type を増やさない。
    CTF、botter（discord / slack / LINE / Gmail）、data_science の拡充、SRE、FastHTML 等は
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

- [x] `AGENTS.md.jinja` を新設し、生成物の設定（task_runner / strictness / docs /
      project_type）に応じた開発フローを自動生成する
      - 内容: テスト・lint・type-check・docs の実行コマンド、編集してよい範囲
        （src/<pkg>/, tests/）、commit 規約（conventional）、CI の構成
      - 生成: library / cli / web_api / data_science / script / kaggle
        （online_judge の AI-NG タイプでは生成しない）
      - 配線: `agents_md_effective`（questions/_internal.yml）を新設し、ファイル名
        条件 `template/{% if agents_md_effective %}AGENTS.md{% endif %}.jinja` で
        生成有無を一元管理（mcp_effective / security_policy_effective と同型）
- [x] README.md.jinja に「See AGENTS.md for AI-agent guidance」を追記する
      （Development setup 付近。docs 生成時は docs にも反映）
- [x] .gitignore / renovate / pre-commit への影響を確認する
      （AGENTS.md は通常の md として扱い、typos / markdown lint / docs 取込の
      対象にするか決める）
      → 確認済み: 素の `.md` として扱う（末尾改行テストの対象に自動で入る）。
      typos は md を検査するが AGENTS.md 固有の除外は不要。docs 取込（index.md /
      sphinx conf）は README 側の既存リンクのみで AGENTS.md 自体は取込対象外。
- [x] CONTRIBUTING.md との住み分けを docs に明記する
      （AGENTS.md = エージェント向け簡潔版、CONTRIBUTING.md = 人間向け詳細版）
      → AGENTS.md.jinja 冒頭で CONTRIBUTING.md へのリンクを明記し住み分けを固定
- [x] AGENTS.md の有無を検証するテストを追加する
      （各 project_type と online_judge の AI 可否で、ファイルの有無が正しいこと）
      → tests/test_example.py に present/absent 4件を追加

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
- [x] `oj_allow_ai` 質問を新設する（atcoder / leetcode 選択時のみ）
      - AI 利用 OK → AGENTS.md を生成（+ README に AI 向け言及）
      - AI 利用 NG → AGENTS.md を生成しない（規約遵守）
      - 実装: questions/online_judge.yml に `oj_allow_ai`（bool, default false,
        when は online_judge かつ atcoder / leetcode）を追加
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
- [x] **2段階化**: `oj_category` 3択（data_science / competitive_coding / ctf）を
      OJ 直後に新設し、`oj_kind` の選択肢をカテゴリごとに切替（kaggle のみ /
      atcoder・leetcode・yukicoder・aoj / ctf のみ）。`default` もカテゴリ連動
      - `oj_ctf` internal を新設（online_judge かつ oj_kind == 'ctf'）。`oj_code`
        はコード提出4種に狭め（CTF 除外：challenges＋tests＋ctf extra を持つため）
      - `ctf_effective` は `oj_ctf or (include_ctf and library/cli)` の2経路に
        拡張（library/cli レイヤーと OJ 所属で同形生成）。`use_src_layout` /
        `pkg_dir` / `agents_md_effective`（CTF は AI OK で常時生成）を対応
      - README / AGENTS.md に CTF 分岐を追加。tests/test_example.py に
        `test_template_oj_ctf_workspace` を追加し、既存 OJ テスト全件に
        `oj_category` を付与
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
- [x] kaggle には AGENTS.md を生成する（AI 利用 OK のため。kaggle 固有の指示:
      GPU の使い方・submission の作り方・データ境界を含める）
      - `agents_md_effective` が kaggle を常時 true にし、AGENTS.md.jinja の
        kaggle 分岐が input/output 境界と pipeline タスクを案内する
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
        CPython + uv 実行環境に載る。マイクロPython（ビルド・実行対象が根本から
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
- [ ] **botter 向け（discord / slack / LINE / Gmail）: 常駐レイヤーの platform として
      実装する**（2026-09-08 方針確定: bot も実装する。project_type は増やさない）
      - 置き場所: `cli` / `web_api` の上に載る opt-in レイヤー（MCP と同型）。
        library には載せない（import される側に実行可能サーバを載せる動機が薄い。
        include_mcp と同じ理由）。`include_bot`（bool）+ `use_recommended_bot` ゲート +
        `bot_platform` 詳細質問（discord / slack / line / gmail / all）の構成を検討
      - 推奨1本（設計原則5「推奨1本 + No でカスタム」）:
        discord = **discord.py**（公式感・事例の多さ vs nextcord / py-cord のフォーク事情を調査して決定。
        pycord 系のメンテ状況・slash command 対応・型スタブ有無で選定）、
        slack = **bolt**（公式 SDK。slack-sdk 素朴利用との住み分けを明記）、
        LINE = **line-bot-sdk**（Messaging API。Webhook 受信は web_api 層 or 単体 FastAPI 同梱かを設計）、
        Gmail = **google-api-python-client + google-auth**（Pub/Sub push or ポーリング。OAuth 認証情報の扱いが他と異なる）
      - 各 platform は「動く見本 + テスト」必須（specialty 解体の教訓）:
        最小コマンド応答（ping/pong 相当）+ in-process または fake-transport テスト。
        空ディレクトリ + 依存だけで終わらせない。web_api の prometheus/rate_limit/cors
        3スイッチ方式を踏襲し、カタログ化しない（認証・管理UI・キュー等は docs の「後で足せる」）
      - 起動形態（項目4 の独立起動モジュール方式を踏襲）: `bot_<platform>.py` の `main()` +
        専用 `[project.scripts]`（例: `bot-discord-<name>`）。`__main__.py` / Docker
        ENTRYPOINT / `python -m <pkg> --version` テストとは衝突させない
      - トークン管理: `.env.example` のトークン変数（例: `DISCORD_TOKEN` / `SLACK_BOT_TOKEN` /
        `LINE_CHANNEL_SECRET` + `LINE_CHANNEL_ACCESS_TOKEN` / Gmail OAuth JSON パス）+
        structlog 連携。起動時 env チェック（トークン必須・欠落時は起動拒否）。
        `.env` は commit しない（MCP の `MCP_ALLOWED_HOSTS` と同型の運用）
      - ログ: 生成 `logging_setup.py` 経由（`LOG_FORMAT=json` がそのまま効く）
      - Docker での常駐/再起動方針: `docker=true && include_bot` 時の `bot-serve` タスク
        （MCP の `mcp-serve` タスクと同型）+ compose service 化・HEALTHCHECK・restart 方針。
        項目6（web_api の Docker 拡充）と一体で検討
      - 依存マトリクス: `docs/reference/dependencies.md` に bot platform 別の runtime/dev
        依存 + entry point + deptry ignores + renovate カテゴリを追記（項目9 のマトリクス維持）
      - 配線: `bot_effective`（+ platform 別 `bot_discord_effective` 等）を
        `questions/_internal.yml` に新設し、render を一元化（mcp_effective /
        scraping_effective と同型）。`use_src_layout` / `pkg_dir` / `import_pkg` /
        `agents_md_effective` / `.env.example` ゲート / `_tasks.jinja` への影響を確認
      - docs: `docs/how-to/bot.md`（生成物一覧・トークン取得手順・非対応の明記）+
        `docs/explanations/long-running.md` に bot を第二の実装例として追記 +
        zensical nav 登録。README Features の常駐レイヤー節にも bot を追記
      - テスト: render（platform 別ファイル有無・依存有無・他タイプへの leak 無し）+
        実実行（fake transport での ping/pong 応答）+ ruff / basedpyright クリーン。
        `test_internal_variable_references_are_forward_only` / Z3 充足維持
      - 設計判断メモ（2026-09-08）: LINE Webhook と Gmail push は HTTP 受信口が要るため
        `web_api` 層との組合せ（base + layer）を第一候補とし、単体 bot でも最小受信
        （単体 FastAPI 同梱 or ポーリング）を選べる形を検討。Gmail は OAuth 認証情報
        （credentials.json / token.json）の gitignore・取扱いを CTF の flag* 除外と同型で実装
      - platform 固有の設計点（実装時に1つずつ潰す）:
        discord = Gateway intents（Privileged Intents の要否・取得手順）/ slash command 登録
        （guild 即時 vs global 遅延）/ 429 rate-limit・再接続 backoff の見本化。
        slack = Socket Mode（WebSocket・ローカル開発容易）vs HTTP（署名検証必須）の選択。
        推奨は Socket Mode 1本化を検討し、署名検証コードは HTTP 選択時のみ生成。
        LINE = Webhook 署名検証（`LINE_CHANNEL_SECRET` による HMAC）の必須実装 +
        `web_api` 併用時の route 設計（単体時は最小 FastAPI 同梱か long-polling か決定）。
        Gmail = OAuth（credentials.json → token.json リフレッシュ）vs サービスアカウントの選択、
        Pub/Sub push（HTTP 受信口要）vs ポーリングの選択。token.json / credentials.json は
        gitignore + gitleaks 対象にし、commit させない（CTF flag* と同型）
      - 他レイヤーとの組合せ定義: bot × MCP / scraping / web_api / data_science の可否マトリクスを
        `combinable` / `has_*` / `*_effective` に落とす。MCP 同時有効時は entry point 衝突
        （`mcp-server-<name>` vs `bot-<platform>-<name>`）と Docker ENTRYPOINT（CLI 既定のままか、
        `bot-serve` / `mcp-serve` 併記か）を決める。ros2 / micropython / oj_code / script は
        単独のまま（bot 質問を出さない。MCP / scraping と同型の除外）
      - パッケージマネージャ横断: bot 依存の pixi（conda-forge 有無・PyPI index 指定要否）/
        poetry / uv の出し分けを pixi how-to と同型で文書化。`tools/check_upstream.py` に
        bot SDK 群（discord.py / slack-bolt / line-bot-sdk / google-api-python-client 等）の
        floor pin を追加し、週次 drift 対象にする（template-dev.md「Hardcoded pins」規約）
      - セキュリティ baseline 連動: `.env.example` ゲートに bot トークン変数を追加、
        `.gitleaks.toml` にトークンパターン（`DISCORD_TOKEN` / `SLACK_BOT_TOKEN` /
        `LINE_CHANNEL_*` / Gmail JSON）の検出可否を検討、test_qa / hygiene の整合を確認。
        AGENTS.md / 生成 README に bot の起動・停止・再起動手順（`bot-serve` タスク含む）を追記
      - （「常駐レイヤー」の設計と MCP の実装例は docs/explanations と docs/how-to に
        文書化済み。discord/slack/LINE/Gmail はこの受け皿に載せる platform の実装として着手）
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
- [x] **MCP scaffold の拡充: prompt + resource template + `.mcp.json`**（2026-09。
      参考: [Zenn 入門記事](https://zenn.dev/kiitosu/articles/31f55b99c33ce5)（v1系だが
      primitive 構成の参考）、[mcp-cookie-cutter](https://github.com/codingthefuturewithai/mcp-cookie-cutter)
      （SDK `<2.0` ピンで基盤は古いが example の豊富さが参考。デコレータ層・Streamlit UI・
      SQLite logging・JIRA DevFlow は守備範囲外として不採用））
      - 三 primitive 揃え: tool（add/divide）+ resource（about + greeting template）+
        prompt（review_code）。in-process テスト7本、basedpyright/ruff/format/deptry 全クリーン
      - `.mcp.json` 生成でホスト登録ゼロ手間化。README・how-to に登録手順を追記
- [ ] **将来拡張: 配布前提スタンドアロン MCP サーバのレシピ**（reference servers 型）
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

## 7. セキュリティ / CTF の扱い

- [x] CTF を project_type に**追加しない**（実行環境は既存 library/cli と同じ。
      設計原則2）。online_judge とも別物（CTF に AI 可否の大会規約は無い）と整理する
      → docs/reference/questionnaire.md に「Not project types」節として文書化済み
- [x] セキュリティ基盤は既に実装済みであることを docs に明記する:
      zizmor（CI 監査）、pip-audit（脆弱性スキャン）、Sentry（任意）
      → pip-audit は _tasks.jinja の `audit` タスクとして分離（recommended/full のみ。
      OSV/PyPI への network 依存のため type-check/check/CI からは外し、offline でも
      green を維持）。zizmor / Sentry は従来通り docs 記載
- [x] 参加者向け CTF レイヤー（`include_ctf`）を実装する（library / cli の上に載る
      opt-in レイヤー。`ctf_effective` で render を一元化）
      - 生成物: `challenges/pwn/example/solve.py`（stdlib のみで動作＋pwntools
        レシピ同梱）、`tests/test_ctf_example.py`（solve.py の実実行検証）、
        `ctf` extra（pwntools / z3-solver）、.gitignore（vuln / flag* 除外）、
        ruff per-file-ignores（challenges 緩和）、deptry DEP002 許可
      - テスト: tests/test_example.py に3件（render / 実実行＋ruff /
        他タイプへの leak 無し）。構造（Z3/forward-only/union）・改行・QA 全緑
      - 対象外（据え置き）: 問題作成者側（Docker+socat+gdb、CTF 運営）は別リポジトリの
        仕事として生成しない

## 8. SRE / Ansible / IaC の扱い

- [x] Ansible を project_type に**追加しない**（YAML プロジェクトであり Python の
      実行環境と噛み合わない。設計原則3）
      → questionnaire.md の Not project types 節に文書案内として記載
      （web_django のような生成時 abort は無し — 選択肢自体が無いため）
- [x] Terraform / K8s / Ansible 等の IaC は「アプリの隣に置く別リポジトリの仕事」と
      位置づけ、このテンプレートでは生成しない → 同上
- [x] SRE は「web_api の運用強化」に限定して進める:
      healthcheck、非root実行、read-only filesystem、resource limit を Dockerfile /
      compose に追加。otel は見送り（初期質問にしない）。prometheus / rate_limit /
      cors の3スイッチは web_api の観測面として維持
      → 実装済み: Dockerfile runtime に USER appuser + /app chown（uv/pixi 両方）、
      compose.local.yml に read_only + tmpfs（/tmp と ~/.cache）+ mem_limit/cpus
      （plain `compose up` で効く service-level）。
      HEALTHCHECK は従来通り。otel は見送り

## 9. 初期ライブラリの設定（project_type / レイヤー別の初期依存マトリクス）

- [x] project_type ごとに「初期依存セット」を一覧表（マトリクス）に整理する
      - 例: web_api → fastapi/uvicorn/sqlalchemy/alembic/pydantic-settings、
        data_science → polars/duckdb 等、online_judge → なし（stdlib のみ）。
        推奨1本 + No でカスタムの形
      → docs/reference/dependencies.md を新設（runtime/dev/experiment/entry point/
      deptry ignores/renovate/config parity を記載）。zensical nav + reference.md に登録
- [x] 生成される pyproject.toml の初期設定を充実させる
      - ruff / basedpyright の生成先への展開がテンプレート本体と一致しているか確認
        → 共有選択肢（ALL+preview、line-length 120、single-line isort等）は一致、
        差分は意図的（対象の違い）を文書化。ついでに kaggle の deptry 24件を解消
        （`responses` 除去 + ML依存/自己参照の ignore 追加、新規テストで固定）
      - `[project.scripts]` の entry point と、上記4の常駐起動（daemon）の関係を整理
        → マトリクス文書の Entry points 節に整理済み（CLI/MCP/web_api等の対応表）
- [x] 初期依存の更新（下記12のバージョン追従）と整合するよう、生成先 renovate.json の
      packageRules を依存カテゴリごとに整理する
      → Core CI / Release / Container / PyPI / Docs / Scorecard / FAIR /
      Dockerfile の8カテゴリに分割。パリティテストも分割対応に更新
## 10. data-science / kaggle の整理（AGENTS.md / online_judge 再編後の整合）

- [x] data_science の純化後仕様を再確認する: notebooks / data / models / reports /
      paper の分析型として、competition 残骸（_tasks.jinja の dataset/train/predict 等
      の競技タスク、.gitignore の input//exp/ 等）を掃除する
      → 確認済み: _tasks の競技タスクは kaggle 条件、template/.gitignore を
      .gitignore.jinja 化して DS/Kaggle ブロックを条件化し、root から input//exp/
      を削除。.dockerignore も同様に条件化（DS 全枝 + kaggle 全枝）。
      test_gitignore_same は union 検査に更新。README の competition 言及は
      kaggle パスのみ残存（data_science パスは無し）— 意図通り
- [x] kaggle（online_judge 内）の初期依存を整理する: torch/lightgbm/xgboost 等の
      競技用依存、wandb、GPU/CUDA バージョン追従
      → cu124→cu126（torch 2.6凍結のため。cu126でtorch 2.14.0+cu126解決を確認）、
      optuna>=3.5→>=4.0、torch>=2.6→>=2.12、torchvision>=0.21→>=0.27、
      Dockerfile.gpuもCUDA 12.6.3に更新。deptryはクリーン維持
- [x] online_judge（atcoder / leetcode）と kaggle で、AI 可否の扱いが一貫しているかを
      AGENTS.md 生成ロジックで担保する（一元管理のテスト）
      → `agents_md_effective` が library / cli / script / web_api /
      data_science / kaggle を常時、oj_code は oj_allow_ai 時のみ true にし、
      ros2 / micropython は false。tests/test_example.py の 4件で固定

## 11. バージョン追従
- [x] テンプレート本体の renovate.json の運用を点検する
      - lockFileMaintenance / pre-commit / vulnerabilityAlerts は有効。
        テンプレートが固定するバージョン（micropython_version 等）の追従方針を一元化
      → 点検済み: extends/vulnerabilityAlerts/lockFileMaintenance は両方で有効。
- [x] `tools/check_micropython_upstream.py` のような上流確認ツールを他分野へ拡張する
      （ROS 2 distro の EOL、CUDA、python サポート一覧 等）
      → tools/check_upstream.py に統合（MicroPython tag/stubs + CUDA base/cu-index +
      ROS 2 EOL + Python floor + Postgres + Ubuntu）。週次 check-upstream.yml で
      drift issue を自動作成。旧ツールは shim として残し、旧 workflow は手動化。
      template-dev.md に「Hardcoded pins need an upstream check」規約を追加
- [x] 上流フォーク（DiamondLightSource）の新規コミット検知と、copier 自体の
      メジャー更新検知を追加する
      → git フォーク追従は tools/check_upstream_fork.py + 週次
      check-upstream-fork.yml（火曜 06:00）。**check-upstream.yml（pin 専用・月曜）とは
      別物** — 名前は似ているが役割が違う。copier は root pyproject.toml で
      `>=9,<10` に pin し、check_upstream.py が「copier ceiling」pin として
      メジャー drift を週次報告する。ルート依存の pip-audit は task audit +
      週次 dependency-audit.yml（木曜 07:00）で実施
- [ ] v1.0 公開のタイミングで fork を解除し、履歴を新規にして独立リポジトリとして
      公開し直す（2026-09 方針確定。GitHub Support への detach 依頼はしない）
      → 手順: 作業クローンで `git checkout --orphan` + 単一初期コミットを作成し、
      `gh repo create` した新リポジトリへ push（過去ログ・DiamondLightSource 由来の
      履歴は持ち込まない。setuptools-scm 用に v1.0.0 tag を打ち直す）。
      新リポジトリで再設定が必要なもの: EXAMPLE_DEPLOY_KEY 等の secrets、
      GitHub Pages、branch protection、renovate 連携。
      check-upstream-fork.yml は URL 直 fetch なので解除後もそのまま機能する
      （fork の間は Issues が無効のため、週次 workflow の issue 作成ステップは失敗する。
      気になるなら detach まで該当 workflow を無効化）
      → **継承タグの危険性を実害として確認（2026-09-06）**: 現時点の最新タグは
      5.4.0（2026-08-14、DiamondLightSource 由来の内容）で、`copier copy URL` を
      **`--vcs-ref` 無し**で実行すると copier は最新タグをチェックアウトするため、
      古い upstream テンプレートが「現行テンプレート」として使われてしまう
      （BUG.md #1「docs_type に zensical が無い」・#6「component_owner を聞かれる」
      の2件はどちらもこの罠が原因。`git show 5.4.0:copier.yml` で確認済み）。
      **detach まで全ドキュメントの URL 生成コマンドは `--vcs-ref=main` 必須**
      （README / docs/tutorials/create-new.md / adopt-existing.md は対応済み）。
      孤立例: 新規プロジェクトを作るチュートリアル、example 再生成 CI
      （`_example.yml` は既に `--vcs-ref=HEAD` 付きで正常）。detach 時に上記タグを
      削除・打ち直す作業を忘れないこと

## 12. セキュリティ / コンプライアンス基盤の整備（OpenSSF Scorecard / OSPS 準拠）

ルート（テンプレ自体）と生成物の両層に、OpenSSF Scorecard の検証項目とリポジトリ配置

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

## 13. 質問票・テンプレートソースの保守性向上（2026-09）

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
- [x] **pyproject.toml.jinja を `_shared/` フラグメントへ分割**（2026-09。項目5の
      mcp_server.py / logging_setup.py と同じ「共有 partial + 薄い include」パターンを、
      肥大化した pyproject.toml.jinja 自体にも適用）
      - `_shared/pyproject-basedpyright.toml.jinja` / `-ty-checkers.toml.jinja`（pyrefly/ty）/
        `-test-coverage.toml.jinja`（pytest/coverage/typos/vulture/deptry）/
        `-ruff-lint.toml.jinja`（select/ignore/task-tags 本体）/ `-ctf-extra.toml.jinja` /
        `-ctf-lint.toml.jinja` / `-scraping-lint.toml.jinja` / `-kaggle-lint.toml.jinja`
        （per-file-ignores 各節）を新設し、本体からは `{% include %}` のみにする
      - `_shared/pyproject-scraping-banned-api.toml.jinja` は下記項目14（scraping
        レイヤー）の ruff `banned-api` 節をここに同居させ、本体は1行 include のまま
      - 末尾改行規約（上記）はここでも適用: 各 include の直前直後で改行を持たない
        ラッパー行にする。`.pre-commit-config.yaml` の `end-of-file-fixer` に
        `.jinja` 除外を追加し、`pre-commit run --all-files` がこの規約を壊して
        レンダー結果に空行を混入させる事故を構造的に防止（2026-09 に実際に
        7ファイル巻き込まれて発覚・修正 — 生成物側の改行検証は既存の
        `test_generated_files_end_with_single_newline` が担うので、ソース側の
        `end-of-file-fixer` は不要かつ有害と判断）
- [x] **`tests/test_machine_gate.py` を新設**（2026-09。高速な静的事前検査）
      - 全 `.jinja` ソースを Jinja2 でパース（if/endif 不整合等の壊れを検出）+
        全 `questions/*.yml` を YAML としてロード + copier 自身の
        `load_template_config` で解決可能かを検証。uv sync 不要・オフラインで
        ミリ秒オーダーに終わるため、test_example.py の重いレンダーテストより先に
        壊れを検出できる
- [ ] **将来拡張: ジャンル別サブディレクトリ（_subdirectory 切替）は不採用**
      - template/ をジャンル別ツリーに分け `_subdirectory: template/{{ project_type }}` で
        切替える案は調査・実験の結果**不採用**（2026-09）。全8ジャンル共通ファイルが64あり、
        各ツリーへの symlink 共有が過大。質問票の !include 分割（上記）で主目的
        （肥大化解消）は達成済み
- [x] **将来拡張: AGENTS.md / oj_allow_ai の設計と実装**（項目1・2 の残り。AGENTS.md は
      library / cli / web_api / data_science / script / kaggle に常時生成し、AI NG の
      online_judge 種に置かない。項目1 のチェックリストを参照）
- [x] **残存するテスト失敗2件の解消**（2026-09 combo 対応時に発覚。いずれも HEAD でも
      失敗する既存の問題で、combo の退行ではない）
      - `test_template_with_extra_code_and_api_docs`: 生成物の sphinx docs ビルドが
        失敗する。原因切り分けから着手 → **解消**: README 先頭の H1 が
        `<div align="center">` 内にあり MyST が H1 と認識せず myst.header 警告 9件が
        --fail-on-warning で落ちていた。H1 を div 外に移動してテスト通過を確認
      - `test_example_repo_updates`: example リポジトリとの parity 不一致。main push で
        _example.yml が example repo を再生成した後に通す（項目12 の外部依存と同型。
        ローカルでは外部リポジトリへの push 不可のため未実行のまま残す）

## 14. Web スクレイピングレイヤー（include_scraping）の新設

設計原則1に従い project_type は増やさず、CTF / MCP と同じ「既存 project_type の上に
載る opt-in レイヤー」として cli に追加する。**Good-future-python** charter
（respect the source / law / commons。詳細は docs/explanations/good-future.md）を
コードで強制することが狙い — 礼儀正しいスクレイピングを「ドキュメントで頼む」のではなく
「ruff banned-api / robots.txt チェック / レート制限 / CI」で構造的に強制する。

- [x] `include_scraping` 質問を新設する（`project_type == 'cli'` のみ。項目4の
      combo 方式に合わせ `questions/_combo.yml` に配置）
      - Yes で `CHARTER.md` + フェッチャーモジュールを生成。ruff `banned-api` で
        `requests.get` / `httpx.get` / `urllib.request.urlopen` 等の直接呼び出しを
        フェッチャー外で禁止し、全フェッチが1箇所を通ることを構造的に強制
      - CAPTCHA 回避ヘルパーは一切生成しない（サイト規約違反のため対象外と明記）
- [x] `use_recommended_scraping` ゲート（既存 use_recommended_* 方式）+
      `scraping_engine` 詳細質問（httpx / scrapy / memorious / playwright / all）
      - 推奨: httpx — stdlib robots チェック + per-host レート制限 + on-disk
        キャッシュのポライトフェッチャー。新規ランタイム依存なし・オフラインテスト
      - No を選ぶと4エンジンから選択（all は全エンジン同時生成）
- [x] エンジンごとの生成物（`_shared/fetcher-httpx.py.jinja` 他3種 + wrapper 8種
      [src/flat layout × 4エンジン]。項目5/13 と同じ「共有 partial + 薄い wrapper」
      パターン）
      - **httpx**（全エンジンの土台。memorious/playwright/all も再利用）:
        `preflight()` が feed（`/feed`, `/rss.xml`, `/atom.xml`...）→ API ヒント
        （`/api`, `api.` サブドメイン, `openapi.json`）→ scraping の順で判断
        （feed-first / API-second / scraping-last）。robots.txt 拒否は
        `RobotDeniedError`、401/403 は `AccessDeniedError`（回避せず停止）、
        host あたり `max_requests_per_host`（既定100。discovery probe も含む）
        超過は `BudgetExceededError`。判断結果は origin 単位でキャッシュし
        2ページ目以降の probe コストを削減
      - **scrapy**: `ROBOTSTXT_OBEY` + `AUTOTHROTTLE` + `DOWNLOAD_DELAY` を
        `custom_settings` に強制したスパイダー starter
      - **memorious**: レート制限・キャッシュ済み HTTP セッションの crawler config。
        **memorious4 は AGPL-3.0** のため選択時に `license_effective` を
        AGPL-3.0 へ強制上書き（勝手に MIT へ戻さないよう README/docs に明記）
      - **playwright**: JS レンダリングページ向け headless-Chromium フェッチ
        （robots precheck はフェッチャーから再利用）。テストではブラウザ起動しない
        （config デフォルトのみ検証）
      - 全エンジンに offline テスト付き: `test_scraping.py` /
        `test_scrapy_spider.py` / `test_memorious_crawler.py` /
        `test_browser_fetch.py`（`{% if scraping_*_effective %}` で個別出し分け）
- [x] `.cache/fetcher/` / `.cache/ms-playwright/` を gitignore（`_shared/`
      partial 化し `template/.gitignore.jinja` とルート `.gitignore` の両方に
      union 反映。項目13 の末尾改行規約に従い include ラッパーは改行なしで終端）
- [x] docs 新設: `docs/how-to/scraping.md`（生成物一覧・ライセンス影響・非対応の明記）+
      `docs/explanations/good-future.md`（charter 本文。respect the source /
      law / commons の3原則と、各ルールの実施箇所（ruff/pytest/CI）の対応表）+
      zensical.toml nav 登録
- [x] テスト: `test_template_include_scraping_httpx` / `_runs` /
      `_not_offered_elsewhere` / `test_template_scraping_engine_choices` /
      `test_template_scraping_memorious_forces_agpl`（他 project_type に
      scraping 関連の依存/質問が漏れないことも検証）
- [ ] **将来拡張**: CAPTCHA 回避以外のポライトネス拡張（sitemap.xml 優先探索、
      条件付き GET の ETag/If-Modified-Since 対応）は要望が出てから検討。
      現状は feed/API 優先探索 + robots.txt + レート制限 + キャッシュで
      「行儀の良いデフォルト」を満たしていると判断し、初期スコープに含めない

## 15. 検知・運用の残課題（2026-09-05、Strategy.md 実装後に判明）

### 追加対応（2026-09-05 bugs.md / 生成セッションのフィードバック）

- [x] `.env.example` / README "Environment variables" を機能ゲート化
      （web_api / mcp / scraping / sentry / agent scaffold のいずれかがあるときのみ。
      依存ゼロ library へのノイズ解消 = bugs.md #3。`.envrc` は venv アクティベーション
      用として全タイプ常に生成）
- [x] devcontainer ベースイメージを実在する
      `ghcr.io/diamondlightsource/ubuntu-devcontainer:resolute` に戻し
      （`kasi-x/ubuntu-devcontainer` は未公開で devcontainer ビルドが 404 する =
      bugs.md #2）+ `tools/check_upstream.py` に Devcontainer base pin
      （GHCR manifest 実在チェック、404 で drift）を追加
- [x] `use_recommended_agent` の質問文を gate 形式に修正
      （"Add an LLM agent scaffold?" は Yes の意味と gating が逆 = bugs.md #1。
      変数名は設計原則の `use_recommended_*` 統一のため維持）

### 既知の残課題

Strategy.md ①②③④ は commit a82f9a46 で実装済み。当日の push 検証で
**CI-only の失敗が3種類**見つかり、すべて修正済み（詳細は各項目）。

- [x] lint 失敗（2段階）: (a) check-yaml × copier.yml（multi-document）→
      exclude を追加。(b) 新設テストファイルの ruff format 差分（ルートの
      line-length は 120）→ format 適用。**レッスン: 新規ファイル追加後も
      `task lint` を回す。ローカル通過をファイル作成前に確認して終えていた**
- [x] test 失敗①: `test_example_repo_updates` が clone する
      `kasi-x/python-copier-template-example` が存在しない（404）
      → リポジトリを新規作成（public）+ 現 HEAD から生成して初期 push +
      書き込み可能 deploy key を登録 + `EXAMPLE_DEPLOY_KEY` secret を設定。
      テストがローカルで pass することまで確認済み
- [x] test 失敗②（テンプレートバグ）: CI の `_test.yml` は Postgres サービスなしの
      組み合わせで**空文字の `DATABASE_URL` を export する**ため、生成 web_api の
      `settings.py` が空 URL を既定値の代わりに採用し `test_app.py` の import が
      落ちていた（09-03/04 の postgres CI 導入以降、CI だけ赤で未発見）。
      → `env_ignore_empty=True`（settings）+ 生成 `test_app.py` 側も
      空文字を未設定扱いにするよう修正。空 DATABASE_URL での再現テストで確認
- [x] docs 失敗: gh-pages publish が 403。リポジトリの
      `default_workflow_permissions` が read であり、reusable workflow
      （`_docs.yml`）自身の top-level `permissions: contents: read` が
      呼び出し元（ci.yml）の write をキャップするため
      → `_docs.yml` の build ジョブに `permissions: contents: write` を明記
- [x] `example` ジョブも非対話で copier が停止する問題を修正
      （085b1579 追加の scraping 質問が example-answers.yml に答えを持たないため。
      `_example.yml` に `--defaults` + `--with copier-template-extensions` +
      `--trust` を追加。テストの update コマンドとは既に揃っていた）
- [ ] **次の CI run が緑になることの確認**（上記修正の push 後。test 12分前後）
      → 2026-09-07: 大規模変更(bug修正一式 + pre-commit 廃止)を push 済み。
      初回ランで2件の新規失敗を処理済み: ①`_hygiene.yml` のEOFチェックが
      ディレクトリsymlinkでクラッシュ + .jinja 部分テンプレ(意図的に改行なし)を
      検出 → 除外して修正(987abac7)。②Security が zizmor v1.30 の新監査
      `unpinned-tools`(setup-just の just-version 未指定)で失敗 → just 1.58.0 に
      ピン + check_upstream の週次ドリフト報告に追加(87058c2a)。③同 v1.30 の
      `self-repository` 監査が既存の `./.github/workflows/*` 参照形式全体に発火
      → 両 zizmor.yml に意図的 ignore を記載(87e3525e)。最終ランの結果確認が残る
      - [ ] **教訓**: security.yml の zizmor `version: latest` は新監査追加時に
            全プロジェクトの Security を赤くする。ignore 追加はリポジトリ慣例どおり
            理由付きで。zizmor バージョンの固定+renovate追従も検討余地
- [ ] README の CI バッジと実態の乖離に注意: 直近コミットで CI が赤でも
      バッジは古い成功を示し続けた。赤を放置しない運用（push 後の run 確認、
      または merge queue / required checks の見直し）を習慣化する
- [ ] Periodic（リンクチェック）: 2026-08-26 / 09-02 の赤は旧 tox 版 workflow の
      失敗。現行 lychee 版（085b1579 で投入）は水曜スケジュールが初回実行 →
      初回結果を確認し、赤ならリンク修正
- [x] flaky: `test_template_task_runner_just_works` がフル並列実行で 1 回のみ
      失敗（単独・再実行は pass）→ **診断完了（2026-09-06、サブエージェント調査）**。
      最有力は pre-commit 共有ストアの hook 環境インストール競合:
      `repository.py` の `_hook_install` は `py_env-*` を rmtree+再インストールするが
      クローンと異なり flock が無く、hook `rev` 更新後のコールドウィンドウで
      32 ワーカーが同一環境を同時構築して 1 ワーカーが部分的なインストールで落ちる
      （uv キャッシュは競合安全設計のため疑いから除外、git 競合も個別 tmp_path のため除外）。
      対策として xdist ワーカー毎の `PRE_COMMIT_HOME` 分離を試したが、
      **コールドインストールが 32 回発生して 48 失敗・7分44秒化したため撤回**
      （tests/conftest.py に経緯を記載）。発生頻度は低いため現状は共有ストアのまま、
      flake 時は solo 再実行。pre-commit 本体への報告草稿を
      upstream-drafts/10 に用意済み
- [x] ルート `.python-version` が未レンダの Jinja 式のまま（`ros2_pkg` 等の変数は
      ルートに存在しない）。全 uv コマンドで warning が出て CI ログも汚れるので、
      `3.11` 等の固定値にするか削除する
      → **解消（2026-09-06）**: ルート `.python-version` は `3.11` に固定。
      生成物側は `template/.python-version.jinja` がルートへの symlink だったため
      ros2 の distro 別ピン（humble=3.10 / jazzy=3.12）が壊れていた — symlink を
      解除して Jinja 式の実ファイルに戻し、ルートと生成物で役割を分離。
      ros2 テスト2件の失敗も同時に解消
- [x] ~~fork の間は Issues が無効のため、週次 workflow の issue 作成ステップが
      失敗する~~ → **解消（2026-09-06）**: リポジトリで Issues / Discussions を
      有効化した（節16 フェーズ0）。workflow 側のガードは不要

## 15.6. ランナー実行監査で発見したバグ（2026-09-07）

「lint タスクが各タスクランナーで**実行**できること」を検証した（それまで
レンダー内容の assert のみで、実行は task/just のみカバー）。即座に3件発見:

- [x] **poe**: `lint` の `&&` 入りコマンドが `cmd` 型（非シェル）で壊れる
      → `_tasks.jinja` の poe 出力を、単一コマンドでも `&&` を含む場合は
      `shell` 型にする分岐で修正
- [x] **非 git ワークスペースで `uv sync` が即死**（前述の fallback_version）も
      この監査で発見
- [x] **invoke / duty**: 生成された tasks.py / duties.py 自体が ruff format
      違反（余分な空行・88超の1行コマンド）→ フォーマッタテンプレートを
      書き直し（2空行整列・複数行 ctx.run/c.run・E501 ファイル豁免）+
      `_version.py`（setuptools-scm が単一引用符で生成）を ruff 対象外に
- [x] **恒久テスト**: `test_task_runner_lint_tasks_execute`（make + poe を実走。
      invoke/duty は生成プロジェクト自身の ruff が tasks/duties ファイルを
      検査するためフォーマット面を担保）、pixi ネイティブタスクの内容固定

## 15.4. pre-commit 廃止 → GitHub Actions への移行（2026-09-07）

方針決定: pre-commit はテンプレートにも本リポジトリにも残さない。
開発フローは「**`fix` タスクで自動修正してから commit**(明示的)」に変更し、
リポジトリ衛生チェックは CI の **`_hygiene.yml`** reusable workflow に集約した。

- [x] **生成物の lint タスクを ruff 直実行に変更**:
      `lint` = `ruff format --check .` + `ruff check .`(チェックのみ・CI 安全)、
      旧 `code-fix` を **`fix`** に改名(`ruff check --fix` + `ruff format`)。
      typos / deptry / vulture / basedpyright は従来どおり `type-check` タスクに残存
      (pre-commit とは二重だった)
- [x] **`_hygiene.yml` 新設**(ルートに実体、生成物へ symlink、`{% if not ros2_pkg %}` ゲート):
      競合マーカー / 10MB超ファイル / EOF改行 / YAML パース(jinja・copier.yml 除外)/
      **gitleaks**(gitleaks-action@SHA、.gitleaks.toml 引き継ぎ)/
      **actionlint**(`docker://rhysd/actionlint` を sha256 ダイジェスト固定)/
      **conventional commits**(uvx conventional-pre-commit==4.4.0 で PR title + 各コミットを検証)/
      **nbstripout**(ipynb がある時だけ、hashFiles ゲート)/
      **REUSE**(hashFiles ゲート)/ **CITATION.cff**(cffconvert、hashFiles ゲート)
- [x] **ci.yml(ルート+生成物)** に hygiene ジョブを追加し required-checks に組み込み
- [x] **削除**: `template/.pre-commit-config.yaml.jinja`、ルート `.pre-commit-config.yaml`、
      生成 pyproject dev 依存の `pre-commit`(全 strictness 分岐)、ros2+pixi pixi.toml の
      依存とタスク、devcontainer の `pre-commit install` と `PRE_COMMIT_HOME`
- [x] **テキスト同期**: 生成 README(バッジ含む)/ AGENTS.md(check は git 無しで動く旨に
      更新 = bugs.md #4 の根本解決)/ CONTRIBUTING / PR テンプレート / zizmor.yml・
      actionlint.yaml のヘッダコメント / questions の help 2件 / ルート README /
      docs 配下(lint how-to 全面書き直し ほか)
- [x] **renovate**: pre-commit manager 削除、template renovate.json.jinja に
      「Hygiene actions」無効化ルール新設(gitleaks-action / rhysd/actionlint /
      reuse-action / cffconvert — 生成プロジェクトは copier update 経由で更新)
- [x] **tools/check_upstream.py**: core PyPI floor パターンから pre-commit を除去
- [x] **テスト**: `test_gitleaks_precommit.py`(実走)→ `test_gitleaks_config.py`(静的:
      設定リンク・SHA ピン・SealedSecrets 許容範囲が YAML スコープのまま・塩ルール存続);
      `test_template_no_precommit_hygiene_in_ci` 新設; renovate パリティテストは
      `docker://` を bare イメージ名に正規化; README バッジテストはバッジ不在を固定;
      `test_workflow_security.py` は docker:// ステップの sha256 ダイジェスト要件を追加
- [x] zizmor(生成 `_hygiene.yml` クリーン)/ actionlint(クリーン)/ REUSE lint 準拠を
      ローカルで確認、フルスイート green

## 15.5. BUG.md / bugs.md / BUGS_AND_IMPROVEMENTS.md の一括処理（2026-09-06）

3つのバグ報告ファイル + TODO 17 の未解決項目を全点検証し、再現するものだけ直した。
詳細な項目別ステータスは各ファイル内の 2026-09-06 追記を参照。

**テンプレート側で解決できず copier 本体に起因する問題は
`COPIER_UPSTREAM.md` に寄稿候補として整理した**（unsafe 拒否の UX、exit code
未ドキュメント、jinja 拡張の依存宣言、answers-file のエラー文面、
required 質問の一括報告、DirtyLocalWarning、settings trust の発見性）。
9.18.1 のソースで裏付け取り、upstream の既存 issue との重複も確認済み。

- [x] **web_api + sphinx docs が壊れる**: `docs/conf.py` / `_api.rst` /
      `reference.md` が `{{ package_name }}` を import しており、web_api
      （import root = `app`、`<pkg>` は生成されない）で docs build が必ず落ちる
      → `{{ import_pkg }}` に統一 + オフライン耐性（switcher 確認の
      `requests.get` を try/except）。テスト追加
- [x] **micropython + sphinx の組合せが壊れる**: docs_type の choices を静的化した
      副作用で sphinx が選べてしまい、import できないパッケージの autodoc で
      docs build が落ちる → render 時に zensical へフォールバック
      （`sphinx` / `zensical` internal 変数。AGPL 強制上書きと同型）。テスト追加
- [x] **`_dist.yml` の `--version` 検査が `find | head -1` 推測**:
      `version-command` input を新設し、生成側 `ci.yml` が `import_pkg` から
      正確なコマンドを渡す（web_api は CLI entry point が無いため import チェック）。
      data_science（src/ 直下にパッケージ無し）で旧ヒューリスティックが壊れる件も同時解消
- [x] **非インタラクティブ生成の根本原因**: copier は unsafe feature ありの
      テンプレートを `--trust` 無しでは**何も出力せず exit 4** で終了する。
      README の非インタラクティブ節を `--trust` 必須 +
      `uvx --with copier-template-extensions` で書き直し、トラブルシュート表付き
- [x] **全質問に default が付いていることの機械検証**
      （`test_every_asked_question_has_a_default`。`gitlab_group` だけ無かった
      — `{{ git_user_name() }}` を追加し `--defaults` + gitlab.com が通るように）
- [x] **codecov upload を push to main に制限**（`_test.yml`。PR では fork が
      token 無しで upload 失敗する noise のみ）
- [x] **`make_switcher.py` に `--ref` オプション**（gh-pages 固定の解除。
      既定は従来どおり `origin/gh-pages`）
- [x] **生成物 ruff 設定**: `DTZ007` を recommended の extend-ignore に追加
      （naive パース → `.replace(tzinfo=...)` 後付パターン。理由コメント付き）+
      `fixture-parentheses = false` を明示固定（括弧なし `@pytest.fixture` が
      テンプレートのスタイル。ruff デフォルト反転での silent restyle を防止）
- [x] **pixi how-to 新設**（`docs/how-to/pixi.md` + nav 登録）:
      `[tool.pixi.*]` in pyproject の設計、**フラットな dependencies テーブル**
      （per-package サブテーブルは `invalid character in string` エラーになる）、
      conda vs PyPI の出し分け、**PyTorch は PyPI index 指定**（conda-forge の
      ビルド欠け対策。kaggle の uv と同じ発想）、`pixi.toml` からの移行手順
- [x] **web_api + data_science コンボの `app/` と `src/` の関係**を生成物
      README（"two trees coexist" 節）と AGENTS.md（callout）に記載。テスト追加
- [x] **生成物 AGENTS.md に git init 注記**（check/lint は pre-commit 経由で
      git リポジトリ必須。publish pipeline の鶏と卵問題への回答）
- [x] **BUGS_AND_IMPROVEMENTS.md（25項目）を全点再確認**し、検証結果を同ファイルに
      記録: 10件は適用時より前に解決済み（pixi CI、vscode、concurrency、
      permissions、DLS 言及、docs 出し分け等）、#7/#17/#18/#20/#11/#8 を今回修正、
      #1/#3/#5/#6/#19/#21〜#25 は誤認または意図的設計、#9'（pyproject のコメント量）
      のみ見送り（生成物だけで完結させる教訓コメントの意図的スタイルのため）

## 16. 普及・標準化戦略（2026-09-05 調査。GitHub API で外部事実を確認済み）

「多くの人に使われる新しいスタンダードとして維持する」ための対外的な戦略。
節11(v1.0 fork解除の**手順**)・Strategy.md(内部品質の検知)とは独立の軸 ——
本節は発見可能性・比較優位・ガバナンスという対外面を扱う。詳しい根拠・比較・
一次情報源へのリンクは `docs/explanations/vision.md`（今回新設、公開ドキュメント）
に書いた。ここには実行チェックリストのみ置く。

### 現状（事実。2026-09-05、GitHub API で確認）

| repo | stars | forks | 備考 |
|---|---|---|---|
| kasi-x/python-copier-template（本リポジトリ） | 0 | 0 | fork継続中、作成2026-08-12(3週間強)、topics空、has_issues=false、has_discussions=false、homepage未設定、description が upstream 由来のまま |
| DiamondLightSource/python-copier-template（upstream） | 25 | 10 | issues 66件 open |
| pawamoy/copier-uv | 157 | 29 | 2024-02〜、単独メンテ・実績あり |
| scientific-python/cookie | 410 | 79 | Scientific Python コミュニティが背景 |
| cjolowicz/cookiecutter-hypermodern-python | 1921 | 235 | **2024-05-18 以降 push なし = 実質メンテ終了**、乗り換え先を探しているユーザー層が存在するはず |

**加えて `https://kasi-x.github.io/python-copier-template/`(と `/main/`)は現在 404**——
README・CONTRIBUTING.md が案内するドキュメントリンクが機能していない状態。
copier 公式ドキュメントには GitHub topic ベースのテンプレート発見導線があり、
`copier-template` という topic を付けるとその一覧に載る仕組みがある(現状 topics=[] で未活用)。

### フェーズ0: 今日中に終わる、コード変更不要の修正 → **実施済み(2026-09-06)**

- [x] GitHub Pages を有効化した → **初回は build_type=workflow で設定したが誤り**。
      `_docs.yml` は peaceiris/actions-gh-pages で **gh-pages ブランチ**に
      publish する方式のため、`build_type=legacy` + `source: gh-pages /` に
      訂正し、`POST .../pages/builds` で初回ビルドを手動トリガー。
      **https://kasi-x.github.io/python-copier-template/ と /main/ が 200 に
      なったことを確認(2026-09-07。長期懸案の 404 解消)**
- [x] Issues / Discussions を有効化した(`gh repo edit --enable-issues
      --enable-discussions`。fork でもオーナーなら有効化できた)。これにより
      節15 の「fork の間は週次 workflow の issue 作成が失敗する」も解消
      (workflow 側のガードは不要になった)
- [x] GitHub topics を追加: `copier-template` `copier` `python` `project-template`
      `cookiecutter-alternative` `uv`
- [x] homepage に docs URL を設定(`https://kasi-x.github.io/python-copier-template/`)
- [x] description をこのリポジトリ自身の言葉に書き直し(upstream 由来の
      "Diamond's opinionated ..." から変更)

### フェーズ1: v1.0 独立(節11の手順に、標準化の観点で以下を追加)

- [ ] **detach 前にリポジトリ名を再検討して一度で決める**——現状名
      "python-copier-template" は upstream と完全同名で、detach 後も検索・引用・
      会話で混同され続ける。detach 後の rename は星・被リンクの再蓄積を
      引き起こすため、名前は detach 前に確定させる(候補の軸: 多ジャンル対応/
      Z3 検証済み/という差別化点を表す語。決めるのは開発者自身の裁量)
- [ ] detach 後、README・CITATION.cff・codemeta.json・新設予定の NOTICE 相当に
      DiamondLightSource 由来である旨を明記する(正統性の担保と礼儀。既存の
      `docs/explanations/why-use-template.md` が python3-pip-skeleton 由来を
      明記しているのと同じパターンをここにも適用)
- [ ] detach 直後、Scorecard workflow を `workflow_dispatch` で1回走らせて
      初期スコアを確認する(private/非公開状態では機能しない旨が既存 TODO に
      記載済み——public 化後の確認として)

### フェーズ2: 発見可能性・比較優位の明文化

- [x] `docs/explanations/vision.md` を README からもリンクした
      (新設の "Why this template" 節から。pitch の一行要約つき)
- [x] README に他テンプレートとの比較を追加した
      (vision.md の表と重複させず、要約+リンクに留める方針どおり)
- [ ] awesome-python 系リストへの PR、r/Python・Hacker News(Show HN)・
      discuss.python.org への投稿を検討する(実行タイミングは detach 後。
      fork のまま告知すると "0 star のフォーク" という第一印象になり逆効果)
- [ ] cookiecutter-hypermodern-python(2024-05 以降更新停止、1900+ stars)
      からの乗り換え層を明示的なターゲットにする——比較記事 or 移行ガイドを書く
- [ ] Strategy.md の MECE ドリフト検知フレームワーク(発生源5分類×検知タイミング
      4分類 + Z3 充足検査)を技術記事として英語で書き起こし、docs か外部ブログに
      公開する。他の copier/cookiecutter 系テンプレートに同種の説明が見当たらない
      技術的差別化の核心なのに、現状 Strategy.md 止まりで対外発信されていない

### フェーズ3: 信頼・ガバナンス(長期)

- [x] `GOVERNANCE.md` を新設した(BDFL 型の明文化、将来メンテナの追加基準、
      レビュー基準、upstream との関係)
- [ ] bus-factor 対策として、second reviewer/co-maintainer 候補を探す
      (コード変更ではなく運用課題。detach 後の方が依頼しやすい——fork のままだと
      「誰の何に協力するのか」が伝わりにくい)

### スコープ規律(やらないことリスト——これも標準化戦略の一部)

- [ ] 新規 `project_type` の追加は当面凍結し、既存の組み合わせ(現状
      library/cli/web_api/data_science/online_judge×5/script/ros2/micropython
      + レイヤー)の安定化・ドキュメント・テスト強化を優先する。「対応範囲の広さ」
      は差別化点だが、伸ばし続けると kitchen-sink 化して新規参入者の意思決定
      コストが上がる——`web_django` を明確に non-goal として拒否する既存パターン
      (README 参照)を、他の際どい追加候補(GUI 質問票、他言語全般対応 等)にも
      同様に適用し、`docs/explanations/vision.md`「What this is deliberately not」
      に追記していく

## 17. 非インタラクティブ生成の改善（2026-09-05 フィードバック）

### 修正済み

- [x] `docs_type` の choices を Jinja テンプレートから静的リストに修正
      （`questions/_common_b.yml`。動的 choices がバリデーション時に評価されず、
      `zensical` が拒否される問題を修正）
- [x] 必須質問 (`package_name`, `description`, `git_platform`) にデフォルト値を追加
      （`questions/_common_c.yml`。`--defaults` フラグで非インタラクティブ生成が
      可能になる）
- [x] README.md に非インタラクティブモードのドキュメントと例を追加

### 残課題（2026-09-06 時点。解消分は下記に降格）

- [ ] 生成物の `dependencies = []` を project_type に応じて自動設定する改善
      （web_api / data_science は既に設定済み。library の空依存は
      「依存ゼロで始める」設計として維持するか、質問にするかは要検討）

### 2026-09-06 に解消（節15.5 で対応。詳細はそちら）

- [x] ~~`--data-file` で指定した値が `when` 条件の評価に反映されない~~
      → 根本原因は `--trust` 漏れ（copier は unsafe feature ありのテンプレートを
      trust 無しでは生成せず exit 4 で終了）。`--trust` + `--defaults` +
      `--data-file` の組合せで `when` gating も含めて正常動作することを
      web_api / pixi / micropython 等で実測。README を書き直し
- [x] ~~`uvx copier copy` で Jinja 拡張が見つからない~~
      → `uvx --with copier-template-extensions copier copy --trust ...` が
      正しい呼び方（`_example.yml` と同じ形）。README に記載
- [x] ~~非インタラクティブ生成時に全質問の `when` 条件を評価してスキップ~~
      → 上記と同根。全質問に default があることを機械検証するテストを追加
      （`gitlab_group` に `{{ git_user_name() }}` を追加して全質問 default 完備）
- [x] ~~Pixi 依存の正しいフォーマットのドキュメント追加~~
      → `docs/how-to/pixi.md` 新設（フラットテーブル、エラー例つき）
- [x] ~~PyTorch 等の conda-forge バージョン競合のガイドライン~~
      → 同 how-to に `[tool.pixi.pypi-dependencies]` + PyPI index 指定で解説
- [x] ~~`pixi.toml` から `pyproject.toml` [tool.pixi.*] への移行ガイド~~
      → 同 how-to に移行手順を記載

## 18. テンプレート構造の簡素化・重複排除（2026-09-08 監査）

肥大化した `template/pyproject.toml.jinja`・`_tasks.jinja` と flat/src 二重ツリー、
条件分岐の3流儀混在への対処。いずれも render byte-identical 検証つきで進める
（項目13 の copier.yml 分割時と同型）。

- [ ] **flat / src パッケージツリーの二重化を `{{ pkg_dir }}` 1本化する**
      - 現状: `<pkg>` 配下の全モジュール（fetcher / crawler / browser_fetch / spider /
        mcp_server / logging_setup / `__init__` / `__main__` / agent / tools）が
        src 版と flat 版でファイルごと重複し、100文字超の path ガードが鏡像で存在する
      - `questions/_internal.yml` の `pkg_dir` / `import_pkg` は既に配置を計算しているため、
        path 側を `template/{{ pkg_dir }}/fetcher.py` 式に寄せ、真正に置き場が違うもの
        （`app/` vs `<pkg>`、`firmware/`、`src/utils`）だけ wrapper 残しにする
- [ ] **OJ 判定の3流儀を1つに統一する**（`not online_judge` / `not (online_judge and not kaggle)` /
      `project_type not in [...]` が混在。kaggle に Docker は付くが PyPI は付かない等、
      意図か事故か判別できない）
      - `oj_bare`（= oj_code 相当）または `no_pkg`（micropython / oj_code 等）系 internal を
        新設し、docker / pypi / log_library / setuptools / setuptools_scm / testpaths /
        basedpyright-exclude の全参照を置き換える
- [ ] **raw / effective 混在を排除し、template 側は effective のみ参照にする**
      - 例: `include_mcp.when` の `project_type == 'web_api' or include_web_api` と
        `mcp_effective` の `cli or web_api(effective)` の二重定義、`.env.example` ファイル名の
        raw/effective 混在、`kaggle` vs `data_science` vs `has_*` の混在使用
      - 方針: 質問の `when` は raw、render（template 本体・ファイル名・`_tasks.jinja`・
        Dockerfile・task ブロック）は effective のみ。混在箇所を洗い出して置き換える
- [ ] **`layout` 除外リスト・`combinable` 三重ガードを一元化する**
      - `layout.when` / `use_src_layout` / `log_library.when` の除外リストを
        `needs_layout_choice` 系 internal に集約し、各 `when` から参照する
      - `include_web_api.when` + `combinable` + `has_web_api` + 各ファイルの `{% if web_api %}`
        の重なりは「`--data-file` 強制時の leak 防止に三重が必要」という現状理由を
        `questions/_combo.yml` に文書化するか、`combinable` を `has_*` に畳むか決める
- [ ] **`dev` 依存ブロックの triplication を base + append 化する**
      - `template/pyproject.toml.jinja` の `strictness == 'none'` / `'basic'` 分岐は
        約30行ほぼ逐語重複。`dev_base` + `{% if strictness in ['recommended','full'] %}`
        append に書き換える
- [ ] **`run` prefix と python-version 三重定義を `_shared/macros.jinja` に抽出する**
      - 現状: `run` / `run_x` / `ros_source` が `_tasks.jinja`・`README.md.jinja`・
        `Dockerfile.jinja` に分散、`requires-python` + classifiers +
        `[tool.basedpyright]pythonVersion` + ty-checkers `python-version` +
        `.python-version.jinja` が humble=3.10 / jazzy=3.12 / else=3.11 の三項を重複保持
      - `run_prefix()` / `python_version()` / `classifiers()` を macro 化し各所から import。
        `tools/check_upstream.py` の pin 対象に追加（template-dev.md の規約どおり bump 連動）
- [ ] **黙り上書き（sphinx→zensical、license→AGPL-3.0）を可視化する**
      - micropython + sphinx の zensical フォールバックと memorious 選択時の AGPL-3.0 強制は
        現状 silent。ask 順で validator が書ける側は validator 化、書けない側は
        `_tasks` / CI の警告または `test_example.py` の assert（render 結果と回答の一致）で可視化する
- [ ] **`git_platform` を先に聞くか `repo_url` / `docs_url` を platform 別にする**
      （現状: Project Details で後聞きのため `security_policy` / `scorecard` の `when` で
      絞れず `*_effective` の render 時ガードに迂回し、GitLab でも `repo_url` / `docs_url`
      が github.com 固定になる）
- [ ] **`pyproject.toml.jinja` をさらに分割する**（項目13 の確立パターンで）
      - `dependencies=` の1行20連ゲートと deptry `per_rule_ignores` 文字列組立を
        `_shared/pyproject-deps.toml.jinja` + `_shared/pyproject-deptry.toml.jinja` に抽出し、
        本体は構造のみ残す。dep 追加時の編集箇所を1箇所にする
- [ ] **`_tasks.jinja` を宣言的に安定化する**
      - `{% set tasks = tasks + [...] %}` の8ブロック変異を `when` 付き単一リストにし、
        poe / pixi シリアライザ（`&&` 単一コマンドの `shell` / `cmd` ヒューリスティック含む）を
        単一 macro に統一する。matrix path ごとの task-name 集合を assert する単体テストを追加
        （`audit` の `check` 外し等の退行を検出）
- [ ] **`logging_setup` の2行 wrapper 先頭空行を解消する**
      - template-dev.md の単行 wrapper 規約に反する2行 wrapper が先頭空行を生む既知の残件。
        単行化して byte-identical 検証する

## 19. テスト・CI の高速化と確実性（2026-09-08 監査）

> 2026-09-13 追記: `task test-fast`（venv/network を外す）/ `task test-heavy`（重い方のみ）を追加した（節22 §W9）。
> marker 化とレンダ結果キャッシュ、CI 側の fast/heavy 分割は未着手で下記は有効。単一ケースの調査は
> `task batch CLI_ARGS="--only X --prepare --shell"`（数秒）で pytest を経由しない。

- [ ] **uv / graphviz / uvx ツールのキャッシュを入れる**
      - `astral-sh/setup-uv` の cache 有効化 + `.venv` の `actions/cache`、
        docs run の `apt-get install graphviz` 常駐化、hygiene run の
        `uvx conventional-pre-commit / nbstripout / cffconvert` 冷起動のキャッシュ
- [ ] **CI を fast / heavy に分割する**
      - PR 毎は `test_machine_gate` / `test_copier_structure` / `test_qa` /
        生成 docs / gitleaks / lint の fast のみ、heavy（`test_example` / typecheck）は
        `main` / nightly または `paths:` フィルタに。`pytest -m "not slow"` markers +
        `make_venv` 系の `--dist loadfile` グルーピング、事前 sync 済み base venv 再利用を検討
- [ ] **`timeout-minutes` を全 workflow に付ける**（例: test 60 / docs 20 / hygiene 10）、
      matrix 復活時は `fail-fast`、タグ時の `_docs.yml: sleep 60` を `concurrency` で解消する
- [ ] **network 系テストの扱いを見直す**
      - `test_example_repo_updates`（example リポジトリの clone + `copier update` + diff）は
        ローカル `--vcs-ref=HEAD` diff に置き換えるか `scheduled-check` 専用に移す
      - `z3` の `importorskip` 黙り skip をやめ、必須化または skip 件数を assert する
      - `hypothesis` は現状 `tests/` でゼロ使用（deptry 除外で延命）。property test を
        `_tokenize_when` / questionnaire parser に書くか、依存から外すか決める
- [ ] **setup 重複を composite action 化し、runner 分岐を統一する**
      - `_tasks.yml` / `_test.yml` / `_docs.yml` / `_dist.yml` の
        checkout(fetch-depth:0) + setup-uv/pixi/poetry + setup-task/just 約30行を
        `setup-runner` composite action に抽出する
      - `_test` / `_docs` が `task/just/make/poe/pixi` のみ対応で `invoke/duty` が
        `Unknown task runner` になる分岐漏れを修正（template 側に loud-fail か対応追加）
      - `test_task_runner_just_works` 並みに `invoke` / `duty` の実走テストを追加する
        （poe `cmd &&` / make tab バグはまさに未実走から漏れた）
- [ ] **未検証の組合せ・経路を埋める**
      - テンプレ本体 CI は 3.11 / ubuntu-latest のみ。生成 matrix（3.11-3.14）/
        windows-macos / pixi・poetry venv 経路は render のみ
      - `torch` 系 render（data_science / kaggle）を typecheck 除外のままにしない
        （重いなりの nightly 化等）。`ros2-cpp`（pyproject 無し）の lint/typecheck/fmt 除外も整理
      - `tools/check_upstream.py` の network モード、`generate_license_template.py`、
        `_dist` / `_container` / `_pypi` / `_release` / `_example` workflow 群の未実行を
        いずれかの CI で叩く。`example-answers.yml` に `use_recommended_agent` 経路が無い点も補う
      - `audit` タスク（network のため `check` 外し）は木曜 root audit 以外の検証が無い。
        schedule 検証の有無を明記する

## 20. Docs・導入UX の改善（2026-09-08 監査）

> 2026-09-13 追記: 導入の実務（モード判定・衝突一覧・加算マージ・対話確認・ロールバック）は
> `tools/detect.py` / `tools/adopt.py` として実装し、`docs/how-to/{detect,adopt}.md` と
> `docs/tutorials/adopt-existing.md` を実測ベースに書き直した（節22）。README の TL;DR、
> Features/mermaid の drift 解消、wrapper CLI（§W6）、孤児ページは下記のまま未着手。

- [ ] **コピペで通る導入導線にする**（2026-09-09 更新: `--with` は不要になった。
      copier-template-extensions 依存を排除したため残りは `--trust` / `--vcs-ref` の2 flag）
      - ~~tutorials/installation.md に `--with` を足す~~ → 不要（依存排除で解消）
      - `tutorials/adopt-existing.md:28` の skeleton 経路と :43 非 skeleton 経路の不整合を解消する
      - `--vcs-ref=main` の理由説明3箇所の矛盾を解消する（README は「v1.0 で re-tag 済み」、
        adopt-existing は「v1.0 未到達で必須」）。単一の version-status 注記に集約し TODO-11 漏れを消す
      - 2 flag（`--trust` / `--vcs-ref`）を隠す wrapper script / alias を検討する
- [ ] **欠落・孤児ページを解消する**
      - 生成 README が link する `{{docs_url}}/how-to/run-container` に対応する
        `docs/how-to/run-container.md` を書く（または生成 link を既存 how-to に付け替える。
        現状 Docker 生成物は全て404 link を ship している）
      - `docs/explanations/structure.md` の孤児を `explanations.md` index に登録する
- [ ] **README Features / mermaid と questionnaire の drift を解消する**
      - `docs/reference/questionnaire.md` 側にはある CTF / scraping /
        `use_recommended_scraping` / `scraping_engine` / `license_check` /
        `oj_category=ctf` / 新 security 意味が、README Features + mermaid に無い。
        questionnaire を正として README を再生成する
      - ついでに toolchain default 矛盾を解消する（help は推奨 `uv + just`、
        README は `Task (default)`）。mermaid は quickstart の後に移すか折りたたむ
- [ ] **生成ドキュメントを堅くする**
      - 生成 `CONTRIBUTING.md.jinja`（30行・外部 how-to URL 依存・`_commit.split` pin 脆弱）を
        `AGENTS.md` と同じコマンドブロック内蔵型にし、offline でも作業可能にする。
        `copier update` での AGENTS.md / CONTRIBUTING.md 乖離を防ぐ
      - 生成 README の `<details> Platform-specific setup` の Linux/macOS vs Windows
        同一コマンド並列（noise）を差分化または削除、`**pkg** is a Python package that ...`
        プレースホルダの ship しやすさに対処（validator / コメント誘導）、docs 無効時の
        `See ... (.github/CONTRIBUTING.md)` 弱代替を手当てする
- [ ] **質問票の小粒改善**
      - `project_type=web_django` の罠選択肢（選ぶと abort）を choices から外し、文書ポインタにする
      - `license` help の40行 SPDX ダンプを端末向けに短縮（全文は docs 参照）
      - `example-answers.yml`（全 gate-off 網羅 fixture）を `create-new.md` +
        `reference/questionnaire.md` から non-interactive 起点として link する
      - `create-new.md` の commit 手順 `uv sync` 固定を runner 対応に
        （`uv sync` / `pixi install` / `poetry install` / ros2 / micropython 分岐）
      - README 先頭に5行 TL;DR quickstart + prerequisites（uv / git init）を置く

### 修正詳細

#### Issue: docs_type バリデーション問題
**症状**: `--data-file` で `docs_type: zensical` を指定すると
`ValueError: Invalid choice for 'docs_type': 'zensical' is not in ['README', 'sphinx']`
エラーになる。

**原因**: `choices` に Jinja テンプレート (`{%- if micropython_pkg %}...`) を使用すると、
バリデーション時に Jinja が評価されず、一部の choices しか認識されない。

**修正**: `choices` を静的リスト `[README, zensical, sphinx, great-docs]` に変更。
micropython プロジェクトでは sphinx が不要な制限は、テンプレート側で対応
（`template/{% if docs %}docs{% endif %}.jinja` で条件制御）。

#### Issue: 必須質問のデフォルト値不足

**症状**: `--defaults` フラグを使用しても `package_name`, `description`,
`git_platform` が "required" エラーになる。

**原因**: これらの質問に `default` が設定されていないため。

**修正**: 各質問にデフォルト値を追加:
- `package_name`: `my_package`
- `description`: `A Python project generated from python-copier-template`
- `git_platform`: `github.com`

## 21. copier 本体への機能提案・fork 運用（2026-09-08 新設）

`notes/COPIER_UPSTREAM.md` + `notes/upstream-drafts/`（報告済み9件・パッチ2本凍結）は
そのまま残し、*新規*の機能提案と fork 作業場は `copier-fork/` に集約する。
二重管理にしない: 既報9件の再記述は `copier-fork/` に持ち込まない。

- [x] **`copier-fork/` 作業場を新設する**（2026-09-08）
      - `copier-fork/README.md`（hub: 新旧二拠点の整理・非目標・workflow）
      - `copier-fork/FEATURES.md`（新規機能 F1〜F7 + Research。重複する既報9件は拡張参照のみ）
      - `copier-fork/patches/README.md`（命名 `<area>-<slug>.patch`・作成/検証手順）
      - `copier-fork/scripts/{fork-setup,sync-upstream,verify-patch}.sh`
       （fork 作成・upstream 同期・`git apply --check` 検証。`bash -n` 済み）
      - 非目標の明記: upstream コードの vendoring なし（patch は quoted context のみ）、
        生成物への混入なし（`template/` 外のため `copier.yml` 除外不要）
- [ ] **fork を作成し、F3（missing 一括報告）から着手する**
      - `copier-fork/scripts/fork-setup.sh` で fork（先方慣例ブランチは `master`）。
        ベースラインは copier 9.18.1（本リポジトリ `.venv` 版）。以降は
        `sync-upstream.sh` で追従し、FEATURES.md の行番号参照を更新する
      - 着手順序（小→大）: F3 → F5 → F6 → F1/F2/F4/F7（Discussion 先行）。
        文言系（F3/F5）は既報1/2/4 の PR と同型の単発 PR として出しやすい
      - PR 前に upstream `CONTRIBUTING.md` 通りに該当テストを回す
        （F3 なら answers 系、F5 なら VCS 系）。`verify-patch.sh` で事前検査
- [ ] **投稿は手動で行う**（copier の `AI_POLICY.md` 要件。エージェント投稿禁止）
      - 草稿は貼らず自分の言葉に整える。`gh` コマンド例は `notes/COPIER_UPSTREAM.md`
        「投稿手順」節を正とする（`copier-fork/` に複写しない）

## 22. 劇的改善：実装済みの道具と残タスク（2026-09-11 監査 → 2026-09-13 更新）

委託用の詳細仕様（Target / Change / Acceptance / 所有権 / wave / 共有コントラクト §C1〜C9）は
**`notes/PLAN-improvements.md`** を正とする。この節は「何が動いていて、何が残っているか」を持つ。

動機（実測・再掲）: 最新タグ `5.4.0` は inherited upstream の内容で fork の機能を 1 つも含まず
（`git show 5.4.0:copier.yml` に fork 機能 0 回、HEAD は 69 commits 先）、既定の `copier copy` は
`Invalid choice for 'docs_type': 'zensical'` と `Question "author_name" is required` で失敗する。
全テストが `vcs_ref="HEAD"` 固定のためこの欠陥を検出できない。加えて実行検証は 10 構成のみ
（質問空間 ≳378）、`.github/workflows` に `timeout-minutes` が 0 件。

### 22.1 実装済み: テンプレートを扱う道具（`tools/`）

| 道具 | 何をするか | 入口 | テスト |
|---|---|---|---|
| `tools/detect.py` | 対象のモード判定（`fresh` / `adopt` / `update` / `foreign`）、既存資産の棚卸し、`COLLISIONS`（= `skip`）、実行可能な adopt コマンドの印字。保護条件は `template/` のパス名条件から**実行時導出**（HEAD と作業ツリーの差でも正しい）。形状質問は推測しない（SPEC §12） | `task detect DIR=... CLI_ARGS="--json"` | 22 |
| `tools/adopt.py` | **トランザクション付き adopt**: 計画 → 対話確認 → 適用 → 検証 → 破れれば全体ロールバック。`--ref` は「最新タグが同じ質問集合を持つときだけタグ、でなければ既定ブランチ」を動的判定 | `task adopt DIR=... CLI_ARGS="--dry-run"` | 22 |
| `tools/pyproject_merge.py` | `pyproject.toml` への加算マージ（deps / `[dependency-groups]` / `[tool.*]`）。既存値は不変、tomlkit でレイアウト保持、ビルド・環境テーブルは対象外 | adopt から | 15 |
| `tools/file_merge.py` | `.gitignore` / `Makefile` / `justfile` の追記、`Taskfile.yml`（`tasks:` が最後のキーのときだけ承認つき追記）、既存 `ci.yml` がある場合の `copier-ci.yml` 併置 | adopt から | 12 |
| `tools/batch.py` | JSONL の生成リクエストを順に実行して**判定**（`expect` / `commands`）。`--prepare` で環境構築、`--shell` で調査ループ | `task batch FILE=... CLI_ARGS=...` | 15 |
| `tools/questionnaire.py` | 質問票をデータとして読む（`!include` 解決済みの実質問順、`choices_template` 対応、`_` 設定は分離） | CLI / MCP | 9 |
| `tools/mcp_server.py` | 上記を MCP tool として公開（`template_status` / `list_questions` / `inspect_project` / `adopt_project` / `render_project` / `list_batch_requests` / `run_batch`）。stdio の stdout を汚さない（render は fd 1→2） | `task mcp` | 12 |

テスト 3 段速も導入済み: `task test-fast`（venv/network を外す）/ `task test`（フル）/
`task batch CLI_ARGS="--only X --prepare --shell"`（1 ケース）。詳細は `docs/how-to/test-loop.md`。
関連 docs: `docs/how-to/{detect,adopt,batch,test-loop}.md`、`docs/tutorials/adopt-existing.md`。

### 22.2 残タスク

- [ ] **W0: fork detach と既定経路の是正**（最優先・不可逆 → タグ番号を実測してからユーザー承認）
      - 継承タグを削除し HEAD に新タグを 1 つだけ打つ。`--vcs-ref` 前提の記述（README / adopt-existing /
        `tests/test_generation_docs.py`）を撤去し、「引数なし `copier copy` が fork の質問票を出す」テストに置換
      - 次タグは PEP440 で `5.4.0` より大きくする（`1.0.0` は `UserMessageError` で update 不能。下記 22.3）
- [ ] **W1: `copier update` 適合マトリクス + 質問票 diff ガード**
      - fixture answers × リリース済み ref で「旧 ref 生成 → HEAD へ update → conflict なし・生成物 check 緑」
      - 「質問の改名/削除/既定変更には `_migrations` 追記必須」を最終リリースタグとの diff で強制
- [ ] **W2: タスク定義の宣言的モデル化**（`_tasks.jinja` の 8 ブロック mutation 廃止、byte-identical 検証つき）
- [ ] **W3: Z3 の証人で質問票の全葉を実行検証**（エンジンは `tools/batch.py`、fast/heavy の 2 tier）
- [ ] **W4: サポートマトリクスの宣言と長尾の整理**（`support.yml`、W3 の後）
- [ ] **W5: ドキュメントを質問票から生成**（`tools/gen_docs.py --check` を CI に。README Features / mermaid の drift 解消を含む）
- [ ] **W6: 導入のワンコマンド化**（wrapper CLI + presets。`detect` / `adopt` を呼び、`web_django` を choices から削除）
- [ ] **W7: CI 衛生**（全 workflow に `timeout-minutes`、setup-uv / .venv / apt / uvx のキャッシュ、
      `_docs.yml` の `sleep 60` を `concurrency` 化）
- [ ] **W9: テスト実行コストの削減**（marker 化 + レンダ結果キャッシュ。実測値は PLAN §W9）
- [x] **W-P の残り**: `_load_questions` の `tools/questionnaire` 委譲 → **実質完了と判断（2026-09-09）**。
      現行の `_load_questions` は copier ネイティブの `load_template_config`（!include 解決の
      権威あるローダ）を使う 12 行の薄い実装で、委譲先の `Question` モデルは
      validator 等の未知キーを落とすため Z3 ガードの入力を劣化させる。`tools/questionnaire.py`
      --json は **109 問**（108 + existing_project）を正しく数え、JSON/MCP 層として役割分担。
      読み取り側は実装済み
- [ ] **W10（新）**: `tasks.py` / `duties.py` への追記。現状は報告のみ。Python なので「関数を追記 + 必要な import が
      無ければ報告」の形にし、`Taskfile.yml` と同じ承認ループに載せる
- [ ] **W11（新）**: 既存 `ci.yml` への**ジョブ単位マージ**。現状は `copier-ci.yml` 併置で回避している。
      ジョブ名が空いているときだけ承認つきで追記する（YAML 追記の安全性判定は `Taskfile.yml` の実装を流用）

### 22.3 既知の罠（W0 が踏む・copier 9.18.1 で実測再現済み）

次タグは PEP440 で `5.4.0` より大きくする必要がある（例 `6.0.0`）。`1.0.0` を打つと、現 HEAD で生成済みの
プロジェクト（answers の `_commit: 5.4.0-69-ge2a210e1` → version `5.4.0.post69.dev0+e2a210e1`）に対し
`_main.py:1368-1371` が `UserMessageError` を **raise** し、`copier update` が一切通らなくなる:

```
You are downgrading from 5.4.0.post69.dev0+e2a210e1 to 1.0.0. Downgrades are not supported.
```

さらに、同一 commit に複数のバージョンタグを残すと dunamai が低い方を選び偽のダウングレードになるため、
**継承タグは削除し、HEAD のバージョンタグは 1 つだけ**にする。
`_template.py:421` の migration 選択は `new >= migration.version > old` なので、既存の `2.0.0` エントリは
既存ユーザーには発火しない（正常）。受け入れ条件は「HEAD 生成物を新タグへ `copier update` して `_commit` が
前進すること」を実測すること。再現手順と詳細は `notes/PLAN-improvements.md` の W0 を参照。

dirty なテンプレートでは `copier update` が成立しない点も実測済み（copier が clone 内に合成コミットを作り、
その describe がレンダ毎に変わるため「ダウングレード」と判定される）。`tools/batch.py` はこれを
`update-precondition`（clean tree 必須）として実装し、`tests/test_example.py` の adopt-update テストも
clean clone から render する形に修正済み。
