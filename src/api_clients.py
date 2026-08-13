import os
import sys
import json
import base64
import re
import asyncio
import aiohttp
import logging
from typing import Dict, Any, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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
            err_str = str(e) if str(e) else repr(e)
            # Unrecoverable error statuses
            if "status 402" in err_str or "status 401" in err_str or "status 404" in err_str or "CONTENT_FILTERED" in err_str:
                logger.warning(f"Unrecoverable error encountered ({err_str}), skipping retries.")
                raise e
            
            if attempt == max_retries:
                logger.error(f"Max retries ({max_retries}) reached. Error: {err_str}")
                raise e
            
            logger.warning(f"Attempt {attempt}/{max_retries} failed ({err_str}). Retrying in {delay:.1f}s...")
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
        base_clean = base_url.rstrip("/")
        if base_clean.endswith("/chat/completions"):
            base_clean = base_clean[:-17]
        elif base_clean.endswith("/chat"):
            base_clean = base_clean[:-5]

        if api_key.startswith("nvapi-") and "openrouter.ai" in base_clean:
            self.base_url = "https://integrate.api.nvidia.com/v1"
        else:
            self.base_url = base_clean
        self.default_model = default_model or "meta/llama-3.1-70b-instruct"
        self.local_fallback = LocalOllamaClient() if enable_local_fallback else None

    async def _raw_generate_chat(self, system_prompt: str, user_prompt: str, model: Optional[str] = None, temperature: float = 0.7, max_tokens: Optional[int] = None) -> str:
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
        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=90)) as response:
                if response.status != 200:
                    text = await response.text()
                    logger.error(f"LLM API Error (Status {response.status}): {text}")
                    raise Exception(f"LLM API request failed with status {response.status}: {text}")
                
                result = await response.json()
                return result["choices"][0]["message"]["content"]

    # Prioritized model pool for automatic failover when a model is overloaded, rate-limited, or timing out
    DEFAULT_NVIDIA_POOL = [
        "meta/llama-3.3-70b-instruct",
        "meta/llama-3.1-70b-instruct",
        "meta/llama-3.2-3b-instruct"
    ]

    async def generate_chat(self, system_prompt: str, user_prompt: str, model: Optional[str] = None, temperature: float = 0.7, max_tokens: Optional[int] = None) -> str:
        # Build sequence of models to attempt: requested model first, then the remaining models from the pool
        requested_model = model or self.default_model
        model_queue = [requested_model]
        for m in self.DEFAULT_NVIDIA_POOL:
            if m not in model_queue:
                model_queue.append(m)

        last_exception = None
        for attempt_idx, current_model in enumerate(model_queue):
            try:
                if attempt_idx > 0:
                    logger.warning(f"🤖 [Model Rotation Agent] Conmutando a modelo de respaldo ({attempt_idx}/{len(model_queue) - 1}): {current_model}")
                
                return await _async_retry(
                    self._raw_generate_chat, system_prompt, user_prompt, model=current_model, temperature=temperature, max_tokens=max_tokens, max_retries=2
                )
            except Exception as e:
                last_exception = e
                logger.warning(f"⚠️ [Model Rotation Agent] Modelo '{current_model}' presentó error/lentitud: {e}")
                continue

        # If all cloud models in pool failed, try local Ollama if enabled
        if self.local_fallback:
            logger.warning(f"Todos los modelos de la nube fallaron ({last_exception}). Intentando respaldo local Ollama...")
            try:
                return await self.local_fallback.generate_chat(system_prompt, user_prompt, temperature=temperature)
            except Exception as local_e:
                logger.error(f"El respaldo local Ollama también falló: {local_e}")
        
        raise last_exception or Exception("Todos los modelos del pool de rotación fallaron.")



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


_POLLINATIONS_LOCK = asyncio.Semaphore(1)


class PollinationsImageClient:
    """
    Fallback client using Pollinations AI (FLUX model) for high-definition image generation.
    Supports rate limiting and retry handling for HTTP 429.
    """
    async def generate_image(self, prompt: str, output_path: str, aspect_ratio: str = "16:9") -> str:
        import urllib.parse
        width, height = (576, 1024) if aspect_ratio == "9:16" else (1024, 576)
        encoded_prompt = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&model=flux&nologo=true&seed={hash(prompt) % 100000}"
        
        async with _POLLINATIONS_LOCK:
            logger.info(f"Generando imagen con motor Pollinations FLUX: {prompt[:60]}...")
            max_attempts = 4
            for attempt in range(1, max_attempts + 1):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                            if response.status == 429:
                                logger.warning(f"Pollinations AI colada (429), reintentando en 2.5s (Intento {attempt}/{max_attempts})...")
                                await asyncio.sleep(2.5)
                                continue
                            if response.status != 200:
                                text_error = await response.text()
                                raise Exception(f"Pollinations AI request failed ({response.status}): {text_error}")
                            image_bytes = await response.read()
                            if len(image_bytes) < 3000:
                                raise Exception(f"Pollinations AI returned invalid image payload ({len(image_bytes)} bytes).")
                            dir_name = os.path.dirname(output_path)
                            if dir_name:
                                os.makedirs(dir_name, exist_ok=True)
                            with open(output_path, "wb") as f:
                                f.write(image_bytes)
                            logger.info(f"Imagen guardada exitosamente en: {output_path}")
                            await asyncio.sleep(1.0)
                            return output_path
                except Exception as e:
                    if attempt == max_attempts:
                        raise e
                    logger.warning(f"Error en intento {attempt} con Pollinations AI: {e}. Reintentando...")
                    await asyncio.sleep(2.0)
            raise Exception("No se pudo obtener imagen de Pollinations AI después de varios intentos.")


class HuggingFaceImageClient:
    """
    Client for Hugging Face Serverless Inference API Image Generation.
    Supports FLUX.1-schnell, SD 3.5, etc.
    """
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("HUGGINGFACE_API_KEY", "").strip() or os.getenv("HF_TOKEN", "").strip()
        self.model = model or os.getenv("HUGGINGFACE_IMAGE_MODEL", "").strip() or "black-forest-labs/FLUX.1-schnell"

    async def generate_image(self, prompt: str, output_path: str, aspect_ratio: str = "16:9") -> str:
        if not self.api_key:
            raise ValueError("No se configuró HUGGINGFACE_API_KEY en el entorno o interfaz.")
            
        model_name = self.model.strip()
        url = f"https://router.huggingface.co/hf-inference/models/{model_name}"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "inputs": prompt
        }
        
        logger.info(f"Generando imagen con Hugging Face ({model_name}): {prompt[:60]}...")
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=90)) as response:
                if response.status != 200:
                    text_error = await response.text()
                    logger.error(f"Hugging Face Image Gen Error ({response.status}): {text_error[:200]}")
                    raise Exception(f"Hugging Face API Error ({response.status}): {text_error[:150]}")
                
                image_bytes = await response.read()
                if len(image_bytes) < 1000:
                    raise Exception(f"Hugging Face devolvió datos de imagen inválidos ({len(image_bytes)} bytes).")
                
                dir_name = os.path.dirname(output_path)
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(image_bytes)
                logger.info(f"Imagen guardada exitosamente con Hugging Face en: {output_path}")
                return output_path


class NvidiaImageClient:
    """
    Client for NVIDIA Cloud API Image Generation supporting BFL FLUX and SD 3.5.
    Supports retries, aspect ratio (16:9 or 9:16), and automatic fallback to Hugging Face, Pollinations FLUX and local SD WebUI.
    """
    def __init__(self, api_key: str, model: str = "black-forest-labs/flux-1-schnell", default_model: Optional[str] = None, enable_local_fallback: bool = True):
        self.api_key = api_key
        self.model = default_model or model
        self.base_url = "https://ai.api.nvidia.com/v1/genai"
        self.pollinations_fallback = PollinationsImageClient()
        self.local_fallback = LocalSDWebUIClient() if enable_local_fallback else None

    async def _raw_generate_image(self, prompt: str, output_path: str, aspect_ratio: str = "16:9") -> str:
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
            
        width, height = (576, 1024) if aspect_ratio == "9:16" else (1024, 576)
        aspect_suffix = "9:16 vertical portrait framing" if aspect_ratio == "9:16" else "16:9 widescreen cinematic framing"
        final_prompt = f"{sanitized_prompt}, {aspect_suffix}"

        model_str = (self.model or "").strip()
        if model_str.startswith("http://") or model_str.startswith("https://"):
            url = model_str
        else:
            url = f"{self.base_url}/{model_str}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        if "black-forest-labs" in self.model:
            payload = {
                "prompt": final_prompt,
                "width": width,
                "height": height,
                "seed": 0,
                "steps": 4
            }
        else:
            payload = {
                "prompt": final_prompt,
                "cfg_scale": 5.0,
                "seed": 0,
                "steps": 25,
                "aspect_ratio": aspect_ratio
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

    async def generate_image(self, prompt: str, output_path: str, aspect_ratio: str = "16:9") -> str:
        try:
            return await _async_retry(self._raw_generate_image, prompt, output_path, aspect_ratio=aspect_ratio)
        except Exception as e:
            hf_key = os.getenv("HUGGINGFACE_API_KEY", "").strip() or os.getenv("HF_TOKEN", "").strip()
            if hf_key:
                hf_model = os.getenv("HUGGINGFACE_IMAGE_MODEL", "stabilityai/stable-diffusion-xl-base-1.0").strip()
                logger.warning(f"NVIDIA Image API falló ({e}). Conmutando a Hugging Face API ({hf_model})...")
                try:
                    hf_client = HuggingFaceImageClient(api_key=hf_key, model=hf_model)
                    return await hf_client.generate_image(prompt, output_path, aspect_ratio=aspect_ratio)
                except Exception as hf_err:
                    logger.error(f"Fallo en Hugging Face API: {hf_err}")

            logger.warning(f"Conmutando a motor de respaldo Pollinations FLUX...")
            try:
                return await self.pollinations_fallback.generate_image(prompt, output_path, aspect_ratio=aspect_ratio)
            except Exception as pol_e:
                logger.error(f"Fallo en motor Pollinations FLUX: {pol_e}")
                if self.local_fallback:
                    try:
                        return await self.local_fallback.generate_image(prompt, output_path)
                    except Exception:
                        pass
                raise e
