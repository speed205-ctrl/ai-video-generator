import os
import sys
import json
import asyncio
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.api_clients import NvidiaImageClient

async def regenerate_images():
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    nvidia_key = os.getenv("NVIDIA_IMAGE_KEY") or os.getenv("NVIDIA_API_KEY")
    nvidia_model = os.getenv("NVIDIA_IMAGE_MODEL", "black-forest-labs/flux.2-klein-4b")
    
    if not nvidia_key:
        print("Error: No se encontró NVIDIA_API_KEY en el archivo .env.")
        return

    client = NvidiaImageClient(api_key=nvidia_key, model=nvidia_model)
    output_dir = r"C:\Users\Jaime Enrique\OneDrive\Documents\youtube\project\output\video_luna_la_ia_de_microsoft_que_aprendió_a_odiar_en_24_horas_20260608_095805"
    escaleta_path = os.path.join(output_dir, "escaleta.json")
    
    if not os.path.exists(escaleta_path):
        print(f"Error: No se encontró la escaleta en {escaleta_path}")
        return
        
    with open(escaleta_path, "r", encoding="utf-8") as f:
        escaleta = json.load(f)
        
    escenas = escaleta.get("escenas", [])
    print(f"Iniciando regeneración de {len(escenas)} imágenes usando NVIDIA ({nvidia_model})...")
    
    # Control de concurrencia para evitar saturar la API
    sem = asyncio.Semaphore(2)

    async def process_image(scene):
        num = scene.get("numero_escena")
        prompt = scene.get("prompt_imagen")
        img_rel = scene.get("imagen_path")
        img_path = os.path.join(output_dir, img_rel)
        
        async with sem:
            print(f"[Escena {num}] Generando imagen...")
            try:
                await client.generate_image(prompt, img_path)
                print(f"[Escena {num}] Imagen guardada exitosamente.")
            except Exception as e:
                print(f"[Escena {num}] Error al generar: {e}")

    tasks = [process_image(scene) for scene in escenas]
    await asyncio.gather(*tasks)
    print("\nProceso de regeneración finalizado.")

if __name__ == "__main__":
    asyncio.run(regenerate_images())
