# -*- coding: utf-8 -*-
"""
VoyageFlow v6.2.64
Spot Info Agent rules

目的:
- app.pyにスポット確認ロジックを増やし続けない
- 確実に説明できる辞書・公式リンクだけを扱う
- LLMに開催日・休館日・営業時間を作らせない

注意:
- ここはまずハッカソンMVP向けの小さな辞書です。
- 未登録スポットは services.spot_info_agent 側で公式検索リンクへfallbackします。
"""

SPOT_RELIABILITY_RULES = {
    "両国国技館": {
        "type": "event_date",
        "official_url": "https://kokugikan.sumo.or.jp/Schedule/show/2026-05",
        "event_keywords": ["相撲", "大相撲", "五月場所", "夏場所"],
        "valid_ranges": [("2026-05-10", "2026-05-24")],
        "warning": "2026年5月5日は大相撲五月場所の開催期間外です。五月場所は2026-05-10〜2026-05-24の公式予定です。",
        "alternative": "代替案: 相撲博物館、両国散策、ちゃんこ料理、または開催期間中への日程変更を検討してください。",
    },
    "東京国立博物館": {
        "type": "opening_hours",
        "official_url": "https://www.tnm.jp/modules/r_free_page/index.php?id=113",
        "closed_weekdays": [0],
        "holiday_monday_open": True,
        "open_time": "09:30",
        "close_time": "17:00",
        "last_entry_time": "16:30",
        "warning": "東京国立博物館は原則月曜休館、ただし月曜が祝休日の場合は開館し翌平日に休館です。来館前に公式カレンダーを確認してください。",
    },
    "国立西洋美術館": {
        "type": "opening_hours",
        "official_url": "https://www.nmwa.go.jp/jp/visit/",
        "closed_weekdays": [0],
        "holiday_monday_open": True,
        "open_time": "09:30",
        "close_time": "17:30",
        "fri_sat_close_time": "20:00",
        "last_entry_minutes_before_close": 30,
        "warning": "国立西洋美術館は原則月曜休館、ただし祝休日の場合は開館し翌平日に休館です。開館時間外や休館日に当たらないか公式情報を確認してください。",
    },
    "歌舞伎座": {
        "type": "official_confirmation",
        "official_url": "https://www.kabuki-bito.jp/theaters/kabukiza/",
        "warning": "歌舞伎座の演目・開演時刻は月ごとに変わります。旅程時刻と公演時刻が合うか公式公演情報で確認してください。",
    },
    "東京芸術劇場": {
        "type": "official_confirmation",
        "official_url": "https://www.geigeki.jp/",
        "warning": "コンサート・観劇は日時指定イベントです。会場名だけでは開催有無を確定できないため、公式スケジュールとチケット情報を確認してください。",
    },
}

# v6.2.59内蔵値と同じ2026年祝日辞書。
# 祝日情報は年ごとに変わるため、今後は data/japanese_holidays_YYYY.py などへ分離予定。
JAPANESE_PUBLIC_HOLIDAYS_2026 = {
    "2026-01-01", "2026-01-12", "2026-02-11", "2026-02-23", "2026-03-20",
    "2026-04-29", "2026-05-03", "2026-05-04", "2026-05-05", "2026-05-06",
    "2026-07-20", "2026-08-11", "2026-09-21", "2026-09-22", "2026-09-23",
    "2026-10-12", "2026-11-03", "2026-11-23",
}

SPOT_INFO_SOURCES = {
    "両国国技館": {
        "category": "venue",
        "primary_url": "https://kokugikan.sumo.or.jp/",
        "primary_label": "公式情報を見る",
        "note": "大相撲開催日は公式スケジュール確認が必要です。",
    },
    "東京国立博物館": {
        "category": "museum",
        "primary_url": "https://www.tnm.jp/",
        "primary_label": "公式カレンダーを見る",
        "note": "休館日・特別展は公式ページで確認してください。",
    },
    "国立西洋美術館": {
        "category": "museum",
        "primary_url": "https://www.nmwa.go.jp/",
        "primary_label": "公式情報を見る",
        "note": "休館日・開館時間・企画展は公式ページで確認してください。",
    },
    "歌舞伎座": {
        "category": "theater",
        "primary_url": "https://www.kabuki-bito.jp/theaters/kabukiza/",
        "primary_label": "公演情報を見る",
        "note": "演目・開演時刻・チケット状況は公式ページ確認が必要です。",
    },
    "東京芸術劇場": {
        "category": "theater",
        "primary_url": "https://www.geigeki.jp/",
        "primary_label": "公演スケジュールを見る",
        "note": "日時指定イベントのため公式スケジュール確認が必要です。",
    },
    "浅草寺": {
        "category": "shrine_temple",
        "primary_url": "https://www.senso-ji.jp/",
        "primary_label": "公式情報を見る",
        "note": "行事・拝観関連情報は公式ページで確認してください。",
    },
    "東京ディズニーランド": {
        "category": "theme_park",
        "primary_url": "https://www.tokyodisneyresort.jp/tdl/event.html",
        "primary_label": "イベント情報を見る",
        "note": "運営時間・ショー・休止施設は公式アプリ/公式サイト確認が必要です。",
    },
    "東京ディズニーシー": {
        "category": "theme_park",
        "primary_url": "https://www.tokyodisneyresort.jp/tds/event.html",
        "primary_label": "イベント情報を見る",
        "note": "運営時間・ショー・休止施設は公式アプリ/公式サイト確認が必要です。",
    },
    "東京ディズニーリゾート": {
        "category": "theme_park",
        "primary_url": "https://www.tokyodisneyresort.jp/tdr/event.html",
        "primary_label": "イベント情報を見る",
        "note": "運営時間・ショー・休止施設は公式アプリ/公式サイト確認が必要です。",
    },
    "東京スカイツリー": {
        "category": "commercial_complex",
        "primary_url": "https://www.tokyo-skytree.jp/event/",
        "primary_label": "イベント情報を見る",
        "note": "営業時間・イベントは公式ページで確認してください。",
    },
    "東京ソラマチ": {
        "category": "commercial_complex",
        "primary_url": "https://www.tokyo-solamachi.jp/event/",
        "primary_label": "イベント情報を見る",
        "note": "営業時間・イベントは公式ページで確認してください。",
    },
    "上野恩賜公園": {
        "category": "park",
        "primary_url": "https://www.tokyo-park.or.jp/park/ueno/",
        "primary_label": "公園情報を見る",
        "note": "イベント・施設情報は公式ページで確認してください。",
    },
}
