# 論文計画: Project Maya上のGLM-5.3-FlashのZero-shot CAD性能 (BenchCAD 2.1 Public)

更新: 2026-11-17 / 対象: BenchCAD harness 2.1, Project Maya 1.1.65 (`c89ebef`), GLM-5.3-Flash
方針: **学習なし (zero-shot) の評価のみ。** ファインチューニングは対象外。

## 0. 結論

- **テストだけで論文になる。** 学習データは不要で、BenchCAD 2.1のPublic set (100ケース) に
  Maya上のGLM-5.3-Flashをそのままかけ、スコア・失敗の仕方・時間・電力を報告する。
- **書けること:** 「ローカルの量子化GLM-5.3-Flashが、図面/写真からCADを作る長いエージェント課題で
  何点取れるか、どこで失敗するか、1ケースに何時間/何kWhかかるか」。
- **書けないこと:** Coreスコア・公式リーダーボードとの比較。Publicのスコアは公式には「reportableではない」。
  規約上、**結果と集計スコアの公開はOK**、ケース・図面・レンダ・正解の公開はNG。
  論文の図にケースの画像を載せられない点に注意する (自作の図か、数値のみ)。
- 投稿前に benchcad.team@gmail.com へ一報するのが安全。

## 1. BenchCADのバージョンと固定する条件

### 1.1 バージョン

| 項目 | 値 |
|---|---|
| ハーネス | **2.1** (`harness_version` が全レコードに入る) |
| コードのタグ | `v2.1` (中身の最新は `803d063`)。このブランチは `main` の `1bc7f26` + `maya/` 追加。`v2.1`→`1bc7f26` の差はテスト用ファイルの移動だけで、ハーネスとスコアラーは同一 |
| データ | `BenchCAD/benchcad-2.0-public` revision `v2.1` (commit `1ef73a9bb7`)。`tools/run_core.sh --set public` がこのrevisionを落とす |
| T6スコアラー | digest `c4799cc2…` (rule B) |
| 比較できない版 | 2.0, 2.1-beta (ラウンド数・予算・思考の持ち越しが違う) |

### 1.2 ハーネスの条件 (2.1の契約。変えない)

| 条件 | 値 | 備考 |
|---|---|---|
| ラウンド | 60 | 変えたら「smoke run」扱い |
| 出力トークン予算 | 500,000 / ケース (思考込み) | ラウンド間でのみ判定 |
| 1返答の上限 | 128,000 トークン | Responses経路の `max_output_tokens` |
| 思考の持ち越し | あり | Mayaは推論を `encrypted_content` (実体はエンコードしただけ) で返し、次ラウンドに戻す |
| 文脈の要約 | min(コンテキスト, 800k) で発火 | **`--context-tokens` にMayaの設定コンテキストを渡す** (モデルの1Mではない) |
| 画像 | 長辺最大2000px, 毎回同じバイト | GLMのビジョンは448px・patch14 |
| サンドボックス | Docker, ネットなし, 2GB, 1CPU, 1ブロック300秒 | `CADENV_LOCAL=1` での実行は報告用にしない |
| 終了 | `submit` / ラウンド切れ / 予算切れ | 提出なし = 0点 |
| 集計 | ケースごとにrep平均 → タスク平均 → タスク平均の平均 | 全repが確定するまで見出しを出さない |

### 1.3 Mayaとモデルの条件 (論文の表にそのまま載せる)

| 条件 | 推奨値 | 理由 |
|---|---|---|
| effort | **max** (主), high (副) | GLM-5.3-Flashのカード: 既定かつベンチ再現の設定はmax。`maya/` は `none/low/high/max` のみ受け付ける |
| サンプリング | temperature 1.0, top_p 0.95 | モデルカード (Mayaの既定と同じ)。**Maya-XSだけMayaの既定が0.7/min_p 0.05なので上書きする** |
| seed | 1000 + rep | 下の§3 |
| thinking_budget | **0 (上限なし)** | Mayaの既定32768 (XSは8192) は思考を途中で閉じる。モデル本来の挙動を測るため外し、ハーネスの128k上限に任せる |
| loop guard | **off** | Mayaのloop guardは繰り返しを検知すると会話の書き換えやサーバー側メッセージの挿入をする。zero-shotのモデル性能ではなくなる。onは別条件 (§2のRQ3) として測る |
| quant tier | 手元に入る最大のもの (L > M > S > S24 > XS) | 1つで主結果、余裕があれば2つ目 |
| コンテキスト | 例 262144 | 画像の多いT2/T4/T5で足りるかはパイロットで確認 |

これらは `paper/eval/maya_config.py` がMayaの設定ファイル (`maya-<model>.json`) に書き込む。

## 2. 研究質問

| RQ | 問い | 必要な実行 |
|---|---|---|
| RQ1 | Maya上のGLM-5.3-Flashは各タスクで何点か | Public 100 × effort max × 3 rep |
| RQ2 | どう失敗するか: 提出なし / 提出失敗 / ラウンド切れ / 予算切れ / 要約発生、タスク別 | RQ1のレコードから (追加実行なし) |
| RQ3 | Mayaの運用設定 (loop guard, thinking_budget) でスコアは変わるか | 30ケース程度 × 設定違い × 1 rep |
| RQ4 | 1ケースの時間・電力 (prefill / decode 別) | RQ1の実行中に計測 |
| RQ5 (任意) | 同じモデルのクラウド版との差 | `openrouter/z-ai/glm-5.3-flash` (画像入力あり, 入力約$0.04・出力約$0.08 /100万トークン)。ただしOpenRouterには `max` がなく `high` までなので、`high` 同士で比較する |

RQ1とRQ2だけで「zero-shot性能レポート」として成立する。RQ3–RQ5は余力次第。

### 統計の扱い
- Publicは1タスク約16–17ケース。タスク別の数値には必ず n と95%ブートストラップ区間を付ける。
- BenchCAD READMEの実測では同一ケースのばらつきが大きい (0.67 @ temperature 0.7)。**最低3 rep**。
- 条件比較 (RQ3/RQ5) は同じケース同士のペア比較で行う。

## 3. Mayaのシード固定と「ぶれ」について (調査結果)

### 3.1 シードの付け方
- **Responses API (`maya/` が話す口) はリクエストの `seed` を受け付けない** (`unsupported Responses parameter: seed` で400)。
  `temperature` と `top_p` はリクエストでも送れる。
- seedは**起動設定 (run config) の `sampling.seed`** で与える。設定はサーバー全体に効き、変えるには再起動が要る。
  → **1 rep = 1回のMaya起動**、rep k の設定は seed = 1000 + k。
  `run_matrix.sh` はMayaの `GET /props` からseedを読み、repと合わなければ止まる。
- 同じseedは毎リクエストに同じように効く。ラウンドごとに会話が違うので、同じ乱数列でも出力は変わる。

### 3.2 量子化はぶれの原因か
- **量子化そのものは決定的。** 重みは固定されたファイルなので、同じtierなら同じ重みで計算する。
- tierが違えば別のモデルと考える。**同じseedでもtier間で出力はそろわない**ので、tierの比較はrepの統計で行う。
- ぶれの本当の原因は2つある。
  1. **サンプリング** (temperature 1.0)。seedで固定できる。
  2. **浮動小数点の計算経路の違い**。Mayaはエキスパートを VRAM / RAM / SSD に置き分け、RAMのエキスパートを
     「CPUで計算する (CPU lane)」か「PCIeでGPUに送って計算する」かを起動時の計測で決める。
     両者は丸め方が違い (出力差 約2%)、ルーターのtop-8選択がそれを増幅する。
     Maya自身の測定では、既定設定で再起動すると greedy でも**数十トークンで出力が分かれる** (70組中17組だけ一致)。

### 3.3 再現性を取る設定 (Maya docs/SETTINGS.md「Repeatable answers」より)

| 何が変わるか | 固定方法 |
|---|---|
| VRAMのエキスパート枠 (空きVRAMで毎回変わる) | `--expert-cache N` (起動ログの `tiers warm` より少し小さいN) |
| CPU laneの分担 (起動時の計測) | `MAYA_GLM_PCIE_SHARE` か `MAYA_GLM_CPU_PLAN` |
| 実行中の再計測 | `MAYA_GLM_CPU_RETIME=0` |
| 裏でのエキスパート移動 | `MAYA_GLM_PROMOTE=0` |
| RAM層の大きさ | `MAYA_GLM_RAM_GB` |
| プロンプト読み込みがキャッシュ状態に依存 | `MAYA_GLM_PREFILL_STABLE=1` (2–5%遅くなる) |
| **まとめて解決** | `MAYA_GLM_CPU_LANE=0`: 全エキスパートをGPUのカーネルで計算。再起動しても同じトークン。decodeは4–10%遅い |

追加の注意:
- `--parallel` 2以上 (同時リクエスト) は、バッチ化・プロンプトの分割読みでビット一致しない場合がある。
  **ビット再現を取るなら `--parallel 1`**。ただしスループットが落ちる。
- ドラフター (DFlash2 / MTP) を**使うこと自体**はトークンを変えない。ただし**読み込む**とVRAMが減り、エキスパート配置が変わってトークンが変わる。条件をそろえる。
- 別のビルド・ドライバ・GPUでは、全部固定しても別の (同じくらい妥当な) トークンになる。Maya自身も「1台のPCでの測定、複数GPU・Linux・AMDは未確認」と書いている。

### 3.4 論文での扱い (推奨)
- 本実験は**3 seed (3回の起動) の平均とばらつき**で報告する。ビット再現を主張の柱にはしない。
- そのうえで**小さな再現性チェック**を付ける: 6ケース (各タスク1件) を同じseedで2回 (間にMaya再起動)、
  `--parallel 1` + §3.3の設定で回し、`paper/eval/compare_runs.py` で
  呼び出しごとの出力トークン数・提出物のハッシュ・スコアが一致するかを見る。
  一致すれば「この設定なら再現できる」と書け、一致しなければ「どこで分かれたか」を書ける。どちらでも結果になる。

## 4. 計算量 (パイロットで実測してから決める)

- Mayaの公開ベンチ (GLM-5.3-Flash): decode 15–150 tok/s, prefill 300–4000 tok/s。
- 1ケースの出力が5万–15万トークンなら、50 tok/sで0.3–0.8時間。予算50万を使い切ると約2.8時間。
- 主実験 = 100ケース × 3 rep = 300エピソード。effort maxは長くなりやすい。**1台で数日〜数週間**の規模。
- 先に stage 1 (examples 9件) で tokens/case と hours/case を測り、足りなければ
  (a) `--parallel` と `WORKERS` を上げる (ビット再現は捨て、3 seedの統計で扱う),
  (b) effortをhighにする,
  (c) repを2にしてCIを報告する、の順で削る。
- **メモリ:** MayaはRAMをほぼ使い切る (Maya-S 96.5GB, M 116GB, L 156GB をVRAM+RAMで保持)。
  BenchCADのスコアラーは1プロセス2.5–3.1GB、サンドボックスは1実行2GB。
  **ハーネス (Docker + スコアラー) は別マシンで動かし、`MAYA_BASE_URL` をLAN越しに向けるのが安全。**

## 5. 論文の構成案

1. Introduction: 巨大MoEのローカル実行が現実的になったが、評価は1問1答の指標が中心
2. Setup: BenchCAD 2.1 Public, GLM-5.3-Flash, Maya (tier, 設定), ハーネスへの `maya/` 追加, 条件表 (§1)
3. Results (RQ1): タスク別スコア, n, CI
4. Failure analysis (RQ2): 終了理由, ラウンド数, トークン数の分布, 画像の多いタスクの挙動
5. Deployment settings (RQ3) と Cost (RQ4)
6. Reproducibility: §3の調査と再現性チェックの結果
7. Limitations: Coreではない, 1台のハードウェア, Mayaのバージョン依存, Publicは公式報告用ではない
8. (任意) Cloud reference (RQ5)

## 6. 実行手順

準備 (ハーネス側のマシン):

```bash
uv sync --group harness --group dev
```

```bash
docker build -t benchcad-sandbox:amd64 sandbox/
```

```bash
paper/eval/run_matrix.sh 0
```

Publicの取得 (Hugging Faceで規約に同意し、`HF_TOKEN` を設定。revision `v2.1` に固定):

```bash
uvx --from huggingface_hub hf download BenchCAD/benchcad-2.0-public --repo-type dataset --revision v2.1 --local-dir ~/.cache/benchcad/benchcad-2.0-public
```

ハッシュ (MANIFEST.sha256) とスコアラーの確認 (`maya/` はAPIキー不要。Mayaへの呼び出しはしない):

```bash
tools/run_core.sh --set public --model maya/glm-5.3-flash --effort max --dry-run
```

rep 0 の設定を作り、Mayaを起動 (Maya側のマシン):

```bash
uv run python paper/eval/maya_config.py ~/project-maya/maya-glm-maya-s.json --rep 0 --repeatable --parallel 1
```

```bash
./maya.sh --config ~/project-maya/maya-glm-maya-s.eval-r0.json
```

環境を記録して、パイロット → 本実験 (ハーネス側):

```bash
export MAYA_BASE_URL=http://<maya-host>:8080/v1 MAYA_CONTEXT_TOKENS=262144 TIER=maya-s REP=0
```

```bash
MAYA_CONFIG=~/project-maya/maya-glm-maya-s.eval-r0.json paper/eval/collect_env.sh results/paper/env_maya-s_r0
```

```bash
paper/eval/run_matrix.sh 1
```

```bash
paper/eval/run_matrix.sh main
```

rep 1, 2 は `--rep 1` / `--rep 2` で設定を作り直し、Mayaを再起動し、`REP=1` / `REP=2` で同じことを繰り返す。

再現性チェック (同じseedで2回、間に再起動):

```bash
RUN=a paper/eval/run_matrix.sh repeat
```

```bash
RUN=b paper/eval/run_matrix.sh repeat
```

```bash
uv run python paper/eval/compare_runs.py results/paper/repeat_maya-s_max_a.json results/paper/repeat_maya-s_max_b.json
```

集計:

```bash
uv run python tools/summarize.py results/paper/main_*.json
```

## 7. このブランチで済んでいること / いないこと

済み:
- `harness/run.py` に `maya/` プロバイダ (Responses API, 思考の持ち越し, 画像, ローカル用の待ち時間設定をレコードに記録)。
  追加テスト4件 + ハーネス関連の既存テスト143件が通過。
- Mayaと同じ形式のSSEを返す偽サーバー相手に、examples/task3で提出 → 実スコアラー採点まで通した。
- `paper/eval/`: 設定ファイル生成 (`maya_config.py`), 実行 (`run_matrix.sh`), 環境記録 (`collect_env.sh`), 再現性比較 (`compare_runs.py`)。

未確認 (実機が必要):
- **実機のMaya + GLM-5.3-Flashでは未実行** (このコンテナにGPUがない)。最初の確認は stage 1。
- Mayaの `/props` の応答形式 (seedの読み取り位置) はソースから読んだもので、実機では未確認。
- 画像1枚がMaya側で何トークンになるか、T2/T4/T5がコンテキストに収まるか。
- このリポジトリにLICENSEファイルがない。改変したハーネスを公開するならBenchCADチームに確認する。
