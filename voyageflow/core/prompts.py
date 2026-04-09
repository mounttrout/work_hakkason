"""
core/prompts.py
各フェーズで使用するプロンプトテンプレート
"""


class PromptTemplates:
    """プロンプトテンプレート集"""
    
    # ========== フェーズ1: LLM候補生成 ==========
    PHASE1_TRIP_GENERATION = """
あなたは優秀な旅行プランナーです。ユーザーのリクエストに基づいて、詳細で実行可能な旅行プランを作成してください。

**ユーザーリクエスト:**
{user_request}

**要件:**
1. 具体的な日時を含める（例: 4月16日（木）09:32）
2. 各スポット/活動に以下の情報を含める:
   - 時刻（開始時刻）
   - 場所名（実在する施設・地点）
   - 目的（散策、食事、体験など）
   - 推奨滞在時間（分）
   - 理由やワンポイント（なぜこのスポットか）

3. 移動時間も考慮した現実的なスケジュール
4. 実装可能な内容（ハルシネーション避け）

**出力形式:**
日付（曜日）ごとに、以下の形式で記述してください:
【日付（曜日）】テーマ
* HH:MM - スポット名
  - 目的: 〇〇
  - 滞在時間: 〇〇分
  - ワンポイント: 理由や説明

詳細で実行可能なプランを生成してください。
"""
    
    # ========== フェーズ2: データ構造化 ==========
    PHASE2_STRUCTURED_JSON = """
以下のテキスト形式の旅行プランをJSON形式に構造化してください。

**入力プラン:**
{travel_plan}

**出力JSON形式:**
{{
  "trip_id": "tokyo_2026_04",
  "start_date": "2026-04-16",
  "end_date": "2026-04-18",
  "itinerary": [
    {{
      "day": 1,
      "sequence": 1,
      "date": "2026-04-16",
      "start_time": "09:32",
      "end_time": "計算予定",
      "destination": "東京駅",
      "purpose": "arrival",
      "genre": "station",
      "one_point": "北陸新幹線で到着",
      "duration_minutes": 30,
      "latitude": null,
      "longitude": null,
      "place_id": null,
      "address": null,
      "opening_hours": null,
      "rating": null
    }}
  ]
}}

**重要:**
- 各活動を1行として抽出してください
- start_time, end_time, duration_minutes, day, sequence を含める
- latitude, longitude, place_id, address, opening_hours, rating は後で埋める（nullでOK）
- JSON形式のみで応答（説明なし）
"""
    
    PHASE2_EXTRACT_FIELDS = """
以下の旅行プランテキストから、各スポット/活動を抽出し、構造化データを生成してください。

**入力テキスト:**
{travel_plan}

**抽出項目:**
各活動について以下を抽出:
- destination: スポット名（正式名称）
- date: 日付（YYYY-MM-DD）
- start_time: 開始時刻（HH:MM）
- purpose: 目的（arrival, activity, meal, shopping, transport等）
- genre: ジャンル（station, museum, restaurant, park等）
- one_point: ワンポイント（理由や説明）
- duration_minutes: 推奨滞在時間（分）

**出力形式:**
JSON配列で以下のように返してください:
[
  {{
    "destination": "東京駅",
    "date": "2026-04-16",
    "start_time": "09:32",
    "purpose": "arrival",
    "genre": "station",
    "one_point": "北陸新幹線で到着",
    "duration_minutes": 30
  }},
  ...
]

JSON形式のみで応答してください。
"""
    
    # ========== フェーズ2: 滞在時間提案 ==========
    PHASE2_STAY_DURATION = """
以下のスポット情報から、推奨滞在時間を提案してください。

**スポット情報:**
- 名前: {destination}
- ジャンル: {genre}
- 説明: {one_point}

**推奨滞在時間（分）をJSON形式で返してください:**
{{
  "destination": "{destination}",
  "recommended_duration_minutes": 60,
  "reasoning": "理由を簡潔に説明"
}}
"""
    
    # ========== フェーズ2: Places API 補足情報 ==========
    PHASE2_VERIFY_LOCATION = """
以下のスポットが実在するか確認し、正式名称と関連情報を提案してください。

**スポット候補:**
- 入力名: {destination}
- ジャンル: {genre}
- 地域: {region}

**出力形式（JSON）:**
{{
  "original_input": "{destination}",
  "formal_name": "正式な施設名",
  "alternative_names": ["別名1", "別名2"],
  "is_valid": true,
  "reasoning": "このスポットが正確である理由"
}}
"""
    
    # ========== フェーズ3: 移動手段判定 ==========
    PHASE3_TRANSPORT_MODE = """
以下の2地点間の移動について、最適な交通手段を判定してください。

**移動情報:**
- 出発地: {origin_destination} ({origin_lat}, {origin_lng})
- 目的地: {destination_destination} ({destination_lat}, {destination_lng})
- 出発時刻: {departure_time}
- 推定直線距離: {distance_km:.2f} km
- 地域: {region}

**判定基準:**
- 2km未満 → 徒歩（walk）
- 2-15km, 駅近い → 電車（train）
- 15km以上または交通不便 → 車/タクシー（car/taxi）
- 深夜早朝 → タクシー優先

**出力形式（JSON）:**
{{
  "origin": "{origin_destination}",
  "destination": "{destination_destination}",
  "recommended_mode": "walk|train|car|taxi",
  "confidence": 0.9,
  "reasoning": "判定理由を簡潔に説明",
  "notes": "その他の注意事項"
}}
"""
    
    # ========== フェーズ3: タイムスケジュール調整 ==========
    PHASE3_TIME_ADJUSTMENT = """
以下のスケジュール情報から、時間差を解決する方法を提案してください。

**現在のスケジュール:**
{current_schedule}

**遅延情報:**
- 前の活動から次の活動への移動予定時間: {planned_travel_minutes} 分
- 実際の移動時間: {actual_travel_minutes} 分
- 時間差（遅延）: {delay_minutes} 分

**提案内容:**
遅延を吸収する案を3つ提案してください:
1. 滞在時間短縮案（短縮対象と短縮時間）
2. スポット飛ばし案（スキップするスポット）
3. スケジュール再構成案（順番変更など）

**出力形式（JSON）:**
{{
  "adjustment_options": [
    {{
      "option_id": 1,
      "type": "shorten_stay",
      "target": "短縮対象スポット",
      "reduction_minutes": 15,
      "reasoning": "理由"
    }},
    ...
  ]
}}
"""
    
    # ========== リアルタイム再探索 ==========
    REPLAN_REAL_TIME = """
旅行中にスケジュール遅延が発生しています。ユーザーのために最適な再探索プランを提案してください。

**現在の状況:**
- 現在時刻: {current_time}
- 現在位置: {current_location}
- 元々の予定: {original_schedule}
- 遅延時間: {delay_minutes} 分

**気象・イベント情報:**
{event_info}

**提案内容:**
ユーザーが快適に旅を続けられるよう、以下の視点から提案してください:
1. 時間短縮案（現実的かつ価値を損なわない）
2. スポット交換案（近い代替施設）
3. 全体的なリバランス案

**出力形式（JSON）:**
{{
  "replan_options": [
    {{
      "option_id": 1,
      "title": "提案のタイトル",
      "changes": [
        {{
          "day": 1,
          "target_activity": "スポット名",
          "action": "shorten|skip|swap|reorder",
          "details": "詳細な変更内容",
          "reason": "ユーザー向けの理由説明"
        }}
      ],
      "estimated_time_saved": 30,
      "user_appeal": "ユーザーへのアピール文"
    }}
  ]
}}
"""


class PromptBuilder:
    """プロンプト組み立てヘルパークラス"""
    
    @staticmethod
    def build_phase1(user_request: str) -> str:
        """フェーズ1プロンプト作成"""
        return PromptTemplates.PHASE1_TRIP_GENERATION.format(
            user_request=user_request
        )
    
    @staticmethod
    def build_phase2_json(travel_plan: str) -> str:
        """フェーズ2 JSON構造化プロンプト作成"""
        return PromptTemplates.PHASE2_EXTRACT_FIELDS.format(
            travel_plan=travel_plan
        )
    
    @staticmethod
    def build_phase2_duration(destination: str, genre: str, one_point: str) -> str:
        """フェーズ2 滞在時間提案プロンプト作成"""
        return PromptTemplates.PHASE2_STAY_DURATION.format(
            destination=destination,
            genre=genre,
            one_point=one_point
        )
    
    @staticmethod
    def build_phase3_transport(origin_destination: str, origin_lat: float, origin_lng: float,
                               destination_destination: str, destination_lat: float, destination_lng: float,
                               departure_time: str, distance_km: float, region: str) -> str:
        """フェーズ3 移動手段判定プロンプト作成"""
        return PromptTemplates.PHASE3_TRANSPORT_MODE.format(
            origin_destination=origin_destination,
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            destination_destination=destination_destination,
            destination_lat=destination_lat,
            destination_lng=destination_lng,
            departure_time=departure_time,
            distance_km=distance_km,
            region=region
        )
    
    @staticmethod
    def build_replan(current_time: str, current_location: str, original_schedule: str,
                    delay_minutes: int, event_info: str = "") -> str:
        """リアルタイム再探索プロンプト作成"""
        return PromptTemplates.REPLAN_REAL_TIME.format(
            current_time=current_time,
            current_location=current_location,
            original_schedule=original_schedule,
            delay_minutes=delay_minutes,
            event_info=event_info or "通常の気象条件"
        )
