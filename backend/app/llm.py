from openai import OpenAI

from .config import settings


def get_llm_client() -> OpenAI:
    return OpenAI(base_url=settings.LLM_BASE_URL, api_key=settings.LLM_API_KEY)


def get_embed_client() -> OpenAI:
    return OpenAI(base_url=settings.SILICONFLOW_BASE_URL, api_key=settings.SILICONFLOW_API_KEY)
