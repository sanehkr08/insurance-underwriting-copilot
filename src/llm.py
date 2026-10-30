"""Ask Gemini or Groq for a JSON answer, switching provider if one fails.

Settings come from .env:
    GEMINI_API_KEY, GROQ_API_KEY   your keys
    PROVIDERS                      order to try, default "gemini,groq"
    GEMINI_MODEL                   default "gemini-3.6-flash"
    GROQ_MODEL                     default "openai/gpt-oss-120b"
"""
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DEFAULT_MODELS = {
    "gemini": "gemini-3.6-flash",
    "groq": "openai/gpt-oss-120b",
}


class LLMError(Exception):
    """Every provider failed."""


def _key(provider: str) -> str | None:
    value = os.getenv(f"{provider.upper()}_API_KEY", "").strip()
    return None if not value or value.startswith("paste-your") else value


def _call_gemini(model: str, key: str, system: str, user: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model=model,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            temperature=0,
        ),
    )
    return response.text


def _call_groq(model: str, key: str, system: str, user: str) -> str:
    from groq import Groq

    client = Groq(api_key=key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return response.choices[0].message.content


CALLERS = {"gemini": _call_gemini, "groq": _call_groq}


def _strip_code_fences(text: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return match.group(1) if match else text


def ask_json(system: str, user: str, schema: type[BaseModel]) -> tuple[BaseModel, str]:
    """Return (parsed answer, "provider:model") from the first provider that works."""
    user = (
        f"{user}\n\nRespond with only a JSON object that matches this JSON schema:\n"
        f"{json.dumps(schema.model_json_schema())}"
    )
    errors = []
    for provider in os.getenv("PROVIDERS", "gemini,groq").split(","):
        provider = provider.strip().lower()
        key = _key(provider)
        if provider not in CALLERS or key is None:
            continue
        model = os.getenv(f"{provider.upper()}_MODEL", DEFAULT_MODELS[provider])
        try:
            text = CALLERS[provider](model, key, system, user)
            return schema.model_validate_json(_strip_code_fences(text)), f"{provider}:{model}"
        except ValidationError as e:
            errors.append(f"{provider}:{model} gave JSON in the wrong shape: {str(e)[:300]}")
        except Exception as e:
            errors.append(f"{provider}:{model} failed: {type(e).__name__}: {str(e)[:300]}")
        print(f"  ! {errors[-1][:160]} - trying next provider")
    raise LLMError("No provider worked:\n" + "\n".join(errors or ["no API keys found in .env"]))
