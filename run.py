#!/usr/bin/env python3
"""
Punto de entrada directo para iniciar la Web UI de AI Video Automation Suite.
Uso:
    python run.py
"""
import sys
import os

# Asegurar que el directorio raíz esté en sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 60)
    print(" 🎬  AI Video Automation Suite - Iniciando Servidor")
    print(" 🌐  Abre en tu navegador: http://localhost:8000")
    print("=" * 60 + "\n")
    uvicorn.run("src.app:app", host="127.0.0.1", port=8000, reload=False)
