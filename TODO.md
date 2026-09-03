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
- `web_api` は scaffold として未完成: FastAPI/uvicorn の依存・app コードが無く、
  Dockerfile の ENTRYPOINT が `{{ repo_name }}`（CLI）のまま。compose は Postgres を
  立てるが、起動する HTTP サーバが存在しない。DB はあるのに ORM/マイグレが無い。
- 生成物が「動く」ことを検証するテストが無い（ディレクトリ存在 + 依存の有無のみ）。

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

- [ ] copier.yml の project_type に `online_judge` を追加する
      - help: 競技用プロジェクト。種類（kaggle / atcoder / leetcode）により
        AI コーディングエージェント利用の可否が異なり、AGENTS.md の有無が変わる
- [ ] `oj_kind` 質問を新設する（online_judge 選択時のみ）
      - 初期: kaggle（AI 可）/ atcoder / leetcode
      - atcoder / leetcode では AI 可否をさらに質問する（下記）
- [ ] `oj_allow_ai` 質問を新設する（atcoder / leetcode 選択時のみ）
      - AI 利用 OK → AGENTS.md を生成（+ README に AI 向け言及）
      - AI 利用 NG → AGENTS.md を生成しない（規約遵守）
- [ ] online_judge の生成物（最小構成・追加依存なし・stdlib のみ）
      - `solutions/` ディレクトリ（問題別 .py 雛形: solve() 関数 + 標準入力の
        読み込み + `if __name__ == "__main__"`）
      - `solutions/test_samples.py`（pytest でサンプルケース検証の雛形）
      - README に提出フロー（oj_kind ごとに文言が変わる）
- [ ] online_judge では `use_recommended_agent`（pydantic-ai scaffold）を出さない
      （一元管理: AI NG なら AGENTS.md も pydantic-ai も出さない）
- [ ] online_judge のテスト: 生成物の存在 + solutions の pytest 実行 +
      AGENTS.md の有無（AI 可否で反転）を検証
- [ ] **将来拡張**: oj_kind を世界基準の主要 OJ 9種 + 「その他」（選ぶと更に
      選択肢が出る2段階方式）へ拡張する。今回は kaggle / atcoder / leetcode の
      3種で骨格を作る

## 3. kaggle の data_science 分離 → online_judge の内部タイプへ統合

- [ ] copier.yml から data_science 配下の `competition` 質問を削除する
      （kaggle = oj_kind=='kaggle' として online_judge 側に移す）
- [ ] 内部変数を張り替える: competition 条件を kaggle 条件に変更
      - data_science_layout / pkg_dir（'src/utils'）/ use_gpu_effective / duo / care /
        _tasks.jinja の competition 分岐 等
- [ ] kaggle 用の生成物を移設する（既存 competition のものをほぼそのまま）
      - src/{configs,data,input,output,features,logs,models,notebook,scripts,utils}/
      - utils パッケージ（config/dataset/features/modeling/plots）
      - Dockerfile.gpu + devcontainer.gpu.json + uv の pytorch-cu124 インデックス
      - marimo notebook（src/notebook/explore.py）
- [ ] data_science を純粋な分析型に純化する
      - competition / GPU 質問を外す（notebooks / data / models / reports / paper）
      - **DUO / CARE 質問は data_science に残す**（competition の when 条件を外す）
      - polars/duckdb/pyarrow 等の data_science 初期依存は維持する
- [ ] kaggle には AGENTS.md を生成する（AI 利用 OK のため。kaggle 固有の指示:
      GPU の使い方・submission の作り方・データ境界を含める）
- [ ] 既存テストを移設する: test_template_kaggle_competition → kaggle タイプ用に
      書き換え、test_template_data_science_layout は competition 無しの純化後仕様に
      更新。example-answers.yml / questionnaire.md / README の competition 言及を更新
      （未公開なので移行案内は不要。単に competition を撤去して kaggle に置き換える）

## 4. 「常駐する実行可能物」の実行形態を新設する（bot / MCP server の受け皿）

- [ ] project_type に `daemon` / `service`（常駐実行物: bot、MCP server、長命 worker）を
      追加するか、既存 project_type の上に載るレイヤーとして独立起動モジュールを持つ
      設計にするか決定する
      - 判断基準は設計原則1（実行環境が根本から違うか）。bot/MCP は「イベントループ +
        トークン/env で起動する長命プロセス」で、HTTP サーバとも即終了 CLI とも違う
      - マイクロPython / VFX と違い「ビルド」は通常なので、project_type より
        軽い枠の可能性が高い。まず最小プロトタイプで決める
- [ ] `__main__.py` を「常駐起動（トークン必須、環境変数チェック）」に置き換える分岐を
      設計する（CLI と衝突させない）
- [ ] botter 向け（discord / slack）: 新設した常駐レイヤーの platform として
      discord / slack を実装する
      - discord.py / nextcord / py-cord と slack-sdk / bolt のどれを推奨1本にするか
      - .env.example のトークン管理、structlog 連携、Docker での常駐/再起動方針
- [ ] 既存の `include_mcp` をこの常駐レイヤーへ統合する（下記5と一体で整理）

## 5. MCP の整理（include_mcp と mcp_server の分裂解消）

- [x] `include_mcp`（mcp_server.py 生成 + mcp SDK 依存）と旧 specialty の mcp_server
      （inspector のみ）の2系統を1つに統合する
      - 旧 specialty='mcp_server' を撤去し、inspector 実行方法を include_mcp 生成の
        mcp_server.py docstring / README に移植した。これにより
        「片方だけ選ぶと exclude されない生成コードができる」不整合も構造的に消えた
- [ ] mcp_server の実装例を「型付きツールの登録」まで拡充する（ツール定義・引数スキーマ・
      エラー処理）。テストは in-process client でツール呼び出しを検証する
- [ ] streamable HTTP（リモートMCP）と docker での運用まで含めるかは、
      常駐レイヤーの設計（4）に合わせて決める

## 6. web_api を「動く FastAPI scaffold」へ拡充する（s3rius/FastAPI-template 参考）

- [ ] まず現状の欠落を解消する（どのオプションを選んでも効く土台）
      - FastAPI + uvicorn の依存追加と、動く `app` オブジェクト（app factory + router）
      - Dockerfile ENTRYPOINT / compose command を CLI（--version）から uvicorn での
        サーバ起動に変える（HEALTHCHECK も追加）
      - pydantic-settings で .env.example の DATABASE_URL / HOST / PORT を読む
      - docs の「Add fastapi + uvicorn yourself」を廃止し、生成物に含める
- [ ] `use_recommended_web_api` ゲートを新設する（既存の use_recommended_* 方式に乗せる。
      設計原則5）
      - 推奨: FastAPI + SQLAlchemy 2.0 + alembic + Postgres + demo router/model +
        pytest/httpx テスト。これで「動く scaffold」として完成させる
      - No を選ぶと下記の詳細質問が出る
- [ ] 詳細質問の候補（s3rius の機能一覧から、このテンプレートで採用するものを絞る）
      - **認証**: none（推奨）/ JWT（fastapi-users）。web_api の主要な欠落なので真剣に検討。
        include_sentry と同様の独立オプションにするか直交ゲートにするか決める
      - **Redis**: 入れない（推奨）/ 入れる（キャッシュ・セッション。compose に service 追加）
      - **バックグラウンドタスク**: FastAPI 標準 BackgroundTasks（常に有効）の上で、
        分散タスク（taskiq / arq）を入れるか。まず taskiq を推奨候補として試作
      - **オブザーバビリティ**: prometheus エンドポイント / OpenTelemetry。
        上記9の SRE（web_api 運用強化）と統合して検討する
      - **demo 生成**: demo router + CRUD model の見本を生成する（推奨）/ しない
      - **DB**: Postgres 固定のまま（compose が既に Postgres 前提）。sqlite は
        テスト高速化用として追加する価値があるか判断して1-2個に絞る
      - **ORM**: SQLAlchemy 2.0 の1本固定（s3rius の 5種選択は取らない）
- [ ] 各オプションは「空ディレクトリ + 依存」で終わらせない（specialty 解体の教訓）:
      採用する項目は必ず app 配線・テスト・compose/CI 連動まで含めて「動く」状態で生成し、
      import / 起動 / エンドポイント応答をテストで検証する。動く見本を添えられない
      オプションは採用しない
- [ ] 取り込まない機能を明記する: GraphQL / REST 選択、Kafka / RabbitMQ、ORM 複数選択、
      gunicorn（uvicorn で足りる）、self-hosted swagger（FastAPI 内蔵で足りる）、
      traefik ラベル。docs に「後で足せる」と明記して初期質問にしない

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
