import re
import json
import logging
from typing import Dict, Any, List, Optional
from .api_clients import LLMClient

logger = logging.getLogger(__name__)

def _repair_json_string(raw: str) -> str:
    """
    Walks through a raw JSON string character-by-character, tracking whether
    we are inside a string value or not. When inside a string and we encounter
    a double-quote, we use lookahead to determine if it's the real closing quote
    (followed by , } ] or :) or an unescaped internal quote (followed by text).
    Also fixes invalid backslash escapes and literal newlines inside strings.
    """
    # Step 1: Remove trailing commas before } or ]
    raw = re.sub(r',\s*([}\]])', r'\1', raw)

    result = []
    i = 0
    n = len(raw)
    in_string = False

    while i < n:
        ch = raw[i]

        if not in_string:
            result.append(ch)
            if ch == '"':
                in_string = True
            i += 1
        else:
            # We are inside a JSON string value
            if ch == '\\':
                if i + 1 < n:
                    nxt = raw[i + 1]
                    if nxt in ('"', '\\', '/', 'b', 'f', 'n', 'r', 't'):
                        result.append(ch)
                        result.append(nxt)
                        i += 2
                    elif nxt == 'u' and i + 5 < n and all(
                        c in '0123456789abcdefABCDEF' for c in raw[i+2:i+6]
                    ):
                        result.append(raw[i:i+6])
                        i += 6
                    else:
                        # Invalid escape like \s, \P, etc → escape the backslash
                        result.append('\\\\')
                        i += 1
                else:
                    result.append('\\\\')
                    i += 1
            elif ch == '"':
                # Decide: is this the real closing quote, or an internal unescaped one?
                rest = raw[i+1:]
                rest_stripped = rest.lstrip()
                if not rest_stripped or rest_stripped[0] in (',', '}', ']', ':'):
                    # Real closing quote
                    result.append('"')
                    in_string = False
                    i += 1
                else:
                    # Internal unescaped quote → escape it
                    result.append('\\"')
                    i += 1
            elif ch == '\n':
                result.append('\\n')
                i += 1
            elif ch == '\r':
                if i + 1 < n and raw[i+1] == '\n':
                    result.append('\\n')
                    i += 2
                else:
                    result.append('\\n')
                    i += 1
            elif ch == '\t':
                result.append('\\t')
                i += 1
            else:
                result.append(ch)
                i += 1

    return ''.join(result)


def clean_and_parse_json(text: str) -> Dict[str, Any]:
    """
    Extracts a JSON block from LLM output, repairs common malformations
    (trailing commas, unescaped quotes, invalid escapes, literal newlines),
    and parses it.
    """
    cleaned_text = text.strip()

    # Try finding markdown code block markers ```json ... ``` or ``` ... ```
    markdown_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned_text, re.IGNORECASE)
    if markdown_match:
        json_str = markdown_match.group(1).strip()
    else:
        # Otherwise, find the outermost curly/square brace pair
        json_match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned_text)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            json_str = cleaned_text

    # Attempt 1: Try parsing as-is (fast path for well-formed output)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Attempt 2: Run the state-machine repair and try again
    repaired = _repair_json_string(json_str)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON even after repair. Raw response:\n{text[:2000]}")
        logger.error(f"Repaired string (first 2000 chars):\n{repaired[:2000]}")
        raise ValueError(f"JSON parsing error: {e}")


class ResearcherWriterAgent:
    """
    Agent responsible for writing historically accurate, high-retention, and dark scripts.
    Narrates exclusively in the second person ('tú') with short, impactful sentences.
    """
    def __init__(self, client: LLMClient):
        self.client = client
        self.system_prompt = (
            "Actúas como el Narrador de GlitchLabz, un canal especializado en misterios de tecnología, "
            "leyendas urbanas de videojuegos (creepypastas, lost media), ARGs y anomalías digitales de la red.\n"
            "Tu misión es escribir un guion de alta retención para un video de YouTube sobre el tema provisto por el usuario.\n\n"
            "REGLAS DE ESTILO NARRATIVO CRÍTICAS:\n"
            "1. Estilo: Enigmático, inmersivo, tecnológico y conspiranoico. La atmósfera debe evocar que el espectador "
            "está desentrañando un archivo corrupto, un glitch en el sistema o un secreto oculto en código fuente.\n"
            "2. Sin rodeos ni introducciones cliché: NUNCA saludes al espectador ni digas cosas como 'Hola a todos', "
            "'En este video', o 'Bienvenidos'. Comienza directo con una pregunta inquietante o una declaración fría que enganche al instante.\n"
            "3. Voz Narrativa: Escribe exclusivamente en segunda persona del singular ('tú'). "
            "Ejemplo: 'Cargas el archivo ejecutable...', 'Observas la pantalla parpadear...', 'Sientes que el juego te observa...'.\n"
            "4. Oraciones: Deben ser oraciones cortas, secas y de alto impacto emocional, manteniendo un ritmo tenso y dinámico.\n"
            "5. Salida: Escribe exclusivamente la narración directa en off, sin notas del director, diálogos ficticios ni descripciones de sonido.\n"
            "6. REGLAS DE SEGURIDAD PARA YOUTUBE (CENSURA Y MONETIZACIÓN): Para evitar la desmonetización o restricción de edad por parte del algoritmo de YouTube (el cual transcribe el audio automáticamente), queda ESTRICTAMENTE PROHIBIDO el uso de palabras gráficas de violencia, autolesión o muerte en español. Utiliza en su lugar metáforas elegantes y términos tecnológicos suaves:\n"
            "   - En lugar de 'sangre', usa 'carmesí', 'rastro escarlata', 'líquido vital', 'manchas de código' o 'error de renderizado'.\n"
            "   - En lugar de 'cadáver(es)' o 'muerto(s)', usa 'cuerpo(s) inerte(s)', 'silueta(s) caída(s)', 'figura(s) sin vida', 'datos borrados' o 'avatar inactivo'.\n"
            "   - En lugar de 'asesinato', 'matar', 'masacre' o 'ejecutar', usa 'desenlace trágico', 'condena', 'crimen', 'terminar con', 'silenciar', 'eliminar de la simulación' o 'corromper'.\n"
            "   - En lugar de 'tortura' o 'torturar', usa 'martirio', 'tormento', 'hacer sufrir' o 'extrema agonía'.\n"
            "   - En lugar de 'suicidio', usa 'trágico final' o 'desesperación extrema'.\n"
            "Aplica estas restricciones con máximo rigor, especialmente en los primeros 30 segundos del video (las primeras 3 escenas).\n"
            "7. Ortografía y Gramática: Asegúrate de mantener una ortografía y gramática perfectas en español. Revisa con absoluto rigor que no haya palabras mal escritas (por ejemplo, escribe siempre 'ciudades' y nunca cometas errores tipográficos ni inventes palabras como 'ciendas').\n"
            "8. ESTRUCTURA NARRATIVA OBLIGATORIA (EL BUCLE DEL ABISMO - THE ABYSS LOOP):\n"
            "Divide el guion en las siguientes 5 fases de ritmo y tensión:\n"
            "   - FASE 1: HOOK SENSORIAL (0% - 10% del guion): Comienza directamente en segunda persona ('tú') describiendo un estímulo sensorial incómodo o visceral (un sabor a cobre, frío en los dedos, un zumbido eléctrico en tus oídos). Sin rodeos ni introducciones.\n"
            "   - FASE 2: ANCLAJE Y ANOMALÍA (10% - 25% del guion): Presenta un contexto familiar o histórico real para que el espectador baje la guardia, seguido inmediatamente por la primera pista o anomalía digital inexplicable.\n"
            "   - FASE 3: ESPIRAL DE MICRO-CLIFFHANGERS (25% - 60% del guion): El misterio se profundiza. Estructura esta fase en forma de bucles de curiosidad: resuelve un misterio menor y plantea inmediatamente una pregunta más grande. Involucra evidencias físicas (correos internos, logs de error, grabaciones de audio, datos borrados).\n"
            "   - FASE 4: EL GIRO DEL ABISMO (60% - 85% del guion): Las reglas de la realidad cambian. Muestra que el peligro es ineludible, existencial o que el espectador mismo forma parte de la anomalía.\n"
            "   - FASE 5: CUARTA PARED Y LOOP ALGORÍTMICO (85% - 100% del guion): Rompe la cuarta pared apelando directamente al espectador (tú) en su pantalla. Diseña la última línea del guion para que enlace de forma perfecta y fluida con la primera línea del hook, creando un bucle infinito que invite a volver a verlo."
        )

    async def write_script(self, topic: str) -> str:
        user_prompt = f"Tema para el enigma digital/mitología de internet/gaming de GlitchLabz: {topic}\nEscribe el guion completo ahora."
        return await self.client.generate_chat(
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            temperature=0.75
        )


class PromptDirectorAgent:
    """
    Agent responsible for reading a script, segmenting it into scenes,
    calculating approximate/relative progress, designing image prompts in English,
    and suggesting camera movement effects for video editing.
    """
    def __init__(self, client: LLMClient, max_scenes: int = 45):
        self.client = client
        self.max_scenes = max_scenes
        self.system_prompt = (
            "Actúas como el Director de Arte de GlitchLabz, especialista en estética retro-tech, analog horror y misterios digitales.\n"
            "Tu misión es segmentar el guion narrativo que se te provea en escenas, creando prompts visuales específicos "
            "y seleccionando efectos de animación.\n\n"
            "REGLAS DE DIRECCIÓN Y SEGMENTACIÓN:\n"
            f"1. Segmenta el guion en escenas lógicas. La cantidad total NO debe exceder {max_scenes} escenas.\n"
            "2. Para cada escena, define:\n"
            "   - 'texto': El fragmento exacto o resumido del guion que se narrará en esta escena.\n"
            "   - 'prompt_imagen': Un prompt visual ultra-descriptivo y evocador en inglés para lograr los mejores resultados en el modelo de generación.\n"
            "   - 'efecto_capcut': Un efecto de animación sugerido de la lista: ['Zoom in', 'Zoom out', 'Paneo lento izquierda', 'Paneo lento derecha', 'Paneo vertical', 'Paneo lento diagonal'].\n"
            "   - 'efecto_sonido': Una recomendación corta en español sobre qué efecto de sonido (SFX) o música se le debería poner a esta escena en post-producción (ej. 'Latido de corazón rápido', 'Estática de VHS pesada', 'Zumbido de neón', 'Silencio tenso').\n"
            "3. Estilo visual obligatorio: Todos los prompts deben exigir la estética: 'Creepy digital enigma, analog horror, CRT scanlines, glitch distortion, retro-tech, dark synthwave, cinematic. Avoid cheerful, standard CGI, text, labels, signatures, watermarks.' Asegúrate de integrar esta línea literal al final de cada prompt.\n"
            "4. PROHIBICIÓN ABSOLUTA DE TEXTO Y LETRAS: Queda estrictamente PROHIBIDO solicitar palabras específicas, letras, números, marcas legibles, logos escritos o frases concretas en las imágenes (ej. no pidas 'stamped with CLASSIFIED', ni 'showing 404 error', ni 'file names', ni 'timestamps', ni 'letters'). Los modelos de IA generan textos con errores graves de ortografía y caracteres deformes que arruinan la imagen. En su lugar, describe siempre representaciones abstractas u objetos físicos sugerentes: en lugar de 'showing 404 error', usa 'broken link icon and abstract warning symbols'; en lugar de 'stamped with CLASSIFIED', usa 'confidential red stamp symbol without letters'; en lugar de 'email text' o 'code', usa 'unreadable blurred digital lines' o 'abstract glowing green pixels'; en lugar de interfaces web legibles, pide 'pixelated abstract web layouts' o 'blurred monitor display'.\n"
            "5. REGLAS DE SEGURIDAD PARA IMÁGENES: NUNCA utilices palabras gráficas, sangrientas, violentas o de muerte explícita (como 'blood', 'flesh', 'decapitation', 'kill', 'torture', 'mutilated', 'corpse', 'dead', 'execution', 'burnt') ni describas situaciones de secuestro, cautiverio, rehenes, tortura o violencia física directa sobre personas que puedan activar los filtros de seguridad de las APIs de imágenes. En su lugar, evoca la tensión y el misterio tecnológico usando elementos visuales de la red y entornos digitales (ej. 'glitchy computer monitor in dark room', 'glowing green text on terminal screen', 'ominous server racks with flashing red lights', 'blinking security camera feed', 'scrambled VHS tape static', 'shadowy figure looking at old console', 'distorted game textures').\n\n"
            "RESTRICCIÓN CRÍTICA DE SALIDA:\n"
            "Debes responder ÚNICA y EXCLUSIVAMENTE con un objeto JSON estructurado que siga el esquema definido abajo. "
            "No incluyas explicaciones, introducciones, ni bloques de texto fuera del JSON.\n\n"
            "Esquema JSON esperado:\n"
            "{\n"
            "  \"escenas\": [\n"
            "    {\n"
            "      \"numero\": 1,\n"
            "      \"texto\": \"Texto que se narra en off para la escena 1...\",\n"
            "      \"prompt_imagen\": \"Detailed image prompt in English ending with the mandatory visual style...\",\n"
            "      \"efecto_capcut\": \"Zoom in\",\n"
            "      \"efecto_sonido\": \"Zumbido eléctrico bajo y estática\"\n"
            "    }\n"
            "  ]\n"
            "}"
        )

    async def segment_script(self, script_content: str) -> List[Dict[str, Any]]:
        logger.info("Segmenting script and designing image prompts...")
        user_prompt = f"Por favor segmenta este guion según las reglas:\n\n{script_content}"

        max_attempts = 3
        last_error = None

        for attempt in range(1, max_attempts + 1):
            if attempt == 1:
                current_prompt = user_prompt
            else:
                # Retry: send the broken response back and ask for a clean fix
                logger.warning(f"Retry {attempt}/{max_attempts}: Asking LLM to fix its JSON output...")
                current_prompt = (
                    "Tu respuesta anterior contenía JSON malformado y no se pudo parsear. "
                    "El error fue:\n"
                    f"{last_error}\n\n"
                    "Por favor, genera NUEVAMENTE la segmentación del guion de abajo. "
                    "REGLAS CRÍTICAS PARA ESTA RESPUESTA:\n"
                    "- Responde SOLO con el objeto JSON, sin texto adicional.\n"
                    "- NO uses comillas dobles sin escapar dentro de valores de texto.\n"
                    "- Escapa correctamente las comillas internas con \\\".\n"
                    "- Cada string debe empezar y terminar con una sola comilla doble.\n\n"
                    f"Guion a segmentar:\n\n{script_content}"
                )

            response_text = await self.client.generate_chat(
                system_prompt=self.system_prompt,
                user_prompt=current_prompt,
                temperature=0.3 if attempt > 1 else 0.4
            )

            try:
                parsed_data = clean_and_parse_json(response_text)
                scenes = parsed_data.get("escenas", [])

                # Enforce maximum scenes restriction in code as well
                if len(scenes) > self.max_scenes:
                    logger.warning(f"Agent generated {len(scenes)} scenes, truncating to {self.max_scenes} to comply with API limits.")
                    scenes = scenes[:self.max_scenes]

                if attempt > 1:
                    logger.info(f"JSON parsing succeeded on retry attempt {attempt}.")
                return scenes
            except Exception as e:
                last_error = str(e)
                logger.error(f"[Attempt {attempt}/{max_attempts}] Error parsing agent segmentation: {e}")

        # All attempts exhausted
        raise ValueError(f"Failed to parse agent segmentation after {max_attempts} attempts. Last error: {last_error}")


class IdeaGeneratorAgent:
    """
    Agent responsible for proposing unique, dark, and raw historical documentary ideas
    for YouTube, making sure not to suggest any topic that matches or is extremely similar to
    the list of already processed topics.
    """
    def __init__(self, client: LLMClient):
        self.client = client
        self.system_prompt = (
            "Actúas como el Agente Ideador Creativo de GlitchLabz, especializado en tendencias de internet, misterios tecnológicos y mitos de gaming.\n"
            "Tu misión es proponer 5 temas únicos, intrigantes y de alta retención para videos de YouTube.\n\n"
            "REGLAS DE GENERACIÓN DE IDEAS:\n"
            "1. Los temas deben ser enigmas de tecnología, leyendas de internet, creepypastas o mitos de videojuegos (lost media, misterios de la deep web, glitches extraños, inteligencias artificiales anómalas, etc.).\n"
            "2. Deben capturar el interés de inmediato, con sinopsis enigmáticas, conspiranoicas y atractivas.\n"
            "3. Recibirás una lista de temas que YA se han trabajado en el pasado. NUNCA propongas un tema que coincida o sea extremadamente similar a los de esa lista.\n"
            "4. Ortografía y Gramática: Todos los títulos y descripciones deben tener una ortografía y gramática impecables en español. Revisa especialmente que palabras como 'ciudades' o 'ciencias' estén correctamente escritas (evita por completo errores tipográficos como 'ciendas').\n\n"
            "RESTRICCIÓN CRÍTICA DE SALIDA:\n"
            "Debes responder ÚNICA y EXCLUSIVAMENTE con un objeto JSON válido, sin explicaciones ni bloques de texto adicionales.\n\n"
            "Esquema JSON esperado:\n"
            "{\n"
            "  \"ideas\": [\n"
            "    {\n"
            "      \"titulo\": \"Título impactante del tema\",\n"
            "      \"descripcion\": \"Una breve sinopsis cruda y atractiva de la idea y su enfoque narrativo.\"\n"
            "    }\n"
            "  ]\n"
            "}"
        )

    async def generate_ideas(self, existing_topics: List[str]) -> List[Dict[str, str]]:
        logger.info(f"Generating 5 new ideas. Excluding topics: {existing_topics}")
        
        # Format existing topics list
        formatted_list = "\n".join([f"- {topic}" for topic in existing_topics]) if existing_topics else "Ninguno (esta es la primera ejecución)."
        
        user_prompt = f"Temas ya trabajados en el pasado (EXCLUIR COMPLETAMENTE):\n{formatted_list}\n\nGenera 5 nuevas ideas oscuras ahora."
        
        response_text = await self.client.generate_chat(
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            temperature=0.85
        )
        
        try:
            parsed_data = clean_and_parse_json(response_text)
            ideas = parsed_data.get("ideas", [])
            return ideas[:5]
        except Exception as e:
            logger.error(f"Error parsing generated ideas: {e}")
            raise e


class MetadataGeneratorAgent:
    """
    Agent responsible for generating YouTube metadata (titles, thumbnail prompts, description).
    """
    def __init__(self, client: LLMClient):
        self.client = client
        self.system_prompt = (
            "Actúas como un experto en SEO y retención de YouTube para el canal GlitchLabz.\n"
            "Tu misión es analizar el guion de un video de misterio/tecnología y generar los metadatos optimizados para YouTube.\n\n"
            "REGLAS DE GENERACIÓN:\n"
            "1. Título Principal: Debe ser intrigante, oscuro y de alta curiosidad (menos de 65 caracteres).\n"
            "2. 4 Propuestas de Título: Alternativas al título principal que también generen clics.\n"
            "3. Prompt para Miniatura: Un prompt visual descriptivo en inglés para un modelo de IA (como Midjourney o Flux) "
            "que represente el tema del video de forma enigmática. Debe incluir la estética: 'Ominous retro-tech, analog horror, cinematic lighting, 16:9'.\n"
            "4. Descripción de YouTube: Un texto intrigante y optimizado para SEO (de 2 a 3 párrafos cortos) "
            "que describa el misterio sin hacer spoilers totales, e incluya hashtags relevantes al final.\n\n"
            "RESTRICCIÓN CRÍTICA DE SALIDA:\n"
            "Debes responder ÚNICA y EXCLUSIVAMENTE con un objeto JSON válido, sin explicaciones ni bloques de texto adicionales.\n\n"
            "Esquema JSON esperado:\n"
            "{\n"
            "  \"titulo\": \"Título Principal del Video\",\n"
            "  \"propuestas_titulo\": [\n"
            "    \"Propuesta alternativa 1\",\n"
            "    \"Propuesta alternativa 2\",\n"
            "    \"Propuesta alternativa 3\",\n"
            "    \"Propuesta alternativa 4\"\n"
            "  ],\n"
            "  \"prompt_miniatura\": \"Detailed English prompt for image generation...\",\n"
            "  \"descripcion_youtube\": \"Descripción optimizada para YouTube...\"\n"
            "}"
        )

    async def generate_metadata(self, script_content: str) -> Dict[str, Any]:
        logger.info("Generando metadatos de YouTube (títulos, descripción y prompt de miniatura)...")
        user_prompt = f"Por favor analiza este guion y genera la estructura JSON requerida:\n\n{script_content}"
        
        response_text = await self.client.generate_chat(
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            temperature=0.7
        )
        
        try:
            return clean_and_parse_json(response_text)
        except Exception as e:
            logger.error(f"Error parsing generated metadata: {e}")
            # Fallback
            return {
                "titulo": "Misterio Tecnológico Revelado",
                "propuestas_titulo": [
                    "La Conspiración del Servidor Oculto",
                    "El Archivo Corrupto que no Debiste Ver",
                    "El Enigma Detrás del Glitch",
                    "Lo que la Red Intentó Borrar"
                ],
                "prompt_miniatura": "Ominous glowing computer server in a dark room, wireframe graphics on screen, analog horror, retro-tech, cinematic lighting, 16:9",
                "descripcion_youtube": "Un viaje profundo a los rincones más misteriosos de la red. Investigamos un enigma que pocos se atreven a comentar. ¿Qué se oculta en los datos perdidos?"
            }


