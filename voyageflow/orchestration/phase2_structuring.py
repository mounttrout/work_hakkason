"""
orchestration/phase2_structuring.py
フェーズ2: フリーテキスト旅行プラン → 構造化 DataFrame
"""

import pandas as pd
from typing import Callable, Optional, Dict, Any, List
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.llm_client import GeminiClient
from core.prompts import PromptBuilder
from maps.places_api import PlacesAPI


class Phase2Structuring:
    """フェーズ2: データ構造化"""

    ITINERARY_COLUMNS = [
        "day", "sequence", "date", "start_time", "end_time", "duration_minutes",
        "destination", "purpose", "genre", "one_point",
        "place_id", "latitude", "longitude", "address",
        "opening_hours", "rating", "is_transport", "transport_mode"
    ]

    def __init__(self, gemini_client: Optional[GeminiClient] = None,
                 places_api: Optional[PlacesAPI] = None, logger: Optional[Callable[[str, str, str], None]] = None):
        self.gemini = gemini_client or GeminiClient()
        self.places = places_api or PlacesAPI()
        self.logger = logger

    def _log(self, message: str, level: str = "info") -> None:
        if self.logger:
            self.logger("Phase2", message, level)

    def structure_trip_plan(self, travel_plan: str, start_date: str) -> Optional[pd.DataFrame]:
        print("フェーズ2: データ構造化を開始...\n")
        self._log("データ構造化を開始")

        activities_list = self._text_to_json(travel_plan)
        if not activities_list:
            return None

        print(f"  → {len(activities_list)} 個の活動を抽出\n")
        self._log(f"{len(activities_list)} 個の活動を抽出")

        enriched_activities = self._enrich_with_places_api(activities_list)
        print(f"  → {len(enriched_activities)} 個の活動をエンリッチ\n")
        self._log(f"{len(enriched_activities)} 個の活動をPlacesで補完")

        final_activities = self._enrich_with_durations(enriched_activities)
        print("  → 滞在時間を設定完了\n")
        self._log("滞在時間の推定を完了")

        df = self._activities_to_dataframe(final_activities, start_date)
        return df

    def _text_to_json(self, travel_plan: str) -> Optional[List[Dict[str, Any]]]:
        prompt = PromptBuilder.build_phase2_json(travel_plan)
        try:
            result = self.gemini.generate_json(prompt, temperature=0.3)
            if isinstance(result, list):
                return result
            if isinstance(result, dict) and "itinerary" in result:
                return result["itinerary"]
            print(f"警告: 予期しないJSON構造: {type(result)}")
            return None
        except Exception as e:
            print(f"エラー: JSON化失敗 - {e}")
            return None

    def _enrich_with_places_api(self, activities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        enriched: List[Dict[str, Any]] = []
        for activity in activities:
            destination = activity.get("destination", "")
            if activity.get("purpose") == "transport":
                enriched.append(activity)
                continue

            print(f"  検索中: {destination}...", end="")
            self._log(f"検索中: {destination}")
            results = self.places.search_text(destination)
            if results:
                top_result = results[0]
                print(" ✓")
                self._log(f"Places検索成功: {destination}")
                activity.update({
                    "place_id": top_result.get("place_id"),
                    "latitude": top_result.get("latitude"),
                    "longitude": top_result.get("longitude"),
                    "address": top_result.get("formatted_address"),
                    "rating": top_result.get("rating"),
                    "formal_name": top_result.get("name"),
                })
                if top_result.get("place_id"):
                    details = self.places.get_place_details(top_result["place_id"])
                    if details:
                        activity.update({
                            "opening_hours": details.get("opening_hours"),
                        })
            else:
                print(" ✗（見つかりません）")
                self._log(f"Places検索失敗: {destination}", level="warning")
            enriched.append(activity)
        return enriched

    def _enrich_with_durations(self, activities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        enriched: List[Dict[str, Any]] = []
        for activity in activities:
            if activity.get("purpose") == "transport":
                enriched.append(activity)
                continue

            if activity.get("duration_minutes"):
                try:
                    activity["duration_minutes"] = int(activity.get("duration_minutes"))
                except Exception:
                    activity["duration_minutes"] = 60
                enriched.append(activity)
                continue

            destination = activity.get("destination", "")
            genre = activity.get("genre", "")
            one_point = activity.get("one_point", "")

            print(f"  提案中: {destination}...", end="")
            self._log(f"滞在時間を推定中: {destination}")
            try:
                prompt = PromptBuilder.build_phase2_duration(destination, genre, one_point)
                result = self.gemini.generate_json(prompt, temperature=0.3)
                if isinstance(result, dict):
                    duration = int(result.get("recommended_duration_minutes", 60))
                    activity["duration_minutes"] = duration
                    print(f" → {duration}分")
                    self._log(f"滞在時間推定: {destination} → {duration}分")
                else:
                    activity["duration_minutes"] = 60
                    print(" → デフォルト(60分)")
                    self._log(f"滞在時間推定: {destination} → デフォルト60分", level="warning")
            except Exception:
                activity["duration_minutes"] = 60
                print(" → エラー、デフォルト値(60分)")
                self._log(f"滞在時間推定エラー: {destination} → デフォルト60分", level="warning")
            enriched.append(activity)
        return enriched

    def _activities_to_dataframe(self, activities: List[Dict[str, Any]], start_date: str) -> pd.DataFrame:
        rows: List[Dict[str, Any]] = []
        trip_start_dt = datetime.strptime(start_date, "%Y-%m-%d")

        # LLM が絶対日付を返しても、旅行開始日を Day1 に再マップする
        parsed_dates: List[datetime] = []
        for activity in activities:
            parsed = self._parse_date(activity.get("date"))
            if parsed is not None:
                parsed_dates.append(parsed)
        base_llm_date = min(parsed_dates) if parsed_dates else trip_start_dt

        current_day = 1
        current_sequence = 1
        current_date = trip_start_dt
        last_start_dt = None

        for activity in activities:
            llm_date = self._parse_date(activity.get("date"))
            if llm_date is not None:
                relative_day = (llm_date.date() - base_llm_date.date()).days + 1
                current_day = max(1, relative_day)
                current_date = trip_start_dt + timedelta(days=current_day - 1)
                current_sequence = 1 if not rows or rows[-1]["day"] != current_day else rows[-1]["sequence"] + 1
            elif rows and rows[-1]["day"] == current_day:
                current_sequence = rows[-1]["sequence"] + 1
            elif rows:
                current_sequence = 1

            start_time = self._normalize_time(activity.get("start_time", "09:00"))
            duration = self._safe_int(activity.get("duration_minutes"), 60)
            start_dt = self._parse_clock(start_time)
            if last_start_dt and start_dt < last_start_dt and llm_date is None:
                current_day += 1
                current_date = trip_start_dt + timedelta(days=current_day - 1)
                current_sequence = 1
            end_dt = start_dt + timedelta(minutes=duration)
            end_time = end_dt.strftime("%H:%M")
            last_start_dt = start_dt

            row = {
                "day": current_day,
                "sequence": current_sequence,
                "date": current_date.strftime("%Y-%m-%d"),
                "start_time": start_time,
                "end_time": end_time,
                "duration_minutes": duration,
                "destination": activity.get("formal_name") or activity.get("destination", "不明"),
                "purpose": activity.get("purpose", "activity"),
                "genre": activity.get("genre", "general"),
                "one_point": activity.get("one_point", ""),
                "place_id": activity.get("place_id"),
                "latitude": activity.get("latitude"),
                "longitude": activity.get("longitude"),
                "address": activity.get("address"),
                "opening_hours": activity.get("opening_hours"),
                "rating": activity.get("rating"),
                "is_transport": False,
                "transport_mode": None,
            }
            rows.append(row)

        df = pd.DataFrame(rows, columns=self.ITINERARY_COLUMNS)
        df = df.sort_values(["day", "sequence"]).reset_index(drop=True)
        return df

    @staticmethod
    def _parse_date(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(text, fmt)
            except Exception:
                continue
        return None

    @staticmethod
    def _parse_clock(value: str) -> datetime:
        try:
            return datetime.strptime(value, "%H:%M")
        except Exception:
            return datetime.strptime("09:00", "%H:%M")

    @staticmethod
    def _normalize_time(value: Any) -> str:
        text = str(value).strip()
        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                return datetime.strptime(text, fmt).strftime("%H:%M")
            except Exception:
                continue
        return "09:00"

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return default


if __name__ == "__main__":
    pass
