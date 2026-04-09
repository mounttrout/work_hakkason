"""
core/json_repair.py
Gemini出力のJSON形式をクリーニング・修復するユーティリティ
"""

import json
import re
from typing import Dict, Any, Optional


class JSONRepair:
    """JSON修復・クリーニングクラス"""
    
    @staticmethod
    def repair_json_string(json_string: str) -> Optional[Dict[str, Any]]:
        """
        不完全または不正なJSON文字列を修復してパース
        
        Args:
            json_string: 修復対象のJSON文字列
        
        Returns:
            パースされた辞書、またはパース不可の場合はNone
        """
        # ステップ1: マークダウンコード囲いを除去
        json_string = JSONRepair._remove_markdown_fences(json_string)
        
        # ステップ2: 前後の空白を削除
        json_string = json_string.strip()
        
        # ステップ3: 直接パースを試みる
        try:
            return json.loads(json_string)
        except json.JSONDecodeError:
            pass
        
        # ステップ4: よくあるエラーを修復
        repaired = JSONRepair._fix_common_errors(json_string)
        
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as e:
            print(f"JSON修復失敗: {e}")
            print(f"修復後のJSON: {repaired[:200]}...")
            return None
    
    @staticmethod
    def repair_json_array(json_array_string: str) -> Optional[list]:
        """
        JSON配列文字列を修復
        
        Args:
            json_array_string: JSON配列文字列
        
        Returns:
            パースされたリスト、またはパース不可の場合はNone
        """
        json_array_string = JSONRepair._remove_markdown_fences(json_array_string)
        json_array_string = json_array_string.strip()
        
        try:
            return json.loads(json_array_string)
        except json.JSONDecodeError:
            pass
        
        repaired = JSONRepair._fix_common_errors(json_array_string)
        
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as e:
            print(f"JSON配列修復失敗: {e}")
            return None
    
    @staticmethod
    def _remove_markdown_fences(text: str) -> str:
        """
        マークダウン形式のコード囲い（```json...```）を除去
        
        Args:
            text: 入力テキスト
        
        Returns:
            囲いを除去したテキスト
        """
        # ```json ... ``` パターン
        text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
        
        return text
    
    @staticmethod
    def _fix_common_errors(json_string: str) -> str:
        """
        よくあるJSON形式エラーを修復
        
        Args:
            json_string: 修復対象のJSON文字列
        
        Returns:
            修復後のJSON文字列
        """
        # 1. シングルクォートをダブルクォートに変換（JSON仕様）
        # ただし、文字列内のシングルクォートは保護
        json_string = JSONRepair._fix_quotes(json_string)
        
        # 2. 末尾のカンマを除去（],}の直前）
        json_string = re.sub(r',\s*([}\]])', r'\1', json_string)
        
        # 3. キーがクォートされていない場合を修復
        # "key": value -> "key": value の形に統一
        json_string = re.sub(r'([{,]\s*)([a-zA-Z_]\w*)(\s*:)', r'\1"\2"\3', json_string)
        
        # 4. null, true, false が正しいか確認（既に正しいはず）
        json_string = json_string.replace('null', 'null')
        json_string = json_string.replace('true', 'true')
        json_string = json_string.replace('false', 'false')
        
        # 5. 不完全なJSON（閉じ括弧がない）を修復
        open_braces = json_string.count('{') - json_string.count('}')
        open_brackets = json_string.count('[') - json_string.count(']')
        
        json_string += '}' * open_braces
        json_string += ']' * open_brackets
        
        return json_string
    
    @staticmethod
    def _fix_quotes(text: str) -> str:
        """
        シングルクォートをダブルクォートに変換（簡易版）
        
        Args:
            text: 入力テキスト
        
        Returns:
            修復後のテキスト
        """
        # 非常に簡易的な実装
        # より完璧には、状態機械を使った実装が必要
        
        result = []
        in_double_quote = False
        in_single_quote = False
        escape_next = False
        
        for i, char in enumerate(text):
            if escape_next:
                result.append(char)
                escape_next = False
                continue
            
            if char == '\\':
                result.append(char)
                escape_next = True
                continue
            
            if char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                result.append(char)
            elif char == "'" and not in_double_quote:
                # シングルクォートをダブルクォートに変換
                result.append('"')
                in_single_quote = not in_single_quote
            else:
                result.append(char)
        
        return ''.join(result)
    
    @staticmethod
    def validate_and_fix(data: Any, schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        パース済みデータを検証し、必要に応じて修復
        
        Args:
            data: パース済みのデータ
            schema: 期待されるスキーマ（オプション）
        
        Returns:
            修復済みのデータ
        """
        if not isinstance(data, dict):
            return {}
        
        # 必須フィールドの確認
        if schema:
            for key, key_type in schema.items():
                if key not in data:
                    data[key] = None
                elif key_type == int and not isinstance(data[key], int):
                    try:
                        data[key] = int(data[key])
                    except (ValueError, TypeError):
                        data[key] = 0
                elif key_type == str and not isinstance(data[key], str):
                    data[key] = str(data[key])
        
        return data


# テスト用
if __name__ == "__main__":
    # テスト1: 不正なJSON
    print("=== テスト1: マークダウン囲いの除去 ===")
    broken_json = """```json
{
  'name': 'Tokyo Station',
  'rating': 4.5,
}
```"""
    
    result = JSONRepair.repair_json_string(broken_json)
    if result:
        print(f"修復成功: {result}")
    
    # テスト2: シングルクォート
    print("\n=== テスト2: シングルクォート修復 ===")
    single_quote_json = "{'key': 'value', 'number': 123}"
    result = JSONRepair.repair_json_string(single_quote_json)
    if result:
        print(f"修復成功: {result}")
    
    # テスト3: 末尾のカンマ
    print("\n=== テスト3: 末尾カンマ修復 ===")
    trailing_comma = '{"items": [1, 2, 3,], "name": "test",}'
    result = JSONRepair.repair_json_string(trailing_comma)
    if result:
        print(f"修復成功: {result}")
