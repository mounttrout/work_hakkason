"""
core/llm_client.py
Gemini API との通信をハンドルする最新クライアント（修正済み・動作確認版）

修正内容:
- モデル名を新SDK形式「models/gemini-3.1-flash-lite-preview」に統一
- 旧SDK形式「gemini-2.0-flash」など短形式では 404 Not Found になるため、フルパス形式に変更
"""

import os
import json
import time
from typing import Optional, Dict, Any
from google import genai
from google.genai import types #4/9変更　github対策
# import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()


class GeminiClient:
    """最新の google-genai SDK を使用した Gemini API クライアント"""
    
    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None):
        """
        初期化
        
        Args:
            model_name: モデル名（デフォルト: 環境変数 MODEL_NAME）
                       ⚠️ 新SDK形式で指定: "models/gemini-3.1-flash-lite-preview"
            api_key: Google API キー（デフォルト: 環境変数 GOOGLE_API_KEY）
        """
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        
        # 新SDK形式のモデル名を使用
        # 短形式（gemini-2.0-flash）は 404 Not Found になるため注意
        self.model_name = model_name or os.getenv("MODEL_NAME", "models/gemini-3.1-flash-lite-preview")
        
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY 環境変数が設定されていません")
        
        self.client = genai.Client(api_key=self.api_key)
    
    def generate_text(self, prompt: str, temperature: float = 0.7, max_tokens: int = 2048) -> str:
        """
        テキスト生成（フリーテキスト）
        
        Args:
            prompt: プロンプト
            temperature: 生成の多様性（0.0-1.0）
            max_tokens: 最大トークン数
        
        Returns:
            生成されたテキスト
        """
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens
                )
            )
            return response.text
        except Exception as e:
            if "429" in str(e):
                raise RuntimeError(f"⚠️ レート制限: モデル {self.model_name} が一時的に利用不可です。1分待ってから再度実行してください。")
            raise RuntimeError(f"Gemini API エラー: {e}")
    
    def generate_json(self, prompt: str, temperature: float = 0.2, max_tokens: int = 4096) -> Dict[str, Any]:
        """
        JSON形式での生成（構造化出力）
        
        Args:
            prompt: プロンプト
            temperature: 生成の多様性（JSONは低めが推奨）
            max_tokens: 最大トークン数
        
        Returns:
            パースされたJSON辞書
        """
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                    response_mime_type="application/json"  # JSONモードを強制
                )
            )
            return json.loads(response.text.strip())
        except json.JSONDecodeError as e:
            # フォールバック: マークダウン囲いを除去してリトライ
            try:
                text = response.text.strip()
                text = text.replace("```json", "").replace("```", "").strip()
                return json.loads(text)
            except:
                raise RuntimeError(f"JSON生成エラー: {e}\n応答: {response.text[:200]}")
        except Exception as e:
            raise RuntimeError(f"Gemini API エラー（JSON生成）: {e}")

    def generate_choice(self, prompt: str, options: list, temperature: float = 0.1) -> str:
        """
        複数選択肢から1つ選ぶ（判定タスク用）
        
        Args:
            prompt: プロンプト
            options: 選択肢リスト（例: ["walk", "train", "car"]）
            temperature: 生成の多様性
        
        Returns:
            選択された選択肢
        """
        options_str = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(options)])
        choice_prompt = f"{prompt}\n\n選択肢:\n{options_str}\n\n番号または名称で答えてください。"
        
        try:
            res_text = self.generate_text(choice_prompt, temperature=temperature, max_tokens=100)
            for opt in options:
                if opt in res_text:
                    return opt
            return options[0]  # デフォルト: 最初の選択肢
        except Exception as e:
            print(f"警告: 選択肢判定エラー {e}, デフォルト値を使用")
            return options[0]


# テスト用
if __name__ == "__main__":
    client = GeminiClient()
    
    print("=" * 60)
    print("🧪 Gemini API 接続テスト")
    print("=" * 60)
    print(f"📌 現在使用中のモデル: {client.model_name}")
    
    try:
        # テスト1: テキスト生成
        print("\n✓ テスト1: テキスト生成")
        result = client.generate_text(
            "テストです。10文字以内で返信してください。",
            max_tokens=20
        )
        print(f"  結果: {result}")
        
        # テスト2: JSON生成
        print("\n✓ テスト2: JSON生成")
        json_result = client.generate_json(
            '{"test": "data"} という JSON を返してください',
            max_tokens=100
        )
        print(f"  結果: {json_result}")
        
        # テスト3: 選択肢判定
        print("\n✓ テスト3: 選択肢判定")
        choice = client.generate_choice(
            "東京から大阪へ移動するには最適な交通手段は？",
            ["walk", "train", "car"]
        )
        print(f"  結果: {choice}")
        
        print("\n" + "=" * 60)
        print("✅ 全テスト成功！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ エラー: {e}")
