# -*- coding: utf-8 -*-
"""
VoyageFlow Spot Enrichment Dictionary
version: v0.2.0
created: 2026-04-27

目的:
- LLMにイベント名・演目名を捏造させないためのスポット情報辞書
- 公式リンク、最新情報確認リンク、予約導線を安全に返す
- 情報が未登録の場合は公式確認/fallbackに回す

注意:
- 開催中イベントは固定情報なので、リリース前・デモ前に必ず見直す
- 不確実なイベント名は登録しない
"""

SPOT_EVENT_DICTIONARY = {
    "歌舞伎座": {
        "area": "東京",
        "category": "theater",
        "official_url": "https://www.kabuki-bito.jp/theaters/kabukiza/",
        "latest_info_url": "https://www.kabuki-bito.jp/theaters/kabukiza/play/972/",
        "reservation_url": "https://www.kabuki-bito.jp/theaters/kabukiza/",
        "display_note": "公演内容・演目・上演時間は月ごとに変わるため、来場前に公式公演情報を確認してください。",
        "known_events": [
            {
                "name": "六月大歌舞伎",
                "period": "2026-06-03〜2026-06-25",
                "source_url": "https://www.kabuki-bito.jp/theaters/kabukiza/play/972/",
            }
        ],
    },
    "東京国立博物館": {
        "area": "東京",
        "category": "museum",
        "official_url": "https://www.tnm.jp/",
        "latest_info_url": "https://www.tnm.jp/modules/r_calender/index.php",
        "reservation_url": "https://www.tnm.jp/",
        "display_note": "展示・催し物は会期変更の可能性があるため、来館前に公式スケジュールを確認してください。",
        "known_events": [],
    },
    "東京ディズニーランド": {
        "area": "東京",
        "category": "theme_park",
        "official_url": "https://www.tokyodisneyresort.jp/tdl/",
        "latest_info_url": "https://www.tokyodisneyresort.jp/tdl/event.html",
        "reservation_url": "https://www.tokyodisneyresort.jp/ticket/index.html",
        "display_note": "イベント・パレード・アトラクション運営状況は日によって変わるため、公式アプリ/公式サイトで確認してください。",
        "known_events": [
            {
                "name": "イッツ・ア・スモールワールドwithグルート",
                "period": "2025-12-27〜2026-06-28",
                "source_url": "https://www.tokyodisneyresort.jp/tdl/event.html",
            },
            {
                "name": "ディズニー・パルパルーザ“ヴァネロペのスウィーツ・ポップ・ワールド”",
                "period": "2026-04-09〜2026-06-30",
                "source_url": "https://www.tokyodisneyresort.jp/tdl/event.html",
            },
            {
                "name": "スター・ツアーズ：ザ・アドベンチャーズ・コンティニュー 特別バージョン",
                "period": "2026-04-23〜2026-06-30",
                "source_url": "https://www.tokyodisneyresort.jp/tdl/event.html",
            },
        ],
    },
    "東京ディズニーリゾート": {
        "area": "東京",
        "category": "theme_park",
        "official_url": "https://www.tokyodisneyresort.jp/",
        "latest_info_url": "https://www.tokyodisneyresort.jp/tdr/calendar/202606/",
        "reservation_url": "https://www.tokyodisneyresort.jp/ticket/index.html",
        "display_note": "運営時間・休止施設・ショー予定は日付により変わるため、公式カレンダーを確認してください。",
        "known_events": [],
    },
    "国立西洋美術館": {
        "area": "東京",
        "category": "museum",
        "official_url": "https://www.nmwa.go.jp/jp/",
        "latest_info_url": "https://www.nmwa.go.jp/jp/exhibitions/",
        "reservation_url": "https://www.nmwa.go.jp/jp/",
        "display_note": "展覧会・開館情報は変更される可能性があるため、公式展覧会ページを確認してください。",
        "known_events": [
            {
                "name": "北斎 冨嶽三十六景 井内コレクションより",
                "period": "2026-03-28〜2026-06-14",
                "source_url": "https://www.nmwa.go.jp/jp/exhibitions/2026hokusai.html",
            },
            {
                "name": "アーティスト・バイ・アーティスト――西洋版画に見る芸術家のイメージ",
                "period": "2026-03-28〜2026-06-21",
                "source_url": "https://www.nmwa.go.jp/jp/exhibitions/2026artists.html",
            },
        ],
    },
    "GINZA SIX": {
        "area": "東京",
        "category": "shopping",
        "official_url": "https://ginza6.tokyo/",
        "latest_info_url": "https://ginza6.tokyo/news/news_category/events",
        "reservation_url": "https://ginza6.tokyo/",
        "display_note": "店舗イベント・催事は短期間で変わるため、来訪前に公式イベントページを確認してください。",
        "known_events": [],
    },
    "名古屋市美術館": {
        "area": "名古屋",
        "category": "museum",
        "official_url": "https://art-museum.city.nagoya.jp/",
        "latest_info_url": "https://art-museum.city.nagoya.jp/exhibitions/",
        "reservation_url": "https://art-museum.city.nagoya.jp/",
        "display_note": "展覧会・イベントは会期変更の可能性があるため、公式ページで確認してください。",
        "known_events": [
            {
                "name": "特別展『銀河鉄道999』50周年プロジェクト 松本零士展 創作の旅路",
                "period": "2026-03-20〜2026-06-07",
                "source_url": "https://art-museum.city.nagoya.jp/exhibitions/post/leiji-m-exh/",
            }
        ],
    },
    "名古屋城": {
        "area": "名古屋",
        "category": "castle",
        "official_url": "https://www.nagoyajo.city.nagoya.jp/",
        "latest_info_url": "https://www.nagoyajo.city.nagoya.jp/event/",
        "reservation_url": "https://www.nagoyajo.city.nagoya.jp/",
        "display_note": "催し・開園時間・公開範囲は変更される可能性があるため、公式ページで確認してください。",
        "known_events": [],
    },
    "熱田神宮": {
        "area": "名古屋",
        "category": "shrine",
        "official_url": "https://www.atsutajingu.or.jp/",
        "latest_info_url": "https://www.atsutajingu.or.jp/",
        "reservation_url": "https://www.atsutajingu.or.jp/",
        "display_note": "祭典・行事・参拝案内は公式サイトで確認してください。",
        "known_events": [],
    },
    "大須商店街": {
        "area": "名古屋",
        "category": "shopping_street",
        "official_url": "https://osu.nagoya/",
        "latest_info_url": "https://osu.nagoya/",
        "reservation_url": "https://osu.nagoya/",
        "display_note": "店舗営業日やイベントは店舗・公式情報を確認してください。",
        "known_events": [],
    },
    "徳川美術館": {
        "area": "名古屋",
        "category": "museum",
        "official_url": "https://www.tokugawa-art-museum.jp/",
        "latest_info_url": "https://www.tokugawa-art-museum.jp/exhibitions/",
        "reservation_url": "https://www.tokugawa-art-museum.jp/",
        "display_note": "展覧会・展示替え・休館日は公式展覧会ページを確認してください。",
        "known_events": [],
    },
}
