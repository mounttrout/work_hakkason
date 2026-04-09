"""
Version: VF-2026-04-09-fix1
Date: 2026-04-09

変更内容:
- google.generativeai と genai.Client の混在バグ修正
- 旧SDKに統一（壊さない優先）
- generate_text / JSON生成を安定化

修正箇所:
- Client初期化部分
- generate_content 呼び出し
"""

import os
import json
from typing import Optional, Dict, Any
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()


class GeminiClient:
    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")

        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY が設定されていません")

        # 🔧 修正: configure に変更（Client廃止）
        genai.configure(api_key=self.api_key)  # ← ここ重要

        self.model_name = model_name or "gemini-1.5-flash"

        # 🔧 修正: GenerativeModel に変更
        self.model = genai.GenerativeModel(self.model_name)

    def generate_text(self, prompt: str, temperature: float = 0.7, max_tokens: int = 2048) -> str:
        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                }
            )
            return response.text

        except Exception as e:
            raise RuntimeError(f"Gemini API エラー: {e}")

    def generate_json(self, prompt: str, temperature: float = 0.2, max_tokens: int = 4096) -> Dict[str, Any]:
        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                }
            )

            text = response.text.strip()
            text = text.replace("```json", "").replace("```", "").strip()

            return json.loads(text)

        except Exception as e:
            raise RuntimeError(f"JSON生成エラー: {e}")