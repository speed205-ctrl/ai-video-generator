import json
import os

escaleta_path = r"C:\Users\Jaime Enrique\OneDrive\Documents\youtube\project\output\video_luna_la_ia_de_microsoft_que_aprendió_a_odiar_en_24_horas_20260608_095805\escaleta.json"
output_txt_path = r"C:\Users\Jaime Enrique\OneDrive\Documents\youtube\project\prompts_pendientes.txt"

with open(escaleta_path, "r", encoding="utf-8") as f:
    escaleta = json.load(f)

escenas = escaleta.get("escenas", [])
prompts = []

# Filtrar desde la escena 4 hasta el final
for escena in escenas:
    numero = escena.get("numero_escena")
    if numero >= 4:
        prompt = escena.get("prompt_imagen", "")
        # Solo agregar el texto crudo del prompt para Stable Diffusion
        prompts.append(prompt)

with open(output_txt_path, "w", encoding="utf-8") as out:
    out.write("\n".join(prompts))

print(f"Archivo guardado exitosamente en: {output_txt_path}")
