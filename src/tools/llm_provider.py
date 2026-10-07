"""LLM Provider and structured inference manager for CloudSentry.

Manages Gemini and Groq integrations via LangChain with automatic detection of API keys
and structured Pydantic output binding, supporting seamless offline fallback.
"""

from typing import Optional, Type, TypeVar, Any, Dict, Tuple
import os
from dotenv import load_dotenv
from pydantic import BaseModel
from langchain_core.messages import SystemMessage, HumanMessage

# Load environment variables
load_dotenv()

T = TypeVar("T", bound=BaseModel)


def get_api_key_provider() -> Tuple[Optional[str], Optional[str]]:
    """Identifies available LLM provider and API key from environment."""
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")

    if gemini_key and gemini_key.strip():
        return "gemini", gemini_key.strip()
    elif groq_key and groq_key.strip():
        return "groq", groq_key.strip()
    return None, None


def is_llm_available() -> bool:
    """Returns True if a supported LLM API key is present in environment."""
    provider, key = get_api_key_provider()
    return provider is not None and bool(key)


def get_chat_model(temperature: float = 0.1) -> Optional[Any]:
    """Instantiates and returns the configured LangChain chat model or None."""
    provider, api_key = get_api_key_provider()
    if not provider or not api_key:
        return None

    try:
        if provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
            return ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=api_key,
                temperature=temperature,
            )
        elif provider == "groq":
            from langchain_groq import ChatGroq
            model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
            return ChatGroq(
                model=model_name,
                groq_api_key=api_key,
                temperature=temperature,
            )
    except Exception:
        return None

    return None


def invoke_structured_llm(
    schema: Type[T],
    system_prompt: str,
    user_prompt: str,
    model: Optional[Any] = None,
) -> Optional[T]:
    """Invokes LLM with structured output binding.

    Returns the parsed Pydantic model instance, or None if offline/error occurs.
    """
    chat_model = model or get_chat_model()
    if chat_model is None:
        return None

    try:
        structured_model = chat_model.with_structured_output(schema)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        result = structured_model.invoke(messages)

        if isinstance(result, schema):
            return result
        elif isinstance(result, dict):
            return schema.model_validate(result)
    except Exception:
        return None

    return None
