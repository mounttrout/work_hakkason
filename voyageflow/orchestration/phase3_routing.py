"""
orchestration/phase3_routing.py
フェーズ3: 移動経路挿入 & タイムスケジュール調整
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Callable, Optional

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.llm_client import GeminiClient
from core.prompts import PromptBuilder
from maps.routes_api import RoutesAPI


class Phase3Routing:
    """フェーズ3: 移動経路挿入"""

    def __init__(
        self,
        gemini_client: Optional[GeminiClient] = None,
        routes_api: Optional[RoutesAPI] = None,
        logger: Optional[Callable[[str, str, str], None]] = None,
    ):
        self.gemini = gemini_client or GeminiClient()
        self.routes = routes_api or RoutesAPI()
        self.logger = logger

    def _log(self, message: str, level: str = "info") -> None:
        if self.logger:
            self.logger("Phase3", message, level)

    def insert_routes(
        self,
        df: pd.DataFrame,
        region: str = "Tokyo",
        user_request: str = "",
        transport_preference: str = "",
    ) -> pd.DataFrame:
        self._log("移動経路挿入を開始")
        preference = self._resolve_transport_preference(transport_preference, user_request)
        self._log(f"移動手段を判定中... preference={preference}")
        df_with_modes = self._assign_transport_modes(df, region, preference)
        self._log("移動手段の設定を完了")
        self._log("移動時間を取得し、移動ステップを挿入中")
        df_with_routes = self._insert_transport_steps(df_with_modes)
        self._log("移動ステップの挿入を完了")
        self._log("タイムスケジュールを検証・調整中")
        df_final = self._validate_and_adjust_schedule(df_with_routes)
        self._log("スケジュール調整完了")
        return df_final

    def _resolve_transport_preference(self, transport_preference: str, user_request: str) -> str:
        label_map = {
            "徒歩メイン": "walk",
            "電車メイン": "train",
            "タクシー": "taxi",
            "レンタカー": "rental_car",
            "自動（おすすめ）": "auto",
            "": "auto",
            None: "auto",
        }
        mapped = label_map.get(transport_preference, None)
        if mapped and mapped != "auto":
            return mapped
        return self._extract_transport_preference(user_request)

    def _assign_transport_modes(self, df: pd.DataFrame, region: str, preference: str) -> pd.DataFrame:
        df = df.copy().reset_index(drop=True)
        df["next_transport_mode"] = None

        for idx in range(len(df) - 1):
            if bool(df.loc[idx, "is_transport"]):
                continue
            next_idx = idx + 1
            if bool(df.loc[next_idx, "is_transport"]):
                continue
            if df.loc[idx, "day"] != df.loc[next_idx, "day"]:
                continue

            origin_lat = df.loc[idx, "latitude"]
            origin_lng = df.loc[idx, "longitude"]
            dest_lat = df.loc[next_idx, "latitude"]
            dest_lng = df.loc[next_idx, "longitude"]

            if pd.isna(origin_lat) or pd.isna(origin_lng) or pd.isna(dest_lat) or pd.isna(dest_lng):
                df.loc[idx, "next_transport_mode"] = preference if preference != "auto" else "train"
                self._log(
                    f"座標不足: {df.loc[idx, 'destination']} → {df.loc[next_idx, 'destination']} は {df.loc[idx, 'next_transport_mode']} で仮設定",
                    level="warning",
                )
                continue

            distance_km = self.routes.compute_distance((origin_lat, origin_lng), (dest_lat, dest_lng))
            origin_destination = str(df.loc[idx, "destination"])
            dest_destination = str(df.loc[next_idx, "destination"])
            departure_time = str(df.loc[idx, "end_time"])

            if preference != "auto":
                transport_mode = self._respect_user_preference(preference, distance_km)
            else:
                transport_mode = self._recommend_general_mode(
                    origin_destination,
                    dest_destination,
                    distance_km,
                    departure_time,
                    region,
                )
            df.loc[idx, "next_transport_mode"] = transport_mode
            self._log(
                f"区間判定: {origin_destination} → {dest_destination} / 距離={distance_km:.2f}km / mode={transport_mode}"
            )
        return df

    def _insert_transport_steps(self, df: pd.DataFrame) -> pd.DataFrame:
        new_rows = []
        for idx in range(len(df)):
            current_row = df.iloc[idx].copy()
            new_rows.append(current_row)
            if idx == len(df) - 1:
                break

            next_row = df.iloc[idx + 1]
            if bool(current_row["is_transport"]) or bool(next_row["is_transport"]):
                continue
            if current_row["day"] != next_row["day"]:
                continue

            transport_mode = current_row.get("next_transport_mode")
            if pd.isna(transport_mode) or not transport_mode:
                self._log(
                    f"移動手段未設定のため移動カードを作れません: {current_row['destination']} → {next_row['destination']}",
                    level="warning",
                )
                continue

            origin_lat = current_row["latitude"]
            origin_lng = current_row["longitude"]
            dest_lat = next_row["latitude"]
            dest_lng = next_row["longitude"]
            current_end_time = str(current_row["end_time"])
            route_polyline = None
            route_info = None
            route_data_source = "fallback"
            route_debug_reason = ""
            route_departure_at = f"{current_row['date']} {current_end_time}"
            departure_dt = self._build_departure_datetime(str(current_row["date"]), current_end_time)

            if pd.isna(origin_lat) or pd.isna(origin_lng) or pd.isna(dest_lat) or pd.isna(dest_lng):
                distance_km = 1.0
                travel_duration = self._fallback_duration_minutes(str(transport_mode), distance_km)
                route_data_source = "fallback_missing_coordinates"
                route_debug_reason = "座標不足のため距離ベース推定"
                route_debug_reason = "Places APIで座標取得できず"
                self._log(
                    f"座標不足のためフォールバック移動を作成: {current_row['destination']} → {next_row['destination']} / origin=({origin_lat},{origin_lng}) dest=({dest_lat},{dest_lng})",
                    level="warning",
                )
            else:
                route_info = self.routes.compute_route(
                    (origin_lat, origin_lng),
                    (dest_lat, dest_lng),
                    mode=str(transport_mode),
                    departure_time=departure_dt,
                )
                if route_info:
                    travel_duration = max(1, int(route_info.get("duration_minutes", 1)))
                    route_polyline = route_info.get("polyline")
                    route_data_source = "google_routes_api"
                    route_debug_reason = "Google Routes API取得成功"
                    self._log(
                        f"Routes API取得成功: {current_row['destination']} → {next_row['destination']} / mode={transport_mode} / duration={travel_duration}分 / departure={route_departure_at}"
                    )
                else:
                    distance_km = self.routes.compute_distance((origin_lat, origin_lng), (dest_lat, dest_lng)) or 1.0
                    travel_duration = self._fallback_duration_minutes(str(transport_mode), distance_km)
                    route_data_source = "fallback_routes_unavailable"
                    route_debug_reason = "Routes API未取得のため距離ベース推定"
                    route_debug_reason = "Routes APIで経路取得できず"
                    self._log(
                        f"Routes API未取得のためフォールバック移動を作成: {current_row['destination']} → {next_row['destination']} / mode={transport_mode} / distance={distance_km:.2f}km / departure={route_departure_at}",
                        level="warning",
                    )

            start_dt = datetime.strptime(current_end_time, "%H:%M")
            end_dt = start_dt + timedelta(minutes=travel_duration)
            route_url = self.routes.build_google_maps_directions_url(
                str(current_row["destination"]),
                str(next_row["destination"]),
                str(transport_mode),
                departure_time=departure_dt,
            )
            route_from = (route_info or {}).get("route_from") or str(current_row["destination"])
            route_to = (route_info or {}).get("route_to") or str(next_row["destination"])
            route_line_simple = (route_info or {}).get("route_line_simple") or self._transport_mode_label(str(transport_mode))
            route_summary = self._build_route_summary(route_from, route_to, str(transport_mode), route_line_simple, travel_duration)
            transport_step = {
                "day": current_row["day"],
                "sequence": float(current_row["sequence"]) + 0.5,
                "date": current_row["date"],
                "start_time": current_end_time,
                "end_time": end_dt.strftime("%H:%M"),
                "duration_minutes": travel_duration,
                "destination": f"{current_row['destination']} → {next_row['destination']}",
                "purpose": "transport",
                "genre": "transit",
                "one_point": f"{self._transport_mode_label(str(transport_mode))}で移動",
                "place_id": None,
                "latitude": None,
                "longitude": None,
                "address": None,
                "opening_hours": None,
                "rating": None,
                "is_transport": True,
                "transport_mode": str(transport_mode),
                "route_url": route_url,
                "route_polyline": route_polyline,
                "route_from": route_from,
                "route_to": route_to,
                "route_line_simple": route_line_simple,
                "route_summary": route_summary,
                "route_data_source": route_data_source,
                "route_departure_at": route_departure_at,
                "route_debug_reason": route_debug_reason,
                "route_debug_reason": route_debug_reason,
            }
            new_rows.append(pd.Series(transport_step))

        df_new = pd.DataFrame(new_rows).reset_index(drop=True)
        for day in df_new["day"].dropna().unique():
            day_mask = df_new["day"] == day
            df_new.loc[day_mask, "sequence"] = range(1, int(day_mask.sum()) + 1)
        return df_new

    @staticmethod
    def _build_departure_datetime(date_str: str, time_str: str) -> Optional[datetime]:
        try:
            return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        except Exception:
            return None

    def _validate_and_adjust_schedule(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy().sort_values(["day", "sequence"]).reset_index(drop=True)
        current_day = None
        cursor_end = None
        for idx in range(len(df)):
            row = df.iloc[idx]
            if current_day != row["day"]:
                current_day = row["day"]
                cursor_end = None

            start_dt = datetime.strptime(str(row["start_time"]), "%H:%M")
            end_dt = datetime.strptime(str(row["end_time"]), "%H:%M")
            duration = max(1, int(row.get("duration_minutes", 1)))

            if cursor_end is not None and start_dt < cursor_end:
                start_dt = cursor_end
                end_dt = start_dt + timedelta(minutes=duration)
                df.at[idx, "start_time"] = start_dt.strftime("%H:%M")
                df.at[idx, "end_time"] = end_dt.strftime("%H:%M")

            cursor_end = end_dt
        return df

    def _recommend_general_mode(
        self,
        origin_destination: str,
        dest_destination: str,
        distance_km: float,
        departure_time: str,
        region: str,
    ) -> str:
        if distance_km is None:
            return "train"
        if distance_km <= 0.8:
            return "walk"
        if distance_km <= 20.0:
            return "train"

        prompt = PromptBuilder.build_phase3_transport(
            origin_destination, 0.0, 0.0,
            dest_destination, 0.0, 0.0,
            departure_time, distance_km, region,
        )
        try:
            result = self.gemini.generate_json(prompt, temperature=0.2)
            mode = str(result.get("recommended_mode", "train"))
            if mode in {"walk", "train", "car", "private_car", "rental_car", "taxi", "bike"}:
                return mode
        except Exception:
            pass
        return "train"

    @staticmethod
    def _extract_transport_preference(user_request: str) -> str:
        text = str(user_request or "")
        lower = text.lower()
        if any(k in text for k in ["タクシー"]) or "taxi" in lower:
            return "taxi"
        if any(k in text for k in ["レンタカー", "車で", "ドライブ"]) or any(k in lower for k in ["car", "drive"]):
            return "rental_car"
        if any(k in text for k in ["電車", "新幹線"]) or any(k in lower for k in ["rail", "train", "transit"]):
            return "train"
        if any(k in text for k in ["徒歩", "歩き"]) or "walk" in lower:
            return "walk"
        if any(k in text for k in ["自転車"]) or "bike" in lower:
            return "bike"
        return "auto"

    @staticmethod
    def _respect_user_preference(preference: str, distance_km: float) -> str:
        if preference == "walk" and distance_km > 5.0:
            return "train"
        if preference in {"taxi", "car", "private_car", "rental_car"} and distance_km <= 0.7:
            return "walk"
        return preference

    @staticmethod
    def _fallback_duration_minutes(mode: str, distance_km: float) -> int:
        """
        Routes API が取れない場合でも極端に短い所要時間にならないようにする。
        特に電車は待ち時間・乗換・駅構内移動を考慮して下限を強めに置く。
        """
        normalized_mode = str(mode or "").lower()
        speed_kmh = {
            "walk": 4.5,
            "train": 28.0,
            "car": 24.0,
            "private_car": 24.0,
            "rental_car": 24.0,
            "taxi": 24.0,
            "bike": 12.0,
        }.get(normalized_mode, 20.0)

        base_minutes = int((max(distance_km, 0.1) / speed_kmh) * 60)

        minimum_minutes = {
            "walk": 5,
            "bike": 8,
            "car": 15,
            "private_car": 15,
            "rental_car": 15,
            "taxi": 15,
            "train": 30,
        }.get(normalized_mode, 10)

        if normalized_mode == "train":
            # 駅構内移動・待ち時間・乗換の最低バッファ
            if distance_km >= 3:
                base_minutes += 10
            if distance_km >= 15:
                base_minutes += 10

        return max(minimum_minutes, base_minutes)

    @staticmethod
    @staticmethod
    def _transport_mode_label(mode: str) -> str:
        return {
            "walk": "徒歩",
            "train": "電車",
            "car": "自家用車",
            "private_car": "自家用車",
            "rental_car": "レンタカー",
            "taxi": "タクシー",
            "bike": "自転車",
        }.get(mode, mode)

    def _build_route_summary(self, route_from: str, route_to: str, transport_mode: str, route_line_simple: str, duration_minutes: int) -> str:
        mode_label = self._transport_mode_label(transport_mode)
        if transport_mode == "train":
            return f"{route_from}→{route_to}：{mode_label} {route_line_simple} {duration_minutes}分"
        return f"{route_from}→{route_to}：{mode_label} {duration_minutes}分"


if __name__ == "__main__":
    pass
