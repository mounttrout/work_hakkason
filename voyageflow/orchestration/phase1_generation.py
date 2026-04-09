"""
orchestration/phase1_generation.py
フェーズ1: Gemini によるフリーテキスト旅行プラン生成
"""

from typing import Callable, Optional
import sys
import os

# パス追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.llm_client import GeminiClient
from core.prompts import PromptBuilder


class Phase1Generator:
    """フェーズ1: LLM候補生成"""
    
    def __init__(self, gemini_client: Optional[GeminiClient] = None, logger: Optional[Callable[[str, str, str], None]] = None):
        """
        初期化
        
        Args:
            gemini_client: GeminiClient インスタンス（デフォルト: 新規作成）
        """
        self.client = gemini_client or GeminiClient()
        self.logger = logger
    
    def generate_trip_plan(self, user_request: str, temperature: float = 0.7) -> str:
        """
        ユーザーリクエストから旅行プランを生成
        
        Args:
            user_request: ユーザーの旅行リクエスト（自然言語）
            temperature: Gemini の生成多様性（0.0-1.0、デフォルト: 0.7）
        
        Returns:
            フリーテキスト形式の旅行プラン
        
        例:
            Input: "来週二泊３日の東京旅行の予定を考えて"
            Output: "【1日目：4月16日（木）】最新技術と大人の知性\n* 09:32：東京駅 到着..."
        """
        prompt = PromptBuilder.build_phase1(user_request)
        
        print(f"フェーズ1: LLM候補生成を開始...")
        print(f"ユーザーリクエスト: {user_request}\n")
        if self.logger:
            self.logger("Phase1", "LLM候補生成を開始...")
            self.logger("Phase1", f"ユーザーリクエスト: {user_request}")
        
        # Gemini に生成を依頼
        trip_plan = self.client.generate_text(prompt, temperature=temperature, max_tokens=4096)
        
        return trip_plan


# テスト用
def test_phase1():
    """フェーズ1のテスト実行"""
    
    # ユーザーリクエスト（例）
    user_request = "来週二泊３日の東京旅行の予定を考えて。エンジニアとしての興味を優先してください。"
    
    try:
        generator = Phase1Generator()
        trip_plan = generator.generate_trip_plan(user_request)
        
        print("=" * 60)
        print("生成された旅行プラン:")
        print("=" * 60)
        print(trip_plan)
        
        return trip_plan
    except Exception as e:
        print(f"エラー: {e}")
        return None


if __name__ == "__main__":
    test_phase1()
