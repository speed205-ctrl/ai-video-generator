import os
import glob
import shutil

# Configuración de rutas
project_dest_dir = r"C:\Users\Jaime Enrique\OneDrive\Documents\youtube\project\output\video_baxter_17_el_satélite_que_transmitió_en_soliario_durante_34_años_20260608_143343\imagenes"

def main():
    print("=== SCRIPT PARA RENOMBRAR E IMPORTAR IMÁGENES CRONOLÓGICAMENTE ===")
    print("Este script ordenará las imágenes de una carpeta por fecha de creación (de más antigua a más nueva)")
    print("y las guardará con los nombres correctos (escena_01.png, escena_02.png...) en el proyecto.\n")
    
    # Pedir la carpeta de origen
    default_origin = r"C:\Users\Jaime Enrique\Downloads"
    print(f"Ruta por defecto sugerida (puedes crear una carpeta dentro de Descargas):")
    print(f"  {default_origin}")
    origin_dir = input("Ingresa la ruta completa de la carpeta donde están tus imágenes generadas (presiona Enter para usar Descargas): ").strip()
    
    if not origin_dir:
        origin_dir = default_origin
        
    if not os.path.exists(origin_dir):
        print(f"Error: La ruta de origen '{origin_dir}' no existe.")
        return

    # Buscar imágenes comunes (png, jpg, jpeg, webp)
    image_extensions = ["*.png", "*.jpg", "*.jpeg", "*.webp"]
    found_files = []
    for ext in image_extensions:
        found_files.extend(glob.glob(os.path.join(origin_dir, ext)))
        
    if not found_files:
        print(f"No se encontraron imágenes (.png, .jpg, .jpeg, .webp) en '{origin_dir}'.")
        return

    # Ordenar por fecha de modificación (la más antigua primero)
    found_files.sort(key=os.path.getmtime)
    
    print(f"\nSe encontraron {len(found_files)} imágenes en la carpeta de origen.")
    print("Las imágenes se procesarán en el orden en que fueron modificadas/creadas (más antigua primero).")
    
    # Confirmar cuántas queremos importar (por ejemplo, las 44 del video)
    total_escenas = 44
    print(f"El video requiere exactamente {total_escenas} imágenes.")
    
    confirm = input(f"¿Deseas importar las primeras {min(len(found_files), total_escenas)} imágenes ordenadas a tu proyecto? (s/n): ").strip().lower()
    if confirm != 's':
        print("Proceso cancelado por el usuario.")
        return
        
    # Crear carpeta de destino si no existe
    os.makedirs(project_dest_dir, exist_ok=True)
    
    # Mapear e importar
    for i, file_path in enumerate(found_files[:total_escenas]):
        escena_num = i + 1
        new_name = f"escena_{escena_num:02d}.png"
        dest_path = os.path.join(project_dest_dir, new_name)
        
        try:
            # Si el archivo original no es PNG, lo copiamos igual pero le cambiamos la extensión a .png 
            # (la mayoría de reproductores y MoviePy toleran que se lea como png aunque sea jpg por dentro, 
            # pero si quieres se puede convertir. Para rapidez, se copia directamente renombrado).
            shutil.copy2(file_path, dest_path)
            print(f"[OK] {os.path.basename(file_path)} -> {new_name}")
        except Exception as e:
            print(f"[ERROR] No se pudo copiar {os.path.basename(file_path)}: {e}")
            
    print(f"\n¡Listo! Las imágenes han sido importadas y renombradas en: {project_dest_dir}")

if __name__ == "__main__":
    main()
