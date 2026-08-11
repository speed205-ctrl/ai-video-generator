import os
import json
import uuid
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from src.utils.capcut_path import get_capcut_draft_path

logger = logging.getLogger(__name__)

class CapCutDraftExporter:
    """
    Exports a local project directly into CapCut Desktop draft format (com.lveditor.draft).
    Creates draft_content.json and draft_meta_info.json with multi-track timeline support.
    """
    def __init__(self, aspect_ratio: str = "9:16"):
        self.aspect_ratio = aspect_ratio
        if aspect_ratio == "9:16":
            self.width = 1080
            self.height = 1920
        else:
            self.width = 1920
            self.height = 1080

    def export_project(self, project_dir: str, target_draft_root: Optional[Path] = None) -> Path:
        project_path = Path(project_dir).resolve()
        escaleta_path = project_path / "escaleta.json"
        
        if not escaleta_path.exists():
            raise FileNotFoundError(f"No se encontró escaleta.json en '{project_path}'.")

        with open(escaleta_path, "r", encoding="utf-8") as f:
            escaleta = json.load(f)

        project_name = project_path.name
        draft_root = target_draft_root or get_capcut_draft_path()
        dest_draft_dir = draft_root / project_name
        dest_draft_dir.mkdir(parents=True, exist_ok=True)

        escenas = escaleta.get("escenas", [])
        total_duration_us = 0

        # Build CapCut Material Lists
        video_materials = []
        audio_materials = []
        text_materials = []
        
        video_segments = []
        audio_voice_segments = []
        text_segments = []

        current_start_us = 0

        for scene in escenas:
            dur_sec = float(scene.get("duracion_segundos", 5.0))
            dur_us = int(dur_sec * 1_000_000)

            rel_img = scene.get("imagen_path", "")
            img_abs_path = (project_path / rel_img).resolve()

            rel_audio = scene.get("audio_path", "")
            audio_abs_path = (project_path / rel_audio).resolve()

            texto = scene.get("texto", "")

            # 1. Video / Image Material & Segment
            if img_abs_path.exists():
                img_material_id = str(uuid.uuid4())
                video_materials.append({
                  "id": img_material_id,
                  "type": "photo",
                  "path": str(img_abs_path).replace("\\", "/"),
                  "duration": dur_us,
                  "height": self.height,
                  "width": self.width
                })

                video_segments.append({
                  "id": str(uuid.uuid4()),
                  "material_id": img_material_id,
                  "target_timerange": {
                    "start": current_start_us,
                    "duration": dur_us
                  },
                  "source_timerange": {
                    "start": 0,
                    "duration": dur_us
                  },
                  "speed": 1.0,
                  "volume": 1.0
                })

            # 2. Voice Audio Material & Segment
            if audio_abs_path.exists():
                audio_material_id = str(uuid.uuid4())
                audio_materials.append({
                  "id": audio_material_id,
                  "type": "extract_music",
                  "path": str(audio_abs_path).replace("\\", "/"),
                  "duration": dur_us,
                  "name": f"Voz Escena {scene.get('numero_escena')}"
                })

                audio_voice_segments.append({
                  "id": str(uuid.uuid4()),
                  "material_id": audio_material_id,
                  "target_timerange": {
                    "start": current_start_us,
                    "duration": dur_us
                  },
                  "source_timerange": {
                    "start": 0,
                    "duration": dur_us
                  },
                  "speed": 1.0,
                  "volume": 1.0
                })

            # 3. Subtitle / Text Segment
            if texto:
                text_material_id = str(uuid.uuid4())
                text_materials.append({
                  "id": text_material_id,
                  "content": texto,
                  "type": "text"
                })

                text_segments.append({
                  "id": str(uuid.uuid4()),
                  "material_id": text_material_id,
                  "target_timerange": {
                    "start": current_start_us,
                    "duration": dur_us
                  }
                })

            current_start_us += dur_us

        total_duration_us = current_start_us

        # Build draft_content.json structure
        draft_content = {
          "canvas_config": {
            "height": self.height,
            "width": self.width,
            "ratio": self.aspect_ratio
          },
          "color_space": 0,
          "config": {
            "sample_rate": 44100
          },
          "duration": total_duration_us,
          "fps": 30.0,
          "id": str(uuid.uuid4()),
          "materials": {
            "audios": audio_materials,
            "videos": video_materials,
            "texts": text_materials
          },
          "tracks": [
            {
              "id": str(uuid.uuid4()),
              "type": "video",
              "segments": video_segments
            },
            {
              "id": str(uuid.uuid4()),
              "type": "audio",
              "segments": audio_voice_segments
            },
            {
              "id": str(uuid.uuid4()),
              "type": "text",
              "segments": text_segments
            }
          ],
          "version": 6
        }

        # Write draft_content.json
        content_json_path = dest_draft_dir / "draft_content.json"
        with open(content_json_path, "w", encoding="utf-8") as f:
            json.dump(draft_content, f, indent=2, ensure_ascii=False)

        # Write draft_meta_info.json
        now_ms = int(time.time() * 1000)
        draft_meta = {
          "draft_id": str(uuid.uuid4()),
          "draft_name": project_name,
          "draft_type": "video",
          "draft_fold_path": str(dest_draft_dir).replace("\\", "/"),
          "tm_draft_create": now_ms,
          "tm_draft_modified": now_ms,
          "duration": total_duration_us
        }

        meta_json_path = dest_draft_dir / "draft_meta_info.json"
        with open(meta_json_path, "w", encoding="utf-8") as f:
            json.dump(draft_meta, f, indent=2, ensure_ascii=False)

        logger.info(f"Borrador de CapCut generado exitosamente en: {dest_draft_dir}")
        return dest_draft_dir
