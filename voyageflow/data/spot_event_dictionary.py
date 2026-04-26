# -*- coding: utf-8 -*-
"""
VoyageFlow spot_event_dictionary.py

【目的】
- ハッカソンMVP向けに、東京・名古屋の主要スポット最新情報を辞書化する。
- app.py に大量の辞書を直接書かず、外部ファイルとして保守する。
- Phase2 / Phase3 の構造化には混ぜず、完成旅程カードの「補足表示」にだけ使う。

【対象期間】
- 2026-06-04 〜 2026-06-10 を主想定。
- event_detail が入っているものは、この期間に日付判定して表示。
- event_detail が空のものは、公式確認リンク / 検索リンク表示に使う。

【重要】
- この辞書は旅程本体を変更しない。
- イベント名をLLMに作らせない。
- 取得できていないものは「公式情報確認」扱いにする。
"""

HACKATHON_TARGET_FROM = "2026-06-04"
HACKATHON_TARGET_TO = "2026-06-10"
DICTIONARY_UPDATED_AT = "2026-04-26"

# type:
# - "event": 旅行日が valid_from〜valid_to に入る場合、headline/details を表示
# - "link_only": 公式リンク・検索リンクの表示に使う
#
# closed_dates:
# - 旅行日が該当した場合、注意文を優先表示する
#
# confidence:
# - "official_verified": 公式ページ由来で日付・名称を確認済み
# - "official_link": 公式確認リンクのみ
# - "search_fallback": 公式ページを特定しない検索補助
SPOT_EVENT_DICTIONARY = [
    # =====================================================
    # 東京 Aランク: 6/4〜6/10で詳細表示したいもの
    # =====================================================
    {
        "spot_name": "歌舞伎座",
        "aliases": ["歌舞伎", "東銀座", "Kabukiza", "歌舞伎座タワー"],
        "city": "東京",
        "category": "theater",
        "type": "event",
        "valid_from": "2026-06-03",
        "valid_to": "2026-06-25",
        "closed_dates": ["2026-06-10"],
        "headline": "六月大歌舞伎",
        "details": [
            "昼の部 午前11時～",
            "夜の部 午後4時30分～",
            "6/10は休演日のため、観劇予定なら日程変更が必要"
        ],
        "source_label": "歌舞伎公式サイト",
        "source_url": "https://www.kabuki-bito.jp/theaters/kabukiza/play/972/",
        "confidence": "official_verified",
    },
    {
        "spot_name": "東京国立博物館",
        "aliases": ["東博", "トーハク", "Tokyo National Museum", "国立博物館"],
        "city": "東京",
        "category": "museum",
        "type": "event",
        "valid_from": "2026-04-14",
        "valid_to": "2026-06-07",
        "closed_dates": [],
        "headline": "前田育徳会創立百周年記念 特別展「百万石！加賀前田家」",
        "details": [
            "会場: 平成館 特別展示室",
            "6/4〜6/7は会期内",
            "6/8以降は会期外の可能性があるため公式カレンダー確認推奨"
        ],
        "source_label": "東京国立博物館 公式カレンダー",
        "source_url": "https://www.tnm.jp/modules/r_calender/index.php?date=2026-06-04",
        "confidence": "official_verified",
    },
    {
        "spot_name": "東京ディズニーランド",
        "aliases": ["ディズニーランド", "TDL", "Tokyo Disneyland", "ランド"],
        "city": "東京近郊",
        "category": "theme_park",
        "type": "event",
        "valid_from": "2026-04-09",
        "valid_to": "2026-06-30",
        "closed_dates": [],
        "headline": "ディズニー・パルパルーザ “ヴァネロペのスウィーツ・ポップ・ワールド” 関連コンテンツ",
        "details": [
            "スウィーツの世界観を楽しむグッズ・メニュー・デコレーション情報あり",
            "パークチケット・当日の運営時間は公式カレンダー確認推奨",
            "混雑しやすいため、朝入園・事前予約導線と相性がよい"
        ],
        "source_label": "東京ディズニーリゾート公式サイト",
        "source_url": "https://www.tokyodisneyresort.jp/treasure/vanellopessweetpopworld2026/",
        "confidence": "official_verified",
    },
    {
        "spot_name": "東京ディズニーシー",
        "aliases": ["ディズニーシー", "TDS", "Tokyo DisneySea", "シー"],
        "city": "東京近郊",
        "category": "theme_park",
        "type": "link_only",
        "valid_from": "2026-06-04",
        "valid_to": "2026-06-10",
        "closed_dates": [],
        "headline": "東京ディズニーシー 公式カレンダー確認",
        "details": [
            "イベント・ショー・運営時間は日別公式カレンダー確認推奨",
            "旅行日ごとのパーク運営時間・休止施設を確認"
        ],
        "source_label": "東京ディズニーリゾート公式サイト",
        "source_url": "https://www.tokyodisneyresort.jp/tds/monthly/calendar/",
        "confidence": "official_link",
    },
    {
        "spot_name": "GINZA SIX",
        "aliases": ["ギンザシックス", "銀座シックス", "Ginza Six"],
        "city": "東京",
        "category": "commercial_complex",
        "type": "link_only",
        "valid_from": "2026-06-04",
        "valid_to": "2026-06-10",
        "closed_dates": [],
        "headline": "GINZA SIX イベント情報",
        "details": ["ポップアップ・展示・店舗イベントは公式イベントページ確認推奨"],
        "source_label": "GINZA SIX 公式サイト",
        "source_url": "https://ginza6.tokyo/news/news_category/events",
        "confidence": "official_link",
    },
    {
        "spot_name": "国立西洋美術館",
        "aliases": ["西洋美術館", "NMWA", "The National Museum of Western Art"],
        "city": "東京",
        "category": "museum",
        "type": "link_only",
        "valid_from": "2026-06-04",
        "valid_to": "2026-06-10",
        "closed_dates": [],
        "headline": "展覧会情報確認",
        "details": ["開催中・今後の展覧会、休館日、チケット情報は公式ページ確認推奨"],
        "source_label": "国立西洋美術館 公式サイト",
        "source_url": "https://www.nmwa.go.jp/jp/exhibitions/",
        "confidence": "official_link",
    },

    # =====================================================
    # 東京 B/Cランク: 公式リンク中心
    # =====================================================
    {"spot_name": "浅草寺", "aliases": ["浅草", "Sensoji", "雷門"], "city": "東京", "category": "shrine_temple", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "参拝・行事情報確認", "details": ["行事・混雑・参拝時間は公式情報確認推奨"], "source_label": "浅草寺 公式サイト", "source_url": "https://www.senso-ji.jp/", "confidence": "official_link"},
    {"spot_name": "明治神宮", "aliases": ["Meiji Jingu", "原宿 明治神宮"], "city": "東京", "category": "shrine_temple", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "参拝・行事情報確認", "details": ["祭典・参拝時間は公式情報確認推奨"], "source_label": "明治神宮 公式サイト", "source_url": "https://www.meijijingu.or.jp/", "confidence": "official_link"},
    {"spot_name": "東京スカイツリー", "aliases": ["スカイツリー", "Tokyo Skytree"], "city": "東京", "category": "tower_observation", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "イベント・チケット情報確認", "details": ["展望台チケット・イベント・営業時間は公式情報確認推奨"], "source_label": "東京スカイツリー 公式サイト", "source_url": "https://www.tokyo-skytree.jp/", "confidence": "official_link"},
    {"spot_name": "東京タワー", "aliases": ["Tokyo Tower"], "city": "東京", "category": "tower_observation", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "イベント・チケット情報確認", "details": ["展望台・ライトアップ・イベントは公式情報確認推奨"], "source_label": "東京タワー 公式サイト", "source_url": "https://www.tokyotower.co.jp/", "confidence": "official_link"},
    {"spot_name": "チームラボプラネッツ", "aliases": ["teamLab Planets", "豊洲 チームラボ"], "city": "東京", "category": "museum", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "展示・チケット情報確認", "details": ["入場枠・チケット在庫・展示情報は公式確認推奨"], "source_label": "teamLab Planets 公式サイト", "source_url": "https://www.teamlab.art/jp/e/planets/", "confidence": "official_link"},
    {"spot_name": "森美術館", "aliases": ["Mori Art Museum", "六本木ヒルズ 森美術館"], "city": "東京", "category": "museum", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "展覧会情報確認", "details": ["開催中の展覧会・チケットは公式確認推奨"], "source_label": "森美術館 公式サイト", "source_url": "https://www.mori.art.museum/", "confidence": "official_link"},
    {"spot_name": "国立新美術館", "aliases": ["The National Art Center Tokyo", "新美"], "city": "東京", "category": "museum", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "展覧会情報確認", "details": ["企画展・公募展・休館日は公式確認推奨"], "source_label": "国立新美術館 公式サイト", "source_url": "https://www.nact.jp/", "confidence": "official_link"},
    {"spot_name": "東京国立近代美術館", "aliases": ["MOMAT", "近代美術館"], "city": "東京", "category": "museum", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "展覧会情報確認", "details": ["企画展・所蔵作品展・休館日は公式確認推奨"], "source_label": "東京国立近代美術館 公式サイト", "source_url": "https://www.momat.go.jp/", "confidence": "official_link"},
    {"spot_name": "江戸東京たてもの園", "aliases": ["たてもの園"], "city": "東京", "category": "museum", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "展示・イベント情報確認", "details": ["開園日・展示・イベントは公式確認推奨"], "source_label": "江戸東京たてもの園 公式サイト", "source_url": "https://www.tatemonoen.jp/", "confidence": "official_link"},
    {"spot_name": "日本科学未来館", "aliases": ["未来館", "Miraikan"], "city": "東京", "category": "museum", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "展示・イベント情報確認", "details": ["常設展・特別展・ドームシアターは公式確認推奨"], "source_label": "日本科学未来館 公式サイト", "source_url": "https://www.miraikan.jst.go.jp/", "confidence": "official_link"},
    {"spot_name": "すみだ水族館", "aliases": ["Sumida Aquarium"], "city": "東京", "category": "aquarium", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "イベント・チケット情報確認", "details": ["営業時間・イベント・チケットは公式確認推奨"], "source_label": "すみだ水族館 公式サイト", "source_url": "https://www.sumida-aquarium.com/", "confidence": "official_link"},
    {"spot_name": "サンシャイン水族館", "aliases": ["Sunshine Aquarium"], "city": "東京", "category": "aquarium", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "イベント・チケット情報確認", "details": ["イベント・営業時間・チケットは公式確認推奨"], "source_label": "サンシャイン水族館 公式サイト", "source_url": "https://sunshinecity.jp/aquarium/", "confidence": "official_link"},
    {"spot_name": "マクセル アクアパーク品川", "aliases": ["アクアパーク品川", "Aqua Park Shinagawa"], "city": "東京", "category": "aquarium", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "イベント・チケット情報確認", "details": ["ショー・営業時間・チケットは公式確認推奨"], "source_label": "アクアパーク品川 公式サイト", "source_url": "https://www.aqua-park.jp/aqua/", "confidence": "official_link"},
    {"spot_name": "上野動物園", "aliases": ["Ueno Zoo"], "city": "東京", "category": "zoo", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "開園・イベント情報確認", "details": ["開園日・イベント・動物展示状況は公式確認推奨"], "source_label": "上野動物園 公式サイト", "source_url": "https://www.tokyo-zoo.net/zoo/ueno/", "confidence": "official_link"},
    {"spot_name": "新宿御苑", "aliases": ["Shinjuku Gyoen"], "city": "東京", "category": "park", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "開園・イベント情報確認", "details": ["開園日・イベント・花の見頃は公式確認推奨"], "source_label": "新宿御苑 公式サイト", "source_url": "https://fng.or.jp/shinjuku/", "confidence": "official_link"},
    {"spot_name": "上野恩賜公園", "aliases": ["上野公園", "Ueno Park"], "city": "東京", "category": "park", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "イベント・園内情報確認", "details": ["園内イベント・施設情報は公式確認推奨"], "source_label": "東京都公園協会", "source_url": "https://www.tokyo-park.or.jp/park/ueno/", "confidence": "official_link"},
    {"spot_name": "代々木公園", "aliases": ["Yoyogi Park"], "city": "東京", "category": "park", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "イベント・園内情報確認", "details": ["週末イベント・園内情報は公式確認推奨"], "source_label": "東京都公園協会", "source_url": "https://www.tokyo-park.or.jp/park/yoyogi/", "confidence": "official_link"},
    {"spot_name": "皇居外苑", "aliases": ["皇居", "Kokyo Gaien"], "city": "東京", "category": "park", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "散策・施設情報確認", "details": ["公開状況・周辺施設は公式確認推奨"], "source_label": "環境省 皇居外苑", "source_url": "https://fng.or.jp/koukyo/", "confidence": "official_link"},
    {"spot_name": "浜離宮恩賜庭園", "aliases": ["浜離宮", "Hamarikyu"], "city": "東京", "category": "garden", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "開園・イベント情報確認", "details": ["開園日・庭園イベントは公式確認推奨"], "source_label": "東京都公園協会", "source_url": "https://www.tokyo-park.or.jp/park/hama-rikyu/", "confidence": "official_link"},
    {"spot_name": "六義園", "aliases": ["Rikugien"], "city": "東京", "category": "garden", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "開園・イベント情報確認", "details": ["開園日・庭園イベントは公式確認推奨"], "source_label": "東京都公園協会", "source_url": "https://www.tokyo-park.or.jp/park/rikugien/", "confidence": "official_link"},
    {"spot_name": "六本木ヒルズ", "aliases": ["Roppongi Hills"], "city": "東京", "category": "commercial_complex", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "イベント情報確認", "details": ["展覧会・ショップイベント・展望台情報は公式確認推奨"], "source_label": "六本木ヒルズ 公式サイト", "source_url": "https://www.roppongihills.com/events/", "confidence": "official_link"},
    {"spot_name": "東京ミッドタウン", "aliases": ["Tokyo Midtown", "ミッドタウン"], "city": "東京", "category": "commercial_complex", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "イベント情報確認", "details": ["イベント・ショップ情報は公式確認推奨"], "source_label": "東京ミッドタウン 公式サイト", "source_url": "https://www.tokyo-midtown.com/jp/event/", "confidence": "official_link"},
    {"spot_name": "渋谷スクランブルスクエア", "aliases": ["SHIBUYA SKY", "渋谷スカイ", "スクランブルスクエア"], "city": "東京", "category": "commercial_complex", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "イベント・展望施設情報確認", "details": ["展望施設チケット・イベントは公式確認推奨"], "source_label": "渋谷スクランブルスクエア 公式サイト", "source_url": "https://www.shibuya-scramble-square.com/", "confidence": "official_link"},
    {"spot_name": "表参道ヒルズ", "aliases": ["Omotesando Hills"], "city": "東京", "category": "commercial_complex", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "イベント情報確認", "details": ["ショップイベント・展示情報は公式確認推奨"], "source_label": "表参道ヒルズ 公式サイト", "source_url": "https://www.omotesandohills.com/", "confidence": "official_link"},
    {"spot_name": "豊洲市場", "aliases": ["Toyosu Market"], "city": "東京", "category": "market", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "営業日・見学情報確認", "details": ["市場カレンダー・見学情報は公式確認推奨"], "source_label": "豊洲市場 公式サイト", "source_url": "https://www.shijou.metro.tokyo.lg.jp/toyosu/", "confidence": "official_link"},
    {"spot_name": "築地場外市場", "aliases": ["築地", "Tsukiji Outer Market"], "city": "東京", "category": "market", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "営業・イベント情報確認", "details": ["店舗営業日・イベントは公式確認推奨"], "source_label": "築地場外市場 公式サイト", "source_url": "https://www.tsukiji.or.jp/", "confidence": "official_link"},
    {"spot_name": "秋葉原", "aliases": ["Akihabara", "アキバ"], "city": "東京", "category": "area", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "周辺イベント確認", "details": ["店舗イベント・ポップアップは検索確認推奨"], "source_label": "Google検索", "source_url": "https://www.google.com/search?q=%E7%A7%8B%E8%91%89%E5%8E%9F+%E3%82%A4%E3%83%99%E3%83%B3%E3%83%88+2026%E5%B9%B46%E6%9C%88", "confidence": "search_fallback"},
    {"spot_name": "原宿 竹下通り", "aliases": ["竹下通り", "原宿", "Takeshita Street"], "city": "東京", "category": "area", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "周辺イベント確認", "details": ["店舗イベント・新店情報は検索確認推奨"], "source_label": "Google検索", "source_url": "https://www.google.com/search?q=%E5%8E%9F%E5%AE%BF+%E7%AB%B9%E4%B8%8B%E9%80%9A%E3%82%8A+%E3%82%A4%E3%83%99%E3%83%B3%E3%83%88+2026%E5%B9%B46%E6%9C%88", "confidence": "search_fallback"},
    {"spot_name": "お台場", "aliases": ["Odaiba", "台場"], "city": "東京", "category": "area", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "周辺イベント確認", "details": ["商業施設・屋内施設イベントは検索確認推奨"], "source_label": "Google検索", "source_url": "https://www.google.com/search?q=%E3%81%8A%E5%8F%B0%E5%A0%B4+%E3%82%A4%E3%83%99%E3%83%B3%E3%83%88+2026%E5%B9%B46%E6%9C%88", "confidence": "search_fallback"},
    {"spot_name": "東京駅", "aliases": ["丸の内", "Tokyo Station"], "city": "東京", "category": "area", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "駅周辺イベント確認", "details": ["丸の内・駅ナカイベントは検索確認推奨"], "source_label": "Google検索", "source_url": "https://www.google.com/search?q=%E6%9D%B1%E4%BA%AC%E9%A7%85+%E4%B8%B8%E3%81%AE%E5%86%85+%E3%82%A4%E3%83%99%E3%83%B3%E3%83%88+2026%E5%B9%B46%E6%9C%88", "confidence": "search_fallback"},
    {"spot_name": "日本橋", "aliases": ["Nihonbashi"], "city": "東京", "category": "area", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "周辺イベント確認", "details": ["商業施設・街歩きイベントは検索確認推奨"], "source_label": "Google検索", "source_url": "https://www.google.com/search?q=%E6%97%A5%E6%9C%AC%E6%A9%8B+%E3%82%A4%E3%83%99%E3%83%B3%E3%83%88+2026%E5%B9%B46%E6%9C%88", "confidence": "search_fallback"},
    {"spot_name": "銀座", "aliases": ["Ginza"], "city": "東京", "category": "area", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "周辺イベント確認", "details": ["百貨店・ギャラリー・商業施設イベントは検索確認推奨"], "source_label": "Google検索", "source_url": "https://www.google.com/search?q=%E9%8A%80%E5%BA%A7+%E3%82%A4%E3%83%99%E3%83%B3%E3%83%88+2026%E5%B9%B46%E6%9C%88", "confidence": "search_fallback"},
    {"spot_name": "東京ドームシティ", "aliases": ["Tokyo Dome City", "東京ドーム"], "city": "東京", "category": "amusement", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "イベント・アトラクション情報確認", "details": ["イベント・アトラクション運営状況は公式確認推奨"], "source_label": "東京ドームシティ 公式サイト", "source_url": "https://www.tokyo-dome.co.jp/", "confidence": "official_link"},
    {"spot_name": "東京ジョイポリス", "aliases": ["Joypolis"], "city": "東京", "category": "amusement", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "イベント・チケット情報確認", "details": ["コラボイベント・営業時間は公式確認推奨"], "source_label": "東京ジョイポリス 公式サイト", "source_url": "https://tokyo-joypolis.com/", "confidence": "official_link"},
    {"spot_name": "SMALL WORLDS Miniature Museum", "aliases": ["スモールワールズ", "有明 スモールワールズ"], "city": "東京", "category": "museum", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "展示・チケット情報確認", "details": ["展示・イベント・営業時間は公式確認推奨"], "source_label": "SMALL WORLDS 公式サイト", "source_url": "https://smallworlds.jp/", "confidence": "official_link"},
    {"spot_name": "キッザニア東京", "aliases": ["KidZania Tokyo"], "city": "東京", "category": "family", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "予約・イベント情報確認", "details": ["入場予約・イベント・営業時間は公式確認推奨"], "source_label": "キッザニア東京 公式サイト", "source_url": "https://www.kidzania.jp/tokyo/", "confidence": "official_link"},
    {"spot_name": "三鷹の森ジブリ美術館", "aliases": ["ジブリ美術館", "Ghibli Museum"], "city": "東京", "category": "museum", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "チケット・展示情報確認", "details": ["日時指定チケット・開館日は公式確認推奨"], "source_label": "三鷹の森ジブリ美術館 公式サイト", "source_url": "https://www.ghibli-museum.jp/", "confidence": "official_link"},
    {"spot_name": "井の頭恩賜公園", "aliases": ["井の頭公園", "Inokashira Park"], "city": "東京", "category": "park", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "園内情報確認", "details": ["園内イベント・施設情報は公式確認推奨"], "source_label": "東京都公園協会", "source_url": "https://www.tokyo-park.or.jp/park/inokashira/", "confidence": "official_link"},
    {"spot_name": "サンリオピューロランド", "aliases": ["ピューロランド", "Sanrio Puroland"], "city": "東京近郊", "category": "theme_park", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "イベント・チケット情報確認", "details": ["ショー・イベント・パスポートは公式確認推奨"], "source_label": "サンリオピューロランド 公式サイト", "source_url": "https://www.puroland.jp/", "confidence": "official_link"},
    {"spot_name": "高尾山", "aliases": ["Mount Takao", "高尾"], "city": "東京", "category": "nature", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "登山・ケーブルカー情報確認", "details": ["天候・ケーブルカー運行・混雑情報は公式確認推奨"], "source_label": "高尾登山電鉄 公式サイト", "source_url": "https://www.takaotozan.co.jp/", "confidence": "official_link"},
    {"spot_name": "よみうりランド", "aliases": ["Yomiuriland"], "city": "東京近郊", "category": "theme_park", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "イベント・チケット情報確認", "details": ["イベント・アトラクション運行状況は公式確認推奨"], "source_label": "よみうりランド 公式サイト", "source_url": "https://www.yomiuriland.com/", "confidence": "official_link"},

    # =====================================================
    # 名古屋 A/Bランク
    # =====================================================
    {
        "spot_name": "名古屋市美術館",
        "aliases": ["Nagoya City Art Museum", "市美術館", "松本零士展"],
        "city": "名古屋",
        "category": "museum",
        "type": "event",
        "valid_from": "2026-03-20",
        "valid_to": "2026-06-07",
        "closed_dates": [],
        "headline": "特別展「『銀河鉄道999』50周年プロジェクト 松本零士展 創作の旅路」",
        "details": [
            "会期: 2026/3/20〜6/7",
            "通常 9:30〜17:00、金曜日は20:00まで",
            "中学生以下無料の設定あり"
        ],
        "source_label": "名古屋市美術館 公式サイト",
        "source_url": "https://art-museum.city.nagoya.jp/exhibitions/post/leiji-m-exh/",
        "confidence": "official_verified",
    },
    {"spot_name": "徳川美術館", "aliases": ["Tokugawa Art Museum"], "city": "名古屋", "category": "museum", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "展覧会情報確認", "details": ["特別展・企画展・休館日は公式確認推奨"], "source_label": "徳川美術館 公式サイト", "source_url": "https://www.tokugawa-art-museum.jp/", "confidence": "official_link"},
    {"spot_name": "名古屋城", "aliases": ["Nagoya Castle"], "city": "名古屋", "category": "castle", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "開園・イベント情報確認", "details": ["イベント・公開状況・本丸御殿情報は公式確認推奨"], "source_label": "名古屋城 公式サイト", "source_url": "https://www.nagoyajo.city.nagoya.jp/", "confidence": "official_link"},
    {"spot_name": "熱田神宮", "aliases": ["Atsuta Jingu"], "city": "名古屋", "category": "shrine_temple", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "参拝・行事情報確認", "details": ["祭典・参拝情報は公式確認推奨"], "source_label": "熱田神宮 公式サイト", "source_url": "https://www.atsutajingu.or.jp/", "confidence": "official_link"},
    {"spot_name": "名古屋市科学館", "aliases": ["Nagoya City Science Museum", "科学館"], "city": "名古屋", "category": "museum", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "展示・プラネタリウム情報確認", "details": ["プラネタリウム・特別展・休館日は公式確認推奨"], "source_label": "名古屋市科学館 公式サイト", "source_url": "https://www.ncsm.city.nagoya.jp/", "confidence": "official_link"},
    {"spot_name": "トヨタ産業技術記念館", "aliases": ["Toyota Commemorative Museum", "産業技術記念館"], "city": "名古屋", "category": "museum", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "展示・イベント情報確認", "details": ["開館日・イベント・実演情報は公式確認推奨"], "source_label": "トヨタ産業技術記念館 公式サイト", "source_url": "https://www.tcmit.org/", "confidence": "official_link"},
    {"spot_name": "大須商店街", "aliases": ["大須", "Osu Shopping Street"], "city": "名古屋", "category": "area", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "周辺イベント確認", "details": ["商店街イベント・店舗情報は公式/検索確認推奨"], "source_label": "大須商店街 公式サイト", "source_url": "https://osu.nagoya/", "confidence": "official_link"},
    {"spot_name": "オアシス21", "aliases": ["Oasis 21"], "city": "名古屋", "category": "commercial_complex", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "イベント情報確認", "details": ["イベント・店舗情報は公式確認推奨"], "source_label": "オアシス21 公式サイト", "source_url": "https://www.sakaepark.co.jp/", "confidence": "official_link"},
    {"spot_name": "中部電力 MIRAI TOWER", "aliases": ["名古屋テレビ塔", "MIRAI TOWER", "ミライタワー"], "city": "名古屋", "category": "tower_observation", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "イベント・展望台情報確認", "details": ["展望台・イベント・ライトアップは公式確認推奨"], "source_label": "中部電力 MIRAI TOWER 公式サイト", "source_url": "https://www.nagoya-tv-tower.co.jp/", "confidence": "official_link"},
    {"spot_name": "東山動植物園", "aliases": ["Higashiyama Zoo", "東山動物園"], "city": "名古屋", "category": "zoo", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "開園・イベント情報確認", "details": ["開園日・イベント・展示状況は公式確認推奨"], "source_label": "東山動植物園 公式サイト", "source_url": "https://www.higashiyama.city.nagoya.jp/", "confidence": "official_link"},
    {"spot_name": "名古屋港水族館", "aliases": ["Port of Nagoya Public Aquarium"], "city": "名古屋", "category": "aquarium", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "イベント・チケット情報確認", "details": ["ショー・イベント・営業時間は公式確認推奨"], "source_label": "名古屋港水族館 公式サイト", "source_url": "https://nagoyaaqua.jp/", "confidence": "official_link"},
    {"spot_name": "白鳥庭園", "aliases": ["Shirotori Garden"], "city": "名古屋", "category": "garden", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "開園・イベント情報確認", "details": ["庭園イベント・開園日は公式確認推奨"], "source_label": "白鳥庭園 公式サイト", "source_url": "https://www.shirotori-garden.jp/", "confidence": "official_link"},
    {"spot_name": "ノリタケの森", "aliases": ["Noritake Garden"], "city": "名古屋", "category": "museum", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "展示・体験情報確認", "details": ["クラフト体験・ショップ情報は公式確認推奨"], "source_label": "ノリタケの森 公式サイト", "source_url": "https://www.noritake.co.jp/mori/", "confidence": "official_link"},
    {"spot_name": "リニア・鉄道館", "aliases": ["SCMAGLEV and Railway Park", "リニア鉄道館"], "city": "名古屋", "category": "museum", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "展示・イベント情報確認", "details": ["開館日・イベント・体験展示は公式確認推奨"], "source_label": "リニア・鉄道館 公式サイト", "source_url": "https://museum.jr-central.co.jp/", "confidence": "official_link"},
    {"spot_name": "レゴランド・ジャパン", "aliases": ["LEGOLAND Japan", "レゴランド"], "city": "名古屋", "category": "theme_park", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "イベント・チケット情報確認", "details": ["イベント・営業時間・チケットは公式確認推奨"], "source_label": "LEGOLAND Japan 公式サイト", "source_url": "https://www.legoland.jp/", "confidence": "official_link"},
    {"spot_name": "Maker's Pier", "aliases": ["メイカーズピア"], "city": "名古屋", "category": "commercial_complex", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "イベント・店舗情報確認", "details": ["店舗イベント・営業情報は公式確認推奨"], "source_label": "Maker's Pier 公式サイト", "source_url": "https://www.makerspier.com/", "confidence": "official_link"},
    {"spot_name": "久屋大通公園", "aliases": ["Hisaya Odori Park", "Hisaya-odori Park"], "city": "名古屋", "category": "park", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "イベント情報確認", "details": ["公園イベント・店舗情報は公式確認推奨"], "source_label": "Hisaya-odori Park 公式サイト", "source_url": "https://rhp.nagoya/", "confidence": "official_link"},
    {"spot_name": "名古屋能楽堂", "aliases": ["Nagoya Noh Theater"], "city": "名古屋", "category": "theater", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "公演情報確認", "details": ["公演・チケット情報は公式確認推奨"], "source_label": "名古屋能楽堂 公式サイト", "source_url": "https://www.bunka758.or.jp/facility/nougakudo/", "confidence": "official_link"},
    {"spot_name": "名古屋市博物館", "aliases": ["Nagoya City Museum"], "city": "名古屋", "category": "museum", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "展示情報確認", "details": ["展示・休館日は公式確認推奨"], "source_label": "名古屋市博物館 公式サイト", "source_url": "https://www.museum.city.nagoya.jp/", "confidence": "official_link"},
    {"spot_name": "名古屋駅", "aliases": ["名駅", "Nagoya Station"], "city": "名古屋", "category": "area", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "駅周辺イベント確認", "details": ["駅ビル・商業施設イベントは検索確認推奨"], "source_label": "Google検索", "source_url": "https://www.google.com/search?q=%E5%90%8D%E5%8F%A4%E5%B1%8B%E9%A7%85+%E3%82%A4%E3%83%99%E3%83%B3%E3%83%88+2026%E5%B9%B46%E6%9C%88", "confidence": "search_fallback"},
    {"spot_name": "栄", "aliases": ["Sakae"], "city": "名古屋", "category": "area", "type": "link_only", "valid_from": "2026-06-04", "valid_to": "2026-06-10", "closed_dates": [], "headline": "周辺イベント確認", "details": ["商業施設・屋外イベントは検索確認推奨"], "source_label": "Google検索", "source_url": "https://www.google.com/search?q=%E5%90%8D%E5%8F%A4%E5%B1%8B+%E6%A0%84+%E3%82%A4%E3%83%99%E3%83%B3%E3%83%88+2026%E5%B9%B46%E6%9C%88", "confidence": "search_fallback"},
]
