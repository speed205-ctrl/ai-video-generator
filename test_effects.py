import os
import json
from PIL import Image
import numpy as np
from moviepy import ImageClip, AudioFileClip, concatenate_videoclips
from moviepy.video.fx import CrossFadeIn

def apply_dynamic_effect(clip, effect_name):
    """
    Applies mathematical transformations to create Zoom and Pan effects
    using PIL for high-quality Lanczos resampling.
    """
    w, h = clip.size
    duration = clip.duration

    def get_zoomed_frame(get_frame, t):
        frame = get_frame(t)
        # Prevent PIL from choking on read-only arrays
        img = Image.fromarray(np.array(frame))
        
        # Calculate current progress (0.0 to 1.0)
        progress = t / duration if duration > 0 else 0
        
        if effect_name == "Zoom in":
            scale = 1.0 + (0.1 * progress) # Max zoom 10%
        elif effect_name == "Zoom out":
            scale = 1.1 - (0.1 * progress) # Start at 10% zoom, go back to normal
        elif "Paneo" in effect_name:
            scale = 1.15 # Static zoom for pan
        else:
            scale = 1.0
            
        new_w, new_h = int(w / scale), int(h / scale)
        max_x_offset = w - new_w
        max_y_offset = h - new_h
        
        # Default center crop
        left = max_x_offset // 2
        top = max_y_offset // 2

        if effect_name == "Paneo lento izquierda":
            # Camera moves left -> crop box moves left -> start right, go left
            left = int(max_x_offset * (1 - progress))
        elif effect_name == "Paneo lento derecha":
            # Camera moves right -> crop box moves right -> start left, go right
            left = int(max_x_offset * progress)
        elif effect_name == "Paneo vertical":
            # Pan up/down. Let's do pan down (start top, go bottom)
            top = int(max_y_offset * progress)
            
        # Crop and resize back to original resolution
        img = img.crop((left, top, left + new_w, top + new_h))
        img = img.resize((w, h), Image.Resampling.LANCZOS)
        
        return np.array(img)

    return clip.transform(get_zoomed_frame)

def test_effects_compilation():
    project_dir = r"C:\Users\Jaime Enrique\OneDrive\Documents\youtube\project\output\video_luna_la_ia_de_microsoft_que_aprendió_a_odiar_en_24_horas_20260608_095805"
    escaleta_path = os.path.join(project_dir, "escaleta.json")
    
    with open(escaleta_path, "r", encoding="utf-8") as f:
        escaleta = json.load(f)
        
    escenas = escaleta.get("escenas", [])[:3] # Solamente las primeras 3 escenas
    clips = []
    
    print(f"Preparando 3 escenas para prueba de efectos con MoviePy...")
    
    for escena in escenas:
        num = escena.get("numero_escena")
        efecto = escena.get("efecto_capcut", "Zoom in")
        img_path = os.path.join(project_dir, escena.get("imagen_path"))
        audio_path = os.path.join(project_dir, escena.get("audio_path"))
        
        print(f"Escena {num}: Aplicando '{efecto}'...")
        
        audio_clip = AudioFileClip(audio_path)
        
        # 1. Crear el clip de imagen y ajustar su duración al audio
        image_clip = ImageClip(img_path).with_duration(audio_clip.duration)
        
        # 2. Aplicar el efecto de movimiento
        animated_clip = apply_dynamic_effect(image_clip, efecto)
        
        # 3. Asignar el audio
        video_scene = animated_clip.with_audio(audio_clip)
        
        # 4. Añadir un crossfadein de 1 segundo para una transición difuminada
        if clips: # Solo si no es la primera escena
            video_scene = video_scene.with_effects([CrossFadeIn(1.0)])
            
        clips.append(video_scene)

    if clips:
        print("Concatenando y renderizando video de prueba (esto tomará un momento)...")
        # Usamos method="compose" para que las transiciones crossfadein se apliquen correctamente
        final_clip = concatenate_videoclips(clips, method="compose")
        output_path = os.path.join(project_dir, "prueba_efectos_3_escenas.mp4")
        
        # Render
        final_clip.write_videofile(
            output_path, 
            fps=24, # 24 FPS para look cinemático
            codec="libx264", 
            audio_codec="aac",
            threads=12, # Usamos los 12 hilos lógicos del Ryzen 5 3600
            preset="fast"
        )
        print(f"\n¡Prueba terminada! Video guardado en: {output_path}")

if __name__ == "__main__":
    test_effects_compilation()
