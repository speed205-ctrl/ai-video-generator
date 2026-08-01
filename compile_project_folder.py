import os
import json
import sys
import argparse

# Reconfigure console output to UTF-8 for Windows compatibility
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Import our main.py compilation module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.main import compile_video

def main():
    parser = argparse.ArgumentParser(description="Compilador general de proyectos de video.")
    parser.add_argument("carpeta", nargs="?", default=None, help="Nombre de la carpeta del proyecto en project/output/ (o ruta completa).")
    
    args = parser.parse_args()
    
    project_base = r"C:\Users\Jaime Enrique\OneDrive\Documents\youtube\project\output"
    
    if not args.carpeta:
        # If no arguments provided, let the user select
        print("Carpetas disponibles en project/output/:")
        subdirs = [d for d in os.listdir(project_base) if os.path.isdir(os.path.join(project_base, d)) and d != "temp"]
        if not subdirs:
            print("  No hay carpetas de proyectos disponibles.")
            sys.exit(0)
            
        for idx, d in enumerate(subdirs):
            print(f"  [{idx}] {d}")
        
        try:
            choice = input("\nSelecciona el número o escribe el nombre de la carpeta: ").strip()
            if choice.isdigit() and int(choice) < len(subdirs):
                folder_name = subdirs[int(choice)]
            else:
                folder_name = choice
        except (KeyboardInterrupt, SystemExit):
            print("\nOperación cancelada.")
            sys.exit(0)
    else:
        folder_name = args.carpeta
        
    # Check if it is a full path or a folder name in output/
    if os.path.exists(folder_name) and os.path.isdir(folder_name):
        project_dir = folder_name
    else:
        project_dir = os.path.join(project_base, folder_name)
        
    escaleta_path = os.path.join(project_dir, "escaleta.json")
    
    if not os.path.exists(project_dir):
        print(f"Error: La carpeta '{project_dir}' no existe.")
        sys.exit(1)
        
    if not os.path.exists(escaleta_path):
        print(f"Error: No se encontró 'escaleta.json' en '{project_dir}'.")
        sys.exit(1)
        
    with open(escaleta_path, "r", encoding="utf-8") as f:
        escaleta = json.load(f)
        
    print(f"\n=== Iniciando compilación de proyecto acelerada por GPU (4 núcleos + NVENC) ===")
    print(f"Proyecto: {project_dir}")
    print(f"Total de escenas a procesar: {len(escaleta.get('escenas', []))}\n")
    
    video_path = compile_video(project_dir, escaleta)
    
    if video_path:
        print(f"\n✅ ¡Proceso finalizado con éxito!")
        print(f"🎞️ Video guardado en: {video_path}")
        print(f"📄 Guía de CapCut guardada en la misma carpeta.")
    else:
        print(f"\n❌ Hubo un error en la compilación.")

if __name__ == "__main__":
    main()
