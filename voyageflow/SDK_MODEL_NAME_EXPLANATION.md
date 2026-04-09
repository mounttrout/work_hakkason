# 🔍 Google Gemini API: SDK バージョンとモデル名形式の違い

## 📋 概要

VoyageFlow で発生した **404 Not Found エラー** は、**SDK のバージョン間でモデル名の形式が異なる** ことが原因でした。

このドキュメントは、そのメカニズムと正しい設定方法を説明します。

---

## 🆚 SDK バージョン比較表

### 旧SDK: `google-generativeai`

```python
# インポート
import google.generativeai as genai

# モデル名形式（短形式）
model_name = "gemini-2.0-flash"           # ❌ 新SDK では動きません
model_name = "gemini-1.5-flash"           # ❌ 新SDK では動きません
model_name = "gemini-3.1-flash-lite"      # ❌ 新SDK では動きません

# API 呼び出し
response = genai.GenerativeModel("gemini-2.0-flash").generate_content(prompt)
```

### 新SDK: `google-genai` ✅

```python
# インポート
from google import genai
from google.genai import types

# モデル名形式（フルパス形式）
model_name = "models/gemini-2.0-flash"                      # ✅ 正しい
model_name = "models/gemini-1.5-flash"                      # ✅ 正しい
model_name = "models/gemini-3.1-flash-lite-preview"         # ✅ 正しい

# API 呼び出し
client = genai.Client(api_key=api_key)
response = client.models.generate_content(
    model=model_name,
    contents=prompt,
    config=types.GenerateContentConfig(...)
)
```

---

## ❌ エラーの流れ

### VoyageFlow で発生していたエラー

```
❌ 設定（.env）
MODEL_NAME=gemini-2.0-flash                # 短形式（旧SDK形式）
│
│ llm_client.py
├─ from google import genai                # 新SDK をインポート
├─ self.model_name = "gemini-2.0-flash"   # モデル名は短形式
│
│ API 呼び出し
├─ client.models.generate_content(
│    model="gemini-2.0-flash",             # 短形式で問い合わせ
│    ...
│  )
│
│ Google API サーバー
├─ 「models/gemini-2.0-flash という資源は何ですか？」
├─ 「gemini-2.0-flash？そんなリソース ID、知りません」
├─ 「本来はモデル ID じゃなくて、リソースパスで指定してほしいんですけど...」
│
❌ レスポンス
404 Not Found
{'message': '', 'status': 'Not Found'}
```

---

## ✅ 修正後の流れ

```
✅ 設定（.env）
MODEL_NAME=models/gemini-3.1-flash-lite-preview   # フルパス形式（新SDK形式）
│
│ llm_client.py
├─ from google import genai                       # 新SDK をインポート
├─ self.model_name = "models/gemini-3.1-flash-lite-preview"  # フルパス形式
│
│ API 呼び出し
├─ client.models.generate_content(
│    model="models/gemini-3.1-flash-lite-preview",  # フルパス形式で問い合わせ
│    ...
│  )
│
│ Google API サーバー
├─ 「models/gemini-3.1-flash-lite-preview？あ、それですね」
├─ 「わかりました。これから処理します」
│
✅ レスポンス
200 OK
{"text": "生成されたテキスト"}
```

---

## 📝 モデル名の形式

### リソースパスの構造

```
models/gemini-3.1-flash-lite-preview
│      │
│      └─ モデル ID（新SDK で求められる形式）
│
└─ リソースタイプ（Google API の標準形式）
  この「models/」が大事
```

### 利用可能なモデル一覧

| モデル ID | フルパス形式（新SDK） | 説明 |
|-----------|-------------------|------|
| `gemini-2.0-flash` | `models/gemini-2.0-flash` | 最新の高速モデル |
| `gemini-1.5-flash` | `models/gemini-1.5-flash` | 安定性重視 |
| `gemini-1.5-pro` | `models/gemini-1.5-pro` | 高精度（レート制限あり） |
| `gemini-3.1-flash-lite-preview` | `models/gemini-3.1-flash-lite-preview` | 軽量版 |

---

## 🔧 VoyageFlow での修正内容

### 修正前（エラーが出ていた）

```python
# core/llm_client.py
def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None):
    self.model_name = model_name or os.getenv("MODEL_NAME", "gemini-2.0-flash")
    # ❌ 短形式 → 404 Not Found
```

```dotenv
# .env
MODEL_NAME=gemini-2.0-flash
# ❌ 短形式 → API が理解できない
```

### 修正後（動作確認済み）

```python
# core/llm_client.py
def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None):
    self.model_name = model_name or os.getenv("MODEL_NAME", "models/gemini-3.1-flash-lite-preview")
    # ✅ フルパス形式 → 200 OK
```

```dotenv
# .env
MODEL_NAME=models/gemini-3.1-flash-lite-preview
# ✅ フルパス形式 → API が正しく理解
```

---

## 🚀 実装手順

### Step 1: `core/llm_client.py` を修正

以下のコードに置き換えてください：

```python
def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None):
    self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
    
    # ✅ フルパス形式でモデル名を指定
    self.model_name = model_name or os.getenv("MODEL_NAME", "models/gemini-3.1-flash-lite-preview")
    
    if not self.api_key:
        raise ValueError("GOOGLE_API_KEY 環境変数が設定されていません")
    
    self.client = genai.Client(api_key=self.api_key)
```

### Step 2: `.env` を修正

```dotenv
# ✅ フルパス形式
MODEL_NAME=models/gemini-3.1-flash-lite-preview
```

### Step 3: テスト実行

```bash
python core/llm_client.py
```

**期待される出力:**
```
============================================================
🧪 Gemini API 接続テスト
============================================================
📌 現在使用中のモデル: models/gemini-3.1-flash-lite-preview

✓ テスト1: テキスト生成
  結果: テストです。

✓ テスト2: JSON生成
  結果: {'test': 'data'}

✓ テスト3: 選択肢判定
  結果: train

============================================================
✅ 全テスト成功！
============================================================
```

---

## 💡 なぜこういう違いが生まれたのか？

### 旧SDK の設計思想
- シンプルさ重視
- ユーザーが覚える形式は短く（`"gemini-2.0-flash"`）
- 内部で自動的に適切なリソースパスに変換

### 新SDK の設計思想
- Google API の標準に統一（すべてのリソースは `resource_type/resource_id`）
- 明示的で曖昧性がない
- REST API との互換性を重視

```
旧SDK: genai.GenerativeModel("gemini-2.0-flash")
       └─ 内部で "models/gemini-2.0-flash" に変換

新SDK: genai.Client().models.generate_content(model="models/gemini-2.0-flash")
       └─ 明示的に "models/..." を指定（変換なし）
```

---

## ⚠️ よくある間違い

### ❌ 間違い1: 短形式をそのまま使う
```python
self.model_name = "gemini-2.0-flash"  # 新SDK では 404 エラー
```

### ❌ 間違い2: `models/` を忘れる
```python
self.model_name = "gemini-3.1-flash-lite-preview"  # 新SDK では 404 エラー
```

### ✅ 正しい方法
```python
self.model_name = "models/gemini-3.1-flash-lite-preview"  # 動作確認済み
```

---

## 🔗 参考リンク

- [Google Gemini API - 公式ドキュメント](https://ai.google.dev/)
- [google-genai Python クライアント](https://github.com/googleapis/python-genai)
- [モデル一覧](https://ai.google.dev/gemini-api/docs/models/gemini)

---

## 📋 チェックリスト

- [ ] `core/llm_client.py` でモデル名がフルパス形式になっている
- [ ] `.env` ファイルでモデル名がフルパス形式になっている
- [ ] `python core/llm_client.py` でテストが成功している
- [ ] `streamlit run app.py` で UI が起動している
- [ ] 各フェーズ（フェーズ1, 2, 3）が正常に実行できている

---

**これで VoyageFlow の SDK バージョン問題は解決しました！** ✅
