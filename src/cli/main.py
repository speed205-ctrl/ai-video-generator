import sys
import argparse
from src.cli.compile import run_compile
from src.cli.import_images import run_import_images
from src.cli.generate_guides import run_generate_guides
import asyncio

def main():
    parser = argparse.ArgumentParser(
        prog="python -m src.cli",
        description="YouTube AI Video Automation Suite - Unified CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="Comando a ejecutar")

    # Subcomando compile
    compile_parser = subparsers.add_parser("compile", help="Compilar un proyecto existente")
    compile_parser.add_argument("folder", nargs="?", default=None, help="Nombre de la carpeta en output/")

    # Subcomando import-images
    import_parser = subparsers.add_parser("import-images", help="Importar imágenes ordenadas cronológicamente")
    import_parser.add_argument("--origen", "-o", default=None, help="Ruta de la carpeta origen")
    import_parser.add_argument("--proyecto", "-p", default=None, help="Nombre o ruta del proyecto destino")

    # Subcomando generate-guides
    guide_parser = subparsers.add_parser("generate-guides", help="Generar guías de edición CapCut")
    guide_parser.add_argument("proyecto", nargs="?", default=None, help="Nombre o ruta del proyecto (opcional)")

    args = parser.parse_args()

    if args.command == "compile":
        run_compile(args.folder)
    elif args.command == "import-images":
        run_import_images(args.origen, args.proyecto)
    elif args.command == "generate-guides":
        asyncio.run(run_generate_guides(args.proyecto))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
