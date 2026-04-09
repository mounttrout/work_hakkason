# VoyageFlow - 実装完了ガイド

## 📋 概要

**VoyageFlow** は、Google Gemini API と Google Maps API を活用した AI旅行プランナーです。
3段階パイプライン（LLM候補生成 → データ構造化 → 移動経路挿入）で、自然言語リクエストから最適な旅程を自動生成します。

---

## 🚀 クイックスタート

### 1️⃣ 環境セットアップ

#### 1.1 Python 環境（Windows）

```bash
# Python 3.9 以上を確認
python --version

# 作業ディレクトリに移動
cd C:\path\to\voyageflow

# 仮想環境を作成（推奨）
python -m venv venv
venv\Scripts\activate

# 依存パッケージをインストール
pip install -r requirements.txt
```

#### 1.2 環境変数設定

`.env` ファイルを作成（`.env.example` をコピーして編集）：

```dotenv
GOOGLE_API_KEY=your_google_api_key_here
MAPS_API_KEY=your_maps_api_key_here
MODEL_NAME=publishers/google/models/gemini-3.1-flash-lite
DEBUG_MODE=False
```

**API キーの取得方法:**
- [Google AI Studio](https://aistudio.google.com) から Gemini API キー取得
- [Google Cloud Console](https://console.cloud.google.com) から Maps API キー取得

### 2️⃣ アプリケーション起動

```bash
# Streamlit アプリを起動
streamlit run app.py
```

自動的にブラウザが開き、`http://localhost:8501` にアクセスされます。

---

## 📁 ファイル構成

```
voyageflow/
├── app.py                              # Streamlit メインアプリ
├── requirements.txt                    # 依存パッケージ
├── .env                               # 環境変数（ユーザーが作成）
├── .env.example                       # 環境変数テンプレート
├── VOYAGEFLOW_SPEC_FINAL.md          # 最終仕様書
│
├── core/
│   ├── llm_client.py                 # Gemini API クライアント
│   ├── prompts.py                    # プロンプトテンプレート集
│   └── json_repair.py                # JSON修復ユーティリティ
│
├── maps/
│   ├── places_api.py                 # Google Places API ラッパー
│   ├── routes_api.py                 # Google Routes API ラッパー
│   └── geo_utils.py                  # 地理計算（未実装）
│
├── orchestration/
│   ├── phase1_generation.py          # フェーズ1: LLM候補生成
│   ├── phase2_structuring.py         # フェーズ2: データ構造化
│   ├── phase3_routing.py             # フェーズ3: 移動経路挿入
│   └── replan_engine.py              # リアルタイム再探索（未実装）
│
└── ui/
    ├── components.py                 # Streamlit UI コンポーネント（未実装）
    └── styles.py                     # カスタムCSS（未実装）
```

---

## 🔄 処理フロー

### フェーズ1: LLM候補生成 (`phase1_generation.py`)

**入力:** ユーザーの自然言語リクエスト
**処理:** Gemini API でフリーテキスト形式の旅行プランを生成
**出力:** テキスト形式の旅行プラン

```
ユーザー: "来週二泊３日の東京旅行の予定を考えて"
  ↓
Gemini（フェーズ1プロンプト）
  ↓
【1日目：4月16日（木）】最新技術と大人の知性
* 09:32：東京駅 到着
  - 目的: 到着
  - 滞在時間: 30分
  - ワンポイント: 北陸新幹線で到着
...
```

### フェーズ2: データ構造化 (`phase2_structuring.py`)

**入力:** フェーズ1の テキスト旅行プラン
**処理:** 
1. Gemini でテキスト → JSON 変換
2. Places API で位置情報を取得
3. Gemini で滞在時間を提案
4. DataFrame に変換

**出力:** 構造化 DataFrame

| day | sequence | start_time | end_time | destination | ... |
|-----|----------|-----------|----------|-------------|-----|
| 1 | 1 | 09:32 | 12:00 | 東京駅 | ... |
| 1 | 2 | 12:00 | 13:30 | 東京ミッドタウン八重洲 | ... |

### フェーズ3: 移動経路挿入 (`phase3_routing.py`)

**入力:** フェーズ2の DataFrame（活動のみ）
**処理:**
1. Gemini で移動手段を判定
2. Routes API で移動時間を計算
3. 移動ステップを DataFrame に挿入
4. タイムスケジュール検証・調整

**出力:** 最終旅程表（活動 + 移動）

| day | sequence | start_time | end_time | destination | purpose | transport_mode |
|-----|----------|-----------|----------|-------------|---------|-----------------|
| 1 | 1 | 09:32 | 12:00 | 東京駅 | arrival | - |
| 1 | 2 | 12:00 | 12:15 | 東京駅 → 東京ミッドタウン | transport | train |
| 1 | 3 | 12:15 | 13:45 | 東京ミッドタウン八重洲 | activity | - |

---

## 🧪 テスト実行方法

### 単体テスト（各モジュール）

```bash
# フェーズ1テスト
python orchestration/phase1_generation.py

# フェーズ2テスト
python orchestration/phase2_structuring.py

# フェーズ3テスト
python orchestration/phase3_routing.py

# Gemini API テスト
python core/llm_client.py

# Places API テスト
python maps/places_api.py

# Routes API テスト
python maps/routes_api.py
```

### 統合テスト（Streamlit）

```bash
# メインアプリを起動
streamlit run app.py

# UI上で以下の流れでテスト:
# 1. 旅行リクエスト入力
# 2. "全フェーズ実行" をクリック
# 3. 各フェーズのタブで結果確認
```

---

## 🎛️ Streamlit UI の使い方

### タブ1: 📝 入力
- **旅行リクエスト**: 自然言語で旅行のリクエストを入力
- **開始日**: 旅行の開始日を選択
- **旅行日数**: 何日間の旅行か指定

**ボタン:**
- 🚀 **フェーズ1実行**: 候補生成のみ実行
- ➡️ **全フェーズ実行**: フェーズ1, 2, 3を順番に実行
- 🔄 **リセット**: 状態をリセット

### タブ2: 🗺️ フェーズ1
- 生成された **テキスト形式の旅行プラン** を表示
- テキストファイルでダウンロード可能

### タブ3: 📊 フェーズ2
- **構造化 DataFrame** を表示
- 活動の数、旅行日数などのメトリクス表示
- CSVでダウンロード可能

### タブ4: 🛣️ フェーズ3
- **最終旅程表** を表示（活動 + 移動ステップ）
- 日別スケジュール表示
- CSVおよび JSONでダウンロード可能

---

## ⚙️ 設定と調整

### サイドバー設定

**Gemini 生成温度** (0.0 - 1.0)
- 低い (0.0): 確定的、安定した出力
- 高い (1.0): 多様性が高い、バリエーション豊か
- デフォルト: 0.7（バランス型）

**デバッグモード**
- オン: エラー詳細を表示
- オフ（デフォルト）: 簡潔なメッセージのみ

---

## 🔧 トラブルシューティング

### エラー: "GOOGLE_API_KEY 環境変数が設定されていません"

**対処:**
1. `.env` ファイルが存在するか確認
2. `GOOGLE_API_KEY=your_key_here` の形式か確認
3. Streamlit を再起動: `Ctrl+C` → `streamlit run app.py`

### エラー: "Places API で候補が見つかりません"

**対処:**
1. 施設名が正しいか確認（例: "江戸東京博物館" など）
2. Google Cloud Console で Places API が有効化されているか確認
3. API 利用制限（APIレベルの制限）を確認

### エラー: "Routes API リクエストエラー"

**対処:**
1. 座標（latitude, longitude）が正しいか確認
2. ネットワーク接続を確認
3. Google Cloud Console で Routes API が有効化されているか確認

### エラー: "JSON修復失敗"

**対処:**
1. Gemini の出力が JSON 形式でない可能性あり
2. `core/json_repair.py` のロジックを改善
3. Gemini のプロンプト温度を下げる（`temperature=0.2`）

### 移動時間が正確でない

**対処:**
1. 座標精度の確認
2. 移動手段の確認（WALK, TRANSIT, DRIVE）
3. 日本国内限定であることを確認

---

## 📊 モック化（オプション）

ハッカソン当日、API がダウンして間に合わない場合、モック関数を用意できます：

### フェーズ1 モック

```python
def generate_trip_plan_mock(user_request: str) -> str:
    return """
【1日目：4月16日（木）】
* 09:32：東京駅 到着
* 12:00：東京ミッドタウン八重洲（90分）
* 14:00：六本木ヒルズ（120分）
"""
```

### フェーズ2 モック

```python
def structure_trip_plan_mock() -> pd.DataFrame:
    data = {
        "day": [1, 1, 1],
        "sequence": [1, 2, 3],
        ...
    }
    return pd.DataFrame(data)
```

### フェーズ3 モック

```python
def insert_routes_mock(df: pd.DataFrame) -> pd.DataFrame:
    # 既に含まれた state を返す
    return df
```

**使用方法:** `orchestration/` 内の各モジュールで、エラー時に `_mock()` 関数を呼び出すようラッピング。

---

## 📈 パフォーマンス最適化

### API 呼び出し削減
- Places API: キャッシング機能を追加（次回リリース）
- Routes API: 事前計算された移動時間テーブル（次回リリース）

### レスポンスタイム改善
- 並列処理：複数の Places API クエリを同時実行
- ストリーミング：Gemini の出力をストリーム表示

---

## 🚧 次のステップ（Future Features）

### Phase 2: リアルタイム再探索
- GPS トラッキング
- リアルタイム気象連携
- 遅延時の自動再提案

### Phase 3: UI強化
- マップ可視化（Folium）
- 編集UI（旅程の手動調整）
- 予約連携（Hotels.com, Tabelog 等）

### Phase 4: ユーザープロファイリング
- 旅行嗜好の学習
- パーソナライズされたレコメンド
- グループ旅行対応

---

## 📞 サポート

問題が発生した場合：
1. ログを確認（デバッグモード有効化）
2. API キーが正しいか再確認
3. 環境変数をリロード（Streamlit 再起動）
4. GitHub Issues（予定）で報告

---

## 📄 ライセンス

MIT License

---

## 🙏 謝辞

- Google Gemini API
- Google Maps Platform
- Streamlit
- Python コミュニティ

---

**VoyageFlow v1.0 - Happy Travels! ✈️**
