# 🎬 VoyageFlow v2.0 - 実行シミュレーション実装ガイド

## 📋 概要

VoyageFlow に **旅程実行シミュレーション機能** を追加します。

従来の Phase 1-3（旅程生成）に加えて、**リアルタイムイベント対応** の可視化ができるようになります。

---

## 🎯 できるようになること

| 操作 | 結果 |
|-----|------|
| **✅ 予定通り進む** | 次のステップに進む |
| **⏰ 遅延発生** | Gemini が遅延を吸収する代替案を生成 |
| **🌧️ 天候変化** | 屋内活動への変更案を提案 |
| **💭 気分が変わった** | ユーザーの気分に合わせた代替案を提案 |
| **📊 進捗表示** | リアルタイムで旅程表が更新 |

---

## 🔧 実装手順

### Step 1: 新しいファイルを追加

```
voyageflow/
├── orchestration/
│   ├── phase1_generation.py      ✅ 既存
│   ├── phase2_structuring.py     ✅ 既存
│   ├── phase3_routing.py         ✅ 既存
│   └── execution_engine.py       🆕 新規追加 ← ここ！
└── app.py                         🔄 修正
```

**ファイル配置:**
1. `orchestration_execution_engine.py` を `voyageflow/orchestration/execution_engine.py` に保存

### Step 2: app.py を置き換え

現在の `app.py` を以下に置き換えます：
- ファイル: `app_with_execution_simulator.py`
- 保存先: `voyageflow/app.py`

### Step 3: 動作確認

```bash
# 依存パッケージをインストール（既に済みのはず）
pip install -r requirements.txt

# Streamlit を起動
streamlit run app.py
```

---

## 📊 ファイル構成の変更

### 変更前（Phase 1）
```
voyageflow/
├── app.py                        # 4つのタブ
├── orchestration/
│   ├── phase1_generation.py
│   ├── phase2_structuring.py
│   └── phase3_routing.py
└── ...
```

### 変更後（Phase 1.5）
```
voyageflow/
├── app.py                        # 5つのタブ（新規: 実行シミュレーション）
├── orchestration/
│   ├── phase1_generation.py
│   ├── phase2_structuring.py
│   ├── phase3_routing.py
│   └── execution_engine.py       # 🆕 新規
└── ...
```

---

## 🎮 UI フロー

```
【タブ1: 入力】
  旅行リクエスト入力
    ↓
【タブ2: フェーズ1】
  テキスト形式の旅行プラン生成
    ↓
【タブ3: フェーズ2】
  構造化 DataFrame（活動のみ）
    ↓
【タブ4: フェーズ3】
  最終旅程表（活動 + 移動）
    ↓
【タブ5: 実行シミュレーション】 🆕
  ┌─ ✅ 予定通り進む
  ├─ ⏰ 遅延発生
  ├─ 🌧️ 天候変化
  ├─ 💭 気分が変わった
  └─ 📋 進捗状況リアルタイム表示
```

---

## 🔄 ExecutionEngine の主要メソッド

### 初期化
```python
from orchestration.execution_engine import ExecutionEngine

engine = ExecutionEngine(df_phase3)
```

### 実行開始
```python
result = engine.start_execution()
# 結果: {"status": "started", "message": "旅程実行を開始しました", ...}
```

### ステップ進行
```python
result = engine.proceed_to_next_step()
# 結果: {"status": "proceeding", "current_step": 1, ...}
```

### イベント発生（遅延例）
```python
result = engine.trigger_event("delay", "15")
# 結果: 
# {
#   "status": "event_triggered",
#   "message": "⏰ 15分の遅延を検知しました",
#   "alternative_plans": [
#     {"id": 1, "title": "案1", "description": "...", ...},
#     ...
#   ]
# }
```

### 代替案の適用
```python
result = engine.apply_alternative(1)
# 結果: {"status": "alternative_applied", "message": "代替案 1 を適用しました"}
```

### 現在状態の取得
```python
status = engine.get_current_status()
# 結果:
# {
#   "current_step": 3,
#   "total_steps": 24,
#   "progress_percentage": 12.5,
#   "current_destination": "大阪城公園",
#   ...
# }
```

---

## 📝 Streamlit セッション状態の管理

app.py では以下のセッション状態を管理しています：

```python
# 基本状態
st.session_state.trip_plan          # フェーズ1出力
st.session_state.df_phase2          # フェーズ2出力
st.session_state.df_phase3          # フェーズ3出力

# 実行シミュレーション状態
st.session_state.execution_engine   # ExecutionEngine インスタンス
st.session_state.show_delay_dialog  # 遅延ダイアログの表示状態
st.session_state.show_weather_dialog # 天候ダイアログの表示状態
st.session_state.show_mood_dialog   # 気分ダイアログの表示状態
st.session_state.event_result       # イベント処理の結果
```

---

## 🎬 実行シミュレーションのシーンフロー

### シーン1: 基本的な進行

```
🚀 旅程実行を開始
  ↓
✅ 予定通り進む（ボタン）→ ステップ1
  ↓
✅ 予定通り進む（ボタン）→ ステップ2
  ↓
✅ 予定通り進む（ボタン）→ ステップ3
  ↓
... 繰り返し ...
  ↓
🎉 旅程完了！
```

### シーン2: イベント対応

```
ステップ5 を実行中
  ↓
⏰ 遅延発生（ボタン）→ 「15分遅延」を入力
  ↓
🎬 Gemini が代替案を生成
  - 案1: 次のステップを15分短縮
  - 案2: スポットを1つ飛ばす
  - 案3: スケジュール全体をリバランス
  ↓
ユーザーが「案1」を選択
  ↓
代替案が適用される
  ↓
✅ 予定通り進む → ステップ6へ
```

---

## 🧪 テスト方法

### 単体テスト（ExecutionEngine）

```bash
python orchestration/execution_engine.py
```

期待される出力：
```
============================================================
🧪 ExecutionEngine テスト
============================================================

✓ テスト1: 実行開始
  旅程実行を開始しました
  現在地: 駅

✓ テスト2: 次のステップに進む
  ステップ 2 に進みました

✓ テスト3: 遅延イベント
  ⏰ 15分の遅延を検知しました
  代替案数: 3

✓ テスト4: 現在の状態
  進捗: 12%
  イベント数: 1

============================================================
✅ テスト完了
============================================================
```

### UI テスト（Streamlit）

```bash
streamlit run app.py
```

操作フロー：
1. タブ1で旅行リクエストを入力
2. 「全フェーズ実行」をクリック
3. タブ2-4で生成過程を確認
4. タブ5「🎬 実行シミュレーション」に遷移
5. 「🚀 旅程実行を開始」をクリック
6. 各ステップで「✅ 予定通り進む」や「⏰ 遅延発生」ボタンを試す

---

## 📊 ハッカソン本番でのデモシーン

### デモシナリオ

```
1️⃣ 旅程生成フェーズ（Phase 1-3）
   「大阪3日間の旅」のリクエストを入力
   → 24ステップの最終旅程表が自動生成

2️⃣ 実行シミュレーションフェーズ
   タブ5に移動
   → 「旅程実行を開始」
   
3️⃣ イベント対応デモ
   Day 1 のステップ3（移動中）で
   → 「遅延発生」ボタン → 15分遅延を入力
   → Gemini が 3つの代替案を自動生成
   → ユーザーが「案1」を選択
   → 旅程表がリアルタイム更新
   
4️⃣ 続行
   「予定通り進む」ボタンで ステップ4へ
   → Day 2 でも同様にイベント対応デモ
   
5️⃣ 完了
   全ステップを進めて「🎉 旅程完了！」
```

**説明ポイント:**
- "LLM（Gemini）が旅程を **動的に最適化** しています"
- "単なるスケジュール管理ではなく、**リアルタイム再探索** を実現"
- "ユーザーの操作（遅延、天候など）に対応して **自動的に代替案を生成**"

---

## 🚨 トラブルシューティング

### エラー: "ExecutionEngine not found"
```
→ orchestration/execution_engine.py が正しい位置にあるか確認
→ orchestration/__init__.py が存在するか確認
```

### エラー: "phase3 データがない"
```
→ 先にタブ1-4で全フェーズを実行してから、タブ5にアクセス
```

### Gemini API エラーが出る場合
```
→ .env ファイルで GOOGLE_API_KEY と MODEL_NAME を確認
→ モデル名は models/gemini-3.1-flash-lite-preview の形式か確認
```

### UI がリアルタイム更新されない
```
→ Streamlit のセッション状態がリセットされていないか確認
→ st.rerun() が呼ばれているか確認
```

---

## 📈 今後の拡張案

| 機能 | 説明 | 難易度 |
|-----|------|--------|
| **GPS トラッキング** | ユーザーの実際の位置を取得 | 中 |
| **外部気象API連携** | 実際の気象データを取得 | 中 |
| **マップ可視化** | Folium で旅程をマップに表示 | 中 |
| **通知機能** | 次のステップが近づいたら通知 | 低 |
| **記念撮影モード** | ステップで記念写真を保存 | 中 |

---

## ✅ チェックリスト

実装完了時に確認してください：

- [ ] `orchestration/execution_engine.py` が voyageflow フォルダに存在
- [ ] `app.py` が修正版に置き換わっている
- [ ] `streamlit run app.py` で UI が起動する
- [ ] タブ5「🎬 実行シミュレーション」が表示される
- [ ] 「🚀 旅程実行を開始」ボタンがクリックできる
- [ ] イベントボタン（遅延、天候など）が機能する
- [ ] 代替案が Gemini から生成されている
- [ ] 代替案選択で旅程表が更新される
- [ ] イベントログが記録されている

---

## 🎉 完成！

これで VoyageFlow v2.0 - **実行シミュレーション対応** の実装が完了です！

ハッカソン本番でこのデモを見せることで、単なる「旅程生成」ではなく、**「動的なリアルタイム対応」** の価値を演出できます。

**頑張ってください！** ✈️
