# AI Video Automation Suite

Una suite completa y modular impulsada por inteligencia artificial para la producción automatizada de guiones, descarga de recursos (audio e imagen) y ensamblado de videos de alta retención para YouTube y redes verticales.

## Caracteristicas

* **Exportador Directo a CapCut Desktop**: Creación nativa de borradores locales (draft_content.json y draft_meta_info.json) compatibles con CapCut Desktop Windows en cualquier unidad (C: y D:).
* **Soporte Multi-Formato (9:16 y 16:9)**: Configuración de lienzo y resolución adaptable para contenido vertical (Reels, Shorts, TikTok 1080x1920) o horizontal (YouTube 1920x1080).
* **Generacion de Guiones Inmersivos**: Agente escritor optimizado para narración en segunda persona ("tú") y estructuras de alta retención (Abyss Loop).
* **Filtros de Seguridad Antifiltros**: Sanitización de términos sensibles en español para evitar desmonetizaciones de audio en YouTube.
* **Agente Director de Arte**: Segmentación automática en escenas y diseño de prompts visuales optimizados para modelos fotorrealistas (Juggernaut XL, Flux, SDXL).
* **Resiliencia de API y Exponential Backoff**: Reintentos automáticos configurados ante errores de límite de tasa (HTTP 429) o fallos de servidor (5xx).
* **Fallback a Proveedores Locales**: Soporte de conmutación automática hacia servidores locales de Ollama (texto) y AUTOMATIC1111/ComfyUI (imágenes).
* **Subtítulos Sincronizados (.srt)**: Exportación automática de archivos SubRip (.srt) con marcas de tiempo exactas.
* **Reanudación de Proyectos (Checkpointing)**: Detección inteligente de archivos preexistentes para reanudar ejecuciones interrumpidas.
* **Inspector y Editor de Escena Individual**: Interfaz web para previsualizar, modificar el prompt o la voz y regenerar únicamente una escena específica.

## Instalacion y Requisitos

### Requisitos Previos
* **Python 3.10 o superior**
* **CapCut Desktop** (opcional, para editar directamente los borradores exportados).
* **FFmpeg** instalado y configurado en la variable de entorno PATH del sistema.

### Configuración del Entorno
Crea un archivo `.env` en la raíz de la carpeta `project/` con tus credenciales de API correspondientes:

```env
# Claves de LLM (OpenRouter o NVIDIA API)
OPENROUTER_API_KEY=tu_clave_aqui
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet

NVIDIA_API_KEY=tu_clave_aqui
NVIDIA_MODEL=meta/llama-3.1-405b-instruct

# ElevenLabs (Voces AI)
ELEVENLABS_API_KEY=tu_clave_aqui
ELEVENLABS_VOICE_ID=tu_voz_id_preferido

# Nvidia Image API (Flux / SDXL)
NVIDIA_IMAGE_KEY=tu_clave_aqui
NVIDIA_IMAGE_MODEL=black-forest-labs/flux.2-klein-4b

# Ruta personalizada opcional de borradores de CapCut Desktop
CAPCUT_DRAFT_PATH=C:/CapCut Projects/com.lveditor.draft
```

## Instrucciones de Uso

### 1. Exportar Borradores a CapCut Desktop
Para generar un borrador local directo que se abra automáticamente en tu aplicación de CapCut Desktop:

* **Exportar en formato vertical (Shorts / Reels / TikTok 9:16):**
  ```powershell
  python -m src.cli export-capcut <nombre_proyecto> --aspect-ratio 9:16
  ```

* **Exportar en formato horizontal (YouTube 16:9):**
  ```powershell
  python -m src.cli export-capcut <nombre_proyecto> --aspect-ratio 16:9
  ```

### 2. Comandos CLI Generales
* **Compilar un proyecto existente a video final:**
  ```powershell
  python -m src.cli compile [nombre_carpeta]
  ```

* **Importar imágenes ordenadas cronológicamente:**
  ```powershell
  python -m src.cli import-images --origen "C:/Ruta/A/Descargas" --proyecto "video_nombre"
  ```

* **Generar guías de edición CapCut:**
  ```powershell
  python -m src.cli generate-guides [nombre_proyecto]
  ```

### 3. Iniciar la Interfaz Web
```powershell
python project/src/app.py
```
Abre en tu navegador la URL: `http://localhost:8000`

---
*Desarrollado para la automatización rápida de contenido premium en YouTube y redes sociales.*
