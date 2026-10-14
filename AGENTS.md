# Agent Guide for `architekton-py`

This file is for AI coding agents working in this repository. It states how
to run the checks and where edits belong. The human-facing contribution
guide is [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md); this repo is the
copier template itself, so its shape follows the `AGENTS.md` it generates.

## Commands

The `task` runner ([Taskfile.yml](Taskfile.yml)) drives the common commands:

```sh
task fix         # auto-fix formatting and lint
task lint        # ruff format --check + ruff check
task type-check  # basedpyright + pyrefly, vulture, deptry, typos
task test-fast   # the edit loop: no venv builds, no network (30 s budget)
task check       # lint + type-check + test
task regen       # after a questionnaire change: witnesses, batch, tiers, docs
task docs        # build the documentation site
```

Run `task fix` before committing, then the cheapest tier that covers the
change (the blast-radius table in
[.github/CONTRIBUTING.md](.github/CONTRIBUTING.md)): docs-only changes need
`task lint type-check`; template payload (`template/`, `_shared/`,
`questions/`) needs `task test-fast` plus `task verify-delta`; a
questionnaire change (`copier.yml`, `questions/*.yml`) needs `task regen`
then `task test-fast`.

## Where to edit

- Questionnaire: `copier.yml` and its fragments in `questions/`
- Generated project payload: `template/` (file and directory names carry
  copier's `{% if %}` conditionals) and the shared partials in `_shared/`;
  the generated task-runner model is `_tasks.jinja`
- Template tooling (witnesses, batch runner, docs generator, MCP server,
  CLI): `architekton/`
- Tests: `tests/` (cost tiers are pytest markers; `tests/matrix/` holds the
  witness leaves, invariants and the tier ledger)
- Docs: `README.md` and `docs/`. Blocks marked as generated come from
  `architekton/gen_docs.py --write`; edit their sources, not the output.

`notes/` is internal working material, not documentation: do not cite it
from `docs/` or code.

## Commits and CI

- Use [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, ...).
- CI runs lint, type-check, the test tiers, the witness render matrix and
  a docs build; keep all of them green.

## Field rules (ethics appendix)

Field rules for this project kind live in the marker block below.

The block is maintained by `daimonion agents-md --write` from the law-map guidance sections; edit `.daimonion.yml`, not the block.
Fill or refresh it with
`uvx --from git+https://github.com/politeuma/daimonion@b670aedf38ca33747b2693c1fad771b61a266e74 daimonion agents-md --write`.

To mechanically verify changed files against these triggers before committing,
run `uvx --from git+https://github.com/politeuma/daimonion@b670aedf38ca33747b2693c1fad771b61a266e74 daimonion scan`
(or `... daimonion scan <path>`).

### Rule summaries (English)

English summaries of the guidance sections this project's `.daimonion.yml`
selects. The full sections in the marker block below (facts, prohibited
patterns, regex triggers) are written in Japanese; these summaries translate
their rule lines. Not legal advice.

- **AI and copyright: fetching, training and RAG code must not break the non-enjoyment exception** (`baseline-copyright-ai`): (1) do not circumvent robots.txt or other crawl-refusal measures; (2) do not design RAG that retrieves and re-emits the expression itself; extract facts and concepts only; (3) do not overfit or fine-tune on a specific body of works in order to imitate it.
- **License drift: track dependencies' current licenses and keep BSL/SSPL out** (`baseline-license-drift`): (1) check the current license when adding a dependency and match it against the allowlist; (2) never pull in source-available licenses (BSL, SSPL, ...) unchecked; (3) route fork migrations (Terraform to OpenTofu, ...) through the legitimate successor.
- **PKI chain changes: never hard-code intermediate certificates or issuance chains** (`baseline-pki-chain`): (1) do not bundle or pin intermediate certificates or issuance chains; (2) verify against the OS/system trust store and keep a way to update it; (3) when pinning, pin a public-key set plus backup keys, never a single key.
- **PQC standards: new cryptographic choices use ML-KEM/ML-DSA, in hybrid mode** (`baseline-pqc-fips`): (1) use the standard names (ML-KEM / ML-DSA / SLH-DSA), not submission names such as Kyber, in new code; (2) key exchange is ML-KEM; signatures default to ML-DSA with SLH-DSA as the conservative alternative; do not mix the roles; (3) migrate in hybrid mode (X25519MLKEM768, ...) and adopt no classical-only scheme anew.
- **LLM apps and MCP: least privilege, human approval and output validation by default** (`domain-llm-appsec`): (1) restrict tool permissions to a minimal allowlisted CRUD set; (2) always insert a human approval step before destructive or irreversible operations; (3) validate LLM output structurally before acting on it; never pass it straight to a shell.

<!-- daimonion:ethics:begin kanon=2321063eb6c0 when=always,cli,mcp -->
<!-- Generated by `daimonion agents-md --write` from kanon; edit .daimonion.yml, not this block. -->

## Ethics & legal field rules

Sections from [kanon](https://github.com/politeuma/kanon)
that match this project's `.daimonion.yml` conditions. Each gives a rule summary and regex
triggers up front; facts, prohibited patterns, and the change watch are folded in `<details>`.
Before committing, run `daimonion scan` to match changed lines against these triggers.
Sections are written in Japanese. Not legal advice.

# AIと著作権 — 取得・学習・RAGコードは「非享受目的」を壊さない

> **適用条件**: ウェブ取得(スクレイピング)、データセット構築、
> fine-tuning、RAG/検索、生成物の再配布を実装する場面。
> 日本法(著作権法30条の4)を軸に、法域差の注意も併記する。
> 規模: 国内問題(30条の4は日本法で、権利者の利益も国内法がまず守る)。
> 配布: cli / data-science(取得・学習・RAGコードを書くもの)。
> 要約: (1)robots.txt等の取得拒否措置を回避しない (2)表現そのものを
> 検索・再出力するRAG設計をしない(事実・概念の要約抽出にとどめる)
> (3)模倣を目的とする過学習・特定作品群の追加学習をしない。
> 詳細は本文。
> Triggers: `(?i)\b(scrap|crawl|robots\.txt|rag|retrieval|fine-?tun|dataset|embedding|public[- ]domain|copyright)\b`.


<details>
<summary>詳細解説を展開（事実・判例・禁止パターン・制度変更ウォッチ）</summary>

## 事実

文化庁は2024-03、著作権審議会の議論を経て「AIと著作権に関する
考え方について」を公表した。情報解析を目的とする著作物の利用は
著作権法30条の4で原則適法だが、「著作権者の利益を不当に害する場合」は
権利制限の対象外とされる。同考え方は、(1)特定の表現を忠実に再現させる
目的の過学習や特定作品群のみの追加学習は「表現の享受」目的と評価され
30条の4が適用されない、(2)RAGでデータベース内の創作的表現そのものを
検索・取得して出力に含める設計は享受目的の併存が問題になり得る、
(3)robots.txt等の取得拒否措置の意図的な回避は、将来的な有償の
データ解析市場を不当に害し得る、と整理した。生成物の侵害判断は
従来法理と同じく「類似性」と「依拠性」で行われ、学習データ内に
元作品があり生成結果に創作的特徴が感得できれば依拠性が推認され得る。
また保護期間は法域差(死後70年原則、戦時加算、映画・企業名義の扱い)が
あり、パブリックドメイン判定は対象法域ごとの照合が要る。
出典: 文化庁「AIと著作権に関する考え方について」(REGISTRY.ymlに記録)。

## 禁止パターン

- 取得拒否措置の回避(`ROBOTSTXT_OBEY=False`、UA偽装、
  レート制限回避のためのIPローテーション等)。
- 特定作家・特定リポジトリの文体/実装を再現させるfine-tuning・
  ワンショット模倣プロンプト。
- RAGで原文の表現(コードの連続行、文章段落)をそのまま検索・出力する設計
  (要約・埋め込み化でなく生チャンクを返す構成)。
- 出典を記録せずに取得データを学習/RAG基盤へ流す。
- 「パブリックドメイン」の無検証前提(法域・保護期間の照合なし利用)。

## 推奨設定

- 保持は事実・概念レベルに(要約、埋め込み、統計)。生表現の保持は
  ライセンス/利用規約の確認を通したものに限定し、出典を版管理する。
- 出力側に重複検出を入れる(既知ソースとの長い共通n-gramで
  差し戻すフィルタ)。
- 取り込み工程に利用規約・ライセンス確認ステップを置き、
  拒否措置(robots.txt/ToS)の有無をデータセットのメタデータに記録する。
- パブリックドメイン判定は法域+著作者の没年/公表年を入力にする
  チェッカーを通し、判定根拠を残す。法域別の保護期間データ
  (死後年数・団体名義・戦時加算など)はテンプレート側の単一源
  `_shared/ethics/lang/copyright-terms.yml` に構造化してある。生成物には
  本要約のみ同梱され、チェッカー実装時は対象法域の現行法で再確認する。

具体例(取得とRAGの既定形。悪い形と良い形の対):

```python
# 取得は拒否措置を尊重する(標準庫の robots.txt パーサ)
rp = robotparser.RobotFileParser()
rp.set_url(base_url + "/robots.txt")
rp.read()
if not rp.can_fetch(USER_AGENT, url):
    skip(url)  # 迂回(UA 偽装・IP ローテーション)を書かない

# RAG は生チャンクを返さない: 既知ソースとの長い共通 n-gram を差し戻す
if longest_common_ngram(answer, source, n=12):
    reject("output is too close to the source")
```

## 運用チェック

- 設定側トリガー(Copier QA L1用):
  `(?i)\b(robots|scrapy|BeautifulSoup|httpx|rag|chromadb|faiss|langchain)\b`
  hit時は本節の存在をassert。
- 取得コードのレビュー項目に「拒否措置の尊重/レート/UAの正直さ」を置く。
  担当: データ取得を実装するレビュー役。

## 制度変更ウォッチ

- 変更予告: 文化庁はAIと著作権の論点の継続的な整理を続けており、
  追加の考え方・論点整理が出る可能性。確度: 審議中。
- 確認TODO: 文化庁ページで最新の考え方・Q&Aを一次で確認
  (review_by: 2027-03-31)。
- 影響TODO: 自プロジェクトの学習/RAGデータの取得元一覧に対し、
  拒否措置の現状を再確認する。

<!-- 法的助言ではない。専門家レビュー必須。 / This is not legal advice; expert review required. -->

</details>

# ライセンス変動 — 依存の現行ライセンスを追跡し、BSL/SSPL混入を防ぐ

> **適用条件**: 依存パッケージ・ツールチェーン・コンテナイメージを
> 追加・更新する場面すべて。フォーク元が非OSS化した事例の引用も含む。
> 規模: 世界問題(ライセンス変更はどの法域でも起き、汚染は世界の
> リポジトリに広がる)。
> 配布: library / cli / script / web / data-science(依存を1つでも
> 持つ全プロジェクト種別)。
> 要約: (1)追加時に現行ライセンスを確認し、allowlistと照合する
> (2)BSL/SSPL等のソース可用ライセンスを確認なしで混入させない
> (3)フォーク移行(Terraform→OpenTofu等)は正当な後継を通す。
> 詳細は本文。
> Triggers: `(?i)\b(licen[cs]e|bsl|busl|sspl|rsal|elv2|copyleft|gpl|agpl|lgpl|terraform|opentofu|elasticsearch|redis|source-available)\b`.


<details>
<summary>詳細解説を展開（事実・判例・禁止パターン・制度変更ウォッチ）</summary>

## 事実

HashiCorpは2023-08-10、TerraformをMPL 2.0からBusiness Source License
(BUSL 1.1)へ変更した。コミュニティはフォークOpenTofuを設立し、
Linux Foundation傘下で継続している。2024-04にHashiCorpはOpenTofuに対し
BSL適用後コードの不正利用を主張する書簡を送付し、OpenTofuは公開で反論した
(MPL 2.0版のコードに基づくとする立場。係争は公開記録の範囲で確認できる)。
方向が逆の例もある: Elasticは2024-08にElasticsearchへAGPLv3を
追加選択肢として復帰させ、Redisも2025-05にAGPLv3を追加した。
つまり依存のライセンスは「追加時点の記憶」では正しくなく、
リポジトリ単位で変動する。BUSL自体は発行からChange Date(原則4年)経過で
指定ライセンスへ切り替わるため、版ごとに扱いが変わる点にも注意する。
出典: HashiCorp公式ブログ、OpenTofu FAQ(REGISTRY.ymlに記録)。

## 禁止パターン

- ライセンス確認なしの依存追加(BSL/SSPL/RSAL/ELv2等のソース可用、
  強copyleftの確認漏れ)。
- フォーク元・フォーク先の取り違え(Terraform本家をMPL 2.0と誤記載、
  OpenTofuをBUSLと誤記載)。
- 「昔追加したからOSSのはず」という版の据え置き(renovateやlock更新で
  ライセンス欄を再確認しない運用)。
- ライセンス表示の捏造(README/NOTICEに実態と異なる表記)。

## 推奨設定

- allowlist方針を明文化(Apache-2.0/MIT/BSD/MPL-2.0等を許可、
  GPL系は配布形態照合、BSL/SSPLは例外承認制)。明文化の雛形:
  ```text
  許可: Apache-2.0 / MIT / BSD-2・3-Clause / ISC / MPL-2.0 / Python-2.0 / Unlicense
  要照合: LGPL(リンク形態) / EPL-2.0(例外条項の範囲)
  原則拒否・例外承認制: GPL系(配布形態照合) / AGPL / BSL / SSPL / RSAL / ELv2
  ```
- 依存ライセンスの列挙と照合は、生成物に同梱の `license-check` タスクが
  行う(`pip-licenses --from=mixed --partial-match`。security推奨で有効、
  CIのlintジョブから呼ばれる。fail-on はプロジェクトのライセンスから
  自動導出: permissive/Proprietary等→GPL系(LGPL/AGPL含む)、
  GPL/LGPL→AGPL、AGPL→なし=最強なので打ち止め)。質問票が提示する
  全ライセンスがポリシーに解決される(取りこぼすと「絶対に落ちない
  license-check」が同梱され、本節の L2 主張が嘘になる)。`--partial-match` は
  部分一致なので、`GPL` は `GNU General Public License (GPLv3)` /
  `...(LGPL)` / `...(AGPLv3)` のいずれにも当たる。タスクを落とした
  構成では同型の照合(`pip-licenses`相当でlicense欄を出力しallowlistと照合)を
  自前で組む。
- renovate等の自動更新でメジャー更新・ライセンス欄変化を通知対象にする。
- 競合サービスを作る予定がある場合、SSPL/BSL類は「自分が提供する形」で
  制限に触れるため、早期に弁護士照会(本節はその判断の代行ではない)。

## 運用チェック

- 設定側トリガー(Copier QA L1用):
  `(?i)\b(BUSL|SSPL|RSAL|ELv2|licen[cs]e)\b`
  hit時は本節の存在をassert。
- 依存のライセンス棚卸しを半期に一度、pyproject/lockの差分レビューで
  実施する。担当: 依存管理と同じレビュー役。

## 制度変更ウォッチ

- 変更予告: HashiCorpとOpenTofuの係争は動き得る。確度: 係争中(公開記録)。
  Elastic/Redisの復帰のように逆方向の変更もあり得る。
- 確認TODO: OpenTofu FAQとHashiCorp公式の現行方針を一次で確認
  (review_by: 2027-03-31)。
- 影響TODO: 自プロジェクトがTerraform/OpenTofu類のツールを参照する場合、
  どちらを後継として扱うかドキュメントに明記する。

<!-- 法的助言ではない。専門家レビュー必須。 / This is not legal advice; expert review required. -->

</details>

# PKIチェーン再編 — 中間証明書・発行チェーンをハードコードしない

> **適用条件**: TLSクライアントの実装、証明書ピン留め、trust storeの
> 同梱・固定、mTLS、長寿命デバイスのファームに証明書を焼く場面。
> 規模: 世界問題(チェーン切れは全世界のクライアントで同時に起きる)。
> 配布: IoT・cli・web(長寿命クライアント・証明書ピン留めを行うもの)。
> 要約: (1)中間証明書や発行チェーンの同梱・固定をしない
> (2)検証はOS/システムのtrust storeに従い、更新手段を持つ
> (3)pinする場合は公開鍵集合+バックアップ鍵で、単一鍵に結びつけない。
> 詳細は本文。
> Triggers: `(?i)\b(certificat|trust\s?store|ca_bundle|pinn|openssl|requests|httpx|urllib3|mtls|root\s?ca|intermediate)\b`.


<details>
<summary>詳細解説を展開（事実・判例・禁止パターン・制度変更ウォッチ）</summary>

## 事実

Let's Encryptはクロス署名チェーンの段階的廃止を進めている。
DST Root CA X3によるクロス署名は2024-09-30に失効し、長いチェーン自体も
2024-06-06に提供終了した。2024-04からは中間証明書1枚だけの新しい発行
チェーンに移行している。さらにISRG Root X2をISRG Root X1が署名した
クロス署名証明書は2025-09に失効した。Cloudflareも2024-05-15以降、
クロス署名チェーンからの発行を停止している。発行CAやチェーン構成は
事前告知の上で切り替わる(Let's Encryptはロート鍵儀式も計画発表済み)。
ハードコードされた中間証明書、同梱の古いtrust bundle、特定発行チェーンへ
のピン留めは、この種の切り替えで検証失敗(通信障害)になる。
出典: Let's Encrypt公式(chains/ブログ)、コミュニティスレッド、
Cloudflareコミュニティ(REGISTRY.ymlに記録)。

## 禁止パターン

- 中間証明書のリポジトリ同梱・ファーム焼き込み(`chain.pem`の固定同梱)。
- 特定の中間証明書・SPKI単体へのピン留め(バックアップ鍵なし)。
- 独自trust storeの固定(システム更新を取り込めない形)。
- 検証の握りつぶし(`verify=False`, `ssl.CERT_NONE`での障害回避)。
- 発行CA名・チェーン構成を前提にした分岐(`issuer CN == "R3"`等)。

## 推奨設定

- 検証はOS/システムのtrust storeを使い、`certifi`等は依存更新で追う。
  長寿命デバイスはOTA/設定更新でtrust storeを更新できる経路を持つ。
- ピン留めが必要な場合は公開鍵の集合(現行+バックアップ)に対して行い、
  鍵ローテーション手順と失効時の緊急解除を文書化する。
- チェーン検証をCIに入れる(`openssl s_client -showcerts`相当で
  実チェーンを確認し、issuer前提コードを検出する)。
- 有効期限・失効情報(OCSP/CRL・CTログ)の監視を証明書運用の一部にする。

具体例(TLSクライアントの既定形。悪い形と良い形の対):

```python
# 悪い: 検証の握りつぶしと、焼き込み・単一鍵への固定
httpx.get(url, verify=False)  # CERT_NONE での障害回避
requests.get(url, verify="packaging/chain.pem")  # 同梱チェーンの固定
if issuer_cn(cert) == "R3":
    ...  # 発行チェーン前提の分岐

# 良い: 既定の trust store に従い、pin は公開鍵集合で行う
httpx.get(url)  # システムの検証に従う
pin_set = {"sha256/現行の鍵", "sha256/バックアップ鍵"}  # 手順と一緒に版管理
```

## 運用チェック

- 設定側トリガー(Copier QA L1用):
  `(?i)\b(chain\.pem|ca_bundle|CERT_NONE|verify\s*=\s*False|pin_sha256)\b`
  hit時は本節の存在をassert。
- 自プロジェクトが同梱する証明書・ピン留め一覧を棚卸しし、
  「発行チェーン切り替えで壊れるか」を質問できる状態にする。
  担当: リリース管理者。

## 制度変更ウォッチ

- 変更予告: Let's Encryptは新しいルート証明書の鍵儀式を計画中。
  確度: 公式告知あり(実施時期は未定)。発行チェーンは今後も変更があり得る。
- 確認TODO: letsencrypt.org/certificates/ で現行チェーン構成を確認
  (review_by: 2026-12-18)。
- 影響TODO: 同梱chain/pinを持つリリース物がある場合、
  チェーン変更告知を監視対象に追加する。

<!-- 法的助言ではない。専門家レビュー必須。 / This is not legal advice; expert review required. -->

</details>

# PQC標準 — 新規の暗号選択はML-KEM/ML-DSA系・ハイブリッドで行う

> **適用条件**: TLS・鍵交換・署名・証明書・JWT・VPNなど暗号プリミティブを
> 新規に選択・実装・設定する場面すべて。保守で暗号まわりを触る時も含む。
> 規模: 世界問題(旧暗号は今も全世界で書かれ、被害は保存データとして長期化する)。
> 配布: library / cli / web(TLS・暗号を実装するもの)。
> 要約: (1)標準名で呼ぶ(ML-KEM/ML-DSA/SLH-DSA。応募名Kyber等を新規に使わない)
> (2)鍵共有はKEM=ML-KEM、署名はML-DSAが既定・SLH-DSAは保守的代替と役割を混ぜない
> (3)移行はハイブリッド(X25519MLKEM768等)で行い、旧暗号単独の新規採用をしない。
> 詳細は本文。
> Triggers: `(?i)\b(ml-kem|ml-dsa|slh-dsa|kyber|dilithium|sphincs|fips\s?20[345]|rsa|ecdh|ecdsa|ed25519|tls|ssl|kem|cipher|pqc|post-quantum)\b`.


<details>
<summary>詳細解説を展開（事実・判例・禁止パターン・制度変更ウォッチ）</summary>

## 事実

NISTは2024-08-13、耐量子暗号の正式標準3件を発行した。
FIPS 203 = ML-KEM(鍵カプセル化KEM、CRYSTALS-Kyber由来)、
FIPS 204 = ML-DSA(デジタル署名、CRYSTALS-Dilithium由来。第一選択の既定)、
FIPS 205 = SLH-DSA(署名、SPHINCS+由来。格子前提に依存しない保守的代替)。
3規格は相互互換の選択肢ではなく機能が異なる: ML-KEMは鍵共有専用で署名を持たず、
RSA鍵交換/ECDHを代替する。ML-DSAとSLH-DSAは署名専用で、RSA署名/ECDSAを代替する。
SLH-DSAは安全性をハッシュのみに負う反面、署名が約7.9KB(128s)〜17.1KB(128f)と
巨大で、ML-DSA-44の約2.4KBに比べ通信帯域・ログ・証明書チェーンを圧迫する。
NIST IR 8547はRSA-2048・ECDH-P256等の112bit安全性を2030年までにdeprecated、
2035年までにdisallowedとする移行目標を示した。長期秘匿データは
「今盗聴→後で量子解読」(harvest now, decrypt later)の対象になるため、
移行期限は保存データの秘匿が必要な期間から逆算する。
出典: NIST FIPS 203/204/205・IR 8547(REGISTRY.ymlに記録)。

## 禁止パターン

- 新規コードでのRSA鍵輸送(`RSA/ECB/PKCS1Padding`等)・ECDH単独の鍵共有・
  RSA/ECDSA単独の新規署名設計。
- 応募名の新規採用(`kyber768` `dilithium3`等の設定値・識別子。標準名に直す)。
- 役割の混同(KEMで署名する、署名アルゴリズムで鍵共有する)。
- SLH-DSAのデフォルト採用(帯域・証明書サイズの肥大化。保守的用途に限定)。
- 量子脆弱アルゴリズム単体での長期保存データ暗号化・長期有効なトークン/証明書。

## 推奨設定

- TLS: ハイブリッド群を優先(`X25519MLKEM768`。OpenSSL 3.5系は既定の群に組み込み)。
  非対応相手へは従来群にフォールバックしつつ、棚卸しで残存接続を追跡する。
- 署名/PKI: 新規はML-DSAを既定に。SLH-DSAは帯域に余裕のある保守的な用途のみ。
  移行期は従来署名との二重署名で検証側の互換を取り、composite署名の標準化を追う。
- ライブラリ: 標準名API(`ML-KEM-768`等)を提供する版に上げ、独自実装をしない。
- 用語の移行: ドキュメント・設定・ログの応募名を標準名に置換し、
  対応はIANA等の公式レジストリで確認する。

具体例(設定・識別子に現れる形。悪い形と良い形の対):

```text
# 悪い: 応募名と旧単体の新規採用
kyber768 / dilithium3                  # 応募名。標準名に直す
TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256  # ECDH 単独の新規鍵共有

# 良い: 標準名 + ハイブリッド
ML-KEM-768(鍵共有) / ML-DSA-65(署名)     # FIPS 203/204 の標準名
group = X25519MLKEM768                  # TLS のハイブリッド群(OpenSSL 3.5系は既定群)
```

## 運用チェック

- 暗号資産棚卸し(どの鍵長・アルゴリズムがどこで使われているか)を版管理し、
  IR 8547の2030/2035里程碑に照らした削除計画を持つ。担当: 依存管理と同じ
  レビュー役(単独では回らない)。
- 設定側トリガー(Copier QA L1用):
  `(?i)\b(ml-kem|ml-dsa|slh-dsa|kyber|dilithium|sphincs|fips\s?20[345]|rsa|ecdh|ecdsa|tls)\b`
  hit時は本節の存在をassert。
- JWT・mTLS・VPN等のプロファイルごとに移行可否を確認する。標準団体の
  プロファイル更新待ちの箇所は「待ち」と明示して無理に繋がない。

## 制度変更ウォッチ

- 変更予告: FIPS 206(FN-DSA、Falcon由来)は草案待ち。確度: 審議中。
  CNSA 2.0等の政府調達スケジュールは民間標準より前倒し。
- 確認TODO: IR 8547最終版(草案ipdからfinal化)の確定要件を一次で確認
  (review_by: 2027-03-31)。
- 影響TODO: 自プロジェクトが依存する暗号ライブラリのML-KEM/ML-DSA対応版を
  確認し、pinを外して追従できる状態にしておく。

<!-- 法的助言ではない。専門家レビュー必須。 / This is not legal advice; expert review required. -->

</details>

# LLMアプリ/MCP安全設計 — 最小権限・人間承認・出力検証を既定にする

> **適用条件**: LLM API呼び出し、ツール呼び出し、MCPサーバ/クライアント、
> エージェントループを含むコードを生成・設計する場面。
> 規模: 世界問題(OWASP基準は国際共通で、実インシデントも国境を跨ぐ)。
> 配布: MCP(MCPサーバ・ツール呼び出しコードを生成するもの)。
> 要約: (1)ツール権限はallowlistの最小CRUDに絞る (2)破壊的・不可逆な
> 操作の前に必ず人間承認ステップを入れる (3)LLM出力は構造化検証してから
> 実行し、shell直渡しをしない。詳細は本文。
> Triggers: `(?i)\b(llm|prompt|agent|tool[_-]?call|mcp|openai|anthropic|chat|completion|system[_-]?prompt|guardrail)\b`.


<details>
<summary>詳細解説を展開（事実・判例・禁止パターン・制度変更ウォッチ）</summary>

## 事実

OWASP GenAI Security Projectの「Top 10 for LLM Applications」現行版は
2025年版(genai.owasp.org、2024-11公表)で、LLM01 プロンプトインジェクション、
LLM02 機密情報漏洩、LLM03 サプライチェーン、LLM04 データ/モデルポイズニング、
LLM05 不適切な出力ハンドリング、LLM06 過剰なエージェンシー(Excessive
Agency)、LLM07 システムプロンプト漏洩、LLM08 ベクトル/埋め込みの弱点、
LLM09 誤情報(Misinformation)、LLM10 無制限消費、である。番号は版ごとに
動く(2023-24版では過剰エージェンシーは別番号)ため、参照は番号でなく
名称で行う。過剰なエージェンシーは実インシデント(意図しないデータ削除、
不正送金、未承認の送信)として報告されており、モデルに確認なしで
実行権を渡した設計が直接原因になる。誤情報は「流暢で自信のある誤り」
として下流の意思決定を誘導するため、出力を検証なしで動作に使わない。
次版(2026)は実証インシデントデータに基づく評価への転換が議論されている。
出典: genai.owasp.org/llm-top-10 (REGISTRY.ymlに記録。次版は未公表・要確認)。

## 禁止パターン

- LLM出力の直接実行(`shell=True`、`eval`、SQLの文字列連結)。
- 破壊的・不可逆な操作(delete、送金、送信、本番deploy)の自動承認
  (auto-approve、確認ダイアレスの実行)。
- 書き込み権限トークンの無条件発行(read-onlyで足りる場面にwrite権限)。
- 秘密情報(APIキー、個人情報)のプロンプト埋め込み。
- ガードレール・内部schemaの全文をsystem promptに載せる(漏洩時の
  回避手引きになる)。
- 無制限のツールループ・無制限のAPI消費(回数/金額上限なし)。

## 推奨設定

- ツール権限はallowlist(verb × resourceの最小CRUD)。MCPのツールには
  read-only/副作用の有無をアノテーションで明示する。
- 承認ゲートの既定形: LLMが「操作案+差分」を提示 → 人間が確認 →
  実行。実行結果は監査ログに残す。
  ```
  plan = agent.propose(task)          # 構造化出力(schema検証)
  diff = preview(plan)                 # 実行せず影響を提示
  if not human_approves(diff):         # 破壊的操作は必ず人間
      abort(plan)
  result = executor.run(plan, scope=READ_ONLY_UNLESS_APPROVED)
  ```
- 出力はJSON schema等で構造化検証し、検証失敗は実行せず差し戻す。
- 回数・予算・タイムアウトの上限をツールループに設ける。
- 秘密情報はプロンプトに入れず、実行環境側に注入して参照させる。

## 運用チェック

- 設定側トリガー(Copier QA L1用):
  `(?i)\b(shell\s*=\s*True|eval\(|subprocess|tool_choice|mcp|autonomous)\b`
  hit時は本節の存在をassert。
- エージェントコードのレビュー項目: 「最大何が壊せるか」を一問し、
  その答えが人間承認を経ないと起きないことを確認。担当: コードレビュー役。

## 制度変更ウォッチ

- 変更予告: OWASP次版(2026)は実証インシデントデータ基準への転換が
  議論されている。確度: 未確認(2026-09時点で公開ページは2025年版が現行)。
- 確認TODO: genai.owasp.orgで次版の公表と評価方法を確認
  (review_by: 2026-12-18)。
- 影響TODO: 自プロジェクトのMCP/ツール設計を次版の項目名で
  再マッピングできるよう、参照は名称ベースで書く。

<!-- 法的助言ではない。専門家レビュー必須。 / This is not legal advice; expert review required. -->

</details>
<!-- daimonion:ethics:end -->
