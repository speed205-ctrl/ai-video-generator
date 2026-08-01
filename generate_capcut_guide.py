import os
import sys
import json
import asyncio
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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
    
    # Preparar el prompt del usuario
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
        "   - Filtro recomendado en CapCut: Escribe un filtro real de CapCut que intensifique el tono y la atmósfera del tema "
        "(ej. para terror ártico usa tonos fríos y pálidos como 'Filtro Frío', 'Filtro Bosque Oscuro', 'Filtro Glaciar', 'Filtro Blanco y Negro'; "
        "para anomalías de internet usa 'Filtro VHS III', 'Filtro Cyberpunk', 'Filtro Película Retro', 'Filtro Gloom'). "
        "Sé sumamente creativo y específico con las intensidades del filtro (ej. 'VHS III al 75%').\n"
        "   - Efectos de video y transiciones en CapCut: Recomienda efectos específicos de CapCut (ej. 'Efecto Ruido de Estática (al 30%)', "
        "'Efecto Lente Tembloroso', 'Efecto de Glitch de Señal', 'Flashes sutiles en cortes', 'Desenfoque vertical', 'Efecto Aberración Cromática').\n"
        "   - Efecto de sonido (SFX): Sugiere efectos de sonido realistas acordes al guion y su atmósfera (ej. 'Zumbido de electricidad', "
        "'Crujido de hielo y viento', 'Masticar sordo lejano', 'Teclados mecánicos antiguos', 'Pulsos de sonar', 'Eco distante').\n"
        "   - Música de fondo (BGM): Recomienda cómo debe comportarse la música en esta escena y qué buscar en la biblioteca de CapCut "
        "(ej. 'Baja el volumen al 12% para destacar la voz, busca pistas de \"Dark Ambient Synth\", \"Frozen Drone\", o \"Creepy Piano\"'). "
        "Modula la intensidad de la música en los momentos clave de misterio o terror.\n"
        "3. El tono debe ser directo, profesional y enfocado en que el editor ahorre tiempo al momento de montar el video.\n"
        "Escribe exclusivamente la guía de edición en formato de texto plano y legible, sin introducciones vacías ni notas fuera de la estructura."
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

async def main():
    load_dotenv()
    
    # Configurar API
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

    output_base_dir = r"C:\Users\Jaime Enrique\OneDrive\Documents\youtube\project\output"
    
    if not os.path.exists(output_base_dir):
        print(f"Error: La carpeta de salidas '{output_base_dir}' no existe.")
        return
        
    # Obtener todas las carpetas de proyectos (que empiecen con 'video_')
    project_folders = [
        os.path.join(output_base_dir, d) 
        for d in os.listdir(output_base_dir) 
        if os.path.isdir(os.path.join(output_base_dir, d)) and d.startswith("video_")
    ]
    
    if not project_folders:
        print("No se encontraron carpetas de proyectos 'video_*' en el directorio de salidas.")
        return
        
    print(f"Se encontraron {len(project_folders)} carpetas de proyectos en total.")
    print("Iniciando la generación de guías detalladas para todos los proyectos...")
    
    for folder in project_folders:
        await generate_guide_for_project(llm, folder)
        
    print("\n¡Proceso de generación de guías finalizado para todos los proyectos!")

if __name__ == "__main__":
    asyncio.run(main())
