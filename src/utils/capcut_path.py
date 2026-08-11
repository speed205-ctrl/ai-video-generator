import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

def get_capcut_draft_path() -> Path:
    """
    Detects the CapCut Desktop user project draft path across C: and D: drives.
    Priority 1: Environment variable CAPCUT_DRAFT_PATH from .env.
    Priority 2: Known standard CapCut Desktop installation paths on Windows.
    """
    project_root = Path(__file__).resolve().parent.parent.parent
    load_dotenv(project_root / ".env")
    
    # Priority 1: Check .env override
    env_override = os.getenv("CAPCUT_DRAFT_PATH")
    if env_override:
        override_path = Path(env_override)
        if override_path.exists():
            logger.info(f"Ruta de borradores de CapCut leída desde .env: {override_path}")
            return override_path
        else:
            logger.warning(f"Ruta especificada en CAPCUT_DRAFT_PATH ({env_override}) no existe físicamente.")

    local_app_data = os.getenv("LOCALAPPDATA", "")
    
    # Priority 2: Standard paths on C: and D: drives
    candidate_paths = [
        Path(local_app_data) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft" if local_app_data else None,
        Path("C:/CapCut/User Data/Projects/com.lveditor.draft"),
        Path("C:/CapCut Projects/com.lveditor.draft"),
        Path("D:/CapCut/User Data/Projects/com.lveditor.draft"),
        Path("D:/CapCut/com.lveditor.draft"),
        Path("D:/CapCut Projects/com.lveditor.draft"),
        Path(os.path.expanduser("~/AppData/Local/CapCut/User Data/Projects/com.lveditor.draft"))
    ]
    
    for candidate in candidate_paths:
        if candidate and candidate.exists():
            logger.info(f"Ruta de borradores de CapCut detectada automáticamente: {candidate}")
            return candidate

    # Fallback default path if CapCut is not installed yet (will be created when exporter runs)
    default_fallback = Path(local_app_data) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft" if local_app_data else Path("C:/CapCut Projects/com.lveditor.draft")
    logger.warning(f"No se detectó instalación existente de CapCut Desktop. Usando ruta por defecto: {default_fallback}")
    return default_fallback
