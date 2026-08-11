import os
import sys
import json
import asyncio
import logging
import subprocess
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Set sys.path to resolve relative imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.api_clients import LLMClient
from src.agents import IdeaGeneratorAgent

# Load dotenv from project directory
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(dotenv_path=os.path.join(project_dir, ".env"))

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("app_backend")

app = FastAPI(title="Dark Historical Documentary Creator API")

HISTORY_FILE = os.path.join(project_dir, "history.json")
IDEAS_DB = os.path.join(project_dir, "ideas_memory.db")

def init_db():
    import sqlite3
    try:
        conn = sqlite3.connect(IDEAS_DB)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ideas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT UNIQUE NOT NULL,
                descripcion TEXT NOT NULL,
                fecha_guardado TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        
        # Pre-populate with mock ideas if table is empty
        cursor.execute("SELECT COUNT(*) FROM ideas")
        count = cursor.fetchone()[0]
        if count == 0:
            for idea in MOCK_IDEAS:
                cursor.execute(
                    "INSERT OR IGNORE INTO ideas (titulo, descripcion) VALUES (?, ?)",
                    (idea["titulo"], idea["descripcion"])
                )
            conn.commit()
            logger.info("Base de datos pre-poblada con ideas iniciales de demostración.")
            
        conn.close()
        logger.info("Base de datos SQLite ideas_memory.db inicializada con éxito.")
    except Exception as e:
        logger.error(f"Error al inicializar la base de datos SQLite: {e}")


def save_ideas_to_db(ideas: List[Dict[str, str]]):
    import sqlite3
    try:
        conn = sqlite3.connect(IDEAS_DB)
        cursor = conn.cursor()
        for idea in ideas:
            titulo = idea.get("titulo", "").strip()
            descripcion = idea.get("descripcion", "").strip()
            if titulo and descripcion:
                cursor.execute(
                    "INSERT OR IGNORE INTO ideas (titulo, descripcion) VALUES (?, ?)",
                    (titulo, descripcion)
                )
        conn.commit()
        conn.close()
        logger.info(f"Guardadas {len(ideas)} ideas en la base de datos (ignorando duplicadas).")
    except Exception as e:
        logger.error(f"Error al guardar ideas en SQLite: {e}")

def get_ideas_from_db() -> List[Dict[str, Any]]:
    import sqlite3
    try:
        conn = sqlite3.connect(IDEAS_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT titulo, descripcion, fecha_guardado FROM ideas ORDER BY fecha_guardado DESC")
        rows = cursor.fetchall()
        ideas = []
        for row in rows:
            ideas.append({
                "titulo": row["titulo"],
                "descripcion": row["descripcion"],
                "fecha_guardado": row["fecha_guardado"]
            })
        conn.close()
        return ideas
    except Exception as e:
        logger.error(f"Error al obtener ideas de SQLite: {e}")
        return []


# Pydantic models
class ExecuteRequest(BaseModel):
    tema: str

class ScriptGenerateRequest(BaseModel):
    tema: str
    duracion_minutos: int = 1
    parte_serie: str = "single"

class SaveTempScriptRequest(BaseModel):
    tema: str
    guion: str

class ConfigModel(BaseModel):
    OPENROUTER_API_KEY: str
    OPENROUTER_MODEL: str
    NVIDIA_API_KEY: str
    NVIDIA_MODEL: str
    ELEVENLABS_API_KEY: str
    ELEVENLABS_VOICE_ID: str
    NVIDIA_IMAGE_KEY: str
    NVIDIA_IMAGE_MODEL: str

class RegenerateSceneRequest(BaseModel):
    project_folder: str
    numero_escena: int
    new_prompt: Optional[str] = None
    new_text: Optional[str] = None
    mode: str = "image"  # "image", "audio", "both"

def save_env_config(config: dict):
    env_path = os.path.join(project_dir, ".env")
    
    # Read existing variables from environment
    current_openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    current_nvidia_key = os.getenv("NVIDIA_API_KEY", "")
    current_elevenlabs_key = os.getenv("ELEVENLABS_API_KEY", "")
    current_nvidia_image_key = os.getenv("NVIDIA_IMAGE_KEY", "")
    
    # Map input keys (if "Configurada", keep current value from env)
    openrouter_key = current_openrouter_key if config.get("OPENROUTER_API_KEY") == "Configurada" else config.get("OPENROUTER_API_KEY", "")
    nvidia_key = current_nvidia_key if config.get("NVIDIA_API_KEY") == "Configurada" else config.get("NVIDIA_API_KEY", "")
    elevenlabs_key = current_elevenlabs_key if config.get("ELEVENLABS_API_KEY") == "Configurada" else config.get("ELEVENLABS_API_KEY", "")
    nvidia_image_key = current_nvidia_image_key if config.get("NVIDIA_IMAGE_KEY") == "Configurada" else config.get("NVIDIA_IMAGE_KEY", "")

    openrouter_model = config.get("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
    nvidia_model = config.get("NVIDIA_MODEL", "meta/llama-3.1-405b-instruct")
    elevenlabs_voice = config.get("ELEVENLABS_VOICE_ID", "pNInz6obpgq5okZXeOhx")
    nvidia_image_model = config.get("NVIDIA_IMAGE_MODEL", "black-forest-labs/flux.2-klein-4b")

    # Generate new lines for .env file
    new_lines = [
        "# Configuración de APIs para Automatización de Documentales (Actualizado vía UI)\n\n",
        f"OPENROUTER_API_KEY={openrouter_key}\n",
        f"OPENROUTER_MODEL={openrouter_model}\n\n",
        f"NVIDIA_API_KEY={nvidia_key}\n",
        f"NVIDIA_MODEL={nvidia_model}\n\n",
        f"ELEVENLABS_API_KEY={elevenlabs_key}\n",
        f"ELEVENLABS_VOICE_ID={elevenlabs_voice}\n\n",
        f"NVIDIA_IMAGE_KEY={nvidia_image_key}\n",
        f"NVIDIA_IMAGE_MODEL={nvidia_image_model}\n"
    ]
    
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    
    # Reload environment variables in memory
    load_dotenv(dotenv_path=env_path, override=True)

import random

# Expanded Mock ideas collection across 5 distinct niches
MOCK_IDEAS = [
    # Internet & Gaming
    {"nicho": "gaming", "titulo": "Petscop: El Juego Cancelado de PS1", "descripcion": "Un misterioso juego de 1997 cancelado que esconde un bucle digital infinito sobre trauma y registros corrompidos en YouTube."},
    {"nicho": "gaming", "titulo": "Polybius: El Arcade del Control Mental", "descripcion": "La leyenda urbana de 1981 sobre una máquina arcade en Oregón que causaba amnesia y pesadillas antes de ser confiscada por hombres de negro."},
    {"nicho": "gaming", "titulo": "Sad Satan: El Virus de la Deep Web", "descripcion": "Un juego de terror en la red Tor cargado con códigos ocultos, audios distorsionados e imágenes inquietantes en el disco duro de quienes lo jugaron."},
    {"nicho": "gaming", "titulo": "La Canción Lavanda de Pokémon", "descripcion": "Los mitos sobre las frecuencias de audio infrasónicas en la primera versión japonesa de Pueblo Lavanda en 1996."},
    {"nicho": "gaming", "titulo": "LSD: Dream Emulator y el Observador", "descripcion": "Un extraño juego de PlayStation lanzado solo en Japón en 1998 basado en los diarios de sueños de un desarrollador."},

    # Historia Oscura & Expediciones
    {"nicho": "historia", "titulo": "El Incidente del Paso Dyatlov", "descripcion": "En 1959, nueve excursionistas soviéticos murieron en los Urales bajo circunstancias inexplicables: tiendas rasgadas desde dentro y radiación."},
    {"nicho": "historia", "titulo": "La Colonia Perdida de Roanoke", "descripcion": "En 1590, 115 colonos ingleses desaparecieron sin dejar rastro en la isla de Roanoke, dejando solo una palabra tallada en un árbol: CROATOAN."},
    {"nicho": "historia", "titulo": "La Peste del Baile de 1518", "descripcion": "Cientos de personas bailaron sin parar durante semanas en Estrasburgo hasta colapsar por agotamiento en un trance colectivo inexplicable."},
    {"nicho": "historia", "titulo": "El Hombre de la Máscara de Hierro", "descripcion": "Un prisionero anónimo custodiado en la Bastilla durante el reinado de Luis XIV cuya identidad permaneció oculta bajo metal."},
    {"nicho": "historia", "titulo": "La Expedición Perdida de Franklin", "descripcion": "Dos buques británicos atrapados en el hielo del Ártico en 1845 cuyos tripulantes sucumbieron a la locura y al envenenamiento por plomo."},

    # Ciencia & Espacio Profundo
    {"nicho": "ciencia", "titulo": "La Señal WOW!: El Mensaje del Espacio", "descripcion": "En 1977, el radiotelescopio Big Ear captó una potente señal de radio de 72 segundos proveniente de la constelación de Sagitario nunca repetida."},
    {"nicho": "ciencia", "titulo": "Las Emisoras de Números de la Guerra Fría", "descripcion": "Misteriosas estaciones de radio en onda corta (como UVB-76 'El Zumbador') que transmiten tonos monótonos y voces leyendo números 24/7."},
    {"nicho": "ciencia", "titulo": "El Experimento de Filadelfia", "descripcion": "La leyenda sobre el USS Eldridge, un destructor naval presuntamente invisibilizado mediante campos electromagnéticos en 1943."},
    {"nicho": "ciencia", "titulo": "El Manuscrito Voynich", "descripcion": "Un libro ilustrado del siglo XV redactado en una caligrafía e idioma indescifrable que desafía a los mejores criptógrafos del mundo."},
    {"nicho": "ciencia", "titulo": "El Bloop: El Sonido en las Profundidades", "descripcion": "Una ultra-baja frecuencia hidroacústica detectada en el Pacífico en 1997 varias veces más potente que cualquier animal marino conocido."},

    # Aviación & Anomalías Navales
    {"nicho": "aviacion", "titulo": "El Vuelo 19 y el Triángulo de las Bermudas", "descripcion": "Cinco aviones torpederos de la Marina de EE. UU. desaparecieron en 1945 durante un entrenamiento rutinario junto al avión de rescate."},
    {"nicho": "aviacion", "titulo": "El Enigma de D.B. Cooper", "descripcion": "El único secuestro aéreo no resuelto de la historia: en 1971 un hombre saltó en paracaídas desde un Boeing 727 con 200,000 dólares y desapareció."},
    {"nicho": "aviacion", "titulo": "El Barco Fantasma Mary Celeste", "descripcion": "Hallado a la deriva en 1872 cerca de las Azores con la carga intacta, botes salvavidas en su sitio y la tripulación desaparecida."},
    {"nicho": "aviacion", "titulo": "El Vuelo 370 de Malaysia Airlines", "descripcion": "Un Boeing 777 con 239 personas a bordo cambió de rumbo bruscamente y se desvaneció en los radares del Océano Índico en 2014."},
    {"nicho": "aviacion", "titulo": "El SS Ourang Medan: El Barco Maldito", "descripcion": "Un carguero holandés en 1947 cuya tripulación envió un desgarrador mensaje morse antes de ser encontrada sin vida con gestos de terror."},

    # Tecnología & Criptografía
    {"nicho": "tecnologia", "titulo": "Cicada 3301: La Reclutación Criptográfica", "descripcion": "El rompecabezas de la red publicado en 2012 para reclutar a los criptógrafos más brillantes del planeta mediante esteganografía."},
    {"nicho": "tecnologia", "titulo": "Athanasius Kircher y el Transmisor Alquímico", "descripcion": "Los autómatas y dispositivos de cifrado acústico construidos en el siglo XVII para simular voces mecánicas."},
    {"nicho": "tecnologia", "titulo": "Kryptos: La Escultura Infranqueable de la CIA", "descripcion": "Una escultura ubicada en el cuartel general de la CIA con cuatro pasajes cifrados, del cual el cuarto permanece indescifrado tras 30 años."},
    {"nicho": "tecnologia", "titulo": "El Caso de Satoshi Nakamoto", "descripcion": "El misterio en torno al creador anónimo de Bitcoin que desapareció en 2011 dejando una fortuna intacta en la blockchain."},
    {"nicho": "tecnologia", "titulo": "El Glitch del Protocolo NTP y los Relojes Atómicos", "descripcion": "Una anomalía en la sincronización del tiempo global que desfasó servidores bancarios por fracciones de segundo sin explicación oficial."}
]

init_db()

# History database helpers
def read_history() -> List[Dict[str, Any]]:
    if not os.path.exists(HISTORY_FILE):
        # Create empty history file if missing
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error reading history.json: {e}")
        return []

def write_history(history: List[Dict[str, Any]]):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error writing to history.json: {e}")

def update_history_status(tema: str, status: str, folder_name: str = None):
    history = read_history()
    updated = False
    
    # Standardize string for comparison
    target_tema_lower = tema.strip().lower()
    
    for entry in history:
        if entry.get("tema", "").strip().lower() == target_tema_lower:
            entry["status"] = status
            entry["fecha"] = datetime.now().strftime("%Y-%m-%d")
            if folder_name:
                entry["folder_name"] = folder_name
            updated = True
            break
            
    if not updated:
        new_entry = {
            "tema": tema,
            "fecha": datetime.now().strftime("%Y-%m-%d"),
            "status": status
        }
        if folder_name:
            new_entry["folder_name"] = folder_name
        history.append(new_entry)
        
    write_history(history)


# Endpoints
@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serves the main dashboard page."""
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Could not read index.html: {e}")
        raise HTTPException(status_code=500, detail="Frontend index.html file missing or unreadable.")

PROJECT_DETAIL_TEMPLATE = """<!DOCTYPE html>
<html lang="es" class="h-full">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Detalles del Enigma - {tema_nombre}</title>
  <!-- Tailwind CSS CDN -->
  <script src="https://cdn.tailwindcss.com"></script>
  <!-- Google Fonts: Inter & JetBrains Mono -->
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: {
            sans: ['Inter', 'sans-serif'],
            mono: ['JetBrains Mono', 'monospace'],
          },
          colors: {
            dark: {
              950: '#030712',
              900: '#0b0f19',
              800: '#111827',
              700: '#1f2937',
            },
            cyan: {
              400: '#22d3ee',
              500: '#06b6d4',
              600: '#0891b2',
              950: '#083344',
            }
          }
        }
      }
    }
  </script>
  <style>
    body {
      font-family: 'Inter', sans-serif;
      background-color: #030712;
      color: #f3f4f6;
    }
    .glass {
      background: rgba(11, 15, 25, 0.75);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid rgba(255, 255, 255, 0.05);
    }
    .glow-border {
      transition: all 0.3s ease;
    }
    .glow-border:hover {
      border-color: rgba(34, 211, 238, 0.3);
      box-shadow: 0 0 15px rgba(34, 211, 238, 0.1);
    }
    .scrollbar::-webkit-scrollbar {
      width: 6px;
    }
    .scrollbar::-webkit-scrollbar-track {
      background: #030712;
    }
    .scrollbar::-webkit-scrollbar-thumb {
      background: #374151;
      border-radius: 3px;
    }
  </style>
</head>
<body class="min-h-full flex flex-col p-6 space-y-6 overflow-y-auto scrollbar">
  <!-- Header -->
  <header class="glass rounded-xl p-5 flex justify-between items-center shrink-0">
    <div class="flex items-center gap-3">
      <a href="/" class="text-cyan-400 hover:text-cyan-300 font-mono text-xs flex items-center gap-1.5 transition">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
        </svg>
        Volver al Panel
      </a>
      <span class="text-gray-600">|</span>
      <h1 class="text-lg font-bold tracking-wider uppercase text-cyan-400 font-mono">Detalles del Enigma</h1>
    </div>
    <div class="text-xs text-gray-500 font-mono">Proyecto: {folder_name}</div>
  </header>

  <!-- Title & Proposals / YouTube Details -->
  <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
    <!-- Left Column: Title Proposals & Thumbnail (2 cols) -->
    <div class="lg:col-span-2 flex flex-col gap-6">
      <!-- Titles Card -->
      <div class="glass rounded-xl p-6 glow-border">
        <h2 class="text-sm font-semibold uppercase tracking-wider text-cyan-400 mb-4 font-mono">Títulos y Propuestas para YouTube</h2>
        
        <div class="mb-5">
          <label class="block text-[10px] text-gray-500 font-mono uppercase mb-1">Título Principal Generado</label>
          <div class="flex items-center justify-between bg-dark-950/80 border border-white/10 rounded-lg p-3.5">
            <span class="text-base font-bold text-white" id="main-title">{titulo}</span>
            <button onclick="copyToClipboard('main-title')" class="text-xs text-cyan-400 hover:text-cyan-300 font-mono px-3 py-1 border border-cyan-500/20 hover:border-cyan-500/55 rounded transition">Copiar</button>
          </div>
        </div>

        <div>
          <label class="block text-[10px] text-gray-500 font-mono uppercase mb-2">4 Propuestas Alternativas de Título</label>
          <ul class="space-y-2">
            {propuestas_html}
          </ul>
        </div>
      </div>

      <!-- Thumbnail Prompt Card -->
      <div class="glass rounded-xl p-6 glow-border">
        <div class="flex justify-between items-center mb-3">
          <h2 class="text-sm font-semibold uppercase tracking-wider text-cyan-400 font-mono">Prompt para Miniatura (YouTube Thumbnail)</h2>
          <button onclick="copyToClipboard('thumbnail-prompt')" class="text-xs text-cyan-400 hover:text-cyan-300 font-mono px-3 py-1 border border-cyan-500/20 hover:border-cyan-500/55 rounded transition">Copiar Prompt</button>
        </div>
        <div class="bg-dark-950/80 border border-white/10 rounded-lg p-4 font-mono text-xs text-gray-300 leading-relaxed whitespace-pre-wrap" id="thumbnail-prompt">{prompt_miniatura}</div>
      </div>
    </div>

    <!-- Right Column: Youtube Description & Info (1 col) -->
    <div class="flex flex-col gap-6">
      <div class="glass rounded-xl p-6 glow-border flex-1 flex flex-col">
        <div class="flex justify-between items-center mb-3">
          <h2 class="text-sm font-semibold uppercase tracking-wider text-cyan-400 font-mono">Descripción de YouTube</h2>
          <button onclick="copyToClipboard('yt-description')" class="text-xs text-cyan-400 hover:text-cyan-300 font-mono px-3 py-1 border border-cyan-500/20 hover:border-cyan-500/55 rounded transition">Copiar Desc.</button>
        </div>
        <div class="flex-1 bg-dark-950/80 border border-white/10 rounded-lg p-4 font-sans text-xs text-gray-300 leading-relaxed whitespace-pre-wrap overflow-y-auto scrollbar" id="yt-description">{descripcion_youtube}</div>
      </div>
    </div>
  </div>

  <!-- Script and Scenes Timeline -->
  <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
    <!-- Script View (5 cols) -->
    <div class="lg:col-span-5 glass rounded-xl p-6 glow-border flex flex-col max-h-[70vh]">
      <h2 class="text-sm font-semibold uppercase tracking-wider text-cyan-400 mb-3 font-mono">Guion Completo Narrado</h2>
      <div class="flex-1 bg-dark-950/80 border border-white/10 rounded-lg p-4 font-sans text-xs text-gray-300 leading-relaxed overflow-y-auto scrollbar whitespace-pre-wrap">{guion}</div>
    </div>

    <!-- Timeline/Escaleta View (7 cols) -->
    <div class="lg:col-span-7 glass rounded-xl p-6 glow-border flex flex-col max-h-[70vh]">
      <h2 class="text-sm font-semibold uppercase tracking-wider text-cyan-400 mb-1 font-mono">Línea de Tiempo y Escaleta del Video</h2>
      <p class="text-[10px] text-gray-500 mb-3 font-mono">Duración Total: {duracion_total} | Escenas: {total_escenas}</p>
      
      <div class="flex-1 overflow-y-auto scrollbar pr-1 space-y-4">
        {escaleta_html}
      </div>
    </div>
  </div>

  <!-- Footer toast script -->
  <script>
    function copyToClipboard(elementId) {
      const el = document.getElementById(elementId);
      let text = el.innerText || el.textContent;
      
      // Copy
      navigator.clipboard.writeText(text).then(() => {
        alert("¡Copiado al portapapeles con éxito!");
      }).catch(err => {
        console.error("Error al copiar: ", err);
      });
    }
  </script>
</body>
</html>
"""

@app.get("/proyecto/{folder_name}", response_class=HTMLResponse)
async def get_proyecto_details(folder_name: str):
    """Serves a detailed viewer page for a completed project's metadata, script, and escaleta."""
    # Build paths to the files inside project/output/<folder_name>
    target_dir = os.path.join(project_dir, "output", folder_name)
    if not os.path.exists(target_dir):
        raise HTTPException(status_code=404, detail="El proyecto solicitado no existe o fue eliminado.")

    # Read metadata.json
    metadata = {}
    metadata_path = os.path.join(target_dir, "metadata.json")
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception as e:
            logger.error(f"Error reading metadata.json for {folder_name}: {e}")

    # Read escaleta.json
    escaleta = {}
    escaleta_path = os.path.join(target_dir, "escaleta.json")
    if os.path.exists(escaleta_path):
        try:
            with open(escaleta_path, "r", encoding="utf-8") as f:
                escaleta = json.load(f)
        except Exception as e:
            logger.error(f"Error reading escaleta.json for {folder_name}: {e}")

    # Read guion.txt
    guion = ""
    guion_path = os.path.join(target_dir, "guion.txt")
    if os.path.exists(guion_path):
        try:
            with open(guion_path, "r", encoding="utf-8") as f:
                guion = f.read()
        except Exception as e:
            logger.error(f"Error reading guion.txt for {folder_name}: {e}")

    # Build Title proposals HTML
    propuestas_html = ""
    for i, prop in enumerate(metadata.get("propuestas_titulo", [])):
        propuestas_html += f"""
        <li class="flex items-center justify-between bg-dark-950/40 border border-white/5 rounded-lg p-3">
          <span class="text-xs text-gray-300" id="prop-{i}">{prop}</span>
          <button onclick="copyToClipboard('prop-{i}')" class="text-[10px] text-cyan-400 hover:text-cyan-300 font-mono px-2 py-0.5 border border-cyan-500/10 hover:border-cyan-500/30 rounded transition font-medium">Copiar</button>
        </li>
        """
    if not propuestas_html:
        propuestas_html = "<li class='text-xs text-gray-500 font-mono p-3'>No hay propuestas de título disponibles.</li>"

    # Build Escaleta timeline HTML
    escaleta_html = ""
    for scene in escaleta.get("escenas", []):
        num = scene.get("numero_escena", 1)
        text = scene.get("texto", "")
        img_prompt = scene.get("prompt_imagen", "")
        effect = scene.get("efecto_capcut", "")
        start = scene.get("timestamp_inicio", "00:00")
        end = scene.get("timestamp_fin", "00:00")
        duration = scene.get("duracion_segundos", 0.0)
        
        escaleta_html += f"""
        <div class="border border-white/5 bg-white/[0.01] hover:bg-white/[0.02] p-4 rounded-lg transition glow-border">
          <div class="flex justify-between items-center mb-2">
            <span class="font-mono text-xs text-cyan-400 bg-cyan-950/40 border border-cyan-500/20 px-2.5 py-0.5 rounded">Escena {num}</span>
            <span class="text-[10px] text-gray-500 font-mono">Intervalo: {start} &rarr; {end} ({round(duration, 2)}s)</span>
          </div>
          <p class="text-xs text-gray-300 leading-relaxed mb-3">{text}</p>
          
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 border-t border-white/5">
            <div>
              <label class="block text-[9px] text-gray-500 font-mono uppercase mb-0.5">Efecto de Paneo/Zoom</label>
              <span class="text-xs text-cyan-500/80 font-mono font-medium">{effect}</span>
            </div>
            <div>
              <label class="block text-[9px] text-gray-500 font-mono uppercase mb-0.5">Visual Prompt (AI)</label>
              <span class="text-[10px] text-gray-400 leading-snug block line-clamp-2" title="{img_prompt}">{img_prompt}</span>
            </div>
          </div>
        </div>
        """
    if not escaleta_html:
        escaleta_html = "<div class='text-xs text-gray-500 font-mono text-center py-6'>No hay escaleta disponible para este proyecto.</div>"

    # Replace variables in HTML template
    html_content = PROJECT_DETAIL_TEMPLATE
    html_content = html_content.replace("{tema_nombre}", metadata.get("titulo", folder_name))
    html_content = html_content.replace("{folder_name}", folder_name)
    html_content = html_content.replace("{titulo}", metadata.get("titulo", "N/A"))
    html_content = html_content.replace("{propuestas_html}", propuestas_html)
    html_content = html_content.replace("{prompt_miniatura}", metadata.get("prompt_miniatura", "N/A"))
    html_content = html_content.replace("{descripcion_youtube}", metadata.get("descripcion_youtube", "N/A"))
    html_content = html_content.replace("{guion}", guion)
    html_content = html_content.replace("{duracion_total}", escaleta.get("duracion_total_formateada", "N/A"))
    html_content = html_content.replace("{total_escenas}", str(escaleta.get("total_escenas", "N/A")))
    html_content = html_content.replace("{escaleta_html}", escaleta_html)

    return HTMLResponse(content=html_content)

@app.get("/api/history")
async def get_history():
    """Returns the list of generated/processing topics."""
    return read_history()

@app.get("/api/config")
async def get_config():
    """Returns masked/unmasked config state."""
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    nvidia_key = os.getenv("NVIDIA_API_KEY", "")
    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY", "")
    nvidia_image_key = os.getenv("NVIDIA_IMAGE_KEY", "")
    
    return {
        "OPENROUTER_API_KEY": "Configurada" if openrouter_key else "",
        "OPENROUTER_MODEL": os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet"),
        "NVIDIA_API_KEY": "Configurada" if nvidia_key else "",
        "NVIDIA_MODEL": os.getenv("NVIDIA_MODEL", "meta/llama-3.1-405b-instruct"),
        "ELEVENLABS_API_KEY": "Configurada" if elevenlabs_key else "",
        "ELEVENLABS_VOICE_ID": os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgq5okZXeOhx"),
        "NVIDIA_IMAGE_KEY": "Configurada" if nvidia_image_key else "",
        "NVIDIA_IMAGE_MODEL": os.getenv("NVIDIA_IMAGE_MODEL", "black-forest-labs/flux.2-klein-4b")
    }

@app.post("/api/config")
async def post_config(config: ConfigModel):
    """Saves the submitted config back to the .env file and hot-reloads it."""
    try:
        save_env_config(config.dict())
        return {"status": "ok", "message": "Configuración guardada e importada en caliente."}
    except Exception as e:
        logger.error(f"Error saving API configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Error al guardar configuración: {e}")

@app.get("/api/ideas")
async def get_ideas(categoria: Optional[str] = None):
    """Generates 5 unique ideas for topics excluding already worked ones."""
    history = read_history()
    existing_topics = [entry.get("tema", "").lower().strip() for entry in history]

    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    nvidia_key = os.getenv("NVIDIA_API_KEY", "").strip()
    mock_mode = (not openrouter_key and not nvidia_key) or os.getenv("MOCK_MODE") == "true"

    # Filter mock candidates by category if requested
    candidate_mocks = MOCK_IDEAS
    if categoria and categoria != "todos":
        candidate_mocks = [i for i in MOCK_IDEAS if i.get("nicho") == categoria]
        if not candidate_mocks:
            candidate_mocks = MOCK_IDEAS

    # Remove already used topics
    available_mocks = [
        idea for idea in candidate_mocks
        if idea["titulo"].lower().strip() not in existing_topics
    ]
    if len(available_mocks) < 5:
        available_mocks = candidate_mocks

    ideas = []
    if mock_mode:
        logger.info(f"[Mock] Seleccionando 5 ideas variadas al azar (Categoría: {categoria or 'todas'})...")
        ideas = random.sample(available_mocks, min(5, len(available_mocks)))
    else:
        try:
            client = get_configured_llm_client()
            agent = IdeaGeneratorAgent(client)
            ideas = await agent.generate_ideas(existing_topics, category=categoria)
        except Exception as e:
            logger.error(f"Error generando ideas con IA ({e}). Usando catálogo variado de respaldo...")
            ideas = random.sample(available_mocks, min(5, len(available_mocks)))

    if ideas:
        save_ideas_to_db(ideas)

    return {"ideas": ideas}

@app.get("/api/ideas-memory")
async def get_ideas_memory():
    """Returns the list of previously generated ideas from the SQLite database."""
    return {"ideas": get_ideas_from_db()}

@app.delete("/api/ideas-memory")
async def delete_ideas_memory():
    """Clears the ideas memory table."""
    import sqlite3
    try:
        conn = sqlite3.connect(IDEAS_DB)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ideas")
        conn.commit()
        conn.close()
        return {"status": "ok", "message": "Memoria de ideas vaciada con éxito."}
    except Exception as e:
        logger.error(f"Error al vaciar la memoria de ideas: {e}")
        raise HTTPException(status_code=500, detail=f"Error al vaciar la memoria: {e}")


def get_configured_llm_client() -> LLMClient:
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    nvidia_key = os.getenv("NVIDIA_API_KEY", "").strip()
    
    if openrouter_key.startswith("nvapi-"):
        nvidia_key = openrouter_key
        openrouter_key = ""

    if openrouter_key and openrouter_key.startswith("sk-or-"):
        model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
        return LLMClient(
            api_key=openrouter_key,
            base_url="https://openrouter.ai/api/v1",
            default_model=model
        )
    elif nvidia_key:
        model = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-405b-instruct")
        return LLMClient(
            api_key=nvidia_key,
            base_url="https://integrate.api.nvidia.com/v1",
            default_model=model
        )
    else:
        raise ValueError("No hay clave de API válida de LLM configurada.")

def build_fact_enriched_mock_script(tema: str, duracion: int, parte: str = "single") -> str:
    t_lower = tema.lower()
    
    if "franklin" in t_lower:
        if parte == "part1":
            return (
                "Sientes el crujido del hielo helado aprisionando el casco de madera en el Ártico canadiense. Es mayo de mil ochocientos cuarenta y cinco.\n"
                "Sir John Franklin zarpó de Inglaterra con ciento veintinueve hombres a bordo del HMS Erebus y el HMS Terror para cartografiar el Paso del Noroeste.\n"
                "Equipados con motores a vapor y raciones de carne enlatada para tres años, la expedición ingresó al Estrecho de Lancaster sin sospechar que jamás regresarían.\n"
                "En septiembre de mil ochocientos cuarenta y seis, las placas heladas aprisionaron ambos buques cerca de la Isla del Rey Guillermo en completa oscuridad polar.\n"
                "Pero lo que la tripulación descubrió dentro de las latas de alimentos selladas apresuradamente destruiría su cordura antes del primer invierno...\n"
                "Sígueme ahora mismo para ver la Parte 2."
            )
        elif parte == "part2":
            return (
                "Recordemos el horror en el Ártico de mil ochocientos cuarenta y cinco. Atrapados en el hielo, los ciento veintinueve marineros de Franklin enfrentaron una amenaza inesperada.\n"
                "La soldadura de plomo concentrado usada para sellar apresuradamente los envases comenzó a filtrarse en la comida diaria.\n"
                "Los oficiales sufrieron brotes masivos de paranoia, insomnio y encías sangrantes mientras la temperatura caía a menos cuarenta grados.\n"
                "En abril de mil ochocientos cuarenta y ocho, tras la muerte de Franklin, los sobrevivientes abandonaron los barcos para arrastrar botes pesados sobre la banquisa congelada.\n"
                "Lo que las expediciones de rescate hallaron décadas después en los huesos congelados revelaría una desesperada lucha final por la supervivencia...\n"
                "Sígueme para ver la Parte 3 y la revelación del hallazgo moderno."
            )
        elif parte == "part3":
            return (
                "Llegamos al desenlace del misterio de la Expedición Franklin. Durante más de un siglo, el paradero del HMS Erebus y el HMS Terror fue un enigma de la historia naval.\n"
                "Los análisis de ADN y marcas de cortes con navaja en los fémures recuperados en la nieve confirmaron episodios desgarradores de canibalismo en los últimos días.\n"
                "En dos mil catorce, arqueólogos submarinos localizaron los restos intactos del HMS Erebus sumergidos en el fondo marino canadiense.\n"
                "La vajilla del capitán, las botas de los marineros y los documentos de a bordo permanecen intactos en el hielo bajo el agua.\n"
                "Y mientras observas las imágenes sumergidas en tu pantalla, el silencio del Ártico sigue guardando la última lección sobre la soberbia humana."
            )
        else:
            if duracion == 1:
                return (
                    "Sientes el crujido del hielo helado aprisionando el casco de madera en el Ártico canadiense. Es mayo de mil ochocientos cuarenta y cinco.\n"
                    "Sir John Franklin zarpó de Inglaterra con ciento veintinueve hombres a bordo del HMS Erebus y el HMS Terror para encontrar el Paso del Noroeste.\n"
                    "Ambos barcos quedan atrapados en las placas heladas cerca de la Isla del Rey Guillermo durante dos años árticos ininterrumpidos.\n"
                    "Las latas de conserva selladas con plomo barato comienzan a envenenar lentamente a la tripulación con pesadillas y demencia antes de sucumbir al hambre."
                )
            elif duracion == 2:
                return (
                    "Sientes el crujido del hielo helado aprisionando el casco de madera en el Ártico canadiense. Es mayo de mil ochocientos cuarenta y cinco.\n"
                    "Sir John Franklin zarpó de Inglaterra al mando de dos buques de la Real Armada: el HMS Erebus y el HMS Terror, equipados con motores a vapor.\n"
                    "Tras internarse en el Estrecho de Lancaster, los dos barcos quedan atrapados en las placas heladas cerca de la Isla del Rey Guillermo durante dos años.\n"
                    "Las reservas de alimentos enlatados selladas apresuradamente con plomo comienzan a envenenar lentamente a la tripulación con delirios e insomnio.\n"
                    "En abril de mil ochocientos cuarenta y ocho, los sobrevivientes abandonan los buques congelados para caminar sobre el hielo hacia el continente, muriendo en la nieve.\n"
                    "En dos mil catorce, los restos intactos del HMS Erebus fueron descubiertos sumergidos en el fondo marino, conservando la vajilla del capitán."
                )
            else:
                return (
                    "Sientes el crujido del hielo helado aprisionando el casco de madera en el Ártico canadiense. Es mayo de mil ochocientos cuarenta y cinco.\n"
                    "Sir John Franklin zarpó de Inglaterra al mando de dos buques insignia de la Real Armada: el HMS Erebus y el HMS Terror, con ciento veintinueve marineros a bordo.\n"
                    "Su objetivo era cartografiar el último tramo desconocido del Paso del Noroeste, navegando entre icebergs helados en el archipiélago ártico.\n"
                    "En septiembre de mil ochocientos cuarenta y seis, el invierno polar atrapó ambos barcos en las placas de hielo infranqueables al norte de la Isla del Rey Guillermo.\n"
                    "Durante veinticuatro meses en oscuridad casi continua, la tripulación consumió raciones de carne enlatada selladas defectuosamente con soldadura de plomo concentrado.\n"
                    "Los análisis de ADN y restos óseos recuperados décadas después confirmaron niveles tóxicos de plomo que provocaron brotes de paranoia y demencia entre los oficiales.\n"
                    "En abril de mil ochocientos cuarenta y mecho, tras la muerte del capitán Franklin, ciento cinco sobrevivientes abandonaron los buques para arrastrar botes sobre la banquisa congelada.\n"
                    "Marcas de cortes con cuchillo encontradas en los fémures de los restos congelados revelaron la desesperada lucha final por la supervivencia mediante canibalismo.\n"
                    "Las expediciones de rescate enviadas durante años solo hallaron esqueletos diseminados en la nieve y una nota enterrada en un hito de piedras conocida como la Nota de Victory Point.\n"
                    "Y mientras observas las fotografías sumergidas del HMS Erebus descubierto en dos mil catorce, el silencio del Ártico sigue guardando el secreto."
                )

    elif "hierro" in t_lower or "mascara" in t_lower or "máscara" in t_lower:
        if parte == "part1":
            return (
                "Sientes el peso del terciopelo negro y las bisagras de metal helado cubriéndote el rostro. Es julio de mil seiscientos sesenta y nueve.\n"
                "Por orden secreta e incondicional del rey Luis catorce de Francia, un prisionero anónimo es conducido bajo custodia militar a la fortaleza de Pignerol.\n"
                "Las instrucciones del ministro de guerra a su carcelero, Benigno de Saint-Mars, son inflexibles: si el prisionero habla con alguien sobre su identidad, será ejecutado de inmediato.\n"
                "Nadie conoce su rostro ni su verdadero nombre. Pero los rumores en Versalles susurran que comparte la misma sangre real del Rey Sol...\n"
                "Sígueme ahora mismo para ver la Parte 2."
            )
        elif parte == "part2":
            return (
                "Continuamos en las sombras de la Francia de mil seiscientos noventa y ocho. El carcelero Saint-Mars es nombrado gobernador de la legendaria prisión de la Bastilla en París.\n"
                "Consigo traslada a su prisionero más valioso, quien viaja en un carruaje blindado cubriendo su rostro con una máscara ajustada de terciopelo y refuerzos de hierro.\n"
                "Los guardias tienen orden estricta de mantener las armas cargadas apuntando a su celda. El prisionero recibe trato de alta nobleza: vajilla de plata, telas finas y médicos privados.\n"
                "Pero las paredes de piedra guardan un secreto que amenazaba la legitimidad del trono francés...\n"
                "Sígueme para ver la Parte 3 y la revelación final."
            )
        elif parte == "part3":
            return (
                "Llegamos al desenlace del Hombre de la Máscara de Hierro. El diecinueve de noviembre de mil setecientos tres, el prisionero misterioso fallece repentinamente en la Bastilla.\n"
                "Fue sepultado bajo la identidad falsa de Marchioly. Por orden directa de la corona, sus ropas fueron quemadas, su vajilla fundida y las paredes de su celda raspadas para borrar cualquier inscripción.\n"
                "Historiadores como Voltaire sostuvieron la teoría de que se trataba del hermano gemelo mayor de Luis catorce, ocultado para evitar una guerra civil por la corona.\n"
                "Y al revisar los archivos de la Bastilla tres siglos después, el verdadero nombre del hombre detrás del metal sigue siendo el secreto mejor guardado de la monarquía."
            )
        else:
            if duracion == 5:
                return (
                    "Sientes el peso del terciopelo negro y las bisagras de metal helado cubriéndote el rostro en completa oscuridad. Es julio de mil seiscientos sesenta y nueve.\n"
                    "Por orden secreta e incondicional del rey Luis catorce de Francia, un prisionero anónimo es conducido bajo extrema custodia militar a la fortaleza alpina de Pignerol.\n"
                    "Las instrucciones de la corona a su carcelero, Benigno de Saint-Mars, son absolutas: el cautivo debe permanecer aislado en una celda insonorizada y ser ejecutado de inmediato si pronuncia su verdadero nombre.\n"
                    "Durante más de tres décadas, el misterioso hombre acompañó a Saint-Mars en sus traslados por las prisiones del reino, desde Exilles hasta las islas de Lérins.\n"
                    "En mil seiscientos noventa y ocho, el carcelero es nombrado gobernador de la legendaria Bastilla en París. El prisionero es trasladado en un carruaje custodiado por mosqueteros, con su rostro oculto tras una pieza ajustada de metal y terciopelo.\n"
                    "A pesar de su encierro estricto, el cautivo recibía un trato reservado exclusivamente a príncipes de la sangre: comidas servidas en vajilla de plata fina, ropas de seda y la presencia de los médicos reales.\n"
                    "Los rumores en las cortes de Europa comenzaron a circular en voz baja. Filósofos como Voltaire afirmaron tras la Revolución que el prisionero no era otro que el hermano gemelo mayor de Luis catorce.\n"
                    "Otros historiadores sugirieron que se trataba del diplomático italiano Ercole Mattioli o del verdadero padre biológico del monarca, un secreto que habría destruido la dinastía de los Borbones.\n"
                    "El diecinueve de noviembre de mil setecientos tres, el hombre misterioso falleció de forma repentina tras asistir a la misa en la capilla de la Bastilla.\n"
                    "Al día siguiente, fue enterrado bajo el nombre ficticio de Marchioly. La corona ordenó quemar todas sus pertenencias personales, derretir sus cubiertos de plata y raspar la pintura de las paredes de su celda hasta dejar la piedra desnuda.\n"
                    "Tres siglos después, los historiadores han examinado los diarios del teniente de la Bastilla, Etienne du Junca, confirmando la existencia real del prisionero pero no su identidad.\n"
                    "Y mientras contemplas los fríos muros de piedra de la Bastilla en los mapas de la época, el nombre del hombre que vivió y murió tras la máscara permanece borrado en el tiempo."
                )
            else:
                return (
                    "Sientes el peso del terciopelo negro y las bisagras de metal helado cubriéndote el rostro. Es julio de mil seiscientos sesenta y nueve.\n"
                    "Por orden secreta e incondicional del rey Luis catorce de Francia, un prisionero anónimo es conducido bajo custodia militar a la fortaleza de Pignerol.\n"
                    "Las instrucciones al carcelero Saint-Mars eran absolutas: si el prisionero revelaba su nombre a los guardias, debía ser ejecutado al instante.\n"
                    "En mil seiscientos noventa y mecho fue trasladado a la Bastilla en París con el rostro siempre cubierto. A pesar del encierro, recibía trato de alta nobleza y vajilla de plata.\n"
                    "Tras su muerte en mil setecientos tres bajo el nombre falso de Marchioly, la corona ordenó fundir sus pertenencias y quemar su ropa.\n"
                    "Voltaire afirmó que era el hermano gemelo mayor del rey. Y tres siglos después, el rostro detrás del metal sigue siendo el secreto más oscuro de Versalles."
                )

    # Specific historical facts dictionary
    elif "dyatlov" in t_lower or "paso" in t_lower:
        if parte == "part1":
            return (
                "Sientes un frío de menos treinta grados cortándote la respiración en los Montes Urales. Es el dos de febrero de mil novecientos cincuenta y nueve.\n"
                "Nueve excursionistas soviéticos liderados por Igor Dyatlov instalan su tienda en la Montaña de la Muerte. Ninguno regresará con vida.\n"
                "Al caer la noche, una amenaza invisible los obliga a cortar la tienda de lona desde el interior con navajas y huir descalzos hacia la oscuridad helada.\n"
                "Lo que los rescatistas encontraron semanas después en los primeros cuerpos abriría la investigación más enigmática del KGB...\n"
                "Sígueme ahora mismo para ver la Parte 2."
            )
        elif parte == "part2":
            return (
                "Continuamos con el misterio del Paso Dyatlov de mil novecientos cincuenta y nueve. En los Urales congelados, los rescatistas hallan los cuerpos a medio vestir en la nieve.\n"
                "Las autopsias forenses revelan fracturas craneales brutales y tórax aplastados con una fuerza equivalente a un choque de automóvil, pero sin un solo hematoma exterior.\n"
                "A dos de las víctimas les faltaban los ojos y la lengua. Y en los suéteres analizados con contadores Geiger, la radiación gamma seguía emitiendo lecturas elevadas.\n"
                "Lo que decía la última anotación en el diario de ruta guardado en la nieve revelaría lo impensable...\n"
                "Sígueme para ver la Parte 3 y la conclusión del caso."
            )
        elif parte == "part3":
            return (
                "Llegamos al desenlace del Paso Dyatlov. El informe de la fiscalía soviética en mil novecientos cincuenta y nueve fue archivado bajo secreto militar absoluto.\n"
                "La conclusión oficial quedó redactada en una frase vaga: la causa de muerte fue una fuerza elemental irresistible.\n"
                "Fotografías desclasificadas del rollo de película recuperado muestran una esfera de luz flotando en la pendiente antes del ataque.\n"
                "Y mientras revisas las fotos en blanco y negro, la última línea del diario susurra: Ahora sabemos que ellos habitan aquí."
            )
        else:
            if duracion == 1:
                return (
                    "Sientes un frío de menos treinta grados cortándote la respiración en los Montes Urales. Es el dos de febrero de mil novecientos cincuenta y nueve.\n"
                    "Nueve excursionistas soviéticos liderados por Igor Dyatlov instalan su tienda en la Montaña de la Muerte. Ninguno regresará con vida.\n"
                    "Los rescatistas encuentran la carpa rajada desde el interior con navajas. Los cuerpos yacen en la nieve a medio vestir, algunos con costillas fracturadas sin ningún golpe o hematoma externo.\n"
                    "El informe oficial concluye con una frase escalofriante: murieron por una fuerza elemental irresistible. Y en su ropa, la radiación sigue emitiendo señal."
                )
            elif duracion == 2:
                return (
                    "Sientes un frío de menos treinta grados cortándote la respiración en los Montes Urales. Es el dos de febrero de mil novecientos cincuenta y nueve.\n"
                    "Nueve excursionistas soviéticos experimentados, liderados por Igor Dyatlov, establecen su último campamento en la pendiente de la Montaña de la Muerte.\n"
                    "Semanas después, los rescatistas encuentran la carpa principal cortada desde adentro con navajas. Las huellas muestran que huyeron descalzos hacia el bosque nocturno.\n"
                    "Las autopsias forenses revelan fracturas craneales brutales y tórax aplastados con una fuerza equivalente a un choque automovilístico, pero sin ningún rasguño en la piel exterior.\n"
                    "A dos de las víctimas les faltaban los ojos y la lengua. Los registros de la investigación médica soviética fueron clasificados de inmediato por el KGB.\n"
                    "Observas las últimas fotografías recuperadas del rollo de película. La última imagen es una esfera luminosa flotando en la oscuridad de los Urales."
                )
            else:
                return (
                    "Sientes un frío de menos treinta grados cortándote la respiración en los Montes Urales. Es el dos de febrero de mil novecientos cincuenta y nueve.\n"
                    "Nueve excursionistas soviéticos altamente entrenados del Instituto Politécnico de los Urales se adentran en la marcha alpina hacia la montaña Kholat Syakhl.\n"
                    "Al caer la noche, una amenaza invisible los obliga a tomar una decisión desesperada: rasgar la tienda de lona desde adentro con sus propias navajas para escapar.\n"
                    "Corren descalzos sobre la nieve congelada en completa oscuridad, separándose en la matorral a varios cientos de metros de distancia.\n"
                    "La partida de búsqueda encuentra semanas después los primeros cuerpos bajo un pino anciano. Las manos están destrozadas por intentar escalar el tronco helado.\n"
                    "En la quebrada del arroyo, los investigadores hallan a los cuatro miembros restantes con traumas severos: fracturas masivas de costillas y desprendimiento ocular sin lesiones externas.\n"
                    "Los análisis de los contadores Geiger revelan niveles anómalos de radiación gamma concentrados en los suéteres de las víctimas.\n"
                    "El expediente de la fiscalía de Sverdlovsk fue archivado bajo secreto militar antes de ser clausurado con una conclusión vaga: causa de muerte, una fuerza desconocida irresistible.\n"
                    "Revisas la bitácora del diario de ruta en su última página. Una anotación garabateada a mano dice: Ahora sabemos que ellos habitan aquí.\n"
                    "Y mientras miras las fotos en blanco y negro de mil novecientos cincuenta y nueve, el viento helado parece susurrar tu nombre."
                )

    # Dynamic 6-Angle Narrative Matrix for custom/unregistered topics
    import hashlib
    topic_hash = int(hashlib.md5(tema.encode("utf-8")).hexdigest(), 16)
    angle_idx = topic_hash % 6

    if parte == "part1":
        hooks_p1 = [
            f"A las tres de la madrugada, los primeros reportes sobre {tema} registraron una anomalía inexplicable.\nLas pruebas iniciales desafiaron a los investigadores principales de la época.\nPero lo que descubrieron en la segunda inspección cambiaría el curso del caso...\nSígueme ahora mismo para ver la Parte 2.",
            f"Abres la escotilla helada mientras examinas los restos abandonados de {tema}.\nSientes una corriente helada mientras descubres las primeras pistas que la prensa omitió.\nAntes de que las luces se apagaran por completo, una silueta se recortó en la entrada...\nSígueme ahora mismo para ver la Parte 2.",
            f"Un paquete de datos corrompido sobre {tema} fue subido de forma anónima a los servidores.\nAl descompilar el código, los registros de tiempo muestran actividades simultaneous en tres países.\nLa última línea del registro encriptado advertía de un peligro inminente...\nSígueme ahora mismo para ver la Parte 2.",
            f"Día siete de la expedición oficial en la zona de {tema}.\nLas brújulas comenzaron a girar sin control mientras los sensores detectaban presencias en el perímetro.\nEl diario de ruta se interrumpe justo en el momento del hallazgo principal...\nSígueme ahora mismo para ver la Parte 2.",
            f"Nadie en la ciudad se atreve a hablar públicamente sobre lo que ocurrió con {tema}.\nLos periódicos de la época fueron censurados horas después de la primera edición.\nUn expediente filtrado revela la cinta grabada por el último testigo...\nSígueme ahora mismo para ver la Parte 2.",
            f"Observas la fotografía en blanco y negro de {tema} bajo la luz tenue de tu escritorio.\nHay un detalle en el reflejo del cristal que desafía toda lógica fotográfica.\nAl ampliar la imagen, descubres que la sombra está mirando fijamente hacia la cámara...\nSígueme ahora mismo para ver la Parte 2."
        ]
        return hooks_p1[angle_idx]
    elif parte == "part2":
        return (
            f"Continuamos explorando los archivos históricos de {tema}.\n"
            "Las transcripciones de las bitácoras revelan notas enigmáticas dejadas por el equipo de investigación.\n"
            "Fotografías históricas muestran que las evidencias físicas fueron alteradas antes de declarar el caso cerrado.\n"
            "Lo que reveló el análisis posterior permaneció oculto durante décadas...\n"
            "Sígueme para ver la Parte 3 y la conclusión final."
        )
    elif parte == "part3":
        return (
            f"Llegamos al desenlace de los registros sobre {tema}.\n"
            "Investigadores modernos reabrieron las pruebas utilizando tecnología de precisión para analizar los patrones del caso.\n"
            "Las coincidencias en las fechas y las bitácoras demostraron que la historia oficial no contó la verdad completa.\n"
            "Y mientras revisas estas imágenes en tu pantalla, los registros nos recuerdan que la historia sigue abierta."
        )
    else:
        matrix = [
            # Angle 0: Forensic / Police Report
            (
                f"A las tres de la madrugada, los primeros reportes de campo sobre {tema} registraron una alteración inusual.\n"
                "Las pruebas de laboratorio revelaron la presencia de elementos compuestos que desafiaron a los investigadores de la época.\n"
                "Las imágenes archivadas confirman que la zona fue acordonada antes del amanecer por personal no identificado.\n"
                "Y hasta el día de hoy, el expediente permanece abierto para quien intente descifrar su verdadero origen."
            ),
            # Angle 1: First-Person Action / Survival
            (
                f"Abres la escotilla de metal helada mientras el viento choca contra tu rostro. Estás investigando el suceso de {tema}.\n"
                "Sientes un frío intenso en los dedos mientras examinas los restos abandonados en el terreno.\n"
                "Un zumbido tenue vibra en el suelo antes de que las luces principales colapsen por completo.\n"
                "Te detienes un segundo en la oscuridad. Sabiendo que la historia apenas comienza a mostrar sus sombras."
            ),
            # Angle 2: Tech / Data Leak
            (
                f"Un paquete de datos corrompido sobre {tema} fue subido de forma anónima a la red profunda.\n"
                "Al descomprimir las imágenes, los registros de tiempo muestran actividades simultáneas en tres servidores distintos.\n"
                "Las firmas digitales no pertenecen a ninguna compañía o usuario registrado en la época.\n"
                "Y la última línea del archivo garabateada en código hex solo pregunta: ¿Por qué buscas lo que fue borrado?"
            ),
            # Angle 3: Expedition Logbook
            (
                f"Séptimo día de exploración en la zona designada para {tema}.\n"
                "Las brújulas de navegación comienzan a girar sin control mientras las lecturas de los sensores caen a cero.\n"
                "Los miembros del equipo descubren las primeras marcas en la roca que no fueron hechas por herramientas humanas.\n"
                "El diario de ruta se interrumpe abruptamente en esta página, dejando la respuesta inconclusa."
            ),
            # Angle 4: Investigative Journalism
            (
                f"Nadie en el departamento se atreve a hablar públicamente sobre lo que ocurrió con {tema}.\n"
                "Los informes de prensa publicados en la época omitieron intencionalmente los testimonios de los tres testigos principales.\n"
                "Décadas después, un ex-analista entregó una cinta magnética grabada en secreto durante las reuniones finales.\n"
                "Y al escuchar el audio filtrado, comprendes por qué prefirieron guardar silencio."
            ),
            # Angle 5: Psychological Enigma
            (
                f"Observas la fotografía en blanco y negro de {tema} bajo la luz tenue de la habitación.\n"
                "Hay algo en la sombra del fondo que no encaja con la perspectiva original de la escena.\n"
                "Revisas el negativo original y notas que la silueta parece haberse desplazado entre cada toma.\n"
                "Cierras el expediente despacio. Sabiendo que el enigma te ha encontrado a ti."
            )
        ]
        return matrix[angle_idx]

@app.post("/api/generar-guion")
async def generar_guion(req: ScriptGenerateRequest):
    tema = req.tema.strip()
    duracion = req.duracion_minutos if req.duracion_minutos in [1, 2, 5] else 1
    parte = req.parte_serie if req.parte_serie in ["single", "part1", "part2", "part3"] else "single"

    if not tema:
        raise HTTPException(status_code=400, detail="El tema no puede estar vacío.")

    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    nvidia_key = os.getenv("NVIDIA_API_KEY", "").strip()
    mock_mode = (not openrouter_key and not nvidia_key) or os.getenv("MOCK_MODE") == "true"

    if mock_mode:
        logger.info(f"[Mock] Generando guion enriquecido ({parte}) para {tema} ({duracion} min)...")
        return {"tema": tema, "guion": build_fact_enriched_mock_script(tema, duracion, parte=parte)}

    try:
        client = get_configured_llm_client()
        from src.agents import ResearcherWriterAgent
        writer_agent = ResearcherWriterAgent(client)
        script_text = await writer_agent.write_script(tema, target_minutes=duracion, parte_serie=parte)
        return {"tema": tema, "guion": script_text}
    except Exception as e:
        logger.error(f"Error generando guion vía LLM ({e}). Usando guion de respaldo enriquecido ({parte})...")
        return {"tema": tema, "guion": build_fact_enriched_mock_script(tema, duracion, parte=parte)}

@app.post("/api/guardar-guion-temp")
async def guardar_guion_temp(req: SaveTempScriptRequest):
    tema = req.tema.strip()
    guion = req.guion.strip()
    if not tema or not guion:
        raise HTTPException(status_code=400, detail="El tema o el guion no pueden estar vacíos.")
        
    try:
        # Create temp directory inside output if it doesn't exist
        temp_dir = os.path.join(project_dir, "output", "temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        # Create a safe file name based on topic slug
        from src.main import slugify
        safe_name = f"guion_editado_{slugify(tema)}.txt"
        file_path = os.path.join(temp_dir, safe_name)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(guion)
            
        logger.info(f"Saved temporary edited script at: {file_path}")
        return {"status": "ok", "guion_path": file_path}
    except Exception as e:
        logger.error(f"Error saving temporary script: {e}")
        raise HTTPException(status_code=500, detail=f"Error al guardar guion temporal: {str(e)}")

@app.post("/api/ejecutar")
async def ejecutar_video(req: ExecuteRequest):
    """Registers the topic as processing in history.json."""
    tema = req.tema.strip()
    if not tema:
        raise HTTPException(status_code=400, detail="El tema no puede estar vacío.")
        
    logger.info(f"Registering production initiation for: '{tema}'")
    update_history_status(tema, "procesando")
    return {"status": "procesando", "tema": tema}

@app.websocket("/api/ws/ejecutar")
async def websocket_ejecutar(websocket: WebSocket):
    await websocket.accept()
    
    # Retrieve parameters from query string
    params = websocket.query_params
    tema = params.get("tema", "").strip()
    guion_path = params.get("guion_path", "").strip()
    subtitulos = params.get("subtitulos", "false").lower() == "true"
    aspect_ratio = params.get("aspect_ratio", "16:9").strip()
    
    if not tema:
        await websocket.send_text("[System Error] No topic specified.")
        await websocket.close()
        return

    logger.info(f"WebSocket client connected. Launching documentary generation for topic: '{tema}', custom script: {bool(guion_path)}, subtitles: {subtitulos}, aspect_ratio: {aspect_ratio}")
    
    # Determine if we should run the script in mock mode
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    nvidia_key = os.getenv("NVIDIA_API_KEY")
    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
    nvidia_image_key = os.getenv("NVIDIA_IMAGE_KEY")
    
    final_image_key = nvidia_image_key or nvidia_key
    
    script_mock_mode = (not openrouter_key and not nvidia_key) or not elevenlabs_key or not final_image_key or os.getenv("MOCK_MODE") == "true"
    
    main_script_path = os.path.join(project_dir, "src", "main.py")
    
    # Build python execution command
    cmd = [sys.executable, main_script_path, "--tema", tema, "--aspect-ratio", aspect_ratio]
    if guion_path:
        cmd.extend(["--guion_path", guion_path])
    if subtitulos:
        cmd.append("--subtitulos")
    if script_mock_mode:
        cmd.append("--mock")
        await websocket.send_text("[System Info] Ejecutando en modo SIMULACIÓN debido a credenciales faltantes o MOCK_MODE=true.")
        
    # We use a Queue to transfer lines from the reader thread to the async websocket
    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    process = None

    def read_stdout(proc, q, loop_ref):
        try:
            for line in iter(proc.stdout.readline, ""):
                asyncio.run_coroutine_threadsafe(q.put(line.strip()), loop_ref)
        except Exception as read_err:
            logger.error(f"Error reading stdout in thread: {read_err}")
        finally:
            proc.stdout.close()
            exit_val = proc.wait()
            asyncio.run_coroutine_threadsafe(q.put(f"__EXIT_CODE__:{exit_val}"), loop_ref)

    try:
        # Start subprocess using standard subprocess.Popen (independent of Proactor/Selector event loop!)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace"
        )

        # Start a daemon thread to read stdout without blocking the event loop
        thread = threading.Thread(target=read_stdout, args=(process, queue, loop), daemon=True)
        thread.start()

        # Read from queue and send over WebSocket
        exit_code = 0
        project_folder = None
        while True:
            line = await queue.get()
            if line.startswith("__EXIT_CODE__:"):
                exit_code = int(line.split(":", 1)[1])
                break
            if line.startswith("__PROJECT_FOLDER__:"):
                project_folder = line.split(":", 1)[1].strip()
                continue
            # Send lines to web console
            await websocket.send_text(line)
            
        if exit_code == 0:
            logger.info(f"Documentary creation succeeded for: '{tema}'")
            update_history_status(tema, "completado", project_folder)
            await websocket.send_text("[System Success] PROCESAMIENTO FINALIZADO EXITOSAMENTE.")
        else:
            logger.error(f"Documentary creation failed with exit code {exit_code} for: '{tema}'")
            update_history_status(tema, "fallido")
            await websocket.send_text(f"[System Error] El proceso finalizó con código de error {exit_code}.")
            
    except WebSocketDisconnect:
        logger.warning("WebSocket client disconnected during generation.")
        # If client disconnects, terminate the subprocess
        if process:
            try:
                process.terminate()
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Exception during WebSocket process execution: {e}")
        update_history_status(tema, "fallido")
        try:
            await websocket.send_text(f"[System Error] Excepción capturada en el servidor: {e}")
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass

@app.post("/api/scene/regenerate")
async def regenerate_single_scene(req: RegenerateSceneRequest):
    """Regenerates image, audio, or both for a single scene in a project."""
    output_base = os.path.join(project_dir, "output")
    target_dir = os.path.join(output_base, req.project_folder) if not os.path.isabs(req.project_folder) else req.project_folder
    escaleta_path = os.path.join(target_dir, "escaleta.json")
    
    if not os.path.exists(escaleta_path):
        raise HTTPException(status_code=404, detail=f"No se encontró escaleta.json en {req.project_folder}")
        
    with open(escaleta_path, "r", encoding="utf-8") as f:
        escaleta = json.load(f)
        
    escenas = escaleta.get("escenas", [])
    target_scene = None
    for scene in escenas:
        if scene.get("numero_escena") == req.numero_escena:
            target_scene = scene
            break
            
    if not target_scene:
        raise HTTPException(status_code=404, detail=f"Escena {req.numero_escena} no encontrada en la escaleta.")
        
    if req.new_prompt:
        target_scene["prompt_imagen"] = req.new_prompt
    if req.new_text:
        target_scene["texto"] = req.new_text

    from src.api_clients import ElevenLabsClient, NvidiaImageClient
    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY", "")
    elevenlabs_voice = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgq5okZXeOhx")
    nvidia_key = os.getenv("NVIDIA_IMAGE_KEY") or os.getenv("NVIDIA_API_KEY", "")
    nvidia_model = os.getenv("NVIDIA_IMAGE_MODEL", "black-forest-labs/flux.2-klein-4b")

    audio_path = os.path.join(target_dir, f"audios/escena_{req.numero_escena:02d}.mp3")
    image_path = os.path.join(target_dir, f"imagenes/escena_{req.numero_escena:02d}.png")
    prompt_path = os.path.join(target_dir, f"imagenes/prompt_{req.numero_escena:02d}.txt")

    results = {}
    
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(target_scene["prompt_imagen"])

    if req.mode in ["audio", "both"] and elevenlabs_key:
        try:
            tts_client = ElevenLabsClient(elevenlabs_key, elevenlabs_voice)
            await tts_client.text_to_speech(target_scene["texto"], audio_path)
            results["audio"] = "OK"
        except Exception as e:
            logger.error(f"Error al regenerar audio de escena {req.numero_escena}: {e}")
            results["audio"] = f"Error: {e}"
            
    if req.mode in ["image", "both"] and nvidia_key:
        try:
            img_client = NvidiaImageClient(nvidia_key, nvidia_model)
            await img_client.generate_image(target_scene["prompt_imagen"], image_path)
            results["image"] = "OK"
        except Exception as e:
            logger.error(f"Error al regenerar imagen de escena {req.numero_escena}: {e}")
            results["image"] = f"Error: {e}"

    with open(escaleta_path, "w", encoding="utf-8") as f:
        json.dump(escaleta, f, indent=2, ensure_ascii=False)

    return {
        "status": "success",
        "message": f"Escena {req.numero_escena} actualizada correctamente.",
        "results": results,
        "scene": target_scene
    }

if __name__ == "__main__":
    import uvicorn
    # Start the server on port 8000
    uvicorn.run("src.app:app", host="127.0.0.1", port=8000, reload=True)
