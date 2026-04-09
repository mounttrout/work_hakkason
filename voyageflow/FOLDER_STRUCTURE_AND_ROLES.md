# 📁 VoyageFlow フォルダ構成とファイル役割

## 🗂️ フォルダツリー構造

```
voyageflow/                              # ルートディレクトリ
│
├── 📄 ドキュメント
│   ├── README.md                       # クイックスタート＆トラブルシューティング
│   ├── VOYAGEFLOW_SPEC_FINAL.md        # 最終技術仕様書（詳細設計）
│   └── IMPLEMENTATION_CHECKLIST.md     # 実装完了チェックリスト
│
├── ⚙️ 設定ファイル
│   ├── requirements.txt                # Python依存パッケージリスト
│   └── .env.example                   # 環境変数テンプレート（Google APIキー設定用）
│
├── 🎨 メインアプリ
│   └── app.py                          # Streamlit UIアプリ（統合エントリーポイント）
│
├── 🧠 core/                             # LLM・プロンプト・JSON修復モジュール
│   ├── __init__.py                    # Pythonパッケージ初期化（自動作成可）
│   ├── llm_client.py                  # Gemini API クライアント
│   ├── prompts.py                     # プロンプトテンプレート（3フェーズ対応）
│   └── json_repair.py                 # JSON修復＆クリーニングロジック
│
├── 🗺️ maps/                             # Google Maps API ラッパーモジュール
│   ├── __init__.py                    # Pythonパッケージ初期化（自動作成可）
│   ├── places_api.py                  # Google Places API（施設検索・詳細取得）
│   └── routes_api.py                  # Google Routes API（経路・移動時間計算）
│
└── 🔄 orchestration/                    # 3段階パイプラインオーケストレーション
    ├── __init__.py                    # Pythonパッケージ初期化（自動作成可）
    ├── phase1_generation.py           # フェーズ1: LLM候補生成
    ├── phase2_structuring.py          # フェーズ2: データ構造化
    └── phase3_routing.py              # フェーズ3: 移動経路挿入
```

---

## 📋 ファイル詳細一覧

### 🔵 ルートレベルファイル（メインアプリ＆設定）

| ファイル名 | 用途 | 役割 | サイズ |
|----------|------|------|--------|
| **app.py** | Streamlit UI | ユーザーインターフェース・各フェーズの統合実行エントリーポイント | 12.4 KB |
| **requirements.txt** | 依存管理 | プロジェクト実行に必要なPythonパッケージリスト | 139 B |
| **.env.example** | 設定テンプレート | 環境変数設定のテンプレート（ユーザーが`.env`にコピーして編集） | 377 B |

---

### 📚 ドキュメントファイル

| ファイル名 | 用途 | 役割 | サイズ |
|----------|------|------|--------|
| **README.md** | ユーザーガイド | クイックスタート、トラブルシューティング、API設定方法 | 10.3 KB |
| **VOYAGEFLOW_SPEC_FINAL.md** | 技術仕様書 | システムアーキテクチャ、データフロー、3フェーズの詳細設計 | 12.2 KB |
| **IMPLEMENTATION_CHECKLIST.md** | 実装完了記録 | 実装状況、パフォーマンス統計、テスト結果 | 8.8 KB |

---

### 🧠 core/ モジュール（LLM・プロンプト・JSON）

#### `llm_client.py` | **Gemini API クライアント**
```
役割: Google Gemini API との通信を統一的に管理
機能:
  ✓ generate_text()      → フリーテキスト生成（フェーズ1用）
  ✓ generate_json()      → JSON形式生成（構造化データ用）
  ✓ generate_choice()    → 選択肢判定（移動手段判定用）
  ✓ エラーハンドリング   → API レスポンス処理・リトライ
```

#### `prompts.py` | **プロンプトテンプレート集**
```
役割: 3フェーズのプロンプトを一元管理
クラス:
  ├─ PromptTemplates      → 各フェーズのプロンプト定義
  │   ├─ PHASE1_TRIP_GENERATION        → フェーズ1: 旅行プラン生成
  │   ├─ PHASE2_EXTRACT_FIELDS         → フェーズ2: JSON抽出
  │   ├─ PHASE2_STAY_DURATION          → フェーズ2: 滞在時間提案
  │   ├─ PHASE3_TRANSPORT_MODE         → フェーズ3: 移動手段判定
  │   └─ REPLAN_REAL_TIME              → リアルタイム再探索
  │
  └─ PromptBuilder        → プロンプト組み立てヘルパー
      ├─ build_phase1()
      ├─ build_phase2_json()
      ├─ build_phase3_transport()
      └─ build_replan()
```

#### `json_repair.py` | **JSON修復ロジック**
```
役割: Gemini出力の不完全なJSON形式を修復
機能:
  ✓ repair_json_string()   → JSON修復＆パース
  ✓ repair_json_array()    → JSON配列修復
  ✓ マークダウン囲い除去    → ```json...``` 形式を除去
  ✓ シングルクォート変換    → '...' を "..." に
  ✓ 末尾カンマ除去         → 不正なカンマを削除
  ✓ 括弧不完全修復         → 未閉じ括弧を自動補正
```

---

### 🗺️ maps/ モジュール（Google Maps API）

#### `places_api.py` | **Google Places API ラッパー**
```
役割: 施設検索・詳細情報取得の統一インターフェース
クラス: PlacesAPI
機能:
  ✓ search_text()         → 施設名で検索（例: "江戸東京博物館"）
  ✓ get_place_details()   → 詳細情報取得（営業時間・評価など）
  ✓ autocomplete_query()  → 入力補完候補
  ✓ format_place_result() → 検索結果をテキスト形式で表示

戻り値: place_id, 緯度経度, 住所, 営業時間, 評価
```

#### `routes_api.py` | **Google Routes API ラッパー**
```
役割: 経路計算・移動時間取得の統一インターフェース
クラス: RoutesAPI
機能:
  ✓ compute_route()       → 2点間の最短経路＆移動時間を計算
  ✓ compute_distance()    → 直線距離計算（ハバーサイン公式）
  ✓ format_route_result() → 経路情報を人間が読みやすい形式に

対応移動手段: walk（徒歩）, train（電車）, car（車）, taxi（タクシー）, bike（自転車）
```

---

### 🔄 orchestration/ モジュール（3段階パイプライン）

#### `phase1_generation.py` | **フェーズ1: LLM候補生成**
```
役割: ユーザーリクエスト → テキスト形式の旅行プラン生成
クラス: Phase1Generator
メソッド:
  generate_trip_plan(user_request, temperature)
    入力: "来週二泊３日の東京旅行"
    処理: Gemini API（フェーズ1プロンプト）
    出力: テキスト形式の詳細旅行プラン
         【1日目】【2日目】...

処理時間: 10-15秒
```

#### `phase2_structuring.py` | **フェーズ2: データ構造化**
```
役割: テキストプラン → 構造化 DataFrame（活動のみ）
クラス: Phase2Structuring
メソッド:
  structure_trip_plan(travel_plan, start_date)
    入力: フェーズ1のテキストプラン
    処理: 4つのステップ
      1️⃣ Gemini でテキスト → JSON 変換
      2️⃣ Places API で位置情報を取得
      3️⃣ Gemini で滞在時間を提案
      4️⃣ DataFrame に変換
    出力: 構造化 DataFrame
         day, sequence, start_time, end_time, destination, purpose,
         genre, one_point, latitude, longitude, ...

処理時間: 30-45秒
DataFrame カラム:
  - day: 旅行の日数（1, 2, 3...）
  - sequence: その日の順番
  - start_time/end_time: HH:MM形式
  - destination: 目的地名
  - latitude/longitude: Google Places から取得
  - opening_hours: 営業時間
```

#### `phase3_routing.py` | **フェーズ3: 移動経路挿入**
```
役割: 構造化 DataFrame（活動のみ） → 最終旅程表（活動＋移動ステップ）
クラス: Phase3Routing
メソッド:
  insert_routes(df, region)
    入力: フェーズ2の DataFrame
    処理: 3つのステップ
      1️⃣ Gemini で移動手段を判定（距離＆時間ベース）
      2️⃣ Routes API で移動時間を取得
      3️⃣ 移動ステップを DataFrame に挿入
      4️⃣ タイムスケジュール検証・調整
    出力: 最終旅程表（活動＋移動）
         purpose="transport" のステップが追加されたもの

処理時間: 20-35秒

移動手段判定ロジック:
  - 距離 < 2km      → walk（徒歩）
  - 距離 2-15km     → train（電車）
  - 距離 > 15km     → car/taxi（車・タクシー）
```

---

## 🔗 ファイル間の依存関係

```
┌─────────────────────────────────────────────────────────┐
│                    app.py (Streamlit UI)                │
│              ユーザーインターフェース・統合実行            │
└──────────────────┬──────────────────────────────────────┘
                   │
        ┌──────────┼──────────┐
        │          │          │
        ▼          ▼          ▼
 ┌────────────┐ ┌────────────┐ ┌────────────┐
 │ phase1_    │ │ phase2_    │ │ phase3_    │
 │generation  │ │structuring │ │routing     │
 │            │ │            │ │            │
 │フェーズ1    │ │フェーズ2    │ │フェーズ3    │
 └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
       │              │              │
       ▼              ▼              ▼
  llm_client    llm_client       llm_client
   + prompts     + prompts        + prompts
  (テキスト)    (JSON化)      (移動手段判定)
       │              │              │
       │              ├─────────┬────┘
       │              ▼         ▼
       │        places_api  routes_api
       │        (位置情報)  (移動時間)
       │              │         │
       └──────────────┴─────────┘
                │
                ▼
           json_repair
           (JSON修復)
```

---

## 📊 ファイルの役割分類

### 🎯 エントリーポイント
- **app.py** - Streamlit が最初に実行するメインファイル

### 🔌 コア機能モジュール
- **core/** - LLM・プロンプト・JSON修復
- **maps/** - Google Maps API ラッパー
- **orchestration/** - 3段階パイプライン

### 📖 ドキュメント＆設定
- **README.md** - ユーザーガイド
- **.env.example** - 環境変数設定
- **requirements.txt** - 依存パッケージ

---

## 📈 ファイルサイズと複雑度

| ファイル | サイズ | 行数 | 複雑度 |
|---------|-------|------|--------|
| app.py | 12.4 KB | 280 | 中 |
| core/llm_client.py | 6.1 KB | 150 | 低 |
| core/prompts.py | 9.8 KB | 250 | 低 |
| core/json_repair.py | 7.6 KB | 200 | 中 |
| maps/places_api.py | 8.9 KB | 220 | 低 |
| maps/routes_api.py | 7.8 KB | 200 | 中 |
| orchestration/phase1_generation.py | 2.4 KB | 60 | 低 |
| orchestration/phase2_structuring.py | 11.9 KB | 320 | 高 |
| orchestration/phase3_routing.py | 11.3 KB | 310 | 高 |
| **合計** | **77.2 KB** | **1990** | - |

---

## 🔄 データフロー（各フェーズでのファイル使用）

### フェーズ1: LLM候補生成
```
ユーザー入力
    ↓
app.py (UI入力)
    ↓
phase1_generation.py
    ↓
llm_client.py
    ↓
prompts.py (PHASE1_TRIP_GENERATION)
    ↓
Gemini API
    ↓
テキスト形式の旅行プラン
```

### フェーズ2: データ構造化
```
フェーズ1の出力（テキスト）
    ↓
phase2_structuring.py
    ├─ llm_client.py (generate_json)
    ├─ prompts.py (PHASE2_EXTRACT_FIELDS)
    ├─ json_repair.py (修復)
    ├─ places_api.py (位置情報取得)
    ├─ llm_client.py (generate_json)
    └─ prompts.py (PHASE2_STAY_DURATION)
    ↓
構造化 DataFrame（活動のみ）
```

### フェーズ3: 移動経路挿入
```
フェーズ2の出力（DataFrame）
    ↓
phase3_routing.py
    ├─ llm_client.py (generate_json)
    ├─ prompts.py (PHASE3_TRANSPORT_MODE)
    ├─ routes_api.py (compute_route)
    ├─ JSON修復（エラー時）
    └─ DataFrame マージ
    ↓
最終旅程表（活動 + 移動ステップ）
```

---

## 🧪 単体テスト対応

各ファイルの末尾に `if __name__ == "__main__":` テストが存在：

```bash
# 各モジュールを単独で実行可能
python core/llm_client.py          # Gemini API テスト
python maps/places_api.py          # Places API テスト
python maps/routes_api.py          # Routes API テスト
python orchestration/phase1_generation.py  # フェーズ1テスト
python orchestration/phase2_structuring.py # フェーズ2テスト
python orchestration/phase3_routing.py     # フェーズ3テスト
```

---

## ⚠️ 重要なファイル

### 🔑 必須設定ファイル
- **.env** - Google API キー設定
  ```
  GOOGLE_API_KEY=xxx
  MAPS_API_KEY=xxx
  ```

### 🚀 起動ファイル
- **app.py** - Streamlit メインアプリ
  ```bash
  streamlit run app.py
  ```

### 📦 依存管理
- **requirements.txt** - パッケージインストール
  ```bash
  pip install -r requirements.txt
  ```

---

## 💡 ファイル役割サマリー

| ファイル | 目的 | 使用タイミング |
|---------|------|-----------------|
| app.py | ユーザーUI | 常に（エントリーポイント） |
| llm_client.py | LLM通信 | 全フェーズ |
| prompts.py | プロンプト管理 | 全フェーズ |
| json_repair.py | JSON修復 | フェーズ2, 3 |
| places_api.py | 施設検索 | フェーズ2 |
| routes_api.py | 経路計算 | フェーズ3 |
| phase1_generation.py | テキスト生成 | フェーズ1 |
| phase2_structuring.py | データ構造化 | フェーズ2 |
| phase3_routing.py | 経路挿入 | フェーズ3 |

---

## 📝 コード編集時のポイント

### 新しい機能を追加する場合
1. **プロンプト追加** → `core/prompts.py`
2. **API呼び出し追加** → `maps/places_api.py` または `maps/routes_api.py`
3. **フェーズ追加** → `orchestration/phase*_*.py`
4. **UI更新** → `app.py`

### エラーハンドリング改善
1. **JSON 修復** → `core/json_repair.py`
2. **API エラー** → `maps/places_api.py`, `maps/routes_api.py`
3. **LLM エラー** → `core/llm_client.py`

### デバッグ方法
1. **単体テスト実行** → 各ファイルの `if __name__ == "__main__":`
2. **Streamlit デバッグ** → サイドバーの「デバッグモード」チェック
3. **ログ出力** → 各 `print(f"...")` を追加

---

## 🎯 ファイル構成のベストプラクティス

✅ **現在の構成が採用している良い点:**
- モジュール化 → 機能ごとに分離
- 単一責任原則 → 各ファイルが1つの役割
- テスト対応 → 各モジュール単体テスト可能
- ドキュメント完備 → README, 仕様書, チェックリスト
- エラーハンドリング → 例外処理が充実

✅ **拡張しやすい設計:**
- プロンプトは一元管理 → `prompts.py`
- API ラッパーが独立 → `maps/` 新機能追加が容易
- オーケストレーション層 → `orchestration/` フェーズ追加が容易

---

**これで VoyageFlow の全体構成が理解できます！** 🎓
