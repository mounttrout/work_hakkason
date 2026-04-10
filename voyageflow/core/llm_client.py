"""
Version: VF-2026-04-10-restore-model
Date: 2026-04-10

前バージョンからの修正内容:
- 誤って変更していたデフォルトモデルを元の
  "models/gemini-3.1-flash-lite-preview" に戻した
- 既存制約「動作確認できているモデルは変えない」に合わせて修正

触った箇所:
- GeminiClient.__init__ の model_name 初期値
"""

import os
import json
from typing import Optional, Dict, Any

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()


class GeminiClient:
    """Gemini API クライアント"""

    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY が設定されていません")

        genai.configure(api_key=self.api_key)

        # [VF-2026-04-10] 元の動作確認済みモデルへ戻す
        self.model_name = model_name or os.getenv("MODEL_NAME", "models/gemini-3.1-flash-lite-preview")

        # [VF-2026-04-10] 旧SDK系の安全な呼び出しに統一
        self.model = genai.GenerativeModel(self.model_name)

    def generate_text(self, prompt: str, temperature: float = 0.7, max_tokens: int = 2048) -> str:
        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                },
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
                },
            )
            text = response.text.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"JSON生成エラー: {e}")
        except Exception as e:
            raise RuntimeError(f"Gemini API エラー（JSON生成）: {e}")

    def generate_choice(self, prompt: str, options: list, temperature: float = 0.1) -> str:
        options_str = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(options)])
        choice_prompt = f"{prompt}\n\n選択肢:\n{options_str}\n\n番号または名称で答えてください。"

        try:
            res_text = self.generate_text(choice_prompt, temperature=temperature, max_tokens=100)
            for opt in options:
                if opt in res_text:
                    return opt
            return options[0]
        except Exception:
            return options[0]