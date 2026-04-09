# VoyageFlow 3段階パイプライン仕様書（最終版）

## 概要
**「LLM候補生成 → Python グルーピング/構造化 → LLM スケジューリング/再探索」**の3段階アーキテクチャで、旅行計画を動的に生成・最適化します。

---

## フェーズ1: LLM候補生成（Gemini フリーテキスト出力）

### 入力
- **ユーザー入力**: 自然言語での旅行リクエスト
  ```
  例: "来週二泊３日の東京旅行の予定を考えて"
  ```

### 処理
- Gemini API を呼び出し、**制約なしのフリーテキスト**で旅行プランを生成
- 具体的な日時、場所名、滞在時間、理由（ワンポイント）を含める

### 出力形式
```
【1日目：4月16日（木）】
* 09:32：東京駅 到着
* 午後：テクノロジー・アート体験（港区エリア）
  - ザ・プリンス パークタワー東京にて開催の「Oracle AI World Tour Tokyo」
  - 滞在時間: 2時間
  - 理由: エンジニアとしての視点で最新のAIトレンドを肌で感じられる貴重な機会
* 夜：美食のひととき
  - 銀座・丸の内エリア → 銀座うかい亭でディナー
  - 滞在時間: 1.5時間
```

---

## フェーズ2: データ構造化（Python グルーピング → JSON/DataFrame）

### 入力
- フェーズ1の Gemini フリーテキスト出力

### 処理

#### ステップ 2.1: テキスト解析 & 候補抽出
- Gemini に「このテキストから以下の情報を構造化してJSON形式で返せ」と再度プロンプト
- JSON修復ロジック（既存の `json_repair.py`）を使用して形式を整える

#### ステップ 2.2: Places API 統合
各候補について、**Places API で以下を取得**：
- `place_id`: 一意な識別子
- `latitude`, `longitude`: 緯度経度
- `formatted_address`: 住所
- `opening_hours`: 営業時間
- `rating`, `user_ratings_total`: 評価情報

**見つからない場合**: 
- Gemini に「代替候補を提案してください」と再問い合わせ
- または、ユーザーに「〇〇は見つかりませんでした。別のスポットを選びますか？」と通知

#### ステップ 2.3: 滞在時間決定
- Places API のデータ（Google Maps での類似施設の平均滞在時間）を参考に
- Gemini に「このスポット（ジャンル: 美術館）の推奨滞在時間は？」と問い合わせ
- Gemini の提案を使用（ユーザーは後で手動調整可）

### 出力: DataFrame スキーマ

| カラム名 | 型 | 説明 | 例 |
|---------|-----|------|------|
| `day` | int | 旅行の日数（1, 2, 3...） | 1 |
| `sequence` | int | その日の順番 | 1 |
| `start_time` | str | 開始時刻（HH:MM） | "09:32" |
| `end_time` | str | 終了時刻（HH:MM） | "12:00" |
| `duration_minutes` | int | 滞在時間（分） | 150 |
| `destination` | str | 目的地名 | "東京駅" |
| `purpose` | str | 目的（activity, meal, transport等） | "arrival" |
| `genre` | str | ジャンル（museum, restaurant, station等） | "station" |
| `one_point` | str | ワンポイント（理由・説明） | "北陸新幹線で到着" |
| `place_id` | str | Google Places ID | "ChIJ0Z..." |
| `latitude` | float | 緯度 | 35.6762 |
| `longitude` | float | 経度 | 139.7674 |
| `address` | str | 住所 | "東京都千代田区丸の内..." |
| `opening_hours` | str | 営業時間 | "6:00-23:00" |
| `type_suggestion` | str | スポットタイプ（transport_station, museum等） | "transit_station" |
| `rating` | float | Google評価 | 4.6 |
| `is_transport` | bool | 移動フェーズか否か | False |
| `next_destination` | str | 次の目的地（移動フェーズ用） | "六本木ヒルズ" |
| `transport_mode` | str | 移動手段（walk, train, car, taxi等） | null（後続フェーズで決定） |

### 出力例（JSON）
```json
{
  "trip_id": "tokyo_2026_04_16",
  "start_date": "2026-04-16",
  "end_date": "2026-04-18",
  "itinerary": [
    {
      "day": 1,
      "sequence": 1,
      "start_time": "09:32",
      "end_time": "12:00",
      "duration_minutes": 150,
      "destination": "東京駅",
      "purpose": "arrival",
      "genre": "station",
      "one_point": "北陸新幹線で到着",
      "place_id": "ChIJIQHpxozZTIARNV_2-7c-5H0",
      "latitude": 35.6762,
      "longitude": 139.7674,
      "address": "東京都千代田区丸の内1-9-1",
      "opening_hours": "6:00-23:00",
      "rating": 4.6,
      "is_transport": false,
      "transport_mode": null
    },
    {
      "day": 1,
      "sequence": 2,
      "start_time": "12:00",
      "end_time": "14:30",
      "duration_minutes": 150,
      "destination": "東京ミッドタウン八重洲",
      "purpose": "activity",
      "genre": "shopping",
      "one_point": "最新の商業空間をチェック",
      "place_id": "ChIJ...",
      "latitude": 35.6788,
      "longitude": 139.7696,
      "address": "東京都中央区八重洲2-1-1",
      "opening_hours": "10:00-21:00",
      "rating": 4.3,
      "is_transport": false,
      "transport_mode": null
    }
  ]
}
```

---

## フェーズ3: 移動経路挿入 & スケジューリング

### 入力
- フェーズ2の構造化 DataFrame
- ユーザーの移動手段選択（または Gemini の判定）

### 処理

#### ステップ 3.1: 移動手段の判定
**Gemini に以下を判定させ**：
```
「地点A（緯度: 35.67, 経度: 139.76）から地点B（緯度: 35.68, 経度: 139.77）へ移動する場合、
最適な移動手段は何か？（徒歩、電車、車、タクシー）理由も含めて返してください。」
```

**結果を使用して** `transport_mode` を決定
- **段階的実装**: 最初は単純ルール（距離 < 2km で徒歩、それ以上は電車/車）から始め、Gemini判定に移行

#### ステップ 3.2: Routes API で移動時間を取得
```
departure_time: start_time（前の活動の end_time）
origin: (前の location lat/lng)
destination: (次の location lat/lng)
mode: transport_mode
```

**結果**:
- `travel_duration_seconds`: 実際の移動時間
- `departure_time`: 出発時刻
- `arrival_time`: 到着時刻

#### ステップ 3.3: タイムスケジュール検証 & 調整
**ロジック**:
1. `前の活動の end_time` + `移動時間` = `この活動の start_time` か確認
2. **ズレがある場合**:
   - 移動時間が予定を超過 → Gemini に「滞在時間を短縮するか、スポットを飛ばすか提案」を依頼
   - 移動時間が予定より短い → 終了時刻を前倒しするか、そのまま保持（ユーザー選択）

#### ステップ 3.4: 移動ステップの挿入
移動フェーズを DataFrame に新規行として挿入：
```json
{
  "day": 1,
  "sequence": 1.5,
  "start_time": "12:00",
  "end_time": "12:15",
  "duration_minutes": 15,
  "destination": "東京駅 → 東京ミッドタウン八重洲",
  "purpose": "transport",
  "genre": "transit",
  "one_point": "電車で移動",
  "is_transport": true,
  "transport_mode": "train",
  "travel_duration_seconds": 900
}
```

### 出力
```json
{
  "trip_id": "tokyo_2026_04_16",
  "start_date": "2026-04-16",
  "end_date": "2026-04-18",
  "itinerary_with_transport": [
    // フェーズ2の活動 + フェーズ3の移動ステップがマージされたもの
  ],
  "validation_warnings": [
    {
      "day": 1,
      "message": "移動時間が延長したため、ザ・プリンスの滞在時間を15分短縮しました。"
    }
  ]
}
```

---

## 実行時リアルタイム再探索機能（フェーズ 3.5）

### トリガー
- ユーザーが「旅行開始」ボタンを押した後
- 定期的に（例：5分ごと）以下を監視：
  1. 現在位置（GPS or ユーザー入力）
  2. Routes API の最新 ETA
  3. ユーザーチャット入力（「疲れた」「別に行きたい」など）
  4. 外部気象API との連携（降雨など）

### 遅延検知ロジック
```
if (current_time > expected_arrival_time + 15min):
    trigger_replan()
```

### Gemini への再探索プロンプト
```
「現在時刻: 14:45（予定より15分遅延）
現在位置: 東京駅付近
残り予定: 
  - 14:30-16:00: 六本木ヒルズ(2時間)
  - 16:30-18:00: 銀座うかい亭(1.5時間)
  
遅延を吸収する案を3つ提案してください:
1. 滞在時間を短縮する案
2. スポットを飛ばす案
3. 順番を変える案
」
```

### ユーザー選択 → 実行
- UI で提案を表示
- ユーザーが選択 → DataFrame 更新 → Routes API 再取得

---

## データフロー図

```
ユーザー入力（自然言語）
    ↓
【フェーズ1】Gemini（フリーテキスト生成）
    ↓
フリーテキスト旅行プラン
    ↓
【フェーズ2】テキスト解析 → Gemini JSON化 → JSON修復 → Places API統合 → Gemini 滞在時間提案
    ↓
構造化 DataFrame（活動のみ）
    ↓
【フェーズ3】Gemini 移動手段判定 → Routes API → タイムスケジュール検証 → 移動ステップ挿入
    ↓
最終旅程表（活動 + 移動）
    ↓
Streamlit UIで表示 / JSON出力
    ↓
【実行時】ユーザーが「開始」
    ↓
リアルタイム監視 → 遅延検知 → Gemini 再提案 → ユーザー選択 → 更新
```

---

## エラーハンドリング

| エラーケース | 対応 |
|----------|------|
| Places API で候補が見つからない | Gemini に代替候補を再提案させる |
| Routes API がタイムアウト | デフォルト値（距離/平均速度）で推定 |
| Gemini JSON出力が不正 | `json_repair.py`で修復 |
| 滞在時間が営業時間を超過 | ユーザーに警告 + Gemini に調整提案 |
| 合計所要時間が1日の限界を超過 | Gemini に「スポット削減案」を提案 |

---

## 実装優先度

### Phase 1（本実装）
- [ ] フェーズ1: Gemini フリーテキスト生成
- [ ] フェーズ2: テキスト解析 + JSON化 + Places API統合 + DataFrame生成
- [ ] フェーズ3: Gemini 移動手段判定 + Routes API + タイムスケジュール検証 + 移動ステップ挿入
- [ ] Streamlit UI: 最終旅程表の表示

### Phase 2（次回以降）
- [ ] リアルタイム再探索機能
- [ ] 外部気象API連携
- [ ] ユーザープリファレンス保存
- [ ] マップ可視化（Folium or Google Maps Embed）

---

## 環境変数（.env）

```dotenv
GOOGLE_API_KEY=your_google_api_key_here
MAPS_API_KEY=your_maps_api_key_here
MODEL_NAME=publishers/google/models/gemini-3.1-flash-lite
GOOGLE_APPLICATION_CREDENTIALS=path_to_service_account_json
```

---

## ファイル構成（予定）

```
voyageflow/
├── app.py                       # Streamlit メインアプリ
├── .env                         # 環境変数
├── requirements.txt             # 依存パッケージ
├── core/
│   ├── llm_client.py           # Gemini API クライアント
│   ├── json_repair.py          # JSON修復ロジック（既存）
│   └── prompts.py              # 各フェーズのプロンプトテンプレート
├── maps/
│   ├── places_api.py           # Places API ラッパー
│   ├── routes_api.py           # Routes API ラッパー
│   └── geo_utils.py            # 座標計算など
├── orchestration/
│   ├── phase1_generation.py    # フェーズ1: LLM候補生成
│   ├── phase2_structuring.py   # フェーズ2: データ構造化
│   ├── phase3_routing.py       # フェーズ3: 移動経路挿入
│   └── replan_engine.py        # リアルタイム再探索（後続）
└── ui/
    ├── components.py            # Streamlit UI コンポーネント
    └── styles.py                # カスタムCSS
```

---

## 次ステップ
1. **フェーズ1, 2, 3 の実装コード生成** （本日）
2. **Streamlit UI の作成** （本日または明日）
3. **ローカルテスト** （Windows 環境で動作確認）
4. **リアルタイム再探索機能** （ハッカソン向けデモ準備）
