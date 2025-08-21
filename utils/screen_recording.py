# utils/screen_recording.py
import os
import base64
import asyncio
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

from driver.driver_manager import get_driver

# Carpeta destino configurable por .env
OUT_DIR = Path(os.getenv("SCREEN_RECORDINGS_PATH", "screenrecordings"))
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _default_start_opts(platform_name: str) -> Dict[str, Any]:
    """
    Opciones por plataforma (coinciden con Appium).
    - Android: timeLimit, bitRate (Mbps*1e6), videoSize WxH
    - iOS: timeLimit, videoType (h264 / mjpeg)
    """
    if str(platform_name).lower().startswith("android"):
        return {
            "timeLimit": "180",      # segundos
            "bitRate": 4_000_000,    # 4 Mbps
            "videoSize": "720x1280",
            # "bugReport": True,     # opcional
        }
    else:
        return {
            "timeLimit": "180",
            "videoType": "h264",     # o "mjpeg"
            # "videoQuality": "medium",  # opcional
        }


def start_screen_recording(start_opts: Optional[Dict[str, Any]] = None) -> None:
    """
    Inicio sincrónico.
    """
    driver = get_driver()
    if driver is None:
        raise RuntimeError("Driver no inicializado para grabar pantalla.")

    caps = driver.capabilities or {}
    platform_name = str(caps.get("platformName", "Android"))
    opts = _default_start_opts(platform_name)
    if start_opts:
        opts.update(start_opts)

    # Appium-Python-Client: start_recording_screen(**opts)
    driver.start_recording_screen(**opts)


def stop_screen_recording(filename: str, out_dir: Optional[Path] = None) -> Path:
    """
    Detiene la grabación y guarda el MP4.
    """
    driver = get_driver()
    if driver is None:
        raise RuntimeError("Driver no inicializado para grabar pantalla.")

    b64 = driver.stop_recording_screen()  # base64
    out = (out_dir or OUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    file_path = out / (filename if filename.endswith(".mp4") else f"{filename}.mp4")

    with open(file_path, "wb") as f:
        f.write(base64.b64decode(b64))

    print(f"[ScreenRecording] guardado: {file_path}")
    return file_path


# ---------------------- Versiones asíncronas ---------------------- #

async def async_start(start_opts: Optional[Dict[str, Any]] = None) -> None:
    await asyncio.to_thread(start_screen_recording, start_opts)


async def async_stop(filename: str, out_dir: Optional[Path] = None) -> Path:
    return await asyncio.to_thread(stop_screen_recording, filename, out_dir)


# ------------------- Context manager asíncrono -------------------- #

@asynccontextmanager
async def recording(test_name: str,
                    start_opts: Optional[Dict[str, Any]] = None,
                    out_dir: Optional[Path] = None):
    """
    Uso:
    async with recording("login_test"):
        # acciones de prueba
    """
    basename = f"{test_name}_{_timestamp()}"
    try:
        await async_start(start_opts)
        yield basename  # por si quieres usar el nombre dentro del bloque
    finally:
        try:
            await async_stop(basename, out_dir)
        except Exception as e:
            print(f"[ScreenRecording] Error al guardar video: {e}")
