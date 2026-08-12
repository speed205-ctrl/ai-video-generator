import os
import sys
import json
import asyncio
import argparse
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.api_clients import NvidiaImageClient
from src.main import compile_video
from src.exporters.capcut_draft import CapCutDraftExporter

async def regenerate_images(folder_arg: str = None, aspect_ratio: str = "16:9"):
    project_root = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(dotenv_path=os.path.join(project_root, ".env"))
    
    nvidia_key = os.getenv("NVIDIA_IMAGE_KEY") or os.getenv("NVIDIA_API_KEY") or "fallback_key"
    nvidia_model = os.getenv("NVIDIA_IMAGE_MODEL", "black-forest-labs/flux-1-schnell")
    client = NvidiaImageClient(api_key=nvidia_key, model=nvidia_model)
    
    output_base = os.path.join(project_root, "output")
    
    if folder_arg:
        if os.path.exists(folder_arg) and os.path.isdir(folder_arg):
            output_dir = folder_arg
        else:
            output_dir = os.path.join(output_base, folder_arg)
    else:
        # Find latest project directory in output/
        subdirs = [
            os.path.join(output_base, d) for d in os.listdir(output_base)
            if os.path.isdir(os.path.join(output_base, d)) and d != "temp" and d != "temp_subclips"
        ]
        if not subdirs:
            print("Error: No se encontraron proyectos en 'output/'.")
            return
        output_dir = max(subdirs, key=os.path.getmtime)
        print(f"Directorio de proyecto detectado automáticamente: {os.path.basename(output_dir)}")

    escaleta_path = os.path.join(output_dir, "escaleta.json")
    if not os.path.exists(escaleta_path):
        print(f"Error: No se encontró 'escaleta.json' en '{output_dir}'.")
        return
        
    with open(escaleta_path, "r", encoding="utf-8") as f:
        escaleta = json.load(f)
        
    escenas = escaleta.get("escenas", [])
    print(f"Iniciando regeneración de {len(escenas)} imágenes HD (Aspect Ratio: {aspect_ratio})...")
    
    sem = asyncio.Semaphore(2)

    async def process_image(scene):
        num = scene.get("numero_escena") or scene.get("numero", 1)
        prompt = scene.get("prompt_imagen", "")
        img_rel = scene.get("imagen_path") or f"imagenes/escena_{num:02d}.png"
        img_path = os.path.join(output_dir, img_rel)
        
        async with sem:
            print(f"[Escena {num}] Generando imagen...")
            try:
                await client.generate_image(prompt, img_path, aspect_ratio=aspect_ratio)
                print(f"[Escena {num}] Imagen regenerada exitosamente.")
            except Exception as e:
                print(f"[Escena {num}] Error al generar imagen: {e}")

    tasks = [process_image(scene) for scene in escenas]
    await asyncio.gather(*tasks)
    
    print("\nReensamblando video final .mp4...")
    try:
        video_path = compile_video(output_dir, escaleta)
        if video_path:
            print(f"✅ Video compilado con éxito: {video_path}")
    except Exception as err:
        print(f"Error al compilar video: {err}")

    print("Actualizando borrador en CapCut Desktop...")
    try:
        exporter = CapCutDraftExporter(aspect_ratio=aspect_ratio)
        draft_path = exporter.export_project(output_dir)
        print(f"✅ Borrador de CapCut actualizado en: {draft_path}")
    except Exception as err:
        print(f"Error al exportar a CapCut: {err}")

def main():
    parser = argparse.ArgumentParser(description="Regenerador universal de imágenes para proyectos.")
    parser.add_argument("carpeta", nargs="?", default=None, help="Nombre de la carpeta del proyecto en project/output/.")
    parser.add_argument("--aspect-ratio", choices=["16:9", "9:16", "1:1"], default="16:9", help="Relación de aspecto de imágenes.")
    args = parser.parse_args()
    
    ratio = args.aspect_ratio
    if ratio == "1:1":
        ratio = "16:9"  # Use standard aspect ratio parameter mapping
        
    asyncio.run(regenerate_images(args.carpeta, aspect_ratio=ratio))

if __name__ == "__main__":
    main()
