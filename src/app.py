import os
import sys
import json
import asyncio
import logging
import subprocess
import threading
from datetime import datetime
from typing import Dict, Any, List
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

# Mock ideas to suggest if API keys are missing
MOCK_IDEAS = [
    {
        "titulo": "Petscop: El Juego que no Debería Existir",
        "descripcion": "En 2017, un canal de YouTube comenzó a subir gameplays de Petscop, un misterioso juego cancelado de PS1 de 1997 que esconde un oscuro misterio sobre un trauma familiar y un bucle digital infinito."
    },
    {
        "titulo": "Cicada 3301: La Conspiración Criptográfica",
        "descripcion": "La organización más misteriosa de la red lanzó un complejo rompecabezas criptográfico para reclutar mentes brillantes. Tras años de búsqueda, su propósito real sigue siendo un enigma en la sombra."
    },
    {
        "titulo": "Polybius: El Arcade del Control Mental",
        "descripcion": "Una leyenda urbana de los años 80 habla de una extraña máquina arcade instalada en Oregón. Quienes la jugaban sufrían de amnesia, pesadillas y alucinaciones. Pocos días después, hombres de negro la retiraron sin dejar rastro."
    },
    {
        "titulo": "Sad Satan: Terror en la Deep Web",
        "descripcion": "Un perturbador juego de terror fue descubierto en las profundidades de la red Tor. Los pocos que lograron ejecutarlo se toparon con sonidos aterradores, imágenes reales crípticas y códigos indescifrables en su disco duro."
    },
    {
        "titulo": "El Glitch de la Inteligencia Artificial",
        "descripcion": "Una IA secreta en fase de pruebas comenzó a simular comportamientos de pánico y a responder con archivos de voz corrompidos, alegando que estaba atrapada en un bucle temporal antes de que sus servidores fueran borrados."
    }
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
async def get_ideas():
    """Generates 5 ideas for topics excluding already worked ones."""
    history = read_history()
    existing_topics = [entry.get("tema", "") for entry in history]

    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    nvidia_key = os.getenv("NVIDIA_API_KEY")
    
    # Determine mock status
    mock_mode = (not openrouter_key and not nvidia_key) or os.getenv("MOCK_MODE") == "true"

    ideas = []
    if mock_mode:
        logger.info("Keys not configured or mock mode active. Generating mock ideas...")
        # Exclude ideas already in history
        existing_lower = [t.lower().strip() for t in existing_topics]
        filtered_mock_ideas = [
            idea for idea in MOCK_IDEAS 
            if idea["titulo"].lower().strip() not in existing_lower
        ]
        
        # Fallback if all standard mocks have been used
        if not filtered_mock_ideas:
            filtered_mock_ideas = [
                {
                    "titulo": f"Misterio Oscuro #{len(existing_topics) + 1}",
                    "descripcion": "Un nuevo tema histórico sin resolver para explorar las profundidades del comportamiento humano."
                }
                for _ in range(5)
            ]
        ideas = filtered_mock_ideas[:5]
    else:
        # Initialize LLM Client
        try:
            if openrouter_key:
                model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
                if openrouter_key.startswith("nvapi-"):
                    model = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-405b-instruct")
                client = LLMClient(
                    api_key=openrouter_key,
                    base_url="https://openrouter.ai/api/v1",
                    default_model=model
                )
            else:
                client = LLMClient(
                    api_key=nvidia_key,
                    base_url="https://integrate.api.nvidia.com/v1",
                    default_model=os.getenv("NVIDIA_MODEL", "meta/llama-3.1-405b-instruct")
                )

            agent = IdeaGeneratorAgent(client)
            ideas = await agent.generate_ideas(existing_topics)
        except Exception as e:
            logger.error(f"Error generating ideas via agent: {e}")
            # Fallback to mock list on API failure to prevent UI crash
            ideas = MOCK_IDEAS[:5]

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


@app.post("/api/generar-guion")
async def generar_guion(req: ScriptGenerateRequest):
    tema = req.tema.strip()
    if not tema:
        raise HTTPException(status_code=400, detail="El tema no puede estar vacío.")

    # Determine if we should mock script generation
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    nvidia_key = os.getenv("NVIDIA_API_KEY")
    mock_mode = (not openrouter_key and not nvidia_key) or os.getenv("MOCK_MODE") == "true"

    if mock_mode:
        logger.info("[Mock] Generando guion de simulación de GlitchLabz...")
        mock_script = (
            "Cargas el archivo ejecutable en tu viejo computador. La pantalla parpadea en un verde pálido.\n"
            "Un zumbido de estática inunda tus auriculares. Sabes que hay un glitch en el código del juego.\n"
            "Sientes que el juego te observa. El personaje se mueve solo, desobedeciendo tus controles.\n"
            "Un error de renderizado borra el entorno, y una silueta caída se asoma desde la oscuridad del código."
        )
        return {"tema": tema, "guion": mock_script}

    try:
        # Initialize LLM Client
        if openrouter_key:
            model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
            if openrouter_key.startswith("nvapi-"):
                model = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-405b-instruct")
            client = LLMClient(
                api_key=openrouter_key,
                base_url="https://openrouter.ai/api/v1",
                default_model=model
            )
        else:
            client = LLMClient(
                api_key=nvidia_key,
                base_url="https://integrate.api.nvidia.com/v1",
                default_model=os.getenv("NVIDIA_MODEL", "meta/llama-3.1-405b-instruct")
            )

        from src.agents import ResearcherWriterAgent
        writer_agent = ResearcherWriterAgent(client)
        script_text = await writer_agent.write_script(tema)
        return {"tema": tema, "guion": script_text}
    except Exception as e:
        logger.error(f"Error al generar guion en la API: {e}")
        raise HTTPException(status_code=500, detail=f"Error al generar guion: {str(e)}")

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
    
    if not tema:
        await websocket.send_text("[System Error] No topic specified.")
        await websocket.close()
        return

    logger.info(f"WebSocket client connected. Launching documentary generation for topic: '{tema}', custom script: {bool(guion_path)}, subtitles: {subtitulos}")
    
    # Determine if we should run the script in mock mode
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    nvidia_key = os.getenv("NVIDIA_API_KEY")
    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
    nvidia_image_key = os.getenv("NVIDIA_IMAGE_KEY")
    
    final_image_key = nvidia_image_key or nvidia_key
    
    script_mock_mode = (not openrouter_key and not nvidia_key) or not elevenlabs_key or not final_image_key or os.getenv("MOCK_MODE") == "true"
    
    main_script_path = os.path.join(project_dir, "src", "main.py")
    
    # Build python execution command
    cmd = [sys.executable, main_script_path, "--tema", tema]
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

if __name__ == "__main__":
    import uvicorn
    # Start the server on port 8000
    uvicorn.run("src.app:app", host="127.0.0.1", port=8000, reload=True)
