from functools import lru_cache

from anthropic import Anthropic

from app.core.config import settings
from app.core.exceptions import AiNotConfiguredError

MODEL = "claude-opus-5"


def ai_available() -> bool:
    return bool(settings.anthropic_api_key)


@lru_cache
def get_client() -> Anthropic:
    if not settings.anthropic_api_key:
        raise AiNotConfiguredError()
    return Anthropic(api_key=settings.anthropic_api_key)
