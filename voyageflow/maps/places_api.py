"""
maps/places_api.py
Google Places API（New）ラッパー
"""

import os
from typing import Optional, Dict, Any, List

import requests
from dotenv import load_dotenv

load_dotenv()


class PlacesAPI:
    """Google Places API (New) クライアント"""

    TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
    PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("MAPS_API_KEY")
        if not self.api_key:
            raise ValueError("MAPS_API_KEY 環境変数が設定されていません")

    def _headers(self, field_mask: str) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": field_mask,
        }

    def search_text(
        self,
        query: str,
        location: Optional[tuple] = None,
        radius: int = 50000,
        language: str = "ja",
    ) -> List[Dict[str, Any]]:
        body: Dict[str, Any] = {
            "textQuery": query,
            "languageCode": language,
            "maxResultCount": 10,
        }
        if location and len(location) == 2:
            body["locationBias"] = {
                "circle": {
                    "center": {"latitude": float(location[0]), "longitude": float(location[1])},
                    "radius": float(radius),
                }
            }

        field_mask = ",".join([
            "places.id",
            "places.displayName",
            "places.formattedAddress",
            "places.location",
            "places.primaryType",
            "places.types",
            "places.rating",
            "places.userRatingCount",
        ])

        try:
            response = requests.post(
                self.TEXT_SEARCH_URL,
                headers=self._headers(field_mask),
                json=body,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            places = data.get("places", [])
            results: List[Dict[str, Any]] = []
            for result in places:
                loc = result.get("location", {}) or {}
                results.append({
                    "place_id": result.get("id"),
                    "name": (result.get("displayName") or {}).get("text"),
                    "formatted_address": result.get("formattedAddress"),
                    "latitude": loc.get("latitude"),
                    "longitude": loc.get("longitude"),
                    "rating": result.get("rating"),
                    "user_ratings_total": result.get("userRatingCount"),
                    "types": result.get("types", []),
                    "primary_type": result.get("primaryType"),
                })
            if not results:
                print(f"Places API(New) 検索結果なし: query={query}")
            return results
        except requests.HTTPError as e:
            detail = ""
            try:
                detail = response.text
            except Exception:
                pass
            print(f"Places API(New) HTTPエラー: query={query} status={getattr(response, 'status_code', 'unknown')} detail={detail[:400]}")
            return []
        except requests.RequestException as e:
            print(f"Places API(New) リクエストエラー: query={query} error={e}")
            return []

    def get_place_details(self, place_id: str, fields: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        if not fields:
            fields = [
                "id",
                "displayName",
                "formattedAddress",
                "location",
                "regularOpeningHours",
                "rating",
                "userRatingCount",
                "internationalPhoneNumber",
                "websiteUri",
                "types",
                "primaryType",
            ]
        field_mask = ",".join(fields)
        url = self.PLACE_DETAILS_URL.format(place_id=place_id)
        try:
            response = requests.get(
                url,
                headers=self._headers(field_mask),
                params={"languageCode": "ja"},
                timeout=10,
            )
            response.raise_for_status()
            result = response.json()
            loc = result.get("location", {}) or {}
            return {
                "place_id": result.get("id"),
                "name": (result.get("displayName") or {}).get("text"),
                "formatted_address": result.get("formattedAddress"),
                "latitude": loc.get("latitude"),
                "longitude": loc.get("longitude"),
                "opening_hours": self._format_opening_hours(result.get("regularOpeningHours", {})),
                "rating": result.get("rating"),
                "user_ratings_total": result.get("userRatingCount"),
                "phone": result.get("internationalPhoneNumber"),
                "website": result.get("websiteUri"),
                "types": result.get("types", []),
                "primary_type": result.get("primaryType"),
            }
        except requests.HTTPError as e:
            detail = ""
            try:
                detail = response.text
            except Exception:
                pass
            print(f"Place Details(New) HTTPエラー: place_id={place_id} status={getattr(response, 'status_code', 'unknown')} detail={detail[:400]}")
            return None
        except requests.RequestException as e:
            print(f"Place Details(New) リクエストエラー: {e}")
            return None

    def autocomplete_query(self, input_text: str, location: Optional[tuple] = None, radius: int = 30000) -> List[str]:
        # 現段階では search_text を簡易利用
        results = self.search_text(input_text, location=location, radius=radius, language="ja")
        return [r.get("name") or r.get("formatted_address") for r in results if r.get("name") or r.get("formatted_address")]

    def find_nearby_rental_cars(self, location: tuple, radius: int = 1000, language: str = "ja") -> List[Dict[str, Any]]:
        if not location or len(location) != 2:
            return []

        queries = ["レンタカー", "レンタカー 営業所", "car rental"]
        seen = set()
        merged: List[Dict[str, Any]] = []
        for query in queries:
            for result in self.search_text(query, location=location, radius=radius, language=language):
                place_id = result.get("place_id") or f"{result.get('name')}::{result.get('formatted_address')}"
                if place_id in seen:
                    continue
                seen.add(place_id)
                name = str(result.get("name") or "")
                types = [str(t).lower() for t in result.get("types", [])]
                blob = f"{name} {' '.join(types)}".lower()
                if any(keyword in blob for keyword in ["rental", "car_rental", "レンタカー", "times", "ニッポン", "トヨタレンタ", "オリックス", "日産レンタ"]):
                    merged.append(result)
        return merged

    @staticmethod
    def _format_opening_hours(opening_hours: Dict[str, Any]) -> str:
        if not opening_hours:
            return "情報なし"
        periods = opening_hours.get("periods", [])
        if not periods:
            return "営業時間情報なし"
        period = periods[0]
        open_time = (period.get("open") or {}).get("time", "")
        close_time = (period.get("close") or {}).get("time", "")
        if open_time and close_time:
            return f"{open_time[:2]}:{open_time[2:]}-{close_time[:2]}:{close_time[2:]}"
        weekday = opening_hours.get("weekdayDescriptions") or []
        if weekday:
            return str(weekday[0])
        return "営業時間情報取得不可"

    @staticmethod
    def format_place_result(result: Dict[str, Any]) -> str:
        name = result.get("name") or "名称不明"
        address = result.get("formatted_address") or "住所不明"
        rating = result.get("rating")
        rating_text = f" / ★{rating}" if rating is not None else ""
        return f"{name} ({address}{rating_text})"
