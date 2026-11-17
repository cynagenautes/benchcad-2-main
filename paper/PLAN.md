# 論文計画: Project Maya によるGLM-5.3-Flashのローカル展開を BenchCAD 2.1 で検証する

作成日: 2026-11-17 / 対象: BenchCAD harness 2.1 (このリポジトリ), Project Maya 1.1.65 (`c89ebef`), GLM-5.3-Flash

## 0. 結論 (先に)

- **Coreなしでも論文は組める。** ただし主張の形を「リーダーボードで何点」から
  **「同じモデルをローカルで量子化して動かすと、長いエージェント型マルチモーダル課題で何が失われるか」**
  という**対照実験**に変える。比較は全部、同じハーネス・同じPublicケースの中で閉じる。
- 使うデータ: **Public set (100ケース, 6タスク)** と同梱の **9 examples**。
  Publicの規約は「評価のみ」「結果と集計スコアの公開はOK」「ケース・図面・レンダ・正解の公開はNG」。
  BenchCAD自身はPublicのスコアを「reportableではない」としているので、論文では
  **Coreの公表値 (`results/core_reference.json`) と横並びにしない**、と明記する。
  投稿前に benchcad.team@gmail.com へ「Publicの集計スコアを論文に載せる」旨を一報しておくのが安全。
- **学習について重要:** Publicの規約は *train / fine-tune / distil / RL環境化* をすべて禁止している。
  なので学習データはBenchCADから一切作らず、**自前の合成CADデータ** (`paper/synth/`) で作った。
  OpenAI APIでのファインチューニングは**ジョブ作成の直前 (dry run) まで**用意済み (§5)。
- **注意:** OpenAIのFTで学習されるのはOpenAIのモデルであり、GLM-5.3-Flash (Maya) ではない。
  また、OpenAIの出力をローカルモデルの学習に使う (蒸留) のはOpenAIの利用規約上の制約があるので、この計画ではしない。

## 1. なぜ新規性があるか

Mayaは自分の量子化 (Maya-XS/S24/S/M/L) の品質を
**zero-shot正答率の保持率 97.7–99.2%** と **next-token一致率 83–90%** で示している (`bench/results/MAYA-*.md`)。
これは1問1答の指標。BenchCADは

- 最大60ラウンド・50万出力トークンの**長いエージェントループ** (誤差が積み重なる)
- **画像入力** (図面・4面図・基板写真) とCadQueryコード生成
- **LLM judgeなし**の決定的な幾何スコア (voxel IoUやトポロジーなど。定義は `docs/METRICS.md`)

なので、「1トークンあたり1–2%の劣化が、60ラウンドで何%のスコア劣化になるか」を測れる。
これはMaya側の資料にもBenchCAD側の公表値にもまだない。

## 2. 研究質問 (RQ)

| RQ | 問い | 比較 |
|---|---|---|
| RQ1 | 量子化tierでスコアはどれだけ落ちるか | Maya tier (例: S24 / S / M / L) vs **同じモデルのクラウド版** (`openrouter/z-ai/glm-5.3-flash`, 画像入力あり) |
| RQ2 | thinking levelと思考予算の効き方 | effort `none/low/high/max` × Mayaの `thinking_budget` (既定32768) |
| RQ3 | ローカル運用のコスト | 1ケースあたりの時間 (prefill/decode), GPU電力量 (kWh), 電気代 vs APIの$/case |
| RQ4 (任意) | どこで失敗するか | 提出なし / 提出失敗 / ラウンド切れ / 文脈要約の発生, タスク別 (T1–T6) |
| RQ5 (任意) | 合成データでの適応は効くか | OpenAI FTモデル (合成データ) vs 同じベースモデル, Public T1/T3で評価 |

RQ1–RQ3が本筋で、それだけで論文1本になる。RQ5は「OpenAI APIで学習」の部分で、付録扱いが妥当。

## 3. 実験設計

### 3.1 アーム

| アーム | `--model` | effort | rep | ケース |
|---|---|---|---|---|
| Maya tier A (例 S24/S) | `maya/glm-5.3-flash` | low, high | 3 | Public 100 |
| Maya tier B (例 M/L) | `maya/glm-5.3-flash` | low, high | 3 | Public 100 |
| クラウド参照 (同じモデル) | `openrouter/z-ai/glm-5.3-flash` | low, high | 3 | Public 100 |
| effort sweep | `maya/...` (1 tier) | none, low, high, max | 1 | Public 100 |
| (任意) 別系統の参照 | `openai/<id>` など | 1 level | 1 | Public 100 |

- **effortの揃え方:** GLMの段階は `low/high/max` (+none)。MayaはAPIで `medium→high`, `xhigh→max` に黙って丸めるので、
  追加した `maya/` プロバイダは `medium`/`xhigh` を**拒否**する (丸めを結果に紛れ込ませないため)。
  OpenRouter側は `none/low/medium/high` しか送れないので、**両方にある `low` と `high` で比較**する。
- **ハーネスの契約 (60ラウンド / 50万トークン) は変えない。** 変えた場合は「smoke run」扱いで本比較に混ぜない。
- **ローカル固有の設定は記録する:** `MAYA_IDLE_S` (既定900秒: prefill中Mayaは何も送らない),
  `MAYA_CALL_BUDGET_S` (既定7200秒), `--context-tokens` (Mayaの設定コンテキスト。モデルの1Mではない)。
  どれも各レコードの `auth` 欄に入る。Mayaの `thinking_budget` は思考を途中で閉じるので**交絡因子**。設定値を固定して記録する。

### 3.2 統計

- Publicは1タスク約16–17ケース。**タスク平均の差は大きく揺れる**ので、主比較は
  **同一ケースのペア比較** (ケースごとにrep平均→ペア差→ブートストラップ95%CI, Wilcoxon符号順位検定)。
- BenchCAD READMEの実測: 同一ケースのばらつき0.67 (温度0.7), ペア差のSD 0.303。
  100ペアなら標準誤差は約0.03、**差0.06前後から検出可能**。3 repで個々のケースのノイズはさらに下がる。
- タスクごとの数字には必ず n を添える。「提出なし=0点」はハーネスの規則どおり。

### 3.3 計算量の見積り (パイロットで必ず実測する)

- Mayaの公開ベンチ (GLM-5.3-Flash): decode 15–150 tok/s, prefill 300–4000 tok/s (構成次第)。
- 1ケースの出力トークンが仮に5万–15万なら、50 tok/sで 0.3–0.8時間/ケース。
  最悪 (50万トークンを使い切る) なら約2.8時間/ケース。
- 主実験 (2 tier × 2 effort × 3 rep × 100ケース = 1200エピソード) は、1台なら**数週間単位**。
  → **stage 1のパイロット (9 examples) で tokens/case と hours/case を測ってから規模を決める。**
  足りなければ: (a) Mayaの並列スロット (`--parallel`, GLMは最大8) と `--workers` を合わせる,
  (b) effort sweep はタスク層化した30ケースに絞る, (c) rep を2に減らしてCIを報告する。
- **メモリの取り合いに注意:** Mayaは物理RAMをほぼ使い切る (Maya-S 96.5GB, M 116GB, L 156GB をVRAM+RAMで保持)。
  BenchCADのスコアラーは1プロセス2.5–3.1GB、サンドボックスは1実行2GB。
  **ハーネス (Docker+スコアラー) は別マシンで動かし、`MAYA_BASE_URL` をLAN越しに向ける**のが安全。

## 4. 論文の構成案

1. **Introduction** — 巨大MoEのローカル実行 (Maya) が実用域に入った。だが量子化の評価は1問1答の指標だけ。
2. **Background** — BenchCAD 2.1 (6タスク, 幾何スコア), GLM-5.3-Flash (321B/18B active, マルチモーダル, MIT), Maya (エキスパートをGPU/RAM/SSDに配置, Maya quant)。
3. **Setup** — ハーネスへの `maya/` 追加 (Responses API, 思考の持ち越し, 画像), 計測環境, Publicを使う理由と規約。
4. **RQ1** 量子化 vs クラウド — タスク別ペア差, CI。
5. **RQ2** effort / 思考予算。
6. **RQ3** コスト — 時間・電力・$/case のパレート図。
7. **RQ4** 失敗分析 — 終了理由の内訳, 文脈要約の発生, 画像の多いタスク (T2/T4/T5) での挙動。
8. (任意) **RQ5** 合成データでのFT。
9. **Limitations** — Coreではない (Publicは「reportableではない」), 1台のハードウェア, OpenRouterの提供元の量子化が不明, Mayaのバージョン依存。
10. **Conclusion**。

## 5. 「OpenAI APIで学習」部分: ここまで用意済み (ジョブ作成の直前で止めてある)

```
paper/synth/families.py           8種類のパラメトリック部品 (プレート/フランジ/L金具/段付き軸/ポケット/六角スタンドオフ/Uチャンネル/リブ)
paper/synth/generate.py           プログラム → STEP → T3と同じ描き方の4面図 (envs/common/bench_views.py)
paper/train/build_openai_jsonl.py OpenAIのchat FT形式 (system / user+画像 / assistant=```submit```), train/val/ood
paper/train/contamination.py      BenchCADとの重複検査 (バイト一致・canary/名前・体積+bboxの近似一致)。通らないと次へ進めない
paper/train/launch_openai_ft.py   既定は dry run。--execute を付けたときだけアップロードとジョブ作成
```

このコンテナで16サンプルのスモークを通した: 16/16生成成功, 重複検査パス (examples 174ファイル・参照形状7個と照合),
dry runで「何もアップロードせず、ジョブも作っていない」ことを確認。

評価側も、偽のMayaサーバー (Mayaの `serve/responses.py` と同じSSEの順序) を相手に
`harness/run.py --model maya/glm-5.3-flash` を examples/task3 で end-to-end に通した:
提出 → 実スコアラーで採点 (箱の提出で0.20), レコードに `provider: maya`, `effort_sent: high`, ローカル時計の設定が残る。
**実機のMaya + GLM-5.3-Flashではまだ動かしていない** (このコンテナにGPUがない)。最初の実機確認が stage 1。

**本番の手順 (ここから先はユーザーの判断):**

```bash
uv run python paper/synth/generate.py --n 2000 --out data/synth_v1 --seed 0
```

```bash
uv run python paper/train/build_openai_jsonl.py data/synth_v1 --out data/ft_v1 --holdout-family ribbed_plate
```

```bash
uv run python paper/train/contamination.py data/synth_v1 data/ft_v1 --benchcad examples --benchcad ~/.cache/benchcad/benchcad-2.0-public --report data/ft_v1/contamination.json
```

```bash
uv run python paper/train/launch_openai_ft.py data/ft_v1 --base-model <画像FT対応のモデルID> --price-per-mtok <その日の単価>
```

最後のコマンドに `--execute` を付けると学習が始まる (課金が発生する)。
**画像付きFTに対応しているモデルIDと単価は日々変わるので、実行当日にOpenAIのファインチューニングガイドで確認すること。**
スクリプトはモデルIDを仮定しない。

FTモデルの評価は、学習後のモデルIDで `--model openai/<ft-model-id>` としてPublicのT1/T3を回す
(ハーネスはOpenAIのResponses API経由で動く。FTモデルがResponses APIとreasoning設定を受け付けるかは事前に要確認)。

## 6. 実行手順 (評価)

```bash
uv sync --group harness --group dev
```

```bash
docker build -t benchcad-sandbox:amd64 sandbox/
```

```bash
paper/eval/run_matrix.sh 0
```

Mayaを起動 (別マシン可) してから:

```bash
export MAYA_BASE_URL=http://<maya-host>:8080/v1 MAYA_CONTEXT_TOKENS=262144 TIER=maya-s
```

```bash
MAYA_DIR=~/project-maya paper/eval/collect_env.sh results/paper/env_maya-s.txt
```

```bash
paper/eval/run_matrix.sh 1
```

Publicを取得 (HFで規約に同意し、`HF_TOKEN` を設定):

```bash
tools/run_core.sh --set public --dry-run
```

```bash
paper/eval/run_matrix.sh 2
```

```bash
OPENROUTER_API_KEY=... paper/eval/run_matrix.sh 2ref
```

## 7. 既知のリスクと未確認事項

- **OpenRouterの提供元:** `z-ai/glm-5.3-flash` はプロバイダ間でルーティングされ、提供元の量子化が分からないことがある。
  ハーネスには提供元を固定する機能がないので、固定するなら追加実装が必要 (OpenRouterの `provider.order`)。
- **画像の扱い:** GLMのビジョンタワーは448px・patch14。ハーネスは1辺最大2000pxで送る。Maya側で何トークンになるかはパイロットで測る (T2/T4/T5は1ラウンド12–20枚)。
- **Mayaの `thinking_budget`:** 既定32768で思考を打ち切る。クラウド版と条件が揃わないので、揃えるか差を明記する。
- **BenchCADのライセンス:** このリポジトリにはLICENSEファイルがない。ハーネスへの改変 (`maya/`) を論文で配布するなら、BenchCADチームに確認するか、upstreamへPRで出すのが筋。
- **Strata:** 今回は対象外。Mayaは「Strata (llama.cppのハイブリッドfork) のfork」なので、比較を足すなら後から同じ `openai_responses_call` 経路で足せる。
