import os
import json
from moviepy import AudioFileClip

project_dir = r"C:\Users\Jaime Enrique\OneDrive\Documents\youtube\project\output\video_luna_la_ia_de_microsoft_que_aprendió_a_odiar_en_24_horas_20260608_095805"
escaleta_path = os.path.join(project_dir, "escaleta.json")
guia_path = os.path.join(project_dir, "Guia_Edicion_CapCut.txt")

with open(escaleta_path, "r", encoding="utf-8") as f:
    escaleta = json.load(f)

escenas = escaleta.get("escenas", [])
current_time_sec = 0.0

guia_edicion = ["GUÍA DE EDICIÓN Y EFECTOS PARA CAPCUT", "=======================================\n"]

for scene in escenas:
    num = scene.get("numero_escena")
    efecto = scene.get("efecto_capcut", "Zoom in")
    audio_path = os.path.join(project_dir, scene.get("audio_path"))
    
    try:
        audio_clip = AudioFileClip(audio_path)
        duration = audio_clip.duration
        audio_clip.close()
    except Exception:
        duration = 0
        
    m, s = divmod(int(current_time_sec), 60)
    time_str = f"{m:02d}:{s:02d}"
    
    guia_edicion.append(f"[{time_str}] Escena {num}")
    guia_edicion.append(f" - Efecto Visual: {efecto}")
    guia_edicion.append(f" - Efecto de Sonido Sugerido: Ambiente oscuro de tensión, estática de fondo")
    guia_edicion.append(f" - Prompt de la IA base: {scene.get('prompt_imagen', '')}")
    guia_edicion.append("")
    
    current_time_sec += duration

with open(guia_path, "w", encoding="utf-8") as f:
    f.write("\n".join(guia_edicion))

print(f"Guía creada en: {guia_path}")
