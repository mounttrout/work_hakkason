from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

try:
    from maps.routes_api import RoutesAPI
except Exception:
    RoutesAPI = None

try:
    from maps.places_api import PlacesAPI
except Exception:
    PlacesAPI = None

try:
    from utils.display_formatters import is_outdoor_row
except Exception:
    def is_outdoor_row(row: Dict[str, Any]) -> bool:
        text = f"{row.get('destination','')} {row.get('genre','')} {row.get('one_point','')}"
        return any(k in str(text) for k in ["公園", "庭園", "神社", "寺", "外苑", "散策", "屋外"])


class ExecutionEngine:
    """実行シミュレーションの状態管理エンジン"""

    TRANSPORT_LABELS = {
        "walk": "徒歩",
        "train": "電車",
        "car": "自家用車",
        "private_car": "自家用車",
        "rental_car": "レンタカー",
        "taxi": "タクシー",
        "bike": "自転車",
    }

    def __init__(self, df: pd.DataFrame):
        self.base_df = df.copy().reset_index(drop=True)
        self.working_df = df.copy().reset_index(drop=True)
        self.current_step = 0
        self.execution_started = False
        self.event_count = 0
        self.total_delays = 0
        self.event_log: List[Dict[str, Any]] = []
        self.pending_alternatives: Dict[str, Dict[str, Any]] = {}
        self.step_status = {i: "pending" for i in range(len(self.working_df))}
        self.routes = self._build_routes_api()
        self.places = self._build_places_api()
        self._ensure_status_columns()

    def _build_routes_api(self):
        if RoutesAPI is None:
            return None
        try:
            return RoutesAPI()
        except Exception:
            return None

    def _build_places_api(self):
        if PlacesAPI is None:
            return None
        try:
            return PlacesAPI()
        except Exception:
            return None

    def _ensure_status_columns(self) -> None:
        defaults = {
            "execution_status": "pending",
            "is_modified_by_event": False,
            "modification_note": "",
            "original_transport_mode": None,
            "status_color": "future",
            "route_summary": "",
            "route_from": None,
            "route_to": None,
            "route_line_simple": None,
        }
        for col, default in defaults.items():
            if col not in self.working_df.columns:
                self.working_df[col] = default

        for idx in range(len(self.working_df)):
            self.working_df.at[idx, "execution_status"] = self.step_status.get(idx, "pending")
            self.working_df.at[idx, "status_color"] = self._status_to_color(self.step_status.get(idx, "pending"))

    def _sync_df_status(self) -> None:
        for idx in range(len(self.working_df)):
            status = self.step_status.get(idx, "pending")
            self.working_df.at[idx, "execution_status"] = status
            if bool(self.working_df.at[idx, "is_modified_by_event"]):
                self.working_df.at[idx, "status_color"] = "modified"
            else:
                self.working_df.at[idx, "status_color"] = self._status_to_color(status)

    @staticmethod
    def _status_to_color(status: str) -> str:
        return {
            "completed": "completed",
            "in_progress": "in_progress",
            "pending": "future",
            "rerouted": "modified",
            "cancelled": "modified",
        }.get(status, "future")

    def start_execution(self) -> Dict[str, Any]:
        if self.execution_started:
            return {"message": "すでに旅程実行中です。"}
        self.execution_started = True
        if len(self.working_df) > 0:
            self.step_status[0] = "in_progress"
        self._sync_df_status()
        return {"message": "旅程実行を開始しました。", "current_step": self.current_step}

    def proceed_to_next_step(self) -> Dict[str, Any]:
        if not self.execution_started:
            return self.start_execution()
        if len(self.working_df) == 0:
            return {"status": "completed", "message": "旅程データがありません。"}

        self.step_status[self.current_step] = "completed"
        next_idx = self.current_step + 1
        while next_idx < len(self.working_df) and self.step_status.get(next_idx) == "cancelled":
            next_idx += 1

        if next_idx < len(self.working_df):
            self.current_step = next_idx
            if self.step_status.get(self.current_step) != "rerouted":
                self.step_status[self.current_step] = "in_progress"
            self._sync_df_status()
            return {
                "status": "advanced",
                "message": f"ステップ {self.current_step + 1} に進みました。",
                "current_step": self.current_step,
            }

        self._sync_df_status()
        return {"status": "completed", "message": "🎉 旅程完了！", "current_step": self.current_step}

    def get_current_status(self) -> Dict[str, Any]:
        total_steps = len(self.working_df)
        if total_steps == 0:
            progress = 0.0
        else:
            completed_count = sum(1 for status in self.step_status.values() if status == "completed")
            progress = (completed_count / total_steps) * 100
        return {
            "current_step": self.current_step,
            "total_steps": total_steps,
            "progress_percentage": progress,
            "event_count": self.event_count,
            "total_delays": self.total_delays,
        }

    def get_updated_dataframe(self) -> pd.DataFrame:
        self._sync_df_status()
        return self.working_df.copy()

    def _iter_scope_indices(self, scope: str = "all_future") -> List[int]:
        start = self.current_step if self.execution_started else 0
        valid = [idx for idx in range(start, len(self.working_df)) if self.step_status.get(idx) != "completed"]
        if scope == "all_future":
            return valid
        if not valid:
            return []
        current_day = int(self.working_df.iloc[start].get("day", 1)) if start < len(self.working_df) else 1
        if scope == "rest_of_day":
            return [idx for idx in valid if int(self.working_df.iloc[idx].get("day", current_day)) == current_day]

        activity_count = 0
        selected: List[int] = []
        for idx in valid:
            row = self.working_df.iloc[idx]
            selected.append(idx)
            if not bool(row.get("is_transport")) and self.step_status.get(idx) != "cancelled":
                activity_count += 1
            if activity_count >= 2:
                break
        return selected

    def build_replan_scope_text(self, scope: str = "all_future") -> str:
        indices = self._iter_scope_indices(scope)
        if not indices:
            return "残り旅程なし"
        lines: List[str] = []
        for idx in indices:
            row = self.working_df.iloc[idx]
            if bool(row.get("is_transport", False)):
                lines.append(
                    f"- {row.get('start_time','-')}-{row.get('end_time','-')} 移動 / {row.get('destination','-')} / 手段={row.get('transport_mode','-')}"
                )
            else:
                lines.append(
                    f"- {row.get('start_time','-')}-{row.get('end_time','-')} {row.get('destination','-')} / 目的={row.get('purpose','-')} / ジャンル={row.get('genre','-')}"
                )
        return "\n".join(lines)

    def classify_execution_request(self, details: str) -> Dict[str, Any]:
        text = str(details or "").strip()
        intents: List[str] = []
        if any(k in text for k in ["屋内", "雨を避け", "濡れたくない"]):
            intents.append("force_indoor")
        if any(k in text for k in ["楽に", "疲れた", "歩きたくない", "タクシー"]):
            intents.append("ease_move")
        if any(k in text for k in ["短く", "早めに", "切り上げ", "軽く"]):
            intents.append("shorten_plan")
        if any(k in text for k in ["全部キャンセル", "全てキャンセル", "キャンセル", "中止"]):
            intents.append("cancel_remaining")
        if any(k in text for k in ["帰る", "帰りたい", "ホテルに戻る", "戻りたい", "帰宅"]):
            intents.append("return_now")
        if not intents:
            intents.append("ease_move" if "weather" in text.lower() else "shorten_plan")
        return {"raw_text": text, "intents": intents}

    def _build_event_message(self, event_type: str, intents: List[str], details: str, alternatives: List[Dict[str, Any]]) -> str:
        if not alternatives:
            if event_type == "weather":
                return "天候に合わせて変えられる直近の予定が見つからなかったため、現在の旅程を維持します。"
            return "変更できる直近の予定が見つからなかったため、現在の旅程を維持します。"

        if event_type == "weather":
            if "force_indoor" in intents and "ease_move" in intents:
                return "天候不順を踏まえ、屋内候補への切替と移動負荷を下げる代替案を作成しました。"
            if "force_indoor" in intents:
                return "天候不順を踏まえ、屋外予定を避けやすい代替案を作成しました。"
            if "ease_move" in intents:
                return "天候不順を踏まえ、移動負荷を下げる代替案を作成しました。"
            if "shorten_plan" in intents:
                return "天候不順を踏まえ、予定を少し短めに調整する代替案を作成しました。"
            return "天候変化を踏まえて代替案を作成しました。"

        return {
            "mood_change": "気分の変化を踏まえて代替案を作成しました。",
            "delay": "遅延を踏まえて代替案を作成しました。",
            "flight_cancel": "欠航・運休に備えた組み直し候補を作成できます。",
            "cancel": "中止・帰着に向けた組み直し候補を作成できます。",
        }.get(event_type, "イベントに応じた代替案を作成しました。")

    def trigger_event(self, event_type: str, details: str) -> Dict[str, Any]:
        self.event_count += 1
        self.pending_alternatives = {}
        alternatives: List[Dict[str, Any]] = []

        analysis = self.classify_execution_request(details)
        intents = analysis["intents"]
        next_transport_idx = self._find_next_transport_index()
        next_activity_idx = self._find_next_activity_index()
        next_outdoor_idx = self._find_next_outdoor_activity_index()

        if "force_indoor" in intents and next_outdoor_idx is not None:
            swap_alt = self._build_swap_with_indoor_alternative(next_outdoor_idx, details)
            if swap_alt:
                alternatives.append(swap_alt)
                self.pending_alternatives[swap_alt["id"]] = swap_alt

            indoor_replace_alt = self._build_indoor_replacement_alternative(next_outdoor_idx, details)
            if indoor_replace_alt:
                alternatives.append(indoor_replace_alt)
                self.pending_alternatives[indoor_replace_alt["id"]] = indoor_replace_alt

        if "ease_move" in intents and next_transport_idx is not None:
            row = self.working_df.iloc[next_transport_idx]
            current_mode = str(row.get("transport_mode") or "walk")
            target_mode = "taxi" if current_mode != "taxi" else "train"
            alt = {
                "id": f"ease_move_{target_mode}",
                "title": f"次の移動を{self.TRANSPORT_LABELS.get(target_mode, target_mode)}へ変更",
                "description": "移動負荷を下げるため、次の移動だけを楽な手段に変更します。",
                "changes": [self._format_transport_change(next_transport_idx, current_mode, target_mode)],
                "reason": details,
                "action": "transport_change",
                "target_index": next_transport_idx,
                "new_mode": target_mode,
            }
            alternatives.append(alt)
            self.pending_alternatives[alt["id"]] = alt

        if "shorten_plan" in intents and next_activity_idx is not None:
            reduce_minutes = 30 if event_type == "delay" else 20
            alt = {
                "id": "shorten_next_activity",
                "title": "次の予定を短めに調整",
                "description": "次のスポット滞在時間を短縮し、少し余白を作ります。",
                "changes": [f"{self.working_df.at[next_activity_idx, 'destination']} の滞在時間を{reduce_minutes}分短縮"],
                "reason": details,
                "action": "shorten_activity",
                "target_index": next_activity_idx,
                "reduce_minutes": reduce_minutes,
            }
            alternatives.append(alt)
            self.pending_alternatives[alt["id"]] = alt

        if event_type == "delay" and next_transport_idx is not None:
            alt = {
                "id": "add_delay_next_transport",
                "title": "次の移動に遅延を反映",
                "description": "直近の移動に遅延時間を加え、後続予定を後ろ倒しします。",
                "changes": [f"{self.working_df.at[next_transport_idx, 'destination']} に15分の遅延を追加"],
                "reason": details,
                "action": "add_delay",
                "target_index": next_transport_idx,
                "delay_minutes": 15,
            }
            alternatives.append(alt)
            self.pending_alternatives[alt["id"]] = alt

        if "cancel_remaining" in intents or "return_now" in intents:
            alt = self._build_return_now_alternative(details)
            if alt:
                alternatives.append(alt)
                self.pending_alternatives[alt["id"]] = alt

        self.event_log.append({
            "timestamp": datetime.now(),
            "event": event_type,
            "details": details,
            "analysis": ", ".join(intents),
        })

        message = self._build_event_message(event_type, intents, details, alternatives)

        return {"message": message, "alternative_plans": alternatives, "analysis": analysis}

    def apply_alternative(self, alt_id: str) -> Dict[str, Any]:
        alt = self.pending_alternatives.get(alt_id)
        if not alt:
            return {"message": "代替案が見つかりませんでした。"}

        action = alt.get("action")
        if action == "transport_change":
            result = self.update_transport_step(
                int(alt["target_index"]),
                str(alt["new_mode"]),
                reason=self._format_transport_change(
                    int(alt["target_index"]),
                    str(self.working_df.at[int(alt["target_index"]), "transport_mode"] or "walk"),
                    str(alt["new_mode"]),
                ),
            )
        elif action == "shorten_activity":
            result = self._shorten_activity(int(alt["target_index"]), int(alt.get("reduce_minutes", 20)), reason="イベント対応で滞在時間を短縮")
        elif action == "swap_with_future_indoor":
            result = self._swap_rows(int(alt["from_index"]), int(alt["to_index"]), reason=str(alt.get("reason", "屋内優先へ並び替え")))
        elif action == "replace_with_indoor":
            result = self._replace_activity_with_indoor(int(alt["target_index"]), alt.get("place", {}), reason=str(alt.get("reason", "屋内代替へ差し替え")))
        elif action == "return_now":
            result = self._return_now(reason=str(alt.get("reason", "以降の予定を中止して戻る")))
        elif action == "add_delay":
            result = self._add_delay_to_step(
                int(alt["target_index"]),
                int(alt.get("delay_minutes", 15)),
                reason="遅延を旅程に反映",
            )
        else:
            result = {"message": "未対応の代替案です。"}

        self.pending_alternatives = {}
        self._sync_df_status()
        return result

    def update_transport_step(self, step_index: int, new_mode: str, reason: str = "") -> Dict[str, Any]:
        if step_index < 0 or step_index >= len(self.working_df):
            return {"message": "対象ステップが見つかりません。"}
        if not bool(self.working_df.at[step_index, "is_transport"]):
            return {"message": "移動ステップではありません。"}

        row = self.working_df.iloc[step_index]
        old_mode = str(row.get("transport_mode") or "walk")
        new_mode = (new_mode or old_mode).lower()
        if old_mode == new_mode:
            return {"message": "移動手段はすでにその設定です。"}

        duration_before = int(row.get("duration_minutes") or 0)
        duration_after = self._estimate_transport_duration(step_index, new_mode, fallback_minutes=max(1, duration_before))
        delta = duration_after - duration_before

        self.working_df.at[step_index, "original_transport_mode"] = old_mode if pd.isna(self.working_df.at[step_index, "original_transport_mode"]) else self.working_df.at[step_index, "original_transport_mode"]
        self.working_df.at[step_index, "transport_mode"] = new_mode
        self.working_df.at[step_index, "duration_minutes"] = duration_after
        self.working_df.at[step_index, "is_modified_by_event"] = True
        note = reason or self._format_transport_change(step_index, old_mode, new_mode)
        self.working_df.at[step_index, "modification_note"] = note
        self.working_df.at[step_index, "execution_status"] = "rerouted"
        self.step_status[step_index] = "rerouted" if step_index != self.current_step else "in_progress"

        start_dt = self._parse_time(self.working_df.at[step_index, "start_time"])
        new_end_dt = start_dt + timedelta(minutes=duration_after)
        self.working_df.at[step_index, "end_time"] = new_end_dt.strftime("%H:%M")

        origin_name, destination_name = self._transport_endpoints(step_index)
        self.working_df.at[step_index, "route_url"] = self._build_route_url(origin_name, destination_name, new_mode)
        self.working_df.at[step_index, "route_from"] = origin_name
        self.working_df.at[step_index, "route_to"] = destination_name
        self.working_df.at[step_index, "route_line_simple"] = self.TRANSPORT_LABELS.get(new_mode, new_mode)
        self.working_df.at[step_index, "route_summary"] = self._build_route_summary(origin_name, destination_name, new_mode, self.TRANSPORT_LABELS.get(new_mode, new_mode), duration_after)
        self._shift_following_steps_same_day(step_index, delta)
        self._sync_df_status()
        return {
            "message": f"移動手段を {self.TRANSPORT_LABELS.get(old_mode, old_mode)} → {self.TRANSPORT_LABELS.get(new_mode, new_mode)} に変更しました。",
            "duration_delta": delta,
        }

    def _shorten_activity(self, step_index: int, reduce_minutes: int, reason: str) -> Dict[str, Any]:
        if step_index < 0 or step_index >= len(self.working_df):
            return {"message": "対象ステップが見つかりません。"}
        if bool(self.working_df.at[step_index, "is_transport"]):
            return {"message": "スポットステップではありません。"}

        duration_before = int(self.working_df.at[step_index, "duration_minutes"] or 0)
        duration_after = max(15, duration_before - reduce_minutes)
        delta = duration_after - duration_before
        start_dt = self._parse_time(self.working_df.at[step_index, "start_time"])
        end_dt = start_dt + timedelta(minutes=duration_after)

        self.working_df.at[step_index, "duration_minutes"] = duration_after
        self.working_df.at[step_index, "end_time"] = end_dt.strftime("%H:%M")
        self.working_df.at[step_index, "is_modified_by_event"] = True
        self.working_df.at[step_index, "modification_note"] = f"{reason}: {duration_before}分 → {duration_after}分"
        self.working_df.at[step_index, "execution_status"] = "rerouted"
        if step_index != self.current_step:
            self.step_status[step_index] = "rerouted"
        self._shift_following_steps_same_day(step_index, delta)
        self._sync_df_status()
        return {"message": "次の予定の滞在時間を短めに調整しました。"}

    def _swap_rows(self, from_index: int, to_index: int, reason: str) -> Dict[str, Any]:
        day = self.working_df.at[from_index, "day"]
        if self.working_df.at[to_index, "day"] != day:
            return {"message": "同じ日の予定のみ入れ替えできます。"}
        cols = list(self.working_df.columns)
        row_a = self.working_df.iloc[from_index].copy()
        row_b = self.working_df.iloc[to_index].copy()
        preserve_a = (row_a["start_time"], row_a["end_time"], row_a["sequence"])
        preserve_b = (row_b["start_time"], row_b["end_time"], row_b["sequence"])
        for c in cols:
            self.working_df.at[from_index, c] = row_b.get(c)
            self.working_df.at[to_index, c] = row_a.get(c)
        self.working_df.at[from_index, "start_time"], self.working_df.at[from_index, "end_time"], self.working_df.at[from_index, "sequence"] = preserve_a
        self.working_df.at[to_index, "start_time"], self.working_df.at[to_index, "end_time"], self.working_df.at[to_index, "sequence"] = preserve_b
        for idx in [from_index, to_index]:
            self.working_df.at[idx, "is_modified_by_event"] = True
            self.working_df.at[idx, "modification_note"] = reason
            if idx != self.current_step:
                self.step_status[idx] = "rerouted"
        self._sync_df_status()
        return {"message": "屋内の予定を前倒ししました。"}

    def _replace_activity_with_indoor(self, step_index: int, place: Dict[str, Any], reason: str) -> Dict[str, Any]:
        if step_index < 0 or step_index >= len(self.working_df):
            return {"message": "対象ステップが見つかりません。"}
        row = self.working_df.iloc[step_index]
        if bool(row.get("is_transport")):
            return {"message": "スポットステップではありません。"}
        self.working_df.at[step_index, "destination"] = place.get("name") or "近場の屋内スポット"
        self.working_df.at[step_index, "purpose"] = "activity"
        self.working_df.at[step_index, "genre"] = place.get("genre") or "indoor_alt"
        self.working_df.at[step_index, "address"] = place.get("formatted_address") or self.working_df.at[step_index, "address"]
        self.working_df.at[step_index, "latitude"] = place.get("latitude") or self.working_df.at[step_index, "latitude"]
        self.working_df.at[step_index, "longitude"] = place.get("longitude") or self.working_df.at[step_index, "longitude"]
        self.working_df.at[step_index, "one_point"] = place.get("one_point") or "雨を避けながら楽しめる近場の屋内候補です。"
        self.working_df.at[step_index, "is_modified_by_event"] = True
        self.working_df.at[step_index, "modification_note"] = reason
        if step_index != self.current_step:
            self.step_status[step_index] = "rerouted"
        self._sync_df_status()
        return {"message": "次の屋外予定を屋内スポットへ差し替えました。"}

    def _return_now(self, reason: str) -> Dict[str, Any]:
        next_activity_idx = self._find_next_activity_index()
        if next_activity_idx is None:
            return {"message": "残りの予定がありません。"}
        final_destination = self._find_final_destination()
        for idx in range(next_activity_idx + 1, len(self.working_df)):
            self.step_status[idx] = "cancelled"
            self.working_df.at[idx, "is_modified_by_event"] = True
            self.working_df.at[idx, "modification_note"] = "以降の予定をキャンセル"
        self.working_df.at[next_activity_idx, "destination"] = final_destination
        self.working_df.at[next_activity_idx, "purpose"] = "return"
        self.working_df.at[next_activity_idx, "genre"] = "return"
        self.working_df.at[next_activity_idx, "one_point"] = "以降の予定を取りやめて、ここで旅程を終了します。"
        self.working_df.at[next_activity_idx, "is_modified_by_event"] = True
        self.working_df.at[next_activity_idx, "modification_note"] = reason
        self.step_status[next_activity_idx] = "rerouted"
        self._sync_df_status()
        return {"message": f"以降の予定をキャンセルし、{final_destination}へ戻る案に切り替えました。"}

    def _build_swap_with_indoor_alternative(self, next_outdoor_idx: int, details: str) -> Optional[Dict[str, Any]]:
        row = self.working_df.iloc[next_outdoor_idx]
        for idx in range(next_outdoor_idx + 1, len(self.working_df)):
            candidate = self.working_df.iloc[idx]
            if candidate["day"] != row["day"]:
                break
            if bool(candidate.get("is_transport")):
                continue
            if self.step_status.get(idx) == "completed":
                continue
            if not is_outdoor_row(candidate.to_dict()):
                return {
                    "id": f"swap_indoor_{next_outdoor_idx}_{idx}",
                    "title": f"{candidate.get('destination')} を先に回る",
                    "description": "後ろにある屋内スポットを前倒しして、雨の影響を避けます。",
                    "changes": [f"{row.get('destination')} の代わりに {candidate.get('destination')} を先に訪問"],
                    "reason": details,
                    "action": "swap_with_future_indoor",
                    "from_index": next_outdoor_idx,
                    "to_index": idx,
                }
        return None

    def _build_indoor_replacement_alternative(self, next_outdoor_idx: int, details: str) -> Optional[Dict[str, Any]]:
        row = self.working_df.iloc[next_outdoor_idx].to_dict()
        place = self._find_nearby_indoor_place(row)
        if not place:
            place = {
                "name": f"近場の屋内スポット（{row.get('destination')}の代替）",
                "formatted_address": row.get("address") or "近隣エリア",
                "latitude": row.get("latitude"),
                "longitude": row.get("longitude"),
                "genre": "indoor_alt",
                "one_point": "雨を避けながら動線を大きく崩さない代替候補です。",
            }
        return {
            "id": f"replace_indoor_{next_outdoor_idx}",
            "title": "近場の屋内スポットへ差し替え",
            "description": "次の屋外スポットを近場の屋内候補に差し替えます。",
            "changes": [f"{row.get('destination')} → {place.get('name')}"],
            "reason": details,
            "action": "replace_with_indoor",
            "target_index": next_outdoor_idx,
            "place": place,
        }

    def _build_return_now_alternative(self, details: str) -> Optional[Dict[str, Any]]:
        final_destination = self._find_final_destination()
        if not final_destination:
            return None
        return {
            "id": "return_now",
            "title": f"残りをキャンセルして {final_destination} へ戻る",
            "description": "以降の予定を取りやめて、旅程を終了します。",
            "changes": ["残りの予定をキャンセル", f"最終目的地を {final_destination} に切り替え"],
            "reason": details,
            "action": "return_now",
        }


    def _add_delay_to_step(self, step_index: int, delay_minutes: int, reason: str) -> Dict[str, Any]:
        if step_index < 0 or step_index >= len(self.working_df):
            return {"message": "対象ステップが見つかりません。"}
        start_dt = self._parse_time(self.working_df.at[step_index, "start_time"])
        end_dt = self._parse_time(self.working_df.at[step_index, "end_time"]) + timedelta(minutes=delay_minutes)
        self.working_df.at[step_index, "end_time"] = end_dt.strftime("%H:%M")
        self.working_df.at[step_index, "duration_minutes"] = int(self.working_df.at[step_index, "duration_minutes"] or 0) + delay_minutes
        self.working_df.at[step_index, "is_modified_by_event"] = True
        self.working_df.at[step_index, "modification_note"] = f"{reason}: +{delay_minutes}分"
        self.total_delays += delay_minutes
        self._shift_following_steps_same_day(step_index, delay_minutes)
        self._sync_df_status()
        return {"message": f"{delay_minutes}分の遅延を反映しました。"}

    def replace_future_plan(self, new_future_df: pd.DataFrame, reason: str = "", scope: str = "all_future") -> Dict[str, Any]:
        scope_indices = self._iter_scope_indices(scope)
        if not scope_indices:
            return {"message": "組み直す対象の残り旅程がありません。"}
        replace_start = scope_indices[0]
        replace_end = scope_indices[-1]
        prefix_df = self.working_df.iloc[:replace_start].copy().reset_index(drop=True)
        suffix_df = self.working_df.iloc[replace_end + 1:].copy().reset_index(drop=True)
        future_df = new_future_df.copy().reset_index(drop=True)
        if not future_df.empty:
            day_offset = int(prefix_df.iloc[-1].get("day", 1)) - int(future_df.iloc[0].get("day", 1))
            future_df["day"] = future_df["day"].astype(int) + day_offset
            for day in sorted(future_df["day"].dropna().unique()):
                day_mask = future_df["day"] == day
                future_df.loc[day_mask, "sequence"] = range(1, int(day_mask.sum()) + 1)
            if reason:
                first_idx = future_df.index[0]
                future_df.at[first_idx, "is_modified_by_event"] = True
                future_df.at[first_idx, "modification_note"] = f"再計画: {reason}"
        combined = pd.concat([prefix_df, future_df, suffix_df], ignore_index=True)
        self.working_df = combined.reset_index(drop=True)
        self.step_status = {}
        for idx in range(len(self.working_df)):
            if idx < self.current_step:
                self.step_status[idx] = "completed"
            elif idx == self.current_step:
                self.step_status[idx] = "in_progress" if self.execution_started else "pending"
            else:
                self.step_status[idx] = "pending"
        self.pending_alternatives = {}
        self._ensure_status_columns()
        self._sync_df_status()
        return {"message": "残り旅程を組み直して反映しました。"}

    def _cancel_adjacent_transport_rows(self, activity_idx: int, reason: str) -> None:
        target_day = self.working_df.at[activity_idx, "day"]
        for idx in [activity_idx - 1, activity_idx + 1]:
            if idx < 0 or idx >= len(self.working_df):
                continue
            if self.working_df.at[idx, "day"] != target_day:
                continue
            if not bool(self.working_df.at[idx, "is_transport"]):
                continue
            if self.step_status.get(idx) == "completed":
                continue
            self.step_status[idx] = "cancelled"
            self.working_df.at[idx, "is_modified_by_event"] = True
            self.working_df.at[idx, "modification_note"] = reason

    def cancel_next_activity_only(self, reason: str = "次の予定のみキャンセル") -> Dict[str, Any]:
        next_idx = self._find_next_activity_index()
        if next_idx is None:
            return {"message": "キャンセルできる次の予定がありません。"}
        destination = str(self.working_df.at[next_idx, "destination"])
        self.step_status[next_idx] = "cancelled"
        self.working_df.at[next_idx, "is_modified_by_event"] = True
        self.working_df.at[next_idx, "modification_note"] = reason
        self._cancel_adjacent_transport_rows(next_idx, reason)
        self._sync_df_status()
        return {"message": f"次の予定『{destination}』をキャンセルしました。"}

    def cancel_today_and_move_to_lodging(self, reason: str = "本日の残り予定をキャンセルして宿泊先へ移動") -> Dict[str, Any]:
        next_idx = self._find_next_activity_index()
        if next_idx is None:
            return {"message": "本日分を切り替えられる残り予定がありません。"}

        target_day = self.working_df.at[next_idx, "day"]
        lodging_name = self._find_lodging_for_day(int(target_day)) or self._find_any_lodging_destination()
        if not lodging_name:
            return {"message": "宿泊先候補が旅程内で見つかりませんでした。"}

        for idx in range(next_idx + 1, len(self.working_df)):
            if self.working_df.at[idx, "day"] != target_day:
                break
            self.step_status[idx] = "cancelled"
            self.working_df.at[idx, "is_modified_by_event"] = True
            self.working_df.at[idx, "modification_note"] = "本日の残り予定をキャンセル"

        self.working_df.at[next_idx, "destination"] = lodging_name
        self.working_df.at[next_idx, "purpose"] = "hotel"
        self.working_df.at[next_idx, "genre"] = "hotel"
        self.working_df.at[next_idx, "one_point"] = "本日の残り予定を取りやめて、宿泊先へ向かいます。"
        self.working_df.at[next_idx, "is_modified_by_event"] = True
        self.working_df.at[next_idx, "modification_note"] = reason
        self.step_status[next_idx] = "rerouted" if next_idx != self.current_step else "in_progress"
        self._sync_df_status()
        return {"message": f"本日の残り予定をキャンセルし、{lodging_name} へ向かう流れに切り替えました。"}

    def return_to_final_destination_now(self, reason: str = "残り予定をキャンセルして帰着地へ移動") -> Dict[str, Any]:
        return self._return_now(reason=reason)

    def _find_lodging_for_day(self, day: int) -> Optional[str]:
        day_df = self.working_df[self.working_df["day"] == day]
        for _, row in day_df.iterrows():
            if bool(row.get("is_transport")):
                continue
            destination = str(row.get("destination") or "")
            purpose = str(row.get("purpose") or "")
            genre = str(row.get("genre") or "")
            if any(k in destination.lower() for k in ["hotel", "inn", "hostel"]) or "ホテル" in destination:
                return destination
            if any(k in purpose.lower() for k in ["hotel", "stay", "rest"]) or any(k in genre.lower() for k in ["hotel", "lodging"]):
                return destination
        return None

    def _find_any_lodging_destination(self) -> Optional[str]:
        for idx in range(len(self.working_df)):
            if bool(self.working_df.at[idx, "is_transport"]):
                continue
            destination = str(self.working_df.at[idx, "destination"] or "")
            purpose = str(self.working_df.at[idx, "purpose"] or "")
            genre = str(self.working_df.at[idx, "genre"] or "")
            if any(k in destination.lower() for k in ["hotel", "inn", "hostel"]) or "ホテル" in destination:
                return destination
            if any(k in purpose.lower() for k in ["hotel", "stay", "rest"]) or any(k in genre.lower() for k in ["hotel", "lodging"]):
                return destination
        return None

    def _find_future_transport_indices(self) -> List[int]:
        start = self.current_step if self.execution_started else 0
        return [
            idx for idx in range(start, len(self.working_df))
            if bool(self.working_df.at[idx, "is_transport"]) and self.step_status.get(idx) not in {"completed", "cancelled"}
        ]

    def _find_next_transport_index(self) -> Optional[int]:
        items = self._find_future_transport_indices()
        return items[0] if items else None

    def _find_next_activity_index(self) -> Optional[int]:
        start = self.current_step if self.execution_started else 0
        for idx in range(start, len(self.working_df)):
            if not bool(self.working_df.at[idx, "is_transport"]) and self.step_status.get(idx) not in {"completed", "cancelled"}:
                return idx
        return None

    def _find_next_outdoor_activity_index(self) -> Optional[int]:
        start = self.current_step if self.execution_started else 0
        for idx in range(start, len(self.working_df)):
            if self.step_status.get(idx) in {"completed", "cancelled"}:
                continue
            row = self.working_df.iloc[idx].to_dict()
            if not bool(row.get("is_transport")) and is_outdoor_row(row):
                return idx
        return None

    def _find_nearby_indoor_place(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self.places is None:
            return None
        location = None
        lat = row.get("latitude")
        lng = row.get("longitude")
        if pd.notna(lat) and pd.notna(lng):
            location = (float(lat), float(lng))
        area = str(row.get("address") or row.get("destination") or "近く")
        queries = [f"{area} 博物館", f"{area} 美術館", f"{area} カフェ"]
        for q in queries:
            try:
                results = self.places.search_text(q, location=location, radius=3000)
            except Exception:
                results = []
            if results:
                top = results[0]
                genre = "museum"
                types = top.get("types", []) or []
                if "art_gallery" in types:
                    genre = "art_gallery"
                elif "cafe" in types:
                    genre = "cafe"
                return {**top, "genre": genre, "one_point": "近場で立ち寄りやすい屋内候補です。"}
        return None

    def _estimate_transport_duration(self, step_index: int, mode: str, fallback_minutes: int) -> int:
        prev_idx = self._find_previous_activity(step_index)
        next_idx = self._find_next_activity(step_index)
        if prev_idx is None or next_idx is None:
            return max(1, fallback_minutes)

        prev_row = self.working_df.iloc[prev_idx]
        next_row = self.working_df.iloc[next_idx]
        lat1, lng1 = prev_row.get("latitude"), prev_row.get("longitude")
        lat2, lng2 = next_row.get("latitude"), next_row.get("longitude")
        if pd.notna(lat1) and pd.notna(lng1) and pd.notna(lat2) and pd.notna(lng2):
            if self.routes is not None:
                try:
                    route = self.routes.compute_route((float(lat1), float(lng1)), (float(lat2), float(lng2)), mode=mode)
                    if route and route.get("duration_minutes"):
                        return max(1, int(route["duration_minutes"]))
                except Exception:
                    pass
            distance_km = self._compute_distance_km(float(lat1), float(lng1), float(lat2), float(lng2))
            return self._fallback_duration_minutes(mode, distance_km)
        return max(1, fallback_minutes)

    def _find_previous_activity(self, step_index: int) -> Optional[int]:
        for idx in range(step_index - 1, -1, -1):
            if not bool(self.working_df.at[idx, "is_transport"]):
                return idx
        return None

    def _find_next_activity(self, step_index: int) -> Optional[int]:
        for idx in range(step_index + 1, len(self.working_df)):
            if not bool(self.working_df.at[idx, "is_transport"]):
                return idx
        return None

    def _find_final_destination(self) -> str:
        for idx in range(len(self.working_df) - 1, -1, -1):
            if not bool(self.working_df.at[idx, "is_transport"]):
                return str(self.working_df.at[idx, "destination"])
        return "帰着地"

    def _transport_endpoints(self, step_index: int) -> tuple[str, str]:
        prev_idx = self._find_previous_activity(step_index)
        next_idx = self._find_next_activity(step_index)
        origin = str(self.working_df.at[prev_idx, "destination"]) if prev_idx is not None else "現在地"
        destination = str(self.working_df.at[next_idx, "destination"]) if next_idx is not None else str(self.working_df.at[step_index, "destination"])
        return origin, destination

    def _build_route_url(self, origin: str, destination: str, mode: str) -> str:
        if self.routes is not None:
            try:
                return self.routes.build_google_maps_directions_url(origin, destination, mode)
            except Exception:
                pass
        import urllib.parse
        mode_map = {
            "walk": "walking",
            "train": "transit",
            "car": "driving",
            "private_car": "driving",
            "rental_car": "driving",
            "taxi": "driving",
            "bike": "bicycling",
        }
        travelmode = mode_map.get(str(mode).lower(), "walking")
        return (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={urllib.parse.quote(str(origin))}"
            f"&destination={urllib.parse.quote(str(destination))}"
            f"&travelmode={travelmode}"
        )

    def _shift_following_steps_same_day(self, step_index: int, delta_minutes: int) -> None:
        if delta_minutes == 0:
            return
        day = self.working_df.at[step_index, "day"]
        for idx in range(step_index + 1, len(self.working_df)):
            if self.working_df.at[idx, "day"] != day:
                break
            if self.step_status.get(idx) == "cancelled":
                continue
            start_dt = self._parse_time(self.working_df.at[idx, "start_time"]) + timedelta(minutes=delta_minutes)
            end_dt = self._parse_time(self.working_df.at[idx, "end_time"]) + timedelta(minutes=delta_minutes)
            self.working_df.at[idx, "start_time"] = start_dt.strftime("%H:%M")
            self.working_df.at[idx, "end_time"] = end_dt.strftime("%H:%M")

    @staticmethod
    def _parse_time(value: Any) -> datetime:
        return datetime.strptime(str(value), "%H:%M")

    @staticmethod
    def _compute_distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        from math import radians, cos, sin, asin, sqrt

        lon1, lat1, lon2, lat2 = map(radians, [lng1, lat1, lng2, lat2])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        return 6371 * c

    @staticmethod
    def _fallback_duration_minutes(mode: str, distance_km: float) -> int:
        speed_kmh = {
            "walk": 4.5,
            "train": 25.0,
            "car": 22.0,
            "private_car": 22.0,
            "rental_car": 22.0,
            "taxi": 22.0,
            "bike": 12.0,
        }.get(mode, 20.0)
        return max(1, int((distance_km / speed_kmh) * 60))

    def _format_transport_change(self, step_index: int, old_mode: str, new_mode: str) -> str:
        destination = str(self.working_df.at[step_index, "destination"])
        return f"{destination}: {self.TRANSPORT_LABELS.get(old_mode, old_mode)} → {self.TRANSPORT_LABELS.get(new_mode, new_mode)}"

    def _build_route_summary(self, route_from: str, route_to: str, mode: str, line: str, duration: int) -> str:
        mode_label = self.TRANSPORT_LABELS.get(mode, mode)
        if mode == "train":
            return f"{route_from}→{route_to}：{mode_label} {line} {duration}分"
        return f"{route_from}→{route_to}：{mode_label} {duration}分"
