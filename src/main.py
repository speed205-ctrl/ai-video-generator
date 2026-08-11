import os
import sys
import re
import json
import argparse
import asyncio
import logging
from datetime import datetime
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any

# Import our custom modules
# We add the parent directory to system path in case of relative run issues
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.api_clients import LLMClient, ElevenLabsClient, NvidiaImageClient
from src.agents import ResearcherWriterAgent, PromptDirectorAgent, MetadataGeneratorAgent

import numpy as np
import cv2
from PIL import Image

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("main_orchestrator")

def slugify(text: str) -> str:
    """Converts a string to a safe ASCII-only directory name."""
    import unicodedata
    # Normalize string to decompose accented characters and ignore non-ASCII
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "_", text)
    return text.strip("_")

def format_timestamp(seconds: float) -> str:
    """Formats float seconds into a video timeline timestamp MM:SS.MS."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 100)
    return f"{mins:02d}:{secs:02d}.{millis:02d}"

async def process_scene(
    sem: asyncio.Semaphore,
    scene: dict,
    idx: int,
    output_dir: str,
    tts_client: Optional[ElevenLabsClient],
async def process_scene(scene_data: dict, output_dir: str, tts_client, image_client, sem: asyncio.Semaphore, mock_mode: bool = False, aspect_ratio: str = "16:9") -> dict:
    scene_num = scene_data["numero_escena"]
    scene_text = scene_data["texto"]
    scene_prompt = scene_data["prompt_imagen"]
    scene_effect = scene_data.get("efecto_capcut", "zoom_in")
    
    audio_filename = f"escena_{scene_num:02d}.mp3"
    image_filename = f"escena_{scene_num:02d}.png"
    prompt_filename = f"prompt_{scene_num:02d}.txt"
    
    audio_path = os.path.join(output_dir, "audios", audio_filename)
    image_path = os.path.join(output_dir, "imagenes", image_filename)
    prompt_path = os.path.join(output_dir, "imagenes", prompt_filename)
    
    # Save the prompt text file immediately so you have it in case of API failure
    try:
        os.makedirs(os.path.dirname(prompt_path), exist_ok=True)
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(scene_prompt)
    except Exception as e:
        logger.error(f"[Escena {scene_num}] Error al guardar archivo de prompt .txt: {e}")

    # Paths relative to the output folder (for easier portability in escaleta.json)
    rel_audio_path = f"audios/{audio_filename}"
    rel_image_path = f"imagenes/{image_filename}"

    async with sem:
        logger.info(f"[Escena {scene_num}] Procesando recursos concurrentemente...")
        
        # 1. Download TTS audio
        audio_exists_valid = os.path.exists(audio_path) and os.path.getsize(audio_path) > 3000
        if audio_exists_valid:
            logger.info(f"[Escena {scene_num}] Reutilizando audio existente ({os.path.getsize(audio_path)} bytes).")
        elif mock_mode or not tts_client:
            logger.info(f"[Mock] Creando audio silente mock para escena {scene_num}")
            os.makedirs(os.path.dirname(audio_path), exist_ok=True)
            import wave
            duration_est = max(3.5, len(scene_text.split()) * 0.4)
            with wave.open(audio_path, 'w') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(44100)
                wav_file.writeframes(b'\x00\x00' * int(44100 * duration_est))
        else:
            try:
                spanish_replacements = {
                    r"\bsangre\b": "carmesí",
                    r"\bcadáver(es)?\b": "cuerpo\\1 inerte\\1",
                    r"\basesin(ado|ada|ados|adas)\b": "caído\\1",
                    r"\basesinato(s)?\b": "crimen\\1",
                    r"\bmatar(on|lo|la|los|las)?\b": "silenciar\\1",
                    r"\bmasacre(s)?\b": "tragedia\\1",
                    r"\btortura(do|da|dos|das)?\b": "martirio",
                    r"\bsuicidio\b": "desesperación extrema"
                }
                sanitized_text = scene_text
                for pattern, replacement in spanish_replacements.items():
                    sanitized_text = re.sub(pattern, replacement, sanitized_text, flags=re.IGNORECASE)
                
                await tts_client.text_to_speech(sanitized_text, audio_path)
                logger.info(f"[Escena {scene_num}] Audio descargado exitosamente.")
            except Exception as e:
                logger.error(f"[Escena {scene_num}] Error al descargar audio: {e}")
                logger.warning(f"[Escena {scene_num}] Creando archivo de audio silente debido a fallo de API.")
                os.makedirs(os.path.dirname(audio_path), exist_ok=True)
                import wave
                duration_est = max(3.5, len(scene_text.split()) * 0.4)
                with wave.open(audio_path, 'w') as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(44100)
                    wav_file.writeframes(b'\x00\x00' * int(44100 * duration_est))

        # 2. Download Image
        img_dim = (576, 1024) if aspect_ratio == "9:16" else (1024, 576)
        image_exists_valid = os.path.exists(image_path) and os.path.getsize(image_path) > 10000
        if image_exists_valid:
            logger.info(f"[Escena {scene_num}] Reutilizando imagen existente ({os.path.getsize(image_path)} bytes).")
        elif mock_mode or not image_client:
            logger.info(f"[Mock] Creando imagen mock para escena {scene_num}")
            os.makedirs(os.path.dirname(image_path), exist_ok=True)
            from PIL import Image
            Image.new('RGB', img_dim, color='black').save(image_path)
        else:
            try:
                await image_client.generate_image(scene_prompt, image_path, aspect_ratio=aspect_ratio)
                logger.info(f"[Escena {scene_num}] Imagen descargada exitosamente.")
            except Exception as e:
                logger.error(f"[Escena {scene_num}] Error al descargar imagen: {e}")
                logger.warning(f"[Escena {scene_num}] Creando imagen placeholder negra debido a fallo de API.")
                os.makedirs(os.path.dirname(image_path), exist_ok=True)
                from PIL import Image
                Image.new('RGB', img_dim, color='black').save(image_path)

    # 3. Calculate exact duration using mutagen, fallback to words estimation if mutagen fails/mock
    duration = 5.0  # default
    if not mock_mode:
        try:
            from mutagen.mp3 import MP3
            audio = MP3(audio_path)
            duration = audio.info.length
        except Exception as e:
            # Safe fallback if mutagen fails to parse the file
            word_count = len(scene_text.split())
            duration = max(3.0, word_count * 0.4) # Estimate ~150 words per minute (0.4s/word)
            logger.warning(
                f"[Escena {scene_num}] No se pudo leer la duración exacta con Mutagen ({e}). "
                f"Estimando {duration:.2f} segundos."
            )
    else:
        # Mock mode duration based on words to make timeline look realistic
        word_count = len(scene_text.split())
        duration = max(3.5, word_count * 0.4)

    return {
        "numero_escena": scene_num,
        "texto": scene_text,
        "audio_path": rel_audio_path,
        "imagen_path": rel_image_path,
        "prompt_imagen": scene_prompt,
        "efecto_capcut": scene_effect,
        "duracion_segundos": round(duration, 3)
    }

def wrap_text_into_subtitles(text: str, max_chars: int = 35) -> List[str]:
    """Wraps text into lines of maximum max_chars characters without splitting words."""
    words = text.split()
    lines = []
    current_line = []
    current_len = 0
    for word in words:
        if current_len + len(word) + (1 if current_line else 0) > max_chars:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            current_len = len(word)
        else:
            current_line.append(word)
            current_len += len(word) + (1 if len(current_line) > 1 else 0)
    if current_line:
        lines.append(" ".join(current_line))
    return lines

def apply_dynamic_effect(clip, effect_name, scene_text=None):
    """Applies dynamic camera movement and draws subtitles on the frame using OpenCV (high performance)."""
    fh, fw = clip.size[1], clip.size[0] # MoviePy size is (width, height)
    duration = clip.duration

    # Split text into small subtitle chunks
    phrases = []
    if scene_text:
        phrases = wrap_text_into_subtitles(scene_text, max_chars=35)

    def get_zoomed_frame(get_frame, t):
        frame = get_frame(t)
        fh_f, fw_f = frame.shape[:2]
        
        progress = t / duration if duration > 0 else 0
        
        if effect_name == "Zoom in":
            scale = 1.0 + (0.1 * progress)
        elif effect_name == "Zoom out":
            scale = 1.1 - (0.1 * progress)
        elif effect_name and "Paneo" in effect_name:
            scale = 1.15
        else:
            scale = 1.0
            
        new_w, new_h = int(fw_f / scale), int(fh_f / scale)
        max_x_offset = fw_f - new_w
        max_y_offset = fh_f - new_h
        
        left = max_x_offset // 2
        top = max_y_offset // 2

        if effect_name == "Paneo lento izquierda":
            left = int(max_x_offset * (1 - progress))
        elif effect_name == "Paneo lento derecha":
            left = int(max_x_offset * progress)
        elif effect_name == "Paneo vertical":
            top = int(max_y_offset * progress)
            
        left = max(0, min(left, fw_f - new_w))
        top = max(0, min(top, fh_f - new_h))
        
        cropped = frame[top:top + new_h, left:left + new_w]
        
        if cropped.size == 0:
            resized = frame
        else:
            resized = cv2.resize(cropped, (fw_f, fh_f), interpolation=cv2.INTER_CUBIC)
            
        # Draw subtitles directly on the frame (resized is RGB NumPy array)
        if phrases:
            num_phrases = len(phrases)
            phrase_dur = duration / num_phrases if num_phrases > 0 else duration
            phrase_idx = min(int(t / phrase_dur), num_phrases - 1)
            active_phrase = phrases[phrase_idx]
            
            # Responsive font scale and thickness based on frame height
            font_scale = max(0.55, fh_f / 800.0)
            thickness = max(1, int(font_scale * 2.2))
            
            font = cv2.FONT_HERSHEY_SIMPLEX
            text_size = cv2.getTextSize(active_phrase, font, font_scale, thickness)[0]
            text_w, text_h = text_size[0], text_size[1]
            
            # Position: center horizontally, bottom margin (85% of height)
            x = (fw_f - text_w) // 2
            y = int(fh_f * 0.85)
            
            # Draw outline (Black)
            cv2.putText(resized, active_phrase, (x, y), font, font_scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
            # Draw fill (White)
            cv2.putText(resized, active_phrase, (x, y), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)
            
        return resized

    return clip.transform(get_zoomed_frame)

def render_scene_subclip(scene: dict, output_dir: str, temp_dir: str) -> dict:
    """
    Renders a single scene to a temporary .mp4 sub-clip.
    Runs in parallel inside a ProcessPoolExecutor.
    """
    import os
    import sys
    # Ensure correct path in worker sub-processes
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # We must defer moviepy imports to avoid startup GIL locks or pickle issues
    from moviepy import ImageClip, AudioFileClip

    num = scene.get("numero_escena", 0)
    audio_rel = scene.get("audio_path", "")
    image_rel = scene.get("imagen_path", "")
    
    audio_path = os.path.join(output_dir, audio_rel)
    image_path = os.path.join(output_dir, image_rel)
    
    if not os.path.exists(audio_path) or not os.path.exists(image_path):
        return {"numero_escena": num, "success": False, "error": f"Falta audio o imagen"}
        
    temp_clip_path = os.path.join(temp_dir, f"subclip_{num:02d}.mp4")
    temp_audio_path = os.path.join(temp_dir, f"temp_audio_{num:02d}.m4a")
    
    try:
        audio_clip = AudioFileClip(audio_path)
        image_clip = ImageClip(image_path)
        
        if hasattr(image_clip, "with_duration"):
            image_clip = image_clip.with_duration(audio_clip.duration)
        else:
            image_clip = image_clip.set_duration(audio_clip.duration)
            
        efecto = scene.get("efecto_capcut", "Zoom in")
        text_to_draw = scene.get("texto", "") if scene.get("subtitulos", False) else None
        animated_clip = apply_dynamic_effect(image_clip, efecto, text_to_draw)
            
        if hasattr(animated_clip, "with_audio"):
            video_scene = animated_clip.with_audio(audio_clip)
        else:
            video_scene = animated_clip.set_audio(audio_clip)
            
        # Write temporary subclip in CPU. We use preset='ultrafast' and libx264 for speed and safety.
        # threads=1 to avoid resource competition between parallel processes.
        video_scene.write_videofile(
            temp_clip_path,
            fps=24,
            codec="libx264",
            preset="ultrafast",
            audio_codec="aac",
            threads=1,
            logger=None,
            temp_audiofile=temp_audio_path,
            remove_temp=True
        )
        
        # Clean up memory
        audio_clip.close()
        image_clip.close()
        video_scene.close()
        
        return {
            "numero_escena": num,
            "success": True,
            "clip_path": temp_clip_path,
            "duracion": audio_clip.duration
        }
    except Exception as e:
        return {"numero_escena": num, "success": False, "error": str(e)}

def compile_video(output_dir: str, escaleta: dict) -> Optional[str]:
    logger.info("=" * 60)
    logger.info("INICIANDO ENSAMBLADO AUTOMÁTICO DE VIDEO (.MP4)")
    logger.info("=" * 60)
    
    try:
        from moviepy import VideoFileClip, concatenate_videoclips
        from moviepy.video.fx import CrossFadeIn
        from concurrent.futures import ProcessPoolExecutor, as_completed
        import shutil
    except ImportError:
        logger.error("No se pudo importar 'moviepy'. El ensamblado automático de video requiere 'moviepy' instalado.")
        return None

    escenas = escaleta.get("escenas", [])
    if not escenas:
        logger.warning("No hay escenas en la escaleta para compilar el video.")
        return None
        
    # Create temporary directory inside output_dir for subclips
    temp_dir = os.path.join(output_dir, "temp_subclips")
    os.makedirs(temp_dir, exist_ok=True)
    
    logger.info(f"Renderizando {len(escenas)} escenas en paralelo con 4 procesos...")
    
    subclips_info = []
    
    # Run in ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(render_scene_subclip, scene, output_dir, temp_dir): scene
            for scene in escenas
        }
        
        completed_count = 0
        total_scenes = len(escenas)
        
        for future in as_completed(futures):
            completed_count += 1
            res = future.result()
            if res.get("success"):
                logger.info(f"[Progreso] {completed_count}/{total_scenes} escenas procesadas. (Escena {res['numero_escena']} renderizada)")
                subclips_info.append(res)
            else:
                logger.error(f"[Error] Falló render de escena {res['numero_escena']}: {res.get('error')}")
                
    # Check if all scenes were compiled successfully
    if len(subclips_info) < len(escenas):
        logger.warning("Algunas escenas fallaron al renderizar. Se compilará solo con los sub-clips exitosos.")
        
    if not subclips_info:
        logger.error("No se pudo renderizar ningún sub-clip con éxito. Abortando.")
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass
        return None
        
    # Sort subclips by scene number to maintain order
    subclips_info.sort(key=lambda x: x["numero_escena"])
    
    clips = []
    guia_edicion = ["GUÍA DE EDICIÓN Y EFECTOS PARA CAPCUT\n", "=======================================\n"]
    current_time_sec = 0.0
    
    logger.info("Cargando y concatenando sub-clips renderizados...")
    for idx, info in enumerate(subclips_info):
        try:
            num = info["numero_escena"]
            path = info["clip_path"]
            
            # Find original scene details for the CapCut guide
            orig_scene = next((s for s in escenas if s.get("numero_escena") == num), {})
            efecto = orig_scene.get("efecto_capcut", "Zoom in")
            efecto_sonido = orig_scene.get("efecto_sonido", "Música de tensión genérica / Ambiente oscuro")
            
            video_scene = VideoFileClip(path)
            
            # Apply crossfade if it's not the first clip
            if idx > 0:
                video_scene = video_scene.with_effects([CrossFadeIn(1.0)])
                
            clips.append(video_scene)
            
            # Format time for the guide
            m, s = divmod(int(current_time_sec), 60)
            time_str = f"{m:02d}:{s:02d}"
            guia_edicion.append(f"[{time_str}] Escena {num}")
            guia_edicion.append(f" - Efecto Visual: {efecto}")
            guia_edicion.append(f" - Efecto de Sonido: {efecto_sonido}")
            guia_edicion.append(f" - Prompt base: {orig_scene.get('prompt_imagen', '')}")
            guia_edicion.append("")
            
            current_time_sec += info["duracion"]
        except Exception as e:
            logger.error(f"Error al cargar subclip {info['numero_escena']}: {e}")
            
    if not clips:
        logger.error("No se pudieron cargar clips válidos. Abortando.")
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass
        return None
        
    try:
        logger.info("Uniendo clips finales y aplicando efectos de transición...")
        final_clip = concatenate_videoclips(clips, method="compose")
        
        video_filename = "documental_final.mp4"
        video_path = os.path.join(output_dir, video_filename)
        
        logger.info(f"Codificando y exportando video final con aceleración GPU: {video_path}")
        
        final_clip.write_videofile(
            video_path,
            fps=24,
            codec="h264_nvenc",
            audio_codec="aac",
            threads=12,
            logger='bar',
            temp_audiofile=os.path.join(output_dir, "temp-audio-final.m4a"),
            remove_temp=True
        )
        
        # Close all clips
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass
        try:
            final_clip.close()
        except Exception:
            pass
            
        logger.info(f"¡Video compilado con éxito! Ubicación: {video_path}")
        
        # Clean up temporary folder
        logger.info("Limpiando archivos de sub-clips temporales...")
        try:
            shutil.rmtree(temp_dir)
        except Exception as err:
            logger.warning(f"No se pudo limpiar la carpeta temporal {temp_dir}: {err}")
            
        # Save CapCut Guide
        guia_path = os.path.join(output_dir, "Guia_Edicion_CapCut.txt")
        try:
            with open(guia_path, "w", encoding="utf-8") as f:
                f.write("\n".join(guia_edicion))
            logger.info(f"Guía de edición de CapCut guardada en: {guia_path}")
        except Exception as e:
            logger.error(f"Error al guardar la guía de edición: {e}")
            
        # Save SRT Subtitles
        srt_path = os.path.join(output_dir, "subtitulos.srt")
        try:
            srt_lines = []
            def parse_ts_to_srt(ts_str: str) -> str:
                try:
                    parts = ts_str.split(":")
                    mins = int(parts[0])
                    secs_ms = parts[1].split(".")
                    secs = int(secs_ms[0])
                    ms = int(secs_ms[1]) * 10
                    hrs = mins // 60
                    mins = mins % 60
                    return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"
                except Exception:
                    return "00:00:00,000"

            escenas = escaleta.get("escenas", [])
            for idx, scene in enumerate(escenas, start=1):
                text = scene.get("texto", "").strip()
                start_ts = parse_ts_to_srt(scene.get("timestamp_inicio", "00:00.00"))
                end_ts = parse_ts_to_srt(scene.get("timestamp_fin", "00:05.00"))
                srt_lines.append(str(idx))
                srt_lines.append(f"{start_ts} --> {end_ts}")
                srt_lines.append(text)
                srt_lines.append("")

            with open(srt_path, "w", encoding="utf-8") as f:
                f.write("\n".join(srt_lines))
            logger.info(f"Archivo de subtítulos SRT guardado en: {srt_path}")
        except Exception as e:
            logger.error(f"Error al guardar archivo SRT: {e}")

        return video_path
    except Exception as e:
        logger.error(f"Error al concatenar o escribir el video final: {e}")
        # Make sure to close clips even on error
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass
        return None


async def main_async(args):
    # Load environment variables
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    
    topic = args.tema
    max_scenes = args.limite_escenas
    mock_mode = args.mock
    
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    openrouter_model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
    nvidia_key = os.getenv("NVIDIA_API_KEY")
    nvidia_model = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-405b-instruct")
    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
    elevenlabs_voice = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgq5okZXeOhx")
    nvidia_image_key = os.getenv("NVIDIA_IMAGE_KEY")
    nvidia_image_model = os.getenv("NVIDIA_IMAGE_MODEL", "black-forest-labs/flux.2-klein-4b")

    # Auto-correct if NVIDIA key is placed in OpenRouter fields
    if openrouter_key and openrouter_key.startswith("nvapi-"):
        logger.warning("Auto-correcting OpenRouter Model to NVIDIA Model because NVIDIA key was used in OpenRouter field.")
        openrouter_model = nvidia_model

    # Determine final image key (fallback to general NVIDIA API key)
    final_image_key = nvidia_image_key or nvidia_key

    # API validation
    if not mock_mode:
        if not openrouter_key and not nvidia_key:
            logger.error("Error: Se requiere OPENROUTER_API_KEY o NVIDIA_API_KEY en el archivo .env. O ejecuta con '--mock'.")
            sys.exit(1)
        if not elevenlabs_key:
            logger.error("Error: Se requiere ELEVENLABS_API_KEY en el archivo .env. O ejecuta con '--mock'.")
            sys.exit(1)
        if not final_image_key:
            logger.error("Error: Se requiere NVIDIA_IMAGE_KEY o NVIDIA_API_KEY en el archivo .env. O ejecuta con '--mock'.")
            sys.exit(1)

    logger.info("=" * 60)
    logger.info(f"INICIANDO CREADOR DE ENIGMAS DIGITALES - GLITCHLABZ: '{topic}'")
    if mock_mode:
        logger.info("[MOCK MODE ACTIVADO] Se simularán las llamadas a APIs.")
    logger.info("=" * 60)

    # Initialize clients based on available keys
    writer_client = None
    director_client = None
    tts_client = None
    image_client = None

    if not mock_mode:
        # Determine LLM client config (prefer OpenRouter, fallback to NVIDIA)
        if openrouter_key:
            logger.info(f"Inicializando Agente Redactor con OpenRouter ({openrouter_model})")
            writer_client = LLMClient(
                api_key=openrouter_key,
                base_url="https://openrouter.ai/api/v1",
                default_model=openrouter_model
            )
        else:
            logger.info(f"Inicializando Agente Redactor con NVIDIA API ({nvidia_model})")
            writer_client = LLMClient(
                api_key=nvidia_key,
                base_url="https://integrate.api.nvidia.com/v1",
                default_model=nvidia_model
            )

        # Prompt Director uses NVIDIA API if available, otherwise shares OpenRouter
        if nvidia_key:
            logger.info(f"Inicializando Agente de Prompts con NVIDIA API ({nvidia_model})")
            director_client = LLMClient(
                api_key=nvidia_key,
                base_url="https://integrate.api.nvidia.com/v1",
                default_model=nvidia_model
            )
        else:
            logger.info("Inicializando Agente de Prompts compartiendo cliente OpenRouter")
            director_client = writer_client

        tts_client = ElevenLabsClient(api_key=elevenlabs_key, default_voice_id=elevenlabs_voice)
        image_client = NvidiaImageClient(api_key=final_image_key, model=nvidia_image_model)

    # Output Directory Setup
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"video_{slugify(topic)}_{timestamp}"
    output_dir = os.path.join(project_dir, "output", folder_name)
    
    os.makedirs(os.path.join(output_dir, "audios"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "imagenes"), exist_ok=True)
    
    logger.info(f"Directorio de salida creado: {output_dir}")
    print(f"__PROJECT_FOLDER__:{folder_name}", flush=True)

    # --- AGENT 1: RESEARCH & SCRIPT WRITING ---
    script_text = ""
    if getattr(args, "guion_path", None):
        logger.info(f"Cargando guion editado por el usuario desde: {args.guion_path}")
        try:
            with open(args.guion_path, "r", encoding="utf-8") as f:
                script_text = f.read()
        except Exception as e:
            logger.error(f"Error al leer el archivo de guion provisto: {e}")
            sys.exit(1)
    elif mock_mode:
        logger.info("[Mocking Agent 1] Escribiendo guion de GlitchLabz...")
        script_text = (
            "Cargas el archivo ejecutable en tu viejo computador. La pantalla parpadea en un verde pálido.\n"
            "Un zumbido de estática inunda tus auriculares. Sabes que hay un glitch en el código del juego.\n"
            "Sientes que el juego te observa. El personaje se mueve solo, desobedeciendo tus controles.\n"
            "Un error de renderizado borra el entorno, y una silueta caída se asoma desde la oscuridad del código."
        )
    else:
        writer_agent = ResearcherWriterAgent(writer_client)
        try:
            script_text = await writer_agent.write_script(topic)
            logger.info("Guion redactado exitosamente.")
            logger.debug(f"Guion:\n{script_text}")
        except Exception as e:
            logger.error(f"Error en Agente Redactor: {e}")
            sys.exit(1)

    # Save raw script for records
    with open(os.path.join(output_dir, "guion.txt"), "w", encoding="utf-8") as f:
        f.write(script_text)

    # --- YOUTUBE METADATA GENERATION ---
    metadata = {}
    if mock_mode or not writer_client:
        logger.info("[Mocking Metadata] Generando metadatos simulados de YouTube...")
        metadata = {
            "titulo": f"El Enigma de: {topic}",
            "propuestas_titulo": [
                f"La Verdadera Historia Detrás de {topic}",
                f"El Glitch de {topic} que Todos Ignoran",
                f"El Archivo Perdido de {topic}",
                f"¿Qué Fue Realmente de {topic}?"
            ],
            "prompt_miniatura": f"Corrupted glowing computer monitor showing glitchy representation of {topic}, dark room, wireframe textures, analog horror, 16:9",
            "descripcion_youtube": f"Hoy analizamos el intrigante caso de {topic}. Un misterio que ha desconcertado a miles en internet.\n\n#misterio #analoghorror #documental"
        }
    else:
        metadata_agent = MetadataGeneratorAgent(writer_client)
        try:
            metadata = await metadata_agent.generate_metadata(script_text)
            logger.info("Metadatos de YouTube generados exitosamente.")
        except Exception as e:
            logger.error(f"Error al generar metadatos de YouTube: {e}")
            metadata = {
                "titulo": topic,
                "propuestas_titulo": [
                    f"Misterio de {topic}",
                    f"El Enigma de {topic}",
                    f"El Secreto de {topic}",
                    f"Datos Ocultos: {topic}"
                ],
                "prompt_miniatura": "Ominous computer monitor in a dark room, analog horror, retro-tech, cinematic lighting, 16:9",
                "descripcion_youtube": f"Análisis profundo de {topic}. Descubre la verdad que se oculta detrás de este inquietante misterio."
            }

    # Save metadata.json
    metadata_path = os.path.join(output_dir, "metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    # --- AGENT 2: PROMPTS AND DIRECTION ---
    scenes = []
    if mock_mode:
        logger.info("[Mocking Agent 2] Segmentando guion y diseñando prompts...")
        scenes = [
            {
                "numero": 1,
                "texto": "Cargas el archivo ejecutable en tu viejo computador. La pantalla parpadea en un verde pálido.",
                "prompt_imagen": "First-person view of a dusty 1990s CRT computer monitor in a dark room, glowing green terminal text on screen, analog horror aesthetic, CRT scanlines, glitch distortion, 16:9 aspect ratio. Avoid cheerful, standard CGI, or friendly styles.",
                "efecto_capcut": "Zoom in"
            },
            {
                "numero": 2,
                "texto": "Un zumbido de estática inunda tus auriculares. Sabes que hay un glitch en el código del juego.",
                "prompt_imagen": "Close-up of old headphones on a desk, nearby computer screen showing corrupted game graphics with digital noise, analog horror aesthetic, CRT scanlines, glitch distortion, 16:9 aspect ratio. Avoid cheerful, standard CGI, or friendly styles.",
                "efecto_capcut": "Paneo lento izquierda"
            },
            {
                "numero": 3,
                "texto": "Sientes que el juego te observa. El personaje se mueve solo, desobedeciendo tus controles.",
                "prompt_imagen": "Retro 3D game screen with pixelated textures, a low-poly character standing in a dark hallway staring directly back at the camera, analog horror aesthetic, CRT scanlines, glitch distortion, 16:9 aspect ratio. Avoid cheerful, standard CGI, or friendly styles.",
                "efecto_capcut": "Zoom out"
            },
            {
                "numero": 4,
                "texto": "Un error de renderizado borra el entorno, y una silueta caída se asoma desde la oscuridad del código.",
                "prompt_imagen": "A completely black digital void on a monitor with neon red code scrolling, a faint glitchy outline of a humanoid shadow in the center, analog horror aesthetic, CRT scanlines, glitch distortion, 16:9 aspect ratio. Avoid cheerful, standard CGI, or friendly styles.",
                "efecto_capcut": "Paneo vertical"
            }
        ]
    else:
        director_agent = PromptDirectorAgent(director_client, max_scenes=max_scenes)
        try:
            scenes = await director_agent.segment_script(script_text)
            logger.info(f"Segmentación completada. Se generaron {len(scenes)} escenas.")
        except Exception as e:
            logger.error(f"Error en Agente de Prompts: {e}")
            sys.exit(1)

    aspect_ratio = getattr(args, "aspect_ratio", "16:9")

    # --- AGENT 3: EXECUTOR AND ASYNC DOWNLOADS (CONCURRENCY CONTROL = 2) ---
    logger.info("Iniciando descargas de recursos con control de concurrencia (Semaphore = 2)...")
    sem = asyncio.Semaphore(2)
    
    tasks = []
    for idx, scene in enumerate(scenes):
        tasks.append(
            process_scene(
                scene_data=scene,
                output_dir=output_dir,
                tts_client=tts_client,
                image_client=image_client,
                sem=sem,
                mock_mode=mock_mode,
                aspect_ratio=aspect_ratio
            )
        )
        
    # Gather execution results
    processed_scenes = await asyncio.gather(*tasks, return_exceptions=False)
    
    # Sort by scene number just to ensure timeline sequence is correct
    processed_scenes.sort(key=lambda s: s["numero_escena"])

    # --- TIMESTAMPS GENERATION AND ESCALETA ---
    current_time = 0.0
    final_scenes = []
    
    for scene in processed_scenes:
        duration = scene["duracion_segundos"]
        start_ts = format_timestamp(current_time)
        end_ts = format_timestamp(current_time + duration)
        
        scene_info = {
            "numero_escena": scene["numero_escena"],
            "texto": scene["texto"],
            "audio_path": scene["audio_path"],
            "imagen_path": scene["imagen_path"],
            "prompt_imagen": scene["prompt_imagen"],
            "efecto_capcut": scene["efecto_capcut"],
            "duracion_segundos": duration,
            "timestamp_inicio": start_ts,
            "timestamp_fin": end_ts,
            "subtitulos": getattr(args, "subtitulos", False)
        }
        
        final_scenes.append(scene_info)
        current_time += duration

    # Build Escaleta Structure
    escaleta = {
        "tema": topic,
        "aspect_ratio": aspect_ratio,
        "fecha_creacion": datetime.now().isoformat(),
        "total_escenas": len(final_scenes),
        "duracion_total_segundos": round(current_time, 3),
        "duracion_total_formateada": format_timestamp(current_time),
        "escenas": final_scenes
    }

    # Save escaleta.json
    escaleta_path = os.path.join(output_dir, "escaleta.json")
    with open(escaleta_path, "w", encoding="utf-8") as f:
        json.dump(escaleta, f, indent=2, ensure_ascii=False)
        
    # Save prompts_imagenes.txt containing all prompts separated by a blank line
    prompts_txt_path = os.path.join(output_dir, "prompts_imagenes.txt")
    with open(prompts_txt_path, "w", encoding="utf-8") as f:
        prompts_list = [scene.get("prompt_imagen", "") for scene in final_scenes]
        f.write("\n\n".join(prompts_list))
    logger.info(f"Lista consolidada de prompts de imágenes guardada en: {prompts_txt_path}")
        
    # Export CapCut Desktop Draft automatically
    try:
        from src.exporters.capcut_draft import CapCutDraftExporter
        exporter = CapCutDraftExporter(aspect_ratio=aspect_ratio)
        draft_path = exporter.export_project(output_dir)
        logger.info(f"Borrador de CapCut Desktop ({aspect_ratio}) generado en: {draft_path}")
    except Exception as draft_err:
        logger.warning(f"No se pudo exportar automáticamente el borrador de CapCut: {draft_err}")

    # Compile final video (.mp4) using MoviePy (skip in mock mode since audio files are empty/invalid)
    video_path = None
    if not mock_mode:
        try:
            video_path = compile_video(output_dir, escaleta)
        except Exception as video_err:
            logger.error(f"Error general durante el ensamblado automático de video: {video_err}")
    else:
        logger.info("[Mock Mode] Saltando ensamblado automático de video (.mp4) ya que los audios e imágenes son simulados.")
        
    logger.info("=" * 60)
    logger.info("PROCESAMIENTO FINALIZADO EXITOSAMENTE")
    logger.info(f"Escaleta central generada en: {escaleta_path}")
    if video_path:
        logger.info(f"Video final compilado exitosamente en: {video_path}")
    else:
        logger.info("El video no pudo ser compilado automáticamente (revisa los logs para ver la causa).")
    logger.info(f"Duración total del documental: {format_timestamp(current_time)}")
    logger.info(f"Se crearon {len(final_scenes)} escenas con audios e imágenes.")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Automatización de Documentales Históricos Oscuros para YouTube.")
    parser.add_argument("--tema", "-t", type=str, required=True, help="Tema del documental histórico.")
    parser.add_argument("--limite_escenas", "-l", type=int, default=45, help="Máximo de escenas/imágenes a generar (por cuotas de API).")
    parser.add_argument("--mock", action="store_true", help="Ejecutar en modo simulación (sin llamar a APIs reales).")
    parser.add_argument("--guion_path", type=str, default=None, help="Ruta al archivo de guion ya redactado/editado.")
    parser.add_argument("--subtitulos", action="store_true", help="Quemar subtítulos automáticos en el video.")
    parser.add_argument("--aspect-ratio", choices=["16:9", "9:16"], default="16:9", help="Relación de aspecto del video (16:9 o 9:16).")
    
    args = parser.parse_args()
    
    # Run the async loop
    asyncio.run(main_async(args))

if __name__ == "__main__":
    main()
