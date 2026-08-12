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

                efecto = (scene.get("efecto_capcut") or "Zoom in").lower()
                scale_start, scale_end = 1.0, 1.18
                pos_x_start, pos_x_end = 0.0, 0.0

                if "out" in efecto:
                    scale_start, scale_end = 1.18, 1.0
                elif "right" in efecto or "derecha" in efecto:
                    scale_start, scale_end = 1.10, 1.10
                    pos_x_start, pos_x_end = -0.05, 0.05
                elif "left" in efecto or "izquierda" in efecto:
                    scale_start, scale_end = 1.10, 1.10
                    pos_x_start, pos_x_end = 0.05, -0.05

                keyframes_data = [
                    {
                        "id": str(uuid.uuid4()),
                        "keyframe_list": [
                            {
                                "curve_type": "Line",
                                "graph_values": "",
                                "id": str(uuid.uuid4()),
                                "left_control": {"x": 0.0, "y": 0.0},
                                "right_control": {"x": 0.0, "y": 0.0},
                                "time": 0,
                                "values": [scale_start, scale_start]
                            },
                            {
                                "curve_type": "Line",
                                "graph_values": "",
                                "id": str(uuid.uuid4()),
                                "left_control": {"x": 0.0, "y": 0.0},
                                "right_control": {"x": 0.0, "y": 0.0},
                                "time": dur_us,
                                "values": [scale_end, scale_end]
                            }
                        ],
                        "property_type": "KFTypeScale"
                    }
                ]

                if pos_x_start != 0.0 or pos_x_end != 0.0:
                    keyframes_data.append({
                        "id": str(uuid.uuid4()),
                        "keyframe_list": [
                            {
                                "curve_type": "Line",
                                "graph_values": "",
                                "id": str(uuid.uuid4()),
                                "left_control": {"x": 0.0, "y": 0.0},
                                "right_control": {"x": 0.0, "y": 0.0},
                                "time": 0,
                                "values": [pos_x_start, 0.0]
                            },
                            {
                                "curve_type": "Line",
                                "graph_values": "",
                                "id": str(uuid.uuid4()),
                                "left_control": {"x": 0.0, "y": 0.0},
                                "right_control": {"x": 0.0, "y": 0.0},
                                "time": dur_us,
                                "values": [pos_x_end, 0.0]
                            }
                        ],
                        "property_type": "KFTypePosition"
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
                  "volume": 1.0,
                  "common_keyframes": keyframes_data
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

        total_duration_us = current_start_us

        # Find existing working draft in draft_root to borrow platform signature and aux files
        platform_info = {
            "app_id": 359289,
            "app_source": "cc",
            "app_version": "9.2.0",
            "device_id": "603faa1d03041028245f4d76b9f29f8b",
            "hard_disk_id": "acef84cb619c3179848b5a24e8805ccf",
            "mac_address": "7efd53088f00527caa08c2c6a69ab070,70dc91fdcb9666db909caa07e6077ded",
            "os": "windows",
            "os_version": "10.0.19045"
        }

        template_draft_dir = None
        for candidate_folder in draft_root.iterdir():
            if candidate_folder.is_dir() and candidate_folder.name != project_name:
                content_file = candidate_folder / "draft_content.json"
                if content_file.exists():
                    try:
                        with open(content_file, "r", encoding="utf-8") as pf:
                            data = json.load(pf)
                            if "platform" in data and data["platform"]:
                                platform_info = data["platform"]
                                template_draft_dir = candidate_folder
                                break
                    except Exception:
                        pass

        # Build draft_content.json structure matching CapCut 9+ native schema
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
          "id": str(uuid.uuid4()).upper(),
          "materials": {
            "audios": audio_materials,
            "videos": video_materials,
            "texts": text_materials
          },
          "tracks": [
            {
              "id": str(uuid.uuid4()).upper(),
              "type": "video",
              "segments": video_segments
            },
            {
              "id": str(uuid.uuid4()).upper(),
              "type": "audio",
              "segments": audio_voice_segments
            },
            {
              "id": str(uuid.uuid4()).upper(),
              "type": "text",
              "segments": text_segments
            }
          ],
          "version": 360000,
          "new_version": "181.0.0",
          "platform": platform_info,
          "last_modified_platform": platform_info
        }

        # Write draft_content.json
        content_json_path = dest_draft_dir / "draft_content.json"
        with open(content_json_path, "w", encoding="utf-8") as f:
            json.dump(draft_content, f, indent=2, ensure_ascii=False)

        # Copy auxiliary JSON files from template draft if available
        if template_draft_dir and template_draft_dir.exists():
            aux_files = [
                "attachment_pc_common.json", "draft_agency_config.json",
                "draft_agency_info.json", "draft_biz_config.json",
                "draft_virtual_store.json", "key_value.json",
                "performance_opt_info.json", "timeline_layout.json", "draft.extra"
            ]
            import shutil
            for aux_name in aux_files:
                src_aux = template_draft_dir / aux_name
                dst_aux = dest_draft_dir / aux_name
                if src_aux.exists() and not dst_aux.exists():
                    try:
                        shutil.copy2(src_aux, dst_aux)
                    except Exception:
                        pass

        # Write draft_meta_info.json matching CapCut Desktop native format
        now_us = int(time.time() * 1_000_000)
        win_draft_root = str(draft_root).replace("/", "\\")
        win_dest_dir = str(dest_draft_dir).replace("/", "\\")
        
        draft_meta = {
          "cloud_draft_cover": False,
          "cloud_draft_sync": False,
          "cloud_package_completed_time": "",
          "draft_cloud_capcut_purchase_info": "",
          "draft_cloud_last_action_download": False,
          "draft_cloud_package_type": "",
          "draft_cloud_purchase_info": "",
          "draft_cloud_template_id": "",
          "draft_cloud_tutorial_info": "",
          "draft_cloud_videocut_purchase_info": "",
          "draft_cover": "draft_cover.jpg",
          "draft_deeplink_url": "",
          "draft_enterprise_info": {
            "draft_enterprise_extra": "",
            "draft_enterprise_id": "",
            "draft_enterprise_name": "",
            "enterprise_material": []
          },
          "draft_fold_path": win_dest_dir,
          "draft_id": str(uuid.uuid4()).upper(),
          "draft_is_ae_produce": False,
          "draft_is_ai_packaging_used": False,
          "draft_is_ai_shorts": False,
          "draft_is_ai_translate": False,
          "draft_is_article_video_draft": False,
          "draft_is_cloud_temp_draft": False,
          "draft_is_from_deeplink": "false",
          "draft_is_invisible": False,
          "draft_is_pippit_draft": False,
          "draft_is_web_article_video": False,
          "draft_materials": [],
          "draft_materials_copied_info": [],
          "draft_name": project_name,
          "draft_need_rename_folder": False,
          "draft_new_version": "",
          "draft_removable_storage_device": "",
          "draft_root_path": win_draft_root,
          "draft_segment_extra_info": [],
          "draft_timeline_materials_size_": os.path.getsize(content_json_path) if content_json_path.exists() else 10000,
          "draft_type": "",
          "draft_web_article_video_enter_from": "",
          "pippit_avatar_url": "",
          "pippit_extra_info": "",
          "pippit_id": "",
          "pippit_user_name": "",
          "tm_draft_cloud_completed": "",
          "tm_draft_cloud_entry_id": -1,
          "tm_draft_cloud_modified": 0,
          "tm_draft_cloud_parent_entry_id": -1,
          "tm_draft_cloud_space_id": -1,
          "tm_draft_cloud_user_id": -1,
          "tm_draft_create": now_us,
          "tm_draft_modified": now_us,
          "tm_draft_removed": 0,
          "tm_duration": total_duration_us
        }

        meta_json_path = dest_draft_dir / "draft_meta_info.json"
        with open(meta_json_path, "w", encoding="utf-8") as f:
            json.dump(draft_meta, f, indent=2, ensure_ascii=False)

        # Update root_meta_info.json so CapCut Desktop indexes the draft on its home screen
        root_meta_file = draft_root / "root_meta_info.json"
        if root_meta_file.exists():
            try:
                with open(root_meta_file, "r", encoding="utf-8") as f:
                    root_meta = json.load(f)
                
                store = root_meta.get("all_draft_store", [])
                existing = False
                for item in store:
                    if item.get("draft_fold_path", "").replace("/", "\\").lower() == win_dest_dir.lower():
                        existing = True
                        item["draft_root_path"] = win_draft_root
                        item["draft_fold_path"] = win_dest_dir
                        item["draft_json_file"] = f"{win_dest_dir}\\draft_content.json"
                        item["draft_cover"] = f"{win_dest_dir}\\draft_cover.jpg"
                        item["tm_draft_modified"] = now_us
                        item["tm_duration"] = total_duration_us
                        break
                
                if not existing:
                    new_entry = {
                        "cloud_draft_cover": False,
                        "cloud_draft_sync": False,
                        "draft_cloud_last_action_download": False,
                        "draft_cloud_purchase_info": "",
                        "draft_cloud_template_id": "",
                        "draft_cloud_tutorial_info": "",
                        "draft_cloud_videocut_purchase_info": "",
                        "draft_cover": f"{win_dest_dir}\\draft_cover.jpg",
                        "draft_fold_path": win_dest_dir,
                        "draft_id": str(uuid.uuid4()).upper(),
                        "draft_is_ai_shorts": False,
                        "draft_is_cloud_temp_draft": False,
                        "draft_is_invisible": False,
                        "draft_is_pippit_draft": False,
                        "draft_is_web_article_video": False,
                        "draft_json_file": f"{win_dest_dir}\\draft_content.json",
                        "draft_name": project_name,
                        "draft_new_version": "",
                        "draft_root_path": win_draft_root,
                        "draft_timeline_materials_size": os.path.getsize(content_json_path) if content_json_path.exists() else 10000,
                        "draft_type": "",
                        "draft_web_article_video_enter_from": "",
                        "pippit_avatar_url": "",
                        "pippit_extra_info": "",
                        "pippit_id": "",
                        "pippit_user_name": "",
                        "streaming_edit_draft_ready": True,
                        "tm_draft_cloud_completed": "",
                        "tm_draft_cloud_entry_id": -1,
                        "tm_draft_cloud_modified": 0,
                        "tm_draft_cloud_parent_entry_id": -1,
                        "tm_draft_cloud_space_id": -1,
                        "tm_draft_cloud_user_id": -1,
                        "tm_draft_create": now_us,
                        "tm_draft_modified": now_us,
                        "tm_draft_removed": 0,
                        "tm_duration": total_duration_us
                    }
                    store.insert(0, new_entry)
                
                root_meta["all_draft_store"] = store
                with open(root_meta_file, "w", encoding="utf-8") as f:
                    json.dump(root_meta, f, indent=2, ensure_ascii=False)
                logger.info("Registrado exitosamente en root_meta_info.json de CapCut Desktop.")
            except Exception as root_err:
                logger.warning(f"No se pudo actualizar root_meta_info.json: {root_err}")

        logger.info(f"Borrador de CapCut generado exitosamente en: {dest_draft_dir}")
        return dest_draft_dir
