# api/llm_client.py
from __future__ import annotations

import os
import json
import logging
from typing import Any, Dict, List

import httpx
from fastapi import HTTPException

logger = logging.getLogger("llm_client")

# ============================================
# ダミーモード設定
# ============================================

NL_DUMMY_MODE = os.getenv("NL_DUMMY_MODE", "0") == "1"

# ============================================
# Azure OpenAI 設定
# ============================================

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")  # 例: https://xxx.openai.azure.com
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

# デプロイ名（モデル名ではなく「Azure 上の deployment 名」）
AZURE_OPENAI_STOCK_DEPLOYMENT = os.getenv(
    "AZURE_OPENAI_STOCK_DEPLOYMENT",
    "nl-stock-deployment",
)
AZURE_OPENAI_FEATURE_DEPLOYMENT = os.getenv(
    "AZURE_OPENAI_FEATURE_DEPLOYMENT",
    "nl-feature-deployment",
)


class LLMConfigError(RuntimeError):
    pass


# ============================================
# Azure OpenAI 呼び出し
# ============================================

async def _call_chat_completion_azure(
    deployment: str,
    messages: List[Dict[str, Any]],
) -> str:
    """
    Azure OpenAI Chat Completions を叩く薄いラッパー。
    返り値は assistant.message.content の文字列（JSON文字列想定）。

    エンドポイント:
      {endpoint}/openai/deployments/{deployment}/chat/completions?api-version=...
    """
    if not AZURE_OPENAI_ENDPOINT:
        raise LLMConfigError("AZURE_OPENAI_ENDPOINT is not set.")
    if not AZURE_OPENAI_API_KEY:
        raise LLMConfigError("AZURE_OPENAI_API_KEY is not set.")

    url = (
        f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/"
        f"{deployment}/chat/completions"
        f"?api-version={AZURE_OPENAI_API_VERSION}"
    )

    headers = {
        "api-key": AZURE_OPENAI_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        # Azure では body に model は不要（deployment 名でルーティング）
        "messages": messages,
    }

    logger.debug("Calling Azure OpenAI: deployment=%s", deployment)

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            logger.error(
                "Azure OpenAI API error %s: %s", resp.status_code, resp.text
            )
            raise HTTPException(
                status_code=500,
                detail=f"Azure OpenAI API error: {resp.status_code}",
            )

        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except Exception as ex:
            logger.exception("Unexpected Azure OpenAI response: %s", data)
            raise HTTPException(
                status_code=500,
                detail="Unexpected Azure OpenAI response format.",
            ) from ex

        logger.debug("Azure OpenAI raw content: %s", content)
        return content


def _extract_json_text(text: str) -> str:
    """
    Try to extract a JSON substring from LLM text output.

    Strategy:
    - strip surrounding whitespace
    - if it already starts with '{' or '[' return it
    - otherwise find the first '{' and the last '}' and return that slice
    - raise ValueError if no JSON-like braces are found
    """
    if text is None:
        raise ValueError("No text to extract JSON from")

    s = text.strip()
    if not s:
        raise ValueError("Empty string")

    if s[0] in ("{", "["):
        return s

    first = s.find("{")
    last = s.rfind("}")
    if first == -1 or last == -1 or last < first:
        raise ValueError("No JSON object found in text")

    return s[first : last + 1]


# ---------------------------------------
# few-shot 用メッセージ（素材抽出）
# ---------------------------------------

_STOCK_SYSTEM_PROMPT = (
    "You are a Stock Extractor for a CAD system. "
    "The user will describe the raw workpiece (stock) in Japanese. "
    "You must output ONLY JSON with a single top-level key \"stock\". "
    "Do not add explanations or comments."
)

_STOCK_FEWSHOT_MESSAGES: List[Dict[str, Any]] = [
    {
        "role": "system",
        "content": _STOCK_SYSTEM_PROMPT,
    },
    {
        "role": "user",
        "content": "100×60×20 mm の直方体ブロック素材を用意する。\n原点はブロック中心、+Z を上向きとする。",
    },
    {
        "role": "assistant",
        "content": (
            "{\n"
            "  \"stock\": {\n"
            "    \"type\": \"block\",\n"
            "    \"params\": {\n"
            "      \"w\": 100.0,\n"
            "      \"d\": 60.0,\n"
            "      \"h\": 20.0\n"
            "    }\n"
            "  }\n"
            "}"
        ),
    },
]


# ============================================
# ダミー実装（素材）
# ============================================

def _dummy_stock(text: str) -> Dict[str, Any]:
    """
    LLM なしで動かすための簡易ダミー。
    入力に関係なく、ある程度まともな block を返す。
    """
    logger.info("[DUMMY] stock extractor called with text=%r", text)

    # すこしだけ真面目に数値を拾うこともできるが、
    # とりあえずは固定値で十分。
    return {
        "stock": {
            "type": "block",
            "params": {
                "w": 100.0,
                "d": 60.0,
                "h": 20.0,
            },
        }
    }


async def call_stock_extractor(text: str, language: str | None = "ja") -> Dict[str, Any]:
    """
    素材命令（自然言語） → {\"stock\": {...}} を返す。

    戻り値の例:
        {
          "stock": {
            "type": "block",
            "params": { "w": 100.0, "d": 60.0, "h": 20.0 }
          }
        }
    ダミーモード or 設定不足のときは _dummy_stock を使う。
    """
    # ダミーモード or Azure 設定不足ならダミーに切り替え
    if NL_DUMMY_MODE or not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
        return _dummy_stock(text)

    messages = list(_STOCK_FEWSHOT_MESSAGES) + [
        {"role": "user", "content": text}
    ]

    try:
        content = await _call_chat_completion_azure(
            AZURE_OPENAI_STOCK_DEPLOYMENT,
            messages,
        )
    except LLMConfigError as e:
        logger.error("LLM config error in call_stock_extractor: %s", e)
        # 設定エラー時もダミーにフォールバックする
        return _dummy_stock(text)

    # content は JSON 文字列を想定
    # First try direct parse; if it fails, attempt to extract JSON substring
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        try:
            json_text = _extract_json_text(content)
            data = json.loads(json_text)
        except ValueError as ex:
            logger.exception("Failed to extract JSON from stock extractor output: %s", content)
            raise HTTPException(
                status_code=502,
                detail="LLM stock extractor did not return valid JSON.",
            ) from ex
        except json.JSONDecodeError as ex:
            logger.exception("Failed to parse extracted JSON from stock extractor: %s", json_text)
            raise HTTPException(
                status_code=502,
                detail="LLM stock extractor returned invalid JSON after extraction.",
            ) from ex

    return data


# ---------------------------------------
# few-shot 用メッセージ（フィーチャ抽出）
# ---------------------------------------

_FEATURE_SYSTEM_PROMPT = (
    "You are a Feature Extractor for a CAD system. "
    "The user will describe a single machining feature in Japanese. "
    "You must output ONLY JSON with keys \"op\", \"selector\", and \"params\". "
    "Assume the workpiece coordinate system is already known. "
    "Do not add explanations or comments."
)

_FEATURE_FEWSHOT_MESSAGES: List[Dict[str, Any]] = [
    {
        "role": "system",
        "content": _FEATURE_SYSTEM_PROMPT,
    },
    # フェイスミル
    {
        "role": "user",
        "content": "まず、上面を Zマイナス方向に 2 mm フェイスミルして、基準面を作る。",
    },
    {
        "role": "assistant",
        "content": (
            "{\n"
            "  \"op\": \"mill:face\",\n"
            "  \"selector\": \">Z\",\n"
            "  \"params\": {\n"
            "    \"depth\": 2.0\n"
            "  }\n"
            "}"
        ),
    },
    # 矩形ポケット
    {
        "role": "user",
        "content": "次に、上面の中心を原点として、40×30 mm の矩形ポケットを深さ 10 mm、四隅 R4 mm でフライス加工する。",
    },
    {
        "role": "assistant",
        "content": (
            "{\n"
            "  \"op\": \"mill:rect_pocket\",\n"
            "  \"selector\": \">Z\",\n"
            "  \"params\": {\n"
            "    \"width\": 40.0,\n"
            "    \"height\": 30.0,\n"
            "    \"depth\": 10.0,\n"
            "    \"corner_radius\": 4.0,\n"
            "    \"center_x\": 0.0,\n"
            "    \"center_y\": 0.0\n"
            "  }\n"
            "}"
        ),
    },
    # 中心穴
    {
        "role": "user",
        "content": "最後に、上面中心から直径 10 mm、深さ 15 mm の穴を 1 つドリル加工する。",
    },
    {
        "role": "assistant",
        "content": (
            "{\n"
            "  \"op\": \"drill:hole\",\n"
            "  \"selector\": \">Z\",\n"
            "  \"params\": {\n"
            "    \"dia\": 10.0,\n"
            "    \"depth\": 15.0,\n"
            "    \"x\": 0.0,\n"
            "    \"y\": 0.0\n"
            "  }\n"
            "}"
        ),
    },
]


# ============================================
# ダミー実装（フィーチャ）
# ============================================

def _dummy_feature(text: str) -> Dict[str, Any]:
  """
  LLM なしで動かすための簡易フィーチャ推定。
  超ラフにキーワードで判定する。
  """
  t = text.lower()
  logger.info("[DUMMY] feature extractor called with text=%r", text)

  # フェイスミル
  if "フェイス" in text or "荒取り" in text or "フェース" in text:
      return {
          "op": "mill:face",
          "selector": ">Z",
          "params": {
              "depth": 2.0,
          },
      }

  # ポケット
  if "ポケット" in text:
      return {
          "op": "mill:pocket_profile",
          "name": "RectPocket",
          "selector": ">Z",
          "params": {
              "profile_type": "rect",
              "center": {"x": 0.0, "y": 0.0},
              "size": {"x": 40.0, "y": 30.0},
              "depth": 10.0,
              "corner_radius": 4.0,
          },
      }

  # 穴（ドリル）
  if "穴" in text or "ドリル" in text:
      return {
          "op": "drill:hole",
          "selector": ">Z",
          "params": {
              "dia": 10.0,
              "depth": 15.0,
              "x": 0.0,
              "y": 0.0,
          },
      }

  # それ以外は一旦「浅いフェイスミル」にしておく
  return {
      "op": "mill:face",
      "selector": ">Z",
      "params": {
          "depth": 1.0,
      },
  }


async def call_feature_extractor(text: str, language: str | None = "ja") -> Dict[str, Any]:
    """
    フィーチャ命令（自然言語） → 単一フィーチャ JSON を返す。

    戻り値の例:
        {
          "op": "drill:hole",
          "selector": ">Z",
          "params": { "dia": 10.0, "depth": 15.0, "x": 0.0, "y": 0.0 }
        }
    ダミーモード or 設定不足のときは _dummy_feature を使う。
    """
    if NL_DUMMY_MODE or not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
        return _dummy_feature(text)

    messages = list(_FEATURE_FEWSHOT_MESSAGES) + [
        {"role": "user", "content": text}
    ]

    try:
        content = await _call_chat_completion_azure(
            AZURE_OPENAI_FEATURE_DEPLOYMENT,
            messages,
        )
    except LLMConfigError as e:
        logger.error("LLM config error in call_feature_extractor: %s", e)
        # 設定エラー時もダミーにフォールバック
        return _dummy_feature(text)

    # Try direct JSON parse first, fall back to extraction if necessary
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        try:
            json_text = _extract_json_text(content)
            data = json.loads(json_text)
        except ValueError as ex:
            logger.exception("Failed to extract JSON from feature extractor output: %s", content)
            raise HTTPException(
                status_code=502,
                detail="LLM feature extractor did not return valid JSON.",
            ) from ex
        except json.JSONDecodeError as ex:
            logger.exception("Failed to parse extracted JSON from feature extractor: %s", json_text)
            raise HTTPException(
                status_code=502,
                detail="LLM feature extractor returned invalid JSON after extraction.",
            ) from ex

    return data
