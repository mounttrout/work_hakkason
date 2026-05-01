# -*- coding: utf-8 -*-
"""
services/quality_gate_agent.py
VoyageFlow v6.2.82

Quality Gate Agent:
- Geminiには品質判定だけをさせる
- 修正済みの旅程データは返させない
- app.py側が retry / ask user / accept を制御する
"""

import json
import re
from typing import Callable, Dict, List, Optional

from orchestration.phase1_generation import Phase1Generator


def _trim_text(value: str, limit: int = 12000) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...<trimmed>..."


def _safe_json_extract(raw: str) -> Optional[Dict[str, object]]:
    text = str(raw or "").strip()
    if not text:
        return None

    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start:end + 1]
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


def _safe_text(value, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _normalize_issue(issue: Dict[str, object]) -> Dict[str, object]:
    return {
        "type": _safe_text(issue.get("type"), "issue"),
        "severity": _safe_text(issue.get("severity"), "medium").lower(),
        "location": _safe_text(issue.get("location"), ""),
        "problem": _safe_text(issue.get("problem"), _safe_text(issue.get("issue"), "")),
        "suggestion": _safe_text(issue.get("suggestion"), ""),
        "recommended_action": _safe_text(issue.get("recommended_action"), "ask_user"),
        "user_message": _safe_text(issue.get("user_message"), ""),
    }


def _normalize_quality_result(parsed: Dict[str, object], raw: str) -> Dict[str, object]:
    issues_raw = parsed.get("issues") if isinstance(parsed.get("issues"), list) else []
    issues: List[Dict[str, object]] = []
    for issue in issues_raw[:8]:
        if isinstance(issue, dict):
            issues.append(_normalize_issue(issue))

    status = _safe_text(parsed.get("overall_status"), "")
    if status not in {"ok", "retry_recommended", "user_confirmation_required", "fatal"}:
        if not issues:
            status = "ok"
        elif any(issue.get("severity") in {"critical", "high"} for issue in issues):
            status = "user_confirmation_required"
        else:
            status = "retry_recommended"

    retry_scope = _safe_text(parsed.get("retry_scope"), "none")
    if retry_scope not in {"none", "phase2_phase3_only", "ask_user"}:
        retry_scope = "none"

    try:
        score = int(float(parsed.get("score", 0)))
    except Exception:
        score = 0
    score = max(0, min(100, score))

    safe_to_retry = bool(parsed.get("safe_to_auto_retry", False))
    if status == "retry_recommended" and retry_scope == "phase2_phase3_only":
        safe_to_retry = True
    if status in {"fatal", "user_confirmation_required"}:
        safe_to_retry = False

    return {
        "overall_status": status,
        "score": score,
        "summary": _safe_text(parsed.get("summary"), "品質チェック結果です。"),
        "issues": issues,
        "retry_scope": retry_scope,
        "safe_to_auto_retry": safe_to_retry,
        "raw": raw,
    }


def _build_quality_gate_prompt(
    *,
    natural_plan_text: str,
    phase2_text: str,
    phase3_text: str,
    planning_state: Dict[str, object],
    app_logs_text: str,
) -> str:
    planning_json = json.dumps(planning_state, ensure_ascii=False, default=str)
    return f"""
あなたは旅行アプリ VoyageFlow の Quality Gate Agent です。
あなたの役割は「品質判定のみ」です。旅程を書き換えたり、修正版の旅程を作ったりしてはいけません。

重要:
- 自動修正しない
- 修正版のPhase2/Phase3を返さない
- 問題点、重大度、推奨アクションだけをJSONで返す
- Phase1自然文案が良く、Phase2/Phase3構造化だけが怪しい場合は retry_scope を phase2_phase3_only にする
- ホテルの場所、相撲観戦日、徒歩/電車の好みなどユーザー判断が必要なら user_confirmation_required にする
- 問題が軽微なら ok にする
- 同じような再生成を何度も繰り返させるのではなく、判断分岐があるものはユーザー確認に回す

特に確認すること:
1. 出発地・帰着地の整合性
2. 最終帰着後にホテルや観光ノードが残っていないか
3. ホテルが日程・都市移動と矛盾していないか
4. Phase1自然文とPhase3完成旅程の訪問先・目的が大きくずれていないか
5. 移動カードが欠落していないか
6. 明らかに不自然な移動手段がないか
7. 食事・観光・宿泊など purpose が大きく誤分類されていないか
8. ユーザーが最後に判断すべき問題か、Phase2→Phase3再作成で直りそうな問題か

出力JSON形式:
{{
  "overall_status": "ok | retry_recommended | user_confirmation_required | fatal",
  "score": 0,
  "summary": "全体所見を短く",
  "retry_scope": "none | phase2_phase3_only | ask_user",
  "safe_to_auto_retry": false,
  "issues": [
    {{
      "type": "wrong_hotel | impossible_after_return | purpose_mismatch | transport_mismatch | missing_transport | duplicated_node | user_choice_needed | other",
      "severity": "low | medium | high | critical",
      "location": "Dayや時刻など",
      "problem": "何がおかしいか",
      "suggestion": "どう扱うべきか。修正版データは作らない",
      "recommended_action": "accept | retry_phase2_phase3 | ask_user | block",
      "user_message": "ユーザーに確認する場合の短い文"
    }}
  ]
}}

旅行条件:
{planning_json}

Phase1自然文案:
{_trim_text(natural_plan_text)}

Phase2構造化データ:
{_trim_text(phase2_text)}

Phase3完成旅程:
{_trim_text(phase3_text)}

内部ログ抜粋:
{_trim_text(app_logs_text, 8000)}
""".strip()


def run_quality_gate(
    *,
    natural_plan_text: str,
    phase2_text: str,
    phase3_text: str,
    planning_state: Dict[str, object],
    app_logs_text: str,
    logger: Optional[Callable[[str, str], None]] = None,
) -> Dict[str, object]:
    prompt = _build_quality_gate_prompt(
        natural_plan_text=natural_plan_text,
        phase2_text=phase2_text,
        phase3_text=phase3_text,
        planning_state=planning_state,
        app_logs_text=app_logs_text,
    )

    try:
        generator = Phase1Generator(logger=logger)
        raw = generator.generate_trip_plan(prompt, temperature=0.0).strip()
        parsed = _safe_json_extract(raw) or {}
        if not parsed:
            return {
                "overall_status": "user_confirmation_required",
                "score": 0,
                "summary": "Quality GateのJSON解析に失敗しました。出力を確認してください。",
                "issues": [],
                "retry_scope": "none",
                "safe_to_auto_retry": False,
                "raw": raw,
            }
        return _normalize_quality_result(parsed, raw)
    except Exception as e:
        if logger is not None:
            try:
                logger("Quality Gate", f"Quality Gate実行に失敗: {e}")
            except Exception:
                pass
        return {
            "overall_status": "user_confirmation_required",
            "score": 0,
            "summary": "Quality Gateの実行に失敗しました。今回は既存の完成旅程を確認してください。",
            "issues": [],
            "retry_scope": "none",
            "safe_to_auto_retry": False,
            "raw": str(e),
        }
