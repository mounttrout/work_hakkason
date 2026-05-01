# -*- coding: utf-8 -*-
"""
services/quality_gate_agent.py
VoyageFlow v6.2.83

Quality Gate Agent:
- Geminiには完成旅程のチェックリスト判定だけをさせる
- 修正済みの旅程データは返させない
- 明確な安全補正は app.py 側のコードホワイトリストで処理する
- 判断分岐があるものはユーザー確認へ回す
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


def _normalize_check(check: Dict[str, object]) -> Dict[str, object]:
    status = _safe_text(check.get("status"), "warning").lower()
    if status not in {"pass", "warning", "fail"}:
        status = "warning"

    severity = _safe_text(check.get("severity"), "medium").lower()
    if severity not in {"low", "medium", "high", "critical"}:
        severity = "medium"

    action = _safe_text(check.get("recommended_action"), "")
    if action not in {"accept", "auto_fix", "retry_phase2_phase3", "ask_user", "block"}:
        if status == "pass":
            action = "accept"
        elif severity in {"high", "critical"}:
            action = "ask_user"
        else:
            action = "ask_user"

    normalized = {
        "id": _safe_text(check.get("id"), _safe_text(check.get("type"), "quality_check")),
        "category": _safe_text(check.get("category"), "quality"),
        "status": status,
        "severity": severity,
        "location": _safe_text(check.get("location"), ""),
        "evidence": _safe_text(check.get("evidence"), _safe_text(check.get("problem"), _safe_text(check.get("issue"), ""))),
        "suggestion": _safe_text(check.get("suggestion"), ""),
        "recommended_action": action,
        "user_message": _safe_text(check.get("user_message"), ""),
        "source": "llm",
    }
    auto_fix = check.get("auto_fix")
    if isinstance(auto_fix, dict):
        normalized["auto_fix"] = auto_fix
    return normalized


def _check_to_issue(check: Dict[str, object]) -> Dict[str, object]:
    return {
        "type": _safe_text(check.get("id"), "quality_check"),
        "severity": _safe_text(check.get("severity"), "medium"),
        "location": _safe_text(check.get("location"), ""),
        "problem": _safe_text(check.get("evidence"), ""),
        "suggestion": _safe_text(check.get("suggestion"), ""),
        "recommended_action": _safe_text(check.get("recommended_action"), "ask_user"),
        "user_message": _safe_text(check.get("user_message"), ""),
    }


def _normalize_issue(issue: Dict[str, object]) -> Dict[str, object]:
    return {
        "type": _safe_text(issue.get("type"), "issue"),
        "severity": _safe_text(issue.get("severity"), "medium").lower(),
        "location": _safe_text(issue.get("location"), ""),
        "problem": _safe_text(issue.get("problem"), _safe_text(issue.get("issue"), "")),
        "suggestion": _safe_text(issue.get("suggestion"), ""),
        "recommended_action": _safe_text(issue.get("recommended_action"), "ask_user"),
        "user_message": _safe_text(issue.get("user_message"), ""),
        "source": "llm",
    }


def _normalize_quality_result(parsed: Dict[str, object], raw: str) -> Dict[str, object]:
    checks_raw = parsed.get("checks") if isinstance(parsed.get("checks"), list) else []
    checks: List[Dict[str, object]] = []
    for check in checks_raw[:20]:
        if isinstance(check, dict):
            checks.append(_normalize_check(check))

    # 後方互換: issues形式だけ返った場合は checks に寄せる
    if not checks:
        issues_raw = parsed.get("issues") if isinstance(parsed.get("issues"), list) else []
        for issue in issues_raw[:12]:
            if isinstance(issue, dict):
                normalized_issue = _normalize_issue(issue)
                checks.append(_normalize_check({
                    "id": normalized_issue["type"],
                    "category": "legacy_issue",
                    "status": "fail",
                    "severity": normalized_issue["severity"],
                    "location": normalized_issue["location"],
                    "evidence": normalized_issue["problem"],
                    "suggestion": normalized_issue["suggestion"],
                    "recommended_action": normalized_issue["recommended_action"],
                    "user_message": normalized_issue["user_message"],
                }))

    issues = [_check_to_issue(check) for check in checks if check.get("status") in {"fail", "warning"}]

    status = _safe_text(parsed.get("overall_status"), "")
    allowed_status = {"ok", "auto_fix_available", "auto_fix_applied", "retry_recommended", "user_confirmation_required", "fatal"}
    if status not in allowed_status:
        if not issues:
            status = "ok"
        elif any(issue.get("recommended_action") == "auto_fix" for issue in issues):
            status = "auto_fix_available"
        elif any(issue.get("recommended_action") == "retry_phase2_phase3" for issue in issues):
            status = "retry_recommended"
        elif any(issue.get("severity") in {"critical", "high"} for issue in issues):
            status = "user_confirmation_required"
        else:
            status = "user_confirmation_required"

    retry_scope = _safe_text(parsed.get("retry_scope"), "none")
    if retry_scope not in {"none", "phase2_phase3_only", "ask_user"}:
        retry_scope = "none"

    try:
        score = int(float(parsed.get("score", 0)))
    except Exception:
        score = 0
    if score <= 0:
        score = 100
        for check in checks:
            if check.get("status") == "pass":
                continue
            score -= {"low": 5, "medium": 10, "high": 22, "critical": 35}.get(check.get("severity"), 10)
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
        "checks": checks,
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
あなたは旅行アプリ VoyageFlow の Phase3 Quality Gate Agent です。
あなたの役割は「完成旅程をチェックリストに沿って判定すること」だけです。
旅程を書き換えたり、修正版のPhase2/Phase3を作ったりしてはいけません。

基本方針:
- LLMは品質判定だけを行う。
- 自動修正してよいかどうかは recommended_action で示すだけ。
- 実際の修正はアプリ側コードがホワイトリストで制御する。
- 判断が必要なものは ask_user にする。
- Phase1自然文案が良く、Phase2/Phase3構造化だけが怪しい場合は retry_phase2_phase3 を提案する。
- 同じような再生成を何度も繰り返させず、判断分岐があるものはユーザー確認に回す。

必ず次のチェックリストを1項目ずつ意識して判定してください。

[旅行条件チェック]
1. 旅行日数が条件と合っているか。
2. 出発地から始まっているか。
3. 最終帰着地に戻っているか。
4. 主目的地・固定要望が反映されているか。

[ホテルチェック]
5. 泊数分の宿泊があるか。
6. genre=hotel なのに purpose=transport になっていないか。
7. 帰着後にホテルや観光ノードが残っていないか。
8. ホテル名が抽象名の場合、無理に具体ホテル扱いしていないか。

[移動カードチェック]
9. スポット間に移動カードがあるか。
10. 同一地点移動がないか。
11. 徒歩圏内なのに電車・バスになっていないか。
12. 長距離なのに短すぎる移動時間になっていないか。
13. ユーザーの移動希望と矛盾していないか。
※徒歩圏内の短距離移動をwalkにすることは「電車メイン」と矛盾しません。

[目的分類チェック]
14. 観光施設・資料館・博物館が meal になっていないか。
15. 食事場所が観光施設扱いになっていないか。
16. 駅・ホテルが不自然な長時間滞在スポットになっていないか。

[イベント・営業日チェック]
17. 相撲・歌舞伎など日時依存イベントは日付確認が必要か。
18. 開催期間外・公演期間外の可能性がある場合は ask_user にする。
19. 自動で日程変更・スポット変更はしない。

recommended_action の基準:
- accept: 問題なし
- auto_fix: 同一地点移動削除、短距離train→walk、明確なpurpose誤分類など、コード側で安全補正できそうなもの
- retry_phase2_phase3: Phase1は良いが、Phase2/Phase3構造化の再作成で直りそうなもの
- ask_user: 相撲開催日、ホテル選択、日程変更、旅程方針などユーザー判断が必要なもの
- block: 重大でこのまま進めるべきでないもの

出力JSON形式:
{{
  "overall_status": "ok | auto_fix_available | retry_recommended | user_confirmation_required | fatal",
  "score": 0,
  "summary": "全体所見を短く",
  "retry_scope": "none | phase2_phase3_only | ask_user",
  "safe_to_auto_retry": false,
  "checks": [
    {{
      "id": "short_distance_train_to_walk",
      "category": "transport",
      "status": "pass | warning | fail",
      "severity": "low | medium | high | critical",
      "location": "Dayや時刻など",
      "evidence": "成立/不成立の根拠",
      "suggestion": "どう扱うべきか。修正版データは作らない",
      "recommended_action": "accept | auto_fix | retry_phase2_phase3 | ask_user | block",
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
                "checks": [],
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
            "checks": [],
            "issues": [],
            "retry_scope": "none",
            "safe_to_auto_retry": False,
            "raw": str(e),
        }
