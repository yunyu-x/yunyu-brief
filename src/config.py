"""Configuration management using pydantic-settings."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    QWEN = "qwen"
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    OLLAMA = "ollama"


# Provider -> (base_url, env_key_name, default_model)
PROVIDER_CONFIGS = {
    LLMProvider.QWEN: {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
    },
    LLMProvider.OPENAI: {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    },
    LLMProvider.DEEPSEEK: {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
    },
    LLMProvider.OLLAMA: {
        "base_url": "http://localhost:11434/v1",
        "default_model": "qwen2.5",
    },
}


class Settings(BaseSettings):
    """All configuration for Paperboy, loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Debug mode — enables full pipeline tracing
    debug: bool = False

    # Gmail
    gmail_address: str = ""
    gmail_app_password: str = ""
    gmail_label: str = "Newsletters"
    lookback_hours: int = 24

    # LLM
    llm_provider: LLMProvider = LLMProvider.QWEN

    # Qwen
    qwen_api_key: str = ""
    qwen_model: str = "qwen-plus"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"

    # Ollama
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2.5"

    # Agent behavior
    max_agent_turns: int = 3
    max_email_preview_chars: int = 500

    def get_llm_config(self) -> dict:
        """Return (api_key, base_url, model) for the selected provider."""
        provider_cfg = PROVIDER_CONFIGS[self.llm_provider]
        base_url = provider_cfg["base_url"]
        default_model = provider_cfg["default_model"]

        if self.llm_provider == LLMProvider.QWEN:
            return {
                "api_key": self.qwen_api_key,
                "base_url": base_url,
                "model": self.qwen_model or default_model,
            }
        elif self.llm_provider == LLMProvider.OPENAI:
            return {
                "api_key": self.openai_api_key,
                "base_url": base_url,
                "model": self.openai_model or default_model,
            }
        elif self.llm_provider == LLMProvider.DEEPSEEK:
            return {
                "api_key": self.deepseek_api_key,
                "base_url": base_url,
                "model": self.deepseek_model or default_model,
            }
        elif self.llm_provider == LLMProvider.OLLAMA:
            return {
                "api_key": "ollama",  # Ollama doesn't need a real key
                "base_url": self.ollama_base_url or base_url,
                "model": self.ollama_model or default_model,
            }
        raise ValueError(f"Unknown provider: {self.llm_provider}")


def get_settings() -> Settings:
    """Create and return settings instance."""
    return Settings()
