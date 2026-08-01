import os
import json
import sys

# Reconfigure console output to UTF-8 for Windows compatibility
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Import our updated main.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.main import compile_video

def main():
    project_dir = r"C:\Users\Jaime Enrique\OneDrive\Documents\youtube\project\output\video_luna_la_ia_de_microsoft_que_aprendió_a_odiar_en_24_horas_20260608_095805"
    escaleta_path = os.path.join(project_dir, "escaleta.json")
    
    with open(escaleta_path, "r", encoding="utf-8") as f:
        escaleta = json.load(f)
        
    print(f"=== Iniciando compilación COMPLETA acelerada por GPU (RTX 3060) ===")
    print(f"Proyecto: {project_dir}")
    print(f"Total de escenas a procesar: {len(escaleta.get('escenas', []))}\n")
    
    # This will now use the updated main.py logic (apply_dynamic_effect, CrossFade, NVENC)
    video_path = compile_video(project_dir, escaleta)
    
    if video_path:
        print(f"\n✅ ¡Proceso finalizado con éxito!")
        print(f"🎞️ Video guardado en: {video_path}")
        print(f"📄 Guía de CapCut guardada en la misma carpeta.")
    else:
        print(f"\n❌ Hubo un error en la compilación.")

if __name__ == "__main__":
    main()
