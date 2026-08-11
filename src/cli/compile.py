import os
import json
import sys
import argparse

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Import compile_video from src.main
from src.main import compile_video

def run_compile(folder_arg: str = None):
    # Calculate output base relative to project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    project_base = os.path.join(project_root, "output")
    
    if not os.path.exists(project_base):
        print(f"Error: No existe el directorio de salidas en '{project_base}'.")
        return False

    if not folder_arg:
        print("Carpetas disponibles en project/output/:")
        subdirs = [d for d in os.listdir(project_base) if os.path.isdir(os.path.join(project_base, d)) and d != "temp"]
        if not subdirs:
            print("  No hay carpetas de proyectos disponibles.")
            return False
            
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
            return False
    else:
        folder_name = folder_arg
        
    if os.path.exists(folder_name) and os.path.isdir(folder_name):
        project_dir = folder_name
    else:
        project_dir = os.path.join(project_base, folder_name)
        
    escaleta_path = os.path.join(project_dir, "escaleta.json")
    
    if not os.path.exists(project_dir):
        print(f"Error: La carpeta '{project_dir}' no existe.")
        return False
        
    if not os.path.exists(escaleta_path):
        print(f"Error: No se encontró 'escaleta.json' en '{project_dir}'.")
        return False
        
    with open(escaleta_path, "r", encoding="utf-8") as f:
        escaleta = json.load(f)
        
    print(f"\n=== Iniciando compilación de proyecto acelerada por GPU ===")
    print(f"Proyecto: {project_dir}")
    print(f"Total de escenas a procesar: {len(escaleta.get('escenas', []))}\n")
    
    video_path = compile_video(project_dir, escaleta)
    
    if video_path:
        print(f"\n✅ ¡Proceso finalizado con éxito!")
        print(f"🎞️ Video guardado en: {video_path}")
        return True
    else:
        print(f"\n❌ Hubo un error en la compilación.")
        return False

def main():
    parser = argparse.ArgumentParser(description="Compilador general de proyectos de video.")
    parser.add_argument("carpeta", nargs="?", default=None, help="Nombre de la carpeta del proyecto en project/output/ (o ruta completa).")
    args = parser.parse_args()
    run_compile(args.carpeta)

if __name__ == "__main__":
    main()
