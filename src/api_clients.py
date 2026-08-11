import os
import json
import base64
import re
import asyncio
import aiohttp
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

async def _async_retry(coro_func, *args, max_retries: int = 4, initial_delay: float = 1.5, **kwargs):
    """
    Helper for exponential backoff retries on transient errors (HTTP 429, 5xx, or network timeouts).
    Does NOT retry on unrecoverable errors like HTTP 402 (Payment Required) or 401 (Unauthorized).
    """
    delay = initial_delay
    for attempt in range(1, max_retries + 1):
        try:
            return await coro_func(*args, **kwargs)
        except Exception as e:
            err_str = str(e)
            # Unrecoverable error statuses
            if "status 402" in err_str or "status 401" in err_str or "CONTENT_FILTERED" in err_str:
                logger.warning(f"Unrecoverable error encountered ({err_str}), skipping retries.")
                raise e
            
            if attempt == max_retries:
                logger.error(f"Max retries ({max_retries}) reached. Error: {e}")
                raise e
            
            logger.warning(f"Attempt {attempt}/{max_retries} failed ({e}). Retrying in {delay:.1f}s...")
            await asyncio.sleep(delay)
            delay *= 2.0


class LocalOllamaClient:
    """
    Fallback client for local Ollama instances (default: http://localhost:11434).
    """
    def __init__(self, base_url: str = "http://localhost:11434", default_model: str = "qwen2.5-coder:7b"):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model

    async def generate_chat(self, system_prompt: str, user_prompt: str, model: Optional[str] = None, temperature: float = 0.7) -> str:
        model_name = model or self.default_model
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as response:
                if response.status != 200:
                    text = await response.text()
                    raise Exception(f"Local Ollama API error ({response.status}): {text}")
                result = await response.json()
                return result["choices"][0]["message"]["content"]


class LocalSDWebUIClient:
    """
    Fallback client for local AUTOMATIC1111 / SD WebUI / Forge instances (default: http://127.0.0.1:7860).
    """
    def __init__(self, base_url: str = "http://127.0.0.1:7860"):
        self.base_url = base_url.rstrip("/")

    async def generate_image(self, prompt: str, output_path: str) -> str:
        url = f"{self.base_url}/sdapi/v1/txt2img"
        payload = {
            "prompt": prompt,
            "negative_prompt": "text, labels, signatures, watermarks, deformed, blurry",
            "width": 1024,
            "height": 576,
            "steps": 20,
            "cfg_scale": 7.0
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=180)) as response:
                if response.status != 200:
                    text = await response.text()
                    raise Exception(f"Local SD WebUI API error ({response.status}): {text}")
                result = await response.json()
                images = result.get("images", [])
                if not images:
                    raise Exception("No image returned from local SD WebUI API.")
                
                base64_data = images[0]
                image_bytes = base64.b64decode(base64_data)
                with open(output_path, "wb") as f:
                    f.write(image_bytes)
                return output_path


class LLMClient:
    """
    Client for OpenAI-compatible chat completion APIs (OpenRouter, NVIDIA Cloud, etc.).
    Supports exponential backoff and optional fallback to local Ollama.
    """
    def __init__(self, api_key: str, base_url: str, default_model: str, enable_local_fallback: bool = True):
        self.api_key = api_key
        if api_key.startswith("nvapi-") and "openrouter.ai" in base_url:
            logger.warning("Auto-correcting base_url from OpenRouter to NVIDIA Cloud API because API Key starts with 'nvapi-'.")
            self.base_url = "https://integrate.api.nvidia.com/v1"
        else:
            self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.local_fallback = LocalOllamaClient() if enable_local_fallback else None

    async def _raw_generate_chat(self, system_prompt: str, user_prompt: str, model: Optional[str] = None, temperature: float = 0.7) -> str:
        model_name = model or self.default_model
        url = f"{self.base_url}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        if "openrouter.ai" in url:
            headers["HTTP-Referer"] = "https://github.com/google-deepmind/antigravity"
            headers["X-Title"] = "DarkHistoryDocumentaryCreator"

        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=90)) as response:
                if response.status != 200:
                    text = await response.text()
                    logger.error(f"LLM API Error (Status {response.status}): {text}")
                    raise Exception(f"LLM API request failed with status {response.status}: {text}")
                
                result = await response.json()
                return result["choices"][0]["message"]["content"]

    async def generate_chat(self, system_prompt: str, user_prompt: str, model: Optional[str] = None, temperature: float = 0.7) -> str:
        try:
            return await _async_retry(
                self._raw_generate_chat, system_prompt, user_prompt, model=model, temperature=temperature
            )
        except Exception as e:
            if self.local_fallback:
                logger.warning(f"Cloud LLM API failed ({e}). Attempting local Ollama fallback...")
                try:
                    return await self.local_fallback.generate_chat(system_prompt, user_prompt, temperature=temperature)
                except Exception as local_e:
                    logger.error(f"Local Ollama fallback also failed: {local_e}")
            raise e


class ElevenLabsClient:
    """
    Client for ElevenLabs Text-to-Speech API with retries.
    """
    def __init__(self, api_key: str, default_voice_id: str):
        self.api_key = api_key
        self.default_voice_id = default_voice_id
        self.base_url = "https://api.elevenlabs.io/v1/text-to-speech"

    async def _raw_text_to_speech(self, text: str, output_path: str, voice_id: Optional[str] = None) -> str:
        voice = voice_id or self.default_voice_id
        url = f"{self.base_url}/{voice}"
        
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "accept": "audio/mpeg"
        }
        
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status != 200:
                    text_error = await response.text()
                    logger.error(f"ElevenLabs Error (Status {response.status}): {text_error}")
                    raise Exception(f"ElevenLabs request failed with status {response.status}: {text_error}")
                
                with open(output_path, "wb") as f:
                    while True:
                        chunk = await response.content.read(1024)
                        if not chunk:
                            break
                        f.write(chunk)
                return output_path

    async def text_to_speech(self, text: str, output_path: str, voice_id: Optional[str] = None) -> str:
        return await _async_retry(self._raw_text_to_speech, text, output_path, voice_id=voice_id)


class NvidiaImageClient:
    """
    Client for NVIDIA Cloud API Image Generation supporting BFL FLUX.2 Klein 4B and SD 3.5 Large.
    Supports retries and optional fallback to local SD WebUI / AUTOMATIC1111 / Forge.
    """
    def __init__(self, api_key: str, model: str = "black-forest-labs/flux.2-klein-4b", enable_local_fallback: bool = True):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://ai.api.nvidia.com/v1/genai"
        self.local_fallback = LocalSDWebUIClient() if enable_local_fallback else None

    async def _raw_generate_image(self, prompt: str, output_path: str) -> str:
        replacements = {
            r"\bblood(y)?\b": "crimson",
            r"\bdead\b": "still",
            r"\bcorpse(s)?\b": "fallen figure\\1",
            r"\bkill(ed|ing)?\b": "defeat\\1",
            r"\bdecapitat(ed|ion)\b": "shadowed",
            r"\bmutilat(ed|ion)\b": "injured",
            r"\btortur(ed|ing|e)\b": "suffering",
            r"\bburnt flesh\b": "smokey dark texture",
            r"\bflesh\b": "skin",
            r"\bexecution\b": "judgment",
            r"\bmurder(ed|er)?\b": "conflict",
            r"\bsuicide\b": "despair"
        }
        sanitized_prompt = prompt
        for pattern, replacement in replacements.items():
            sanitized_prompt = re.sub(pattern, replacement, sanitized_prompt, flags=re.IGNORECASE)
            
        url = f"{self.base_url}/{self.model}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        if "black-forest-labs" in self.model:
            payload = {
                "prompt": sanitized_prompt,
                "width": 1024,
                "height": 576,
                "seed": 0,
                "steps": 4
            }
        else:
            payload = {
                "prompt": sanitized_prompt,
                "cfg_scale": 5.0,
                "seed": 0,
                "steps": 25,
                "aspect_ratio": "16:9"
            }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=90)) as response:
                if response.status != 200:
                    text_error = await response.text()
                    logger.error(f"NVIDIA Image Gen Error (Status {response.status}): {text_error}")
                    raise Exception(f"NVIDIA Image Gen failed with status {response.status}: {text_error}")
                
                result = await response.json()
                base64_data = None
                finish_reason = None
                if "image" in result:
                    base64_data = result["image"]
                elif "data" in result and isinstance(result["data"], list) and len(result["data"]) > 0:
                    base64_data = result["data"][0].get("b64_json") or result["data"][0].get("url")
                elif "artifacts" in result and isinstance(result["artifacts"], list) and len(result["artifacts"]) > 0:
                    base64_data = result["artifacts"][0].get("base64")
                    finish_reason = result["artifacts"][0].get("finishReason")
                    
                if finish_reason == "CONTENT_FILTERED":
                    raise Exception("La imagen fue bloqueada por el filtro de moderación de contenido de NVIDIA (CONTENT_FILTERED).")
                    
                if not base64_data:
                    raise KeyError(f"Could not extract base64 image data from NVIDIA response.")
                
                if isinstance(base64_data, str) and base64_data.startswith("data:image"):
                    if "," in base64_data:
                        base64_data = base64_data.split(",", 1)[1]
                
                image_bytes = base64.b64decode(base64_data)
                with open(output_path, "wb") as f:
                    f.write(image_bytes)
                return output_path

    async def generate_image(self, prompt: str, output_path: str) -> str:
        try:
            return await _async_retry(self._raw_generate_image, prompt, output_path)
        except Exception as e:
            if self.local_fallback:
                logger.warning(f"Cloud Image API failed ({e}). Attempting local SD WebUI fallback...")
                try:
                    return await self.local_fallback.generate_image(prompt, output_path)
                except Exception as local_e:
                    logger.error(f"Local SD WebUI fallback also failed: {local_e}")
            raise e
