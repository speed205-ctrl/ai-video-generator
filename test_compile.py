import sys
import json
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.main import compile_video

logging.basicConfig(level=logging.INFO)

output_dir = r"C:\Users\Jaime Enrique\OneDrive\Documents\youtube\project\output\video_luna_la_ia_de_microsoft_que_aprendió_a_odiar_en_24_horas_20260608_095805"
escaleta_path = os.path.join(output_dir, "escaleta.json")

with open(escaleta_path, "r", encoding="utf-8") as f:
    escaleta = json.load(f)

print("Starting compile_video...")
try:
    video_path = compile_video(output_dir, escaleta)
    print("Result:", video_path)
except Exception as e:
    print("Fatal exception:", e)
