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
    gmail_label: str = ""  # Empty = INBOX (all emails); set to a label name to filter
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

    # === Twitter/X Source ===
    twitter_enabled: bool = False
    # Comma-separated tech topics (max 10). Empty = broad tech defaults.
    twitter_topics: str = ""
    twitter_lookback_hours: int = 24
    twitter_top_per_topic: int = 20
    twitter_final_top: int = 10

    # twikit (recommended, free, cookie-based)
    twikit_username: str = ""
    twikit_email: str = ""
    twikit_password: str = ""
    twikit_cookies_path: str = ""  # Path to cookies file, default: .twikit_cookies.json

    # twscrape accounts: "user1:pass1:email1:emailpass1,user2:pass2:email2:emailpass2"
    twscrape_accounts: str = ""

    # Nitter instances (comma-separated URLs)
    nitter_instances: str = ""

    # Official X API
    twitter_bearer_token: str = ""

    # H5 output — where to save the full briefing page
    # Can be a local path or a URL prefix for deployed pages
    twitter_h5_output_dir: str = "./output"
    # Base URL for accessing the H5 page (e.g., GitHub Pages URL)
    # Leave empty to use file:// path in email
    twitter_h5_base_url: str = ""

    def get_twitter_topics(self) -> list[str]:
        """Parse comma-separated topics into list, max 10."""
        if not self.twitter_topics.strip():
            return []
        topics = [t.strip() for t in self.twitter_topics.split(",") if t.strip()]
        return topics[:10]

    def get_twscrape_accounts(self) -> list[dict]:
        """Parse twscrape accounts string into list of dicts."""
        if not self.twscrape_accounts.strip():
            return []
        accounts = []
        for entry in self.twscrape_accounts.split(","):
            parts = entry.strip().split(":")
            if len(parts) == 4:
                accounts.append({
                    "username": parts[0],
                    "password": parts[1],
                    "email": parts[2],
                    "email_password": parts[3],
                })
        return accounts

    def get_nitter_instances(self) -> list[str] | None:
        """Parse comma-separated Nitter instances."""
        if not self.nitter_instances.strip():
            return None  # Use defaults
        return [u.strip() for u in self.nitter_instances.split(",") if u.strip()]

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
