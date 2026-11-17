# 引き継ぎ: Project Maya × GLM-5.3-Flash の BenchCAD zero-shot 評価

作成: 2026-11-17 (クラウドセッションからローカル作業への引き継ぎ)
詳しい計画は [`PLAN.md`](PLAN.md)。この文書は「何を調べて何が分かったか」と「ローカルでどこから再開するか」をまとめたもの。

---

## 1. 目的 (確定事項)

- **学習なしの zero-shot 評価だけ**を論文にする。ファインチューニングは対象外 (コードも削除済み)。
- 対象: **Project Maya** 上の **GLM-5.3-Flash** (Strataは対象外)。
- 評価: **BenchCAD 2.1 の Public set (100ケース)** と同梱の examples (9ケース)。Core はアクセス不可のため使わない。

---

## 2. ローカルでの再開手順

### 2.1 ブランチを取る

```bash
git clone https://github.com/cynagenautes/benchcad-2-main && cd benchcad-2-main
```

```bash
git checkout claude/great-faraday-jzy8t2
```

このブランチの中身:

| パス | 内容 |
|---|---|
| `harness/run.py` | `maya/<id>` プロバイダを追加 (下の§4) |
| `tests/test_maya_provider.py` | Mayaと同じSSEを返す偽サーバーでのテスト4件 |
| `paper/PLAN.md` | 論文計画: 条件表, RQ, シード調査, 構成, 実行手順 |
| `paper/HANDOFF.md` | この文書 |
| `paper/eval/maya_config.py` | Mayaの設定ファイルにrep別のseedと評価条件を書き込む |
| `paper/eval/run_matrix.sh` | 段階別の実行 (0 / 1 / main / repeat / ref)。Mayaの `/props` でseedを確認してから走る |
| `paper/eval/collect_env.sh` | 実行環境 (GPU, Mayaのバージョン・設定, `/props`) を結果の隣に保存 |
| `paper/eval/compare_runs.py` | 同じseedで回した2回の結果を比較 (再現性チェック) |

### 2.2 最初にやること (この順)

1. `uv sync --group harness --group dev` と `docker build -t benchcad-sandbox:amd64 sandbox/` (ARMなら `:arm64`)。
2. `paper/eval/run_matrix.sh 0` (mock/oracle が examples 全件で 1.0 になることの確認。モデル不要)。
3. Mayaで GLM-5.3-Flash を起動できる状態にする (`./setup.sh --model glm-maya-s` など)。
4. `paper/eval/maya_config.py` で rep 0 の設定を作り、それでMayaを起動。
5. `paper/eval/collect_env.sh` で環境を記録。
6. **`paper/eval/run_matrix.sh 1` (パイロット: examples 9件)** → 1ケースあたりのトークン数と時間を見る。
   ← **ここが実機での最初の確認。** 本実験の規模 (rep数, effort, 並列数) はこの実測で決める。
7. Public を取得して本実験 (`main`)、再現性チェック (`repeat`)。

各コマンドの完全な形は `PLAN.md` §6。

### 2.3 環境変数

| 変数 | 意味 | 例 |
|---|---|---|
| `MAYA_BASE_URL` | MayaのAPI (別マシン可) | `http://192.168.1.20:8080/v1` |
| `MAYA_API_KEY` | Mayaを鍵付きで起動したときだけ | |
| `MAYA_CONTEXT_TOKENS` | Mayaの設定コンテキスト (run_matrix.shで必須) | `262144` |
| `MAYA_IDLE_S` | 無通信で諦めるまでの秒数 (既定900。prefill中Mayaは何も送らない) | |
| `MAYA_CALL_BUDGET_S` | 1回の呼び出しの上限秒数 (既定7200) | |
| `TIER`, `REP`, `EFFORT`, `WORKERS` | run_matrix.sh 用 (ラベル, rep番号, 既定max, 既定1) | |
| `HF_TOKEN` | Public取得用 (HFで規約に同意したアカウント) | |

---

## 3. 調査結果

### 3.1 BenchCAD (リポジトリとデータ)

- **バージョン:** ハーネス 2.1。タグ `v2.1` の中身の最新は `803d063`。このブランチの土台 `main` の `1bc7f26` と `v2.1` の差は
  テスト用ファイルの移動 (#23) だけで、ハーネスと採点部分は同一。
- **データ:** `BenchCAD/benchcad-2.0-public` の revision `v2.1` (commit `1ef73a9bb7`)。T6スコアラー digest `c4799cc2…`。
  2.0 / 2.1-beta とはスコアを比べられない。
- **ハーネスの契約 (変えない):** 60ラウンド, 1ケース50万出力トークン (思考込み), 1返答128k, 思考の持ち越しあり,
  文脈要約は min(コンテキスト, 800k), 画像は長辺2000pxまで, Dockerサンドボックス (ネットなし・2GB・1CPU・1ブロック300秒),
  提出なし=0点。
- **採点:** LLM judgeなし。幾何で決定的に採点 (T3の現行式は `0.8·iou_term + 0.2·topology`。定義は `docs/METRICS.md`)。
- **リソース:** 採点は1プロセス 2.5–3.1GB, 1ケース16–69秒。ホストに 8GB RAM・2コア以上。
- **既存の公表値** (`results/core_reference.json`) は 2.0・30ラウンド・Core で、今回の条件とは比べられない。
- **LICENSEファイルがない。** 改変ハーネスを公開するならBenchCADチームに確認する。

### 3.2 Public set の規約 (Hugging Face の gating 文面より)

- 評価にのみ使う。**学習・ファインチューニング・蒸留・RL環境化は禁止**。
- データの再アップロード・ミラー・ケース/図面/レンダ/正解の公開は禁止。
  **結果と集計スコアの公開はOK** → 論文の図にケース画像は載せない。
- canary文字列を手元のコピーに残す。汚染の疑いは benchcad.team@gmail.com へ。
- BenchCAD自身は Public のスコアを「reportableではない」としている (公式報告は Core)。
  論文では「Public set での評価」と明記し、Coreの値と並べない。投稿前にBenchCADチームへ一報するのが安全。

### 3.3 GLM-5.3-Flash (Hugging Face モデルカード)

- zai-org, **MIT**, 321B / 18B active, **ネイティブのマルチモーダル** (image-text-to-text), FP8配布, 最大1Mコンテキスト。
- `reasoning_effort` は `low / high / max`、**既定 max** (ベンチ再現はmaxのまま)。
- 評価時のサンプリングは temperature 1.0, top_p 0.95。
- ビジョンは 24ブロックのViT, 448px, patch 14。

### 3.4 Project Maya (`github.com/mw00/project-maya`, v1.1.65, commit `c89ebef`)

- GLM-5.3-Flash 用の Maya quant: XS 73.4GB / S24 94.7GB / **S 96.5GB (既定)** / M 116GB / L 156.3GB
  (VRAM+RAMの合計で保持)。Maya自身の測定で FP8 比 zero-shot 正答率 97.7–99.2%, next-token一致 83–90%。
- 速度 (ユーザー報告): decode 15–150 tok/s, prefill 300–4000 tok/s (構成次第)。
- **API:** OpenAI / Anthropic 互換。`POST /v1/responses` は画像 (`input_image` の data URL), `reasoning.effort`,
  `store:false`, `include:["reasoning.encrypted_content"]` に対応。推論は `response.reasoning_text.delta` で流れ、
  `encrypted_content` は暗号化ではなくエンコードしただけのもの。画像の `detail` は無視 (autoのみ)。
- **effort の丸め:** `medium→high`, `xhigh→max`, `none/off→なし`。
- **Responses API が受け付ける項目:** `temperature`, `top_p` など。**`seed` は受け付けない** (`unsupported Responses parameter`)。
- **サンプリングの既定値** (`tools/maya_quants.py`): GLM は temperature 1.0 / top_p 0.95 / effort max。
  **Maya-XS だけ temperature 0.7 / top_p 0.95 / min_p 0.05**。
- **`thinking_budget`:** 既定 32768 (XSは8192)。超えると思考を閉じて回答に移る。
- **loop guard (既定on):** 繰り返しを検知すると繰り返し部分の削除・短い繰り返しペナルティ・思考の打ち切りをする。
  さらに会話中の重複の省略や、サーバーが書いたメッセージの挿入も行う。`"loop_guard": false` (設定) か `MAYA_LOOP_GUARD=0` で切る。
- **設定ファイル:** setupが書く `maya-<model>.json`。`sampling`, `thinking_budget`, `loop_guard`, `args`, `env` を持つ。
  `./maya.sh --config <file>` で起動。`GET /props` にサンプリング既定値 (seed含む), コンテキスト, スロット数, vision有無が出る。

### 3.5 シードと「ぶれ」(Maya `docs/SETTINGS.md`「Repeatable answers」とソースより)

- seed は設定の `sampling.seed` でサーバー全体に与える。変えるには再起動が要る → **1 rep = 1起動**, seed = 1000 + rep。
- **量子化そのものは決定的** (固定された重み)。tierが違えば別モデルで、同じseedでもtier間で出力はそろわない。
- ぶれの原因は2つ。
  1. サンプリング: seedで固定できる。
  2. 計算経路: RAM層のエキスパートを CPU lane で計算するか PCIe 経由で GPU で計算するかが起動ごとに変わり、
     丸めの差 (約2%) をルーターの top-8 選択が増幅する。既定設定の再起動で一致したのは70組中17組。
- 固定する設定:

| 何が変わるか | 固定方法 |
|---|---|
| VRAMのエキスパート枠 | `--expert-cache N` (起動ログの `tiers warm` より少し小さく) |
| CPU laneの分担 | `MAYA_GLM_PCIE_SHARE` / `MAYA_GLM_CPU_PLAN` |
| 実行中の再計測 | `MAYA_GLM_CPU_RETIME=0` |
| 裏でのエキスパート移動 | `MAYA_GLM_PROMOTE=0` |
| RAM層の大きさ | `MAYA_GLM_RAM_GB` |
| プロンプトの数値がキャッシュ状態に依存 | `MAYA_GLM_PREFILL_STABLE=1` (2–5%遅い) |
| まとめて解決 | `MAYA_GLM_CPU_LANE=0` (全部GPUで計算。decode 4–10%遅い) |

- `--parallel` 2以上はビット一致しないことがある → 再現性チェックは `--parallel 1`。
- ドラフター (DFlash2/MTP) は使っても出力は同じ。ただし読み込むとVRAMが減り、エキスパート配置が変わって出力が変わる。
- 別のビルド・ドライバ・GPUでは一致しない (Maya側の測定も1台のみ。複数GPU・Linux・AMDは未確認と明記)。
- **論文では:** 主結果は3 seedの平均とばらつきで出す。付録に「6ケースを同じseedで2回」の再現性チェックを付ける。

### 3.6 クラウド版 (任意の比較用)

- OpenRouter に `z-ai/glm-5.3-flash` (画像入力あり, 1Mコンテキスト, 入力約$0.04・出力約$0.08 / 100万トークン, 2026-11-17時点)。
- ハーネスの `openrouter/` は effort `none/low/medium/high` のみ (maxなし) → 比較は `high` 同士。
- 提供元がルーティングされ、量子化が不明なことがある。ハーネスに提供元を固定する機能はない。

---

## 4. ハーネスへの変更 (`maya/` プロバイダ)

- `--model maya/<id>` で、`MAYA_BASE_URL` の `/v1/responses` に OpenAI SDK で接続。既存の `openai/` 経路
  (`openai_responses_call`) に base_url・待ち時間の引数を足して共用している。
- effort は `none/low/high/max` のみ受け付ける (Mayaが黙って丸める `medium/xhigh` は拒否)。既定は max。
- 各レコードの `auth` に `maya base_url=... idle_s=... call_budget_s=...` を記録 (鍵の値は記録しない)。
- `tools/run_core.sh` もハーネスのプロバイダ表を使うので `maya/` で動く (APIキー不要)。
- 検証:
  - 追加テスト4件
  - ハーネス関連の既存テスト143件がすべて通過
  - 偽Mayaサーバー相手に examples/task3 で提出→採点まで end-to-end で通過 (箱の提出で0.20)
- **未検証:** 実機のMayaでは一度も動かしていない。

---

## 5. 未解決 / 要確認

- [ ] 実機での最初の疎通 (stage 1)。うまくいかない場合はまずMayaのログと `results/paper/*.json` の `error` を見る。
- [ ] `/props` の `default_generation_settings.params.seed` から実際にseedが読めるか (ソースから読んだ形式)。
- [ ] 画像1枚がMaya側で何トークンになるか、T2/T4/T5 (1ラウンド12–20枚) がコンテキストに収まるか。
- [ ] prefill中の無通信時間が `MAYA_IDLE_S` (900秒) を超えないか。超えたら上げる。
- [ ] 1ケースあたりの時間 → rep数・effort・並列数の決定。
- [ ] Mayaとハーネスを同じマシンで動かすか。MayaはRAMをほぼ使い切るので、別マシン推奨。
- [ ] BenchCADチームへの連絡 (Publicの集計スコアを論文に載せる件, ハーネス改変の公開可否)。
- [ ] 電力の計測方法 (`nvidia-smi --query-gpu=power.draw` の定期記録など。まだ用意していない)。

---

## 6. 出典

- BenchCAD: このリポジトリの `README.md`, `docs/RUNNING.md`, `examples/README.md`, `releases/benchcad-2.1.json`, `tools/run_core.sh`
- Public set: https://huggingface.co/datasets/BenchCAD/benchcad-2.0-public (gating文面と `extra_gated_fields`)
- GLM-5.3-Flash: https://huggingface.co/zai-org/GLM-5.3-Flash
- Project Maya: https://github.com/mw00/project-maya (`README.md`, `docs/RESPONSES.md`, `docs/SETTINGS.md`, `docs/GLM5-FLASH.md`,
  `serve/responses.py`, `serve/server.py`, `serve/frontend.py`, `tools/maya_quants.py`)
- OpenRouter モデル一覧: https://openrouter.ai/api/v1/models
- Project Maya / Strata の概要 (二次情報, 未検証の記述を含む): https://aiwiki.ai/wiki/project_maya, https://toolhalla.ai/tool/strata
