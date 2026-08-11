import os
import glob
import shutil
import argparse

def run_import_images(origin_dir: str = None, project_dir: str = None):
    print("=== IMPORTADOR DE IMÁGENES CRONOLÓGICO ===")
    
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    output_base = os.path.join(project_root, "output")

    if not project_dir:
        # Ask user to pick project folder if not specified
        subdirs = [d for d in os.listdir(output_base) if os.path.isdir(os.path.join(output_base, d)) and d.startswith("video_")]
        if not subdirs:
            print("Error: No se encontraron proyectos en output/.")
            return False
            
        print("Proyectos disponibles:")
        for idx, d in enumerate(subdirs):
            print(f"  [{idx}] {d}")
            
        try:
            choice = input("Selecciona el proyecto de destino (número o nombre): ").strip()
            if choice.isdigit() and int(choice) < len(subdirs):
                target_folder = subdirs[int(choice)]
            else:
                target_folder = choice
            project_dir = os.path.join(output_base, target_folder)
        except (KeyboardInterrupt, SystemExit):
            print("Operación cancelada.")
            return False
            
    dest_dir = os.path.join(project_dir, "imagenes")
    
    default_origin = os.path.join(os.path.expanduser("~"), "Downloads")
    if not origin_dir:
        print(f"\nRuta de descargas detectada: {default_origin}")
        origin_dir = input("Ingresa la ruta completa de la carpeta con imágenes (Enter para usar Descargas): ").strip()
        if not origin_dir:
            origin_dir = default_origin
            
    if not os.path.exists(origin_dir):
        print(f"Error: La ruta origen '{origin_dir}' no existe.")
        return False
        
    image_extensions = ["*.png", "*.jpg", "*.jpeg", "*.webp"]
    found_files = []
    for ext in image_extensions:
        found_files.extend(glob.glob(os.path.join(origin_dir, ext)))
        
    if not found_files:
        print(f"No se encontraron imágenes en '{origin_dir}'.")
        return False
        
    found_files.sort(key=os.path.getmtime)
    print(f"\nSe encontraron {len(found_files)} imágenes ordenadas cronológicamente.")
    
    total_escenas = 44
    os.makedirs(dest_dir, exist_ok=True)
    
    for i, file_path in enumerate(found_files[:total_escenas]):
        escena_num = i + 1
        new_name = f"escena_{escena_num:02d}.png"
        dest_path = os.path.join(dest_dir, new_name)
        try:
            shutil.copy2(file_path, dest_path)
            print(f"[OK] {os.path.basename(file_path)} -> {new_name}")
        except Exception as e:
            print(f"[ERROR] No se pudo copiar {os.path.basename(file_path)}: {e}")
            
    print(f"\n¡Imágenes importadas con éxito en: {dest_dir}")
    return True

def main():
    parser = argparse.ArgumentParser(description="Importador cronológico de imágenes para escenas.")
    parser.add_argument("--origen", "-o", type=str, default=None, help="Carpeta de origen con las imágenes descargadas.")
    parser.add_argument("--proyecto", "-p", type=str, default=None, help="Ruta o nombre del proyecto de destino.")
    args = parser.parse_args()
    run_import_images(args.origen, args.proyecto)

if __name__ == "__main__":
    main()
