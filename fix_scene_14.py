import os
import sys
import json
import asyncio
from dotenv import load_dotenv

# Reconfigure console output to UTF-8 for Windows compatibility
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.api_clients import NvidiaImageClient
from src.main import compile_video

async def fix_image():
    load_dotenv()
    nvidia_key = os.getenv("NVIDIA_IMAGE_KEY") or os.getenv("NVIDIA_API_KEY")
    nvidia_model = os.getenv("NVIDIA_IMAGE_MODEL", "black-forest-labs/flux.2-klein-4b")
    
    if not nvidia_key:
        print("Error: No se encontró NVIDIA_API_KEY en el archivo .env")
        return
        
    project_dir = r"C:\Users\Jaime Enrique\OneDrive\Documents\youtube\project\output\video_el_último_banquete_la_maldición_de_los_exploradores_de_la_isla_de_rakhaty_20260607_234607"
    escaleta_path = os.path.join(project_dir, "escaleta.json")
    
    with open(escaleta_path, "r", encoding="utf-8") as f:
        escaleta = json.load(f)
        
    scene_14 = next((s for s in escaleta["escenas"] if s["numero_escena"] == 14), None)
    if not scene_14:
        print("Error: No se encontró la escena 14 en la escaleta.")
        return
        
    prompt = scene_14["prompt_imagen"]
    img_path = os.path.join(project_dir, scene_14["imagen_path"])
    
    print(f"Regenerando imagen para Escena 14 usando {nvidia_model}...")
    print(f"Prompt: {prompt}")
    print(f"Guardando en: {img_path}")
    
    client = NvidiaImageClient(api_key=nvidia_key, model=nvidia_model)
    try:
        await client.generate_image(prompt, img_path)
        print("¡Imagen de Escena 14 generada con éxito!")
    except Exception as e:
        print(f"Error al generar la imagen: {e}")
        return
        
    # Recompile video
    print("\nRecompilando video final con todas las 32 escenas completas...")
    video_path = compile_video(project_dir, escaleta)
    if video_path:
        print(f"\n[OK] Video final compilado exitosamente: {video_path}")
    else:
        print("\n[ERROR] Ocurrió un error al compilar el video.")

if __name__ == "__main__":
    asyncio.run(fix_image())
