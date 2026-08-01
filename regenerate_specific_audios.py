import os
import sys
import json
import re
import asyncio
from dotenv import load_dotenv

# Reconfigure console output to UTF-8 for Windows compatibility
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.api_clients import ElevenLabsClient
from src.main import compile_video, format_timestamp

async def main():
    load_dotenv()
    
    project_dir = r"C:\Users\Jaime Enrique\OneDrive\Documents\youtube\project\output\video_el_último_banquete_la_maldición_de_los_exploradores_de_la_isla_de_rakhaty_20260607_234607"
    escaleta_path = os.path.join(project_dir, "escaleta.json")
    
    if not os.path.exists(escaleta_path):
        print(f"Error: Escaleta no encontrada en {escaleta_path}")
        return
        
    with open(escaleta_path, "r", encoding="utf-8") as f:
        escaleta = json.load(f)
        
    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
    elevenlabs_voice = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgq5okZXeOhx")
    
    if not elevenlabs_key:
        print("Error: No se encontró ELEVENLABS_API_KEY en el archivo .env")
        return
        
    tts_client = ElevenLabsClient(api_key=elevenlabs_key, default_voice_id=elevenlabs_voice)
    
    # Sanitization rules (same as main.py)
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
    
    # Search regex pattern
    search_pattern = re.compile(
        r"|".join(spanish_replacements.keys()),
        re.IGNORECASE
    )
    
    regenerated_count = 0
    
    print("=== Análisis de escenas en búsqueda de palabras delicadas ===")
    
    for scene in escaleta.get("escenas", []):
        texto = scene.get("texto", "")
        num = scene.get("numero_escena", 0)
        
        # Check if there is any match
        if search_pattern.search(texto):
            print(f"\n[Escena {num}] Encontradas palabras delicadas:")
            print(f"  Texto original: \"{texto}\"")
            
            # Apply replacements
            sanitized_text = texto
            for pattern, replacement in spanish_replacements.items():
                sanitized_text = re.sub(pattern, replacement, sanitized_text, flags=re.IGNORECASE)
                
            print(f"  Texto desinfectado: \"{sanitized_text}\"")
            
            audio_path = os.path.join(project_dir, scene["audio_path"])
            print(f"  Generando nuevo audio en: {audio_path}...")
            
            try:
                # Regenerate audio using ElevenLabs Client
                await tts_client.text_to_speech(sanitized_text, audio_path)
                print(f"  [OK] Audio regenerado con éxito.")
                regenerated_count += 1
            except Exception as e:
                print(f"  [ERROR] Error al generar audio: {e}")
                
    if regenerated_count == 0:
        print("\nNo se encontraron escenas con palabras delicadas para regenerar.")
        return
        
    print(f"\nSe regeneraron {regenerated_count} archivos de audio.")
    print("Recalculando la línea de tiempo de la escaleta...")
    
    # Recalculate duration and timestamps for all scenes
    current_time = 0.0
    for scene in escaleta.get("escenas", []):
        audio_path = os.path.join(project_dir, scene["audio_path"])
        duration = 5.0
        try:
            from mutagen.mp3 import MP3
            audio = MP3(audio_path)
            duration = audio.info.length
        except Exception as e:
            print(f"Advertencia: No se pudo leer duración de {audio_path}: {e}")
            duration = scene.get("duracion_segundos", 5.0)
            
        scene["duracion_segundos"] = round(duration, 3)
        scene["timestamp_inicio"] = format_timestamp(current_time)
        scene["timestamp_fin"] = format_timestamp(current_time + duration)
        current_time += duration
        
    escaleta["duracion_total_segundos"] = round(current_time, 3)
    escaleta["duracion_total_formateada"] = format_timestamp(current_time)
    
    # Save the updated escaleta.json
    with open(escaleta_path, "w", encoding="utf-8") as f:
        json.dump(escaleta, f, indent=2, ensure_ascii=False)
    print("Escaleta actualizada guardada en disco.")
    
    # Recompile video final
    print("\nRecompilando video final con los nuevos audios...")
    video_path = compile_video(project_dir, escaleta)
    if video_path:
        print(f"\n[OK] Video compilado y guardado en: {video_path}")
    else:
        print("\n[ERROR] Ocurrió un error al compilar el video.")

if __name__ == "__main__":
    asyncio.run(main())
