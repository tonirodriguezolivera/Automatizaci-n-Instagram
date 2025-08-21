import os
import sys
import asyncio
import shlex
from pathlib import Path
from typing import Optional, List
import socket

def _default_sdk() -> str:
    if os.getenv("ANDROID_SDK_ROOT"):
        return os.getenv("ANDROID_SDK_ROOT")  # confiar en el entorno
    if os.name == "nt":
        return os.path.expanduser(r"~\AppData\Local\Android\Sdk")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Android/sdk")
    # Linux (Ubuntu)
    return "/home/customer/Documents/Android/Sdk"

SDK_PATH = os.getenv("ANDROID_SDK_ROOT") or _default_sdk()
ADB_PATH = str(Path(SDK_PATH) / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb"))
EMULATOR_BIN = str(Path(SDK_PATH) / "emulator" / ("emulator.exe" if os.name == "nt" else "emulator"))

def _is_port_free(host: str, port: int) -> bool:
    """Verifica si un puerto está libre en el host especificado."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex((host, port)) != 0

async def _run(cmd: List[str], timeout: Optional[int] = None) -> asyncio.subprocess.Process:
    """
    Ejecuta comando como subproceso asíncrono y retorna el proceso ya finalizado
    junto con stdout/stderr decodificados.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise
    proc.stdout_text = (stdout or b"").decode(errors="ignore")
    proc.stderr_text = (stderr or b"").decode(errors="ignore")
    return proc

async def list_devices() -> List[str]:
    """
    Devuelve lista de seriales en estado 'device' usando `adb devices`.
    """
    if not Path(ADB_PATH).exists():
        return []
    proc = await _run([ADB_PATH, "devices"], timeout=15)
    devices: List[str] = []
    lines = proc.stdout_text.splitlines()[1:]  # saltar encabezado
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices

async def is_any_running_devices() -> bool:
    """
    True si existe al menos un dispositivo en estado 'device'.
    """
    print("Checking attached devices ...")
    running = len(await list_devices()) > 0
    if running:
        print("El dispositivo ya está conectado. Apague antes de comenzar las pruebas.")
    return running

async def first_emulator_serial() -> Optional[str]:
    """
    Devuelve el primer serial que luzca como 'emulator-XXXX', si existe.
    """
    for s in await list_devices():
        if s.startswith("emulator-"):
            return s
    return None

async def launch(
    avd_name: str,
    port: Optional[int] = None,
    headless: bool = False,
    wipe_data: bool = False,
    no_snapshot: bool = True,
    extra_args: Optional[List[str]] = None,
    optimize: bool = True
) -> None:
    """
    Lanza un AVD por nombre en un puerto ADB específico. Si no se proporciona puerto,
    busca uno libre comenzando desde 5554. Falla si el puerto está ocupado o si hay
    dispositivos conectados.
    """
    if await is_any_running_devices():
        raise RuntimeError("Ya existe un dispositivo en ejecución. Deténlo antes de iniciar el emulador.")

    if not Path(EMULATOR_BIN).exists():
        raise FileNotFoundError(f"No se encontró el binario del emulador: {EMULATOR_BIN}")

    # Si no se proporciona puerto, buscar uno libre desde 5554
    if port is None:
        port = 5554
        max_tries = 50
        while not _is_port_free("127.0.0.1", port) and max_tries > 0:
            port += 2  # Los puertos ADB avanzan de 2 en 2
            max_tries -= 1
        if max_tries == 0:
            raise RuntimeError(f"No se encontró un puerto ADB libre para {avd_name} comenzando desde 5554")

    # Verificar que el puerto esté libre
    if not _is_port_free("127.0.0.1", port):
        raise RuntimeError(f"El puerto ADB {port} ya está en uso para {avd_name}")

    print(f"Starting emulator for '{avd_name}' on ADB port {port} (expected UDID: emulator-{port})...")
    cmd = [EMULATOR_BIN, "-avd", avd_name]
    cmd += ["-port", str(port)]
    if headless:
        cmd += ["-no-window"]
    if wipe_data:
        cmd += ["-wipe-data"]
    if no_snapshot:
        cmd += ["-no-snapshot"]
    if optimize:
        cmd += [
            "-no-boot-anim",
            "-no-audio",
            "-gpu", "swiftshader_indirect",
        ]
    if extra_args:
        cmd += extra_args
    
    # Lanzar emulador en background
    await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.STDOUT)
    await asyncio.sleep(3)
    print(f"Emulator for '{avd_name}' launched successfully on port {port}!")

async def _adb_shell(serial: Optional[str], args: List[str], timeout: int = 10) -> str:
    base = [ADB_PATH]
    if serial:
        base += ["-s", serial]
    base += ["shell"] + args
    proc = await _run(base, timeout=timeout)
    return (proc.stdout_text or "").strip()

async def wait_for_ready(serial: Optional[str] = None, timeout: int = 300) -> None:
    """
    Espera a que el emulador esté listo (dev.bootcomplete == 1 y init.svc.bootanim == stopped).
    Si no se pasa serial, detecta el primer 'emulator-*' en ~60s.
    """
    print(f"Checking emulator boot status for serial {serial or 'any'}...")
    
    # Detectar serial si no se provee
    detected = serial
    end_detect = asyncio.get_event_loop().time() + 60
    while not detected and asyncio.get_event_loop().time() < end_detect:
        detected = await first_emulator_serial()
        if not detected:
            await asyncio.sleep(2)
    serial = detected
    if not serial:
        raise RuntimeError("No se detectó un serial de emulador (emulator-XXXX).")

    # Esperar dev.bootcomplete == 1
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        try:
            val = await _adb_shell(serial, ["getprop", "dev.bootcomplete"])
            if val == "1":
                break
        except Exception:
            pass
        await asyncio.sleep(2)
    else:
        raise asyncio.TimeoutError(f"Timeout esperando dev.bootcomplete == 1 para {serial}")

    # Esperar bootanim detenido
    end2 = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end2:
        try:
            val = await _adb_shell(serial, ["getprop", "init.svc.bootanim"])
            if val == "stopped":
                print(f"Emulator {serial} is ready to use!")
                return
        except Exception:
            pass
        await asyncio.sleep(3)

    raise asyncio.TimeoutError(f"Timeout esperando init.svc.bootanim == stopped para {serial}")

async def stop(serial: Optional[str] = None) -> None:
    """
    Envía 'adb emu kill'. Si no se pasa serial:
     - Si hay un único emulador-*, lo usa.
     - Si hay varios, usa el primero encontrado.
    """
    print(f"Killing emulator {serial or 'any'}...")
    if not serial:
        serial = await first_emulator_serial()

    base = [ADB_PATH]
    if serial:
        base += ["-s", serial]
    base += ["emu", "kill"]

    try:
        proc = await _run(base, timeout=10)
        if proc.returncode == 0:
            print(f"Emulator {serial or 'any'} closed successfully!")
        else:
            print(f"Advertencia: emu kill rc={proc.returncode}, intentando poweroff...")
            base2 = [ADB_PATH] + (["-s", serial] if serial else []) + ["reboot", "-p"]
            await _run(base2, timeout=10)
    except Exception as e:
        print(f"[Emulator] Error al cerrar emulador {serial or 'any'}: {e}")
