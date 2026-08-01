# AI Video Automation Suite 🎬🤖

Una suite completa y modular impulsada por inteligencia artificial para la producción automatizada de guiones, descarga de recursos (audio y video) y ensamblado de videos de alta retención para YouTube.

## 🚀 Características

* **Generación de Guiones Inmersivos**: Agente escritor optimizado para narración en segunda persona (`tú`) y estructuras de alta retención (Abyss Loop).
* **Filtros de Seguridad Antifiltros**: Sanitización de términos sensibles en español para evitar desmonetizaciones de audio en YouTube.
* **Agente Director de Arte**: Segmentación automática en escenas y diseño de prompts visuales optimizados (ideales para Juggernaut XL y Flux).
* **Guías de Edición CapCut Detalladas**: Generador automático de guías con marcas de tiempo, transiciones, efectos de video, efectos de sonido (SFX) y música.
* **Importador de Imágenes Cronológico**: Script para organizar e importar imágenes descargadas por lote ordenadas por fecha de creación.
* **Compilación de Video con GPU**: Ensamblado acelerado por hardware mediante OpenCV y MoviePy (con transiciones, zooms, paneos y soporte opcional de subtítulos quemados).

## 🛠️ Instalación y Requisitos

### Requisitos Previos
* **Python 3.10 o superior**
* **FFmpeg** instalado y configurado en las variables de entorno (`PATH`) del sistema.

### Configuración del Entorno
1. Clona este repositorio o copia los archivos a tu espacio de trabajo local.
2. Crea un archivo `.env` en la raíz de la carpeta `project/` con tus credenciales de API correspondientes:

```env
# Claves de LLM (OpenRouter o NVIDIA API)
OPENROUTER_API_KEY=tu_clave_aquí
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet  # o tu modelo preferido

NVIDIA_API_KEY=tu_clave_aquí
NVIDIA_MODEL=meta/llama-3.1-405b-instruct

# ElevenLabs (Voces AI)
ELEVENLABS_API_KEY=tu_clave_aquí
ELEVENLABS_VOICE_ID=tu_voz_id_preferido

# Nvidia Image API (Flux / SDXL)
NVIDIA_IMAGE_KEY=tu_clave_aquí
NVIDIA_IMAGE_MODEL=black-forest-labs/flux.2-klein-4b
```

## 🎮 Instrucciones de Uso

### 1. Iniciar la Interfaz Web (Servidor Flask)
Para usar la aplicación de forma visual desde tu navegador web:
```powershell
python project/src/app.py
```
Abre en tu navegador la URL: `http://localhost:5000`

### 2. Generación Completa desde Consola
Para generar un nuevo proyecto completo desde la terminal usando la API:
```powershell
python project/src/main.py --tema "Tu tema del documental"
```
*(Si te quedaste sin créditos de API y quieres realizar pruebas de simulación local, añade el parámetro `--mock`)*

### 3. Renombrar e Importar Imágenes en Lote
Si has generado las imágenes de forma externa (por contingencia de créditos en Stable Diffusion o Leonardo.ai), colócalas en una carpeta temporal en orden y ejecuta:
```powershell
python project/rename_downloaded_images.py
```
El script leerá las imágenes en orden cronológico de creación y las importará con la nomenclatura correcta (`escena_01.png`, etc.) directamente al proyecto.

### 4. Regenerar Guías de Edición para CapCut
Para actualizar las guías de edición CapCut de todos tus proyectos activos:
```powershell
python project/generate_capcut_guide.py
```

### 5. Compilar Video Final
Una vez que tengas todos los audios e imágenes en el directorio de salida del proyecto, compila el video definitivo ejecutando:
```powershell
python project/compile_project_folder.py
```
Selecciona el número correspondiente del listado interactivo y presiona Enter.

---
*Desarrollado para la automatización rápida de contenido premium en YouTube.*
