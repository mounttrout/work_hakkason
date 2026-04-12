# Routes API 診断バンドル

このバンドルは、VoyageFlow 本体を直接いじる前に
Google Routes API がフォールバックへ落ちる理由を切り分けるためのものです。

## まず試すコマンド

```bash
python route_diagnostic.py --origin-name "福井駅" --destination-name "東京駅" --mode train --departure "2026-04-19 12:05"
```

```bash
python route_diagnostic.py --origin-name "東京ビッグサイト" --destination-name "品川駅" --mode train --departure "2026-04-19 02:01"
```

## 見るポイント

- geocode が失敗していないか
- response status が 200 か
- routes が返っているか
- departureTime が期待どおりか
- TRANSIT の first_step に transitDetails があるか

## 想定される原因例

- departureTime の形式が不正
- 座標が駅の入口や周辺施設にずれている
- 深夜時刻などで TRANSIT 経路が返らない
- API キー権限不足
