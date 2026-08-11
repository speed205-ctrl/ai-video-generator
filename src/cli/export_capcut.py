import os
import sys
import argparse
from pathlib import Path
from src.exporters.capcut_draft import CapCutDraftExporter

def run_export_capcut(project_arg: str = None, aspect_ratio: str = "9:16"):
    print("=== EXPORTADOR DE BORRADORES CAPCUT DESKTOP ===")
    
    project_root = Path(__file__).resolve().parent.parent.parent
    output_base = project_root / "output"
    
    if not project_arg:
        subdirs = [d for d in os.listdir(output_base) if os.path.isdir(output_base / d) and d.startswith("video_")]
        if not subdirs:
            print("Error: No se encontraron proyectos en project/output/.")
            return False
            
        print("Proyectos disponibles para exportar a CapCut Desktop:")
        for idx, d in enumerate(subdirs):
            print(f"  [{idx}] {d}")
            
        try:
            choice = input("\nSelecciona el número o nombre del proyecto: ").strip()
            if choice.isdigit() and int(choice) < len(subdirs):
                folder_name = subdirs[int(choice)]
            else:
                folder_name = choice
            project_dir = output_base / folder_name
        except (KeyboardInterrupt, SystemExit):
            print("\nOperación cancelada.")
            return False
    else:
        project_dir = Path(project_arg) if Path(project_arg).is_absolute() else output_base / project_arg

    if not project_dir.exists():
        print(f"Error: La carpeta del proyecto '{project_dir}' no existe.")
        return False

    print(f"\nGenerando borrador local de CapCut para '{project_dir.name}'...")
    print(f"Relación de aspecto seleccionada: {aspect_ratio}")
    
    exporter = CapCutDraftExporter(aspect_ratio=aspect_ratio)
    try:
        draft_path = exporter.export_project(str(project_dir))
        print("\n✅ ¡Borrador de CapCut generado con éxito!")
        print(f"📂 Ubicación del borrador: {draft_path}")
        print("👉 Abre CapCut Desktop en tu equipo para ver el borrador listo en tu panel de proyectos.")
        return True
    except Exception as e:
        print(f"\n❌ Error al exportar el borrador de CapCut: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Exportador de proyectos a borradores de CapCut Desktop.")
    parser.add_argument("proyecto", nargs="?", default=None, help="Nombre o ruta de la carpeta del proyecto en project/output/.")
    parser.add_argument("--aspect-ratio", choices=["9:16", "16:9"], default="9:16", help="Relación de aspecto del lienzo (default: 9:16).")
    args = parser.parse_args()
    run_export_capcut(args.proyecto, args.aspect_ratio)

if __name__ == "__main__":
    main()
