import os
import sys
import json
import asyncio
import argparse
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.api_clients import LLMClient

async def generate_guide_for_project(llm, project_dir):
    folder_name = os.path.basename(project_dir)
    escaleta_path = os.path.join(project_dir, "escaleta.json")
    guia_dest_path = os.path.join(project_dir, "Guia_Edicion_CapCut.txt")
    
    if not os.path.exists(escaleta_path):
        print(f"  [Saltado] No se encontró escaleta.json en {folder_name}")
        return
        
    print(f"\nProcesando proyecto: {folder_name}...")
    
    with open(escaleta_path, "r", encoding="utf-8") as f:
        escaleta = json.load(f)
        
    escenas = escaleta.get("escenas", [])
    tema = escaleta.get("tema", "Misterio Oscuro")
    print(f"  Cargadas {len(escenas)} escenas para '{tema}'. Enviando al LLM...")
    
    escenas_datos = []
    for escena in escenas:
        escenas_datos.append({
            "numero_escena": escena.get("numero_escena"),
            "texto": escena.get("texto"),
            "timestamp_inicio": escena.get("timestamp_inicio"),
            "timestamp_fin": escena.get("timestamp_fin"),
            "efecto_capcut": escena.get("efecto_capcut")
        })
        
    system_prompt = (
        "Actúas como un Director de Edición Profesional de Video para YouTube, especializado en documentales "
        "oscuros de misterio (terror analógico, creepypastas de internet, leyendas históricas oscuras, etc.).\n"
        f"Tu misión es tomar las escenas de la escaleta del tema '{tema}' (con sus textos, movimientos de cámara base y marcas de tiempo) "
        "y redactar una GUÍA DE EDICIÓN ULTRA-DETALLADA ESCENA POR ESCENA PARA CAPCUT.\n\n"
        "INSTRUCCIONES DE FORMATO Y CONTENIDO:\n"
        "1. Genera una estructura clara, ordenada por marcas de tiempo en formato de minutos y segundos (ej. '00:00 - 00:11').\n"
        "2. Para CADA escena, proporciona:\n"
        "   - Marca de tiempo de inicio y fin (ej. [00:11 - 00:25]).\n"
        "   - Filtro recomendado en CapCut: Escribe un filtro real de CapCut que intensifique el tono y la atmósfera del tema.\n"
        "   - Efectos de video y transiciones en CapCut.\n"
        "   - Efecto de sonido (SFX) específico.\n"
        "   - Música de fondo (BGM) recomendada y nivel de volumen.\n"
        "3. El tono debe ser directo, profesional y enfocado en que el editor ahorre tiempo.\n"
        "Escribe exclusivamente la guía de edición en formato de texto plano y legible."
    )
    
    user_prompt = f"Aquí están las escenas y los tiempos para construir la guía:\n\n{json.dumps(escenas_datos, indent=2, ensure_ascii=False)}"
    
    try:
        guia_contenido = await llm.generate_chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.65
        )
        
        with open(guia_dest_path, "w", encoding="utf-8") as out:
            out.write(guia_contenido)
            
        print(f"  [OK] Guía de Edición de CapCut guardada en: {guia_dest_path}")
    except Exception as e:
        print(f"  [ERROR] Error al generar la guía para {folder_name}: {e}")

async def run_generate_guides(target_folder: str = None):
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    load_dotenv(os.path.join(project_root, ".env"))
    
    nvidia_key = os.getenv("NVIDIA_API_KEY")
    nvidia_model = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-405b-instruct")
    
    if not nvidia_key:
        print("Error: No se encontró NVIDIA_API_KEY en el archivo .env.")
        return
        
    llm = LLMClient(
        api_key=nvidia_key,
        base_url="https://integrate.api.nvidia.com/v1",
        default_model=nvidia_model
    )

    output_base_dir = os.path.join(project_root, "output")
    
    if target_folder:
        folder_path = os.path.join(output_base_dir, target_folder) if not os.path.exists(target_folder) else target_folder
        await generate_guide_for_project(llm, folder_path)
    else:
        project_folders = [
            os.path.join(output_base_dir, d) 
            for d in os.listdir(output_base_dir) 
            if os.path.isdir(os.path.join(output_base_dir, d)) and d.startswith("video_")
        ]
        for folder in project_folders:
            await generate_guide_for_project(llm, folder)
            
    print("\n¡Proceso de generación de guías finalizado!")

def main():
    parser = argparse.ArgumentParser(description="Generador de guías de edición CapCut.")
    parser.add_argument("proyecto", nargs="?", default=None, help="Carpeta del proyecto específico (opcional).")
    args = parser.parse_args()
    asyncio.run(run_generate_guides(args.proyecto))

if __name__ == "__main__":
    main()
