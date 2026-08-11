# AI Video Automation Suite

Una suite completa y modular impulsada por inteligencia artificial para la producción automatizada de guiones, descarga de recursos (audio e imagen) y ensamblado de videos de alta retención para YouTube.

## Caracteristicas

* **Generacion de Guiones Inmersivos**: Agente escritor optimizado para narración en segunda persona ("tú") y estructuras de alta retención (Abyss Loop).
* **Filtros de Seguridad Antifiltros**: Sanitización de términos sensibles en español para evitar desmonetizaciones de audio en YouTube.
* **Agente Director de Arte**: Segmentación automática en escenas y diseño de prompts visuales optimizados para modelos fotorrealistas (Juggernaut XL, Flux, SDXL).
* **Resiliencia de API y Exponential Backoff**: Reintentos automáticos configurados ante errores de límite de tasa (HTTP 429) o fallos de servidor (5xx).
* **Fallback a Proveedores Locales**: Soporte de conmutación automática hacia servidores locales de Ollama (texto) y AUTOMATIC1111/ComfyUI (imágenes) en caso de agotamiento de crédito en la nube.
* **Subtítulos Sincronizados (.srt)**: Exportación automática de archivos SubRip (.srt) con marcas de tiempo exactas para YouTube Studio.
* **Reanudación de Proyectos (Checkpointing)**: Detección inteligente de archivos preexistentes para reanudar ejecuciones interrumpidas sin duplicar consumo de API.
* **Inspector y Editor de Escena Individual**: Interfaz web para previsualizar, modificar el prompt o la voz y regenerar únicamente una escena específica sin procesar todo el proyecto.
* **Guías de Edición CapCut Detalladas**: Generador automático de guías con marcas de tiempo, transiciones, efectos de video, efectos de sonido (SFX) y música recomendada.
* **Importador de Imágenes Cronológico**: Script para organizar e importar imágenes descargadas por lote ordenadas por fecha de creación.
* **Compilación de Video con GPU**: Ensamblado acelerado por hardware mediante OpenCV y MoviePy (con transiciones, zooms y paneos).

## Instalacion y Requisitos

### Requisitos Previos
* **Python 3.10 o superior**
* **FFmpeg** instalado y configurado en la variable de entorno PATH del sistema.

### Configuración del Entorno
1. Clona este repositorio o copia los archivos a tu espacio de trabajo local.
2. Crea un archivo `.env` en la raíz de la carpeta `project/` con tus credenciales de API correspondientes:

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
```

## Instrucciones de Uso

### 1. Interfaz CLI Unificada (Recomendado)
El proyecto cuenta con un punto de entrada CLI unificado para ejecutar todos los submódulos:

* **Compilar un proyecto existente:**
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

### 2. Iniciar la Interfaz Web (Servidor FastAPI / Flask)
Para usar la aplicación de forma visual con inspector de escenas y consola en vivo:
```powershell
python project/src/app.py
```
Abre en tu navegador la URL: `http://localhost:8000`

### 3. Generación Completa desde Consola
Para generar un nuevo proyecto completo desde la terminal:
```powershell
python project/src/main.py --tema "Tu tema del documental"
```
Para ejecutar en modo de simulación local (sin consumir créditos):
```powershell
python project/src/main.py --tema "Tu tema del documental" --mock
```

---
*Desarrollado para la automatización rápida de contenido premium en YouTube.*
