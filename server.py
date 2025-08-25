# =========================
# imports reales
# =========================
from multiprocessing import Process, Queue as MPQueue  # <-- FIX: MPQueue es Queue
from collections import defaultdict
from starlette import status

import os
import time
import json
import uuid
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Literal

from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from adb.appium_server_manager import AppiumServerManager
import adb.emulator as Emulator
from utils.screen_recording import async_start, async_stop
from app.instagram_actions import InstagramActions  # Acciones reales de Instagram
from driver.driver_factory import (
    MobilePlatformName,
    initialize_driver_emulador,
    quit_driver,
)
from utils.Xls_Reader import XlsReader
from db.controller import Controller
from utils.emulator_cloner import EmulatorCloner

import math



# =========================
# Setup básico
# =========================
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("runner-api")

app = FastAPI(title="Runner API (Emulators + Appium + Excel -> DB + SSE)", version="1.0.0")

allowed = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Config / ENV
# =========================
VALID_USERNAME = os.getenv("VALID_USERNAME", "spider")
VALID_PASSWORD = os.getenv("VALID_PASSWORD", "Nttspider105!")

# DB del Controller (tu estructura de ./db)
DB_PATH = os.getenv("SQLITE_DB_PATH", "./db/surviral_insta.db")
controller = Controller(DB_PATH)

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads")); UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# AVDs base / flags creación
PLATFORM_VERSION = os.getenv("ANDROID_PLATFORM_VERSION", "12")
HEADLESS = os.getenv("EMU_HEADLESS", "false").lower() in {"1", "true", "yes", "y"}
NO_SNAPSHOT = os.getenv("EMU_NO_SNAPSHOT", "true").lower() in {"1", "true", "yes", "y"}
SHEET_NAME_DEFAULT = os.getenv("SHEET_NAME", "Sheet1")

# Puertos base (ajústalos si corres múltiples jobs con distintas sesiones)
APPIUM_HOST = os.getenv("APPIUM_HOST", "127.0.0.1")
BASE_APPIUM_PORT = int(os.getenv("BASE_APPIUM_PORT", "4723"))
BASE_ADB_PORT = int(os.getenv("BASE_ADB_PORT", "5554"))

# =========================
# Estado (sesiones, SSE y jobs)
# =========================
active_sessions: Dict[str, Dict[str, Any]] = {}
event_queues: Dict[str, asyncio.Queue] = {}
running_jobs: Dict[str, asyncio.Task] = {}   # 1 job por sesión (simple y seguro)

#estado de ejecución por sesión
run_states: Dict[str, Dict[str, Any]] = {}  # sid -> {"status": "idle|running|finished|error", ...}

def get_or_init_run_state(sid: str) -> Dict[str, Any]:
    st = run_states.get(sid)
    if not st:
        st = {
            "status": "idle",         # idle | running | finished | error
            "job_id": None,
            "started_at": None,       # epoch (segundos)
            "finished_at": None,      # epoch (segundos)
            "error": None,
        }
        run_states[sid] = st
    return st

def require_session(request: Request) -> str:
    sid = request.cookies.get("session_id")
    if not sid:
        raise HTTPException(status_code=401, detail="No session cookie")
    data = active_sessions.get(sid)
    if not data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    if time.time() > data["expires_at"]:
        active_sessions.pop(sid, None)
        raise HTTPException(status_code=401, detail="Session expired")
    return sid

def get_q(sid: str) -> asyncio.Queue:
    if sid not in event_queues:
        event_queues[sid] = asyncio.Queue()
    return event_queues[sid]

async def emit(sid: str, etype: str, data: Dict[str, Any]):
    if sid in event_queues:
        await event_queues[sid].put({"type": etype, "data": data, "ts": int(time.time())})

@app.on_event("shutdown")
async def _shutdown():
    # Cierra Controller si tiene recursos abiertos
    controller.close()

# =========================
# Modelos
# =========================
class LoginRequest(BaseModel):
    username: str
    password: str

class LaunchRequest(BaseModel):
    status: Literal["Pending", "Active", "Failed", "Completed", "All"]
    job: int = Field(1, ge=1, description="Número de AVDs a ejecutar en paralelo")

class CloneManyRequest(BaseModel):
    count: int = 1

# =========================
# Helpers AVD / capacidad
# =========================
import math
from typing import List, Dict, Any

async def ensure_avd_capacity(sid: str, incoming_users: List[Dict[str, Any]]) -> List[str]:
    """
    Asegura capacidad de AVDs 'active' suficiente (5 usuarios por AVD) SOLO para los
    usuarios realmente NUEVOS que vienen en 'incoming_users' (deduplicados por 'user'
    y excluyendo los que ya existen en DB).

    Reglas:
    - Si NO hay AVDs en DB -> registrar primero los clones existentes en FS (1,2,4,5, ...)
      y SOLO si aún falta, clonar nuevos AVDs.
    - Si SÍ hay AVDs en DB -> NO registrar desde FS; solo calcular capacidad y clonar si falta.

    Devuelve la lista de NUEVOS clones creados (los registrados desde FS no se devuelven).
    """
    # -------- 0) Determinar 'required_new' considerando duplicados --------
    # Deduplicar la entrada por 'user' (conservando la primera ocurrencia)
    seen = set()
    dedup_incoming = []
    for u in incoming_users:
        uname = (u.get("user") or "").strip()
        if not uname or uname in seen:
            continue
        seen.add(uname)
        dedup_incoming.append(u)

    # Usuarios ya existentes en DB (por PK 'user')
    users_db_rows = controller.users.read_all()  # (user, password, key, new_password, avd_name, status, updated_at)
    existing_usernames = {r[0] for r in users_db_rows}

    new_incoming = [u for u in dedup_incoming if (u.get("user") or "").strip() not in existing_usernames]
    required_new = len(new_incoming)

    await emit(sid, "capacity_input", {
        "incoming_total": len(incoming_users),
        "incoming_dedup": len(dedup_incoming),
        "already_in_db": len(dedup_incoming) - required_new,
        "required_new": required_new
    })

    # Si no hay usuarios nuevos, no hace falta capacidad adicional
    if required_new <= 0:
        await emit(sid, "capacity_plan", {
            "required_users": 0,
            "current_capacity": 0,
            "phase": "no_new_users"
        })
        return []

    # -------- 1) Estado inicial de DB / uso por AVD --------
    avds_db = controller.avds.read_all()      # [(avd_name, status, ...), ...]
    # Recontar uso por AVD con TODOS los usuarios que ya existen en DB
    used_by_avd: Dict[str, int] = {}
    for r in users_db_rows:
        avd = r[4]
        if avd:
            used_by_avd[avd] = used_by_avd.get(avd, 0) + 1

    def calc_capacity(rows) -> int:
        cap = 0
        for name, status, *_ in rows:
            if (status or "").strip().lower() == "active":
                used = used_by_avd.get(name, 0)
                cap += max(0, 5 - used)
        return cap

    # -------- 2) DB vacía -> bootstrap desde FS --------
    if len(avds_db) == 0:
        await emit(sid, "capacity_plan", {
            "required_users": required_new,
            "current_capacity": 0,
            "phase": "bootstrap_fs"
        })

        try:
            await EmulatorCloner.verify_base_files()
        except Exception as e:
            await emit(sid, "avd_base_verify_error", {"error": str(e)})
            # seguimos; será el clonador quien falle si no hay base

        # Registrar TODOS los clones válidos del FS
        try:
            existing_nums = await EmulatorCloner.get_existing_clones()  # p.ej. [1,2,4,5]
        except Exception as e:
            await emit(sid, "avd_existing_scan_error", {"error": str(e)})
            existing_nums = []

        registered_from_fs: List[str] = []
        for n in existing_nums:
            name = f"{EmulatorCloner.BASE_NAME}_Clone{n}"
            avd_path = os.path.join(EmulatorCloner.AVD_DIR, name + ".avd")
            ini_path = os.path.join(EmulatorCloner.AVD_DIR, name + ".ini")
            if os.path.isdir(avd_path) and os.path.isfile(ini_path):
                try:
                    controller.create_avd(name)  # 'active'
                    registered_from_fs.append(name)
                    await emit(sid, "avd_existing_registered", {"avd_name": name})
                except Exception as e:
                    await emit(sid, "avd_existing_register_error", {"avd_name": name, "error": str(e)})
            else:
                await emit(sid, "avd_existing_skip_invalid", {"avd_name": name, "avd_path": avd_path, "ini_path": ini_path})

        # Recalcular capacidad después del bootstrap
        avds_db = controller.avds.read_all()
        capacity = calc_capacity(avds_db)

        await emit(sid, "capacity_plan", {
            "required_users": required_new,
            "current_capacity": capacity,
            "registered_from_fs": registered_from_fs,
            "phase": "after_bootstrap_fs"
        })

        if capacity >= required_new:
            return []

    else:
        # -------- 3) DB NO vacía -> NO registrar FS; solo capacidad/clone --------
        capacity = calc_capacity(avds_db)
        await emit(sid, "capacity_plan", {
            "required_users": required_new,
            "current_capacity": capacity,
            "phase": "db_only"
        })
        if capacity >= required_new:
            return []

    # -------- 4) Aún falta capacidad -> clonar y registrar --------
    deficit = required_new - capacity
    clones_needed = math.ceil(deficit / 5)  # 5 usuarios por AVD

    await emit(sid, "capacity_plan", {
        "required_users": required_new,
        "current_capacity": capacity,
        "deficit": deficit,
        "clones_needed": clones_needed,
        "phase": "cloning"
    })

    created: List[str] = []
    try:
        await EmulatorCloner.verify_base_files()
    except Exception as e:
        await emit(sid, "avd_base_verify_error", {"error": str(e)})
        raise

    for _ in range(clones_needed):
        try:
            await emit(sid, "avd_clone_started", {})
            new_name = await EmulatorCloner.clone_emulator()
            controller.create_avd(new_name)  # registrar en DB como 'active'
            created.append(new_name)
            await emit(sid, "avd_clone_finished", {"avd_name": new_name})
        except Exception as e:
            await emit(sid, "avd_clone_error", {"error": str(e)})
            # Puedes 'raise' si quieres abortar al primer fallo

    return created


def discover_avds_fs() -> List[str]:
    """
    Descubre AVDs en el FS por ~/.android/avd (complementario a los de DB).
    """
    home = Path.home() / ".android" / "avd"
    names: List[str] = []
    if home.exists():
        for p in home.glob("*.avd"):
            names.append(p.stem)
    return sorted(names)

# =========================
# Endpoints base / auth
# =========================
@app.get("/")
async def root():
    return {
        "status": "ok",
        "message": "Runner API lista",
        "db": DB_PATH,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

@app.post("/login")
async def login(body: LoginRequest, response: Response):
    if body.username != VALID_USERNAME or body.password != VALID_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    sid = str(uuid.uuid4())
    active_sessions[sid] = {
        "username": body.username,
        "created_at": time.time(),
        "expires_at": time.time() + 24 * 60 * 60,
    }
    # En producción: secure=True y SameSite=Strict/Lax
    response.set_cookie("session_id", sid, httponly=True, secure=False, max_age=24 * 60 * 60)
    return {"status": "success", "session_id": sid}

@app.get("/verify-session")
async def verify_session(request: Request):
    sid = require_session(request)
    return {"status": "valid", "session_id": sid, "username": active_sessions[sid]["username"]}

@app.post("/logout")
async def logout(request: Request, response: Response):
    sid = request.cookies.get("session_id")
    if sid:
        task = running_jobs.pop(sid, None)
        if task and not task.done():
            task.cancel()
        event_queues.pop(sid, None)
        active_sessions.pop(sid, None)
        run_states.pop(sid, None) 
    response.delete_cookie("session_id")
    return {"status": "success"}

# =========================
# SSE (eventos en tiempo real)
# =========================
@app.get("/events")
async def events(request: Request):
    sid = require_session(request)
    q = get_q(sid)

    async def gen():
        await emit(sid, "sse_open", {"message": "stream started"})
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=10.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'ping', 'data': {'ts': int(time.time())}})}\n\n"
        finally:
            await emit(sid, "sse_close", {"message": "stream closed"})

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

# =========================
# Excel -> DB (Controller) con provisión de AVDs
# =========================
@app.post("/excel/upload")
async def excel_upload(request: Request, file: UploadFile = File(...), sheet_name: str = Query(SHEET_NAME_DEFAULT)):
    sid = require_session(request)
    await emit(sid, "excel_upload_started", {"filename": file.filename, "sheet": sheet_name})

    dest = UPLOAD_DIR / f"{uuid.uuid4()}_{file.filename}"
    raw = await file.read()
    dest.write_bytes(raw)

    try:
        reader = XlsReader(str(dest))
        row_count = reader.get_row_count(sheet_name)
        users: List[Dict[str, Any]] = []
        for row in range(2, row_count + 1):
            username = reader.get_cell_data(sheet_name, col_name="user", row_num=row)
            password = reader.get_cell_data(sheet_name, col_name="password", row_num=row)
            key = reader.get_cell_data(sheet_name, col_name="key", row_num=row)
            new_password = reader.get_cell_data(sheet_name, col_name="new_password", row_num=row)
            if username and password:
                users.append({
                    "user": username,
                    "password": password,
                    "key": key,
                    "new_password": new_password
                })

        # Asegura capacidad física (clones) según la cantidad de usuarios
        if users:
            created_avds = await ensure_avd_capacity(sid, incoming_users=users)

            if created_avds:
                await emit(sid, "avd_provisioned", {"created": created_avds})

        # Asigna usuarios a AVDs mediante el Controller (crea nuevos AVDs en DB si hiciera falta)
        controller.add_users(users)

        await emit(sid, "excel_upload_finished", {"rows": len(users), "sheet": sheet_name})
        return {"status": "success", "rows": len(users), "saved_to": str(dest)}
    except Exception as e:
        await emit(sid, "excel_upload_error", {"error": str(e)})
        raise HTTPException(status_code=400, detail=f"Excel parse/load error: {e}")

# =========================
# Consultas DB (usuarios y AVDs)
# =========================
@app.get("/users")
async def list_users(request: Request):
    sid = require_session(request)
    rows = controller.get_all_users()
    users = [{
        "user": u[0],
        "password": u[1],
        "key": u[2],
        "new_password": u[3],
        "avd_name": u[4],
        "status": u[5],
        "updated_at": u[6],
    } for u in rows]
    return {"count": len(users), "users": users}

@app.get("/db/avds")
async def db_avds(request: Request):
    sid = require_session(request)
    rows = controller.avds.read_all()  # [(avd_name, status, meta?), ...]
    avds = [{"avd_name": r[0], "status": r[1], "meta": r[2] if len(r) > 2 else None} for r in rows]
    return {"count": len(avds), "avds": avds}

# Clonar un AVD (físico) y registrarlo en DB
@app.post("/db/avds/create")
async def db_avds_create(request: Request):
    sid = require_session(request)
    try:
        await EmulatorCloner.verify_base_files()
        await emit(sid, "avd_clone_started", {})
        new_name = await EmulatorCloner.clone_emulator()
        ok = controller.create_avd(new_name)
        await emit(sid, "avd_clone_finished", {"avd_name": new_name})
        return {"status": "success" if ok else "noop", "avd_name": new_name}
    except Exception as e:
        await emit(sid, "avd_clone_error", {"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Error clonando AVD: {e}")

# Clonar varios AVDs de una
@app.post("/emulators/clone")
async def emulators_clone(request: Request, body: CloneManyRequest):
    sid = require_session(request)
    await EmulatorCloner.verify_base_files()
    created: List[str] = []
    for _ in range(max(1, body.count)):
        await emit(sid, "avd_clone_started", {})
        new_name = await EmulatorCloner.clone_emulator()
        controller.create_avd(new_name)
        created.append(new_name)
        await emit(sid, "avd_clone_finished", {"avd_name": new_name})
    return {"status": "success", "created": created}

# Descubrir AVDs del FS (útil para diagnóstico)
@app.get("/emulators/available")
async def emulators_available(request: Request):
    sid = require_session(request)
    names = discover_avds_fs()
    return {"avds_fs": names}


# =========================
# Ver estado de ejecución (job) por sesión
# =========================
@app.get("/run/status")
async def run_status(request: Request):
    sid = require_session(request)
    st = get_or_init_run_state(sid)
    # opcional: enriquecer con si existe task viva
    task = running_jobs.get(sid)
    st_runtime = {
        **st,
        "task_alive": bool(task and not task.done()),
        #"task_alive": "true",

    }
    return {"status": "success", "run_state": st_runtime}

# =========================
# Lógica de ejecución con eventos
# =========================
# === Helpers: Infra por grupo (levantar/derribar una vez por AVD) ===
async def start_infra_for_group(avd_name: str, port_offset: int):
    """
    Levanta Appium + Emulador para un grupo (avd_name) en puertos derivados del offset.
    Devuelve (host, appium_port, appium_url, udid)
    """
    host = APPIUM_HOST
    appium_port = BASE_APPIUM_PORT + (port_offset * 10)   # separación segura por grupo
    adb_port    = BASE_ADB_PORT    + (port_offset * 20)   # separación segura por grupo
    expected_udid = f"emulator-{adb_port}"

    # Appium
    bound_port = await AppiumServerManager.start_appium_server(
        host=host, port=appium_port, wait_timeout=90
    )
    appium_url = f"http://{host}:{bound_port}"

    # Emulador
    log.info(f"[{avd_name}] Lanzando emulador en ADB {adb_port} (UDID: {expected_udid})")
    await Emulator.launch(
        avd_name,
        port=adb_port,
        headless=HEADLESS,
        no_snapshot=NO_SNAPSHOT,
        optimize=True
    )
    await Emulator.wait_for_ready(serial=expected_udid, timeout=300)

    devices = await Emulator.list_devices()
    if expected_udid not in devices:
        await AppiumServerManager.stop_appium_server(host, bound_port)
        raise RuntimeError(f"No se detectó el UDID esperado {expected_udid}. Dispositivos: {devices}")

    return host, bound_port, appium_url, expected_udid


async def stop_infra_for_group(host: str, appium_port: int, udid: str):
    """Cierra Emulador + Appium del grupo."""
    try:
        await Emulator.stop(udid)
        await AppiumServerManager.stop_appium_server(host, appium_port)
    except Exception as e:
        log.warning(f"[{udid}] Error cerrando infra for group: {e}")
        print(f"[{udid}] Error cerrando infra for group: {e}")
        

async def create_driver(avd_name: str, udid: str, appium_url: str):
    driver = await initialize_driver_emulador(
        MobilePlatformName.ANDROID,
        avd_name,
        PLATFORM_VERSION,
        udid,
        appium_url
    )
    log.info(f"[{avd_name}] Driver iniciado. session_id={driver.session_id}")
    return driver


async def reset_instagram_app_safely(driver):
    """
    Reset suave entre usuarios (evita cerrar sesión Appium).
    Ajusta según tu estrategia: terminate/activate o reset().
    """
    try:
        pkg = "com.instagram.android"
        await asyncio.to_thread(driver.terminate_app, pkg)
        await asyncio.sleep(1)
        await asyncio.to_thread(driver.activate_app, pkg)
        await asyncio.sleep(1)
    except Exception as e:
        log.warning(f"[reset] No se pudo reiniciar Instagram: {e}")


async def process_group_async(sid: str, avd_name: str, port_offset: int, user_list: list[dict]):
    """
    Levanta infra UNA VEZ para avd_name, procesa usuarios secuencialmente reutilizando driver,
    grabando cada ejecución por separado, y cierra al final.
    """
    await emit(sid, "avd_group_started", {"avd": avd_name, "users": len(user_list), "offset": port_offset})
    host = None
    appium_port = None
    driver = None
    try:
        # Infra única por grupo
        host, appium_port, appium_url, udid = await start_infra_for_group(avd_name, port_offset)
        await emit(sid, "avd_infra_started", {"avd": avd_name, "udid": udid, "appium_port": appium_port})

        # Driver único por grupo (reutilizable)
        driver = await create_driver(avd_name, udid, appium_url)

        for user in user_list:
            await emit(sid, "user_started", {"avd": avd_name, "user": user["user"]})

            # Reset suave entre usuarios para partir “limpio”
            await reset_instagram_app_safely(driver)

            # Grabar por usuario
            await async_start({"timeLimit": "120"})
            try:
                # Aquí va tu flujo real por usuario:
                # await InstagramActions.register_account(udid, user)
                await asyncio.sleep(5)  # Simulación de trabajo
            finally:
                video_name = f"{udid}_{user['user']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                await async_stop(video_name)

            await emit(sid, "user_finished", {"avd": avd_name, "user": user["user"], "video": video_name})

        await emit(sid, "avd_group_finished", {"avd": avd_name})
    except Exception as e:
        await emit(sid, "avd_group_error", {"avd": avd_name, "error": str(e)})
        log.exception(f"[{avd_name}] Error en el grupo: {e}")
        print(f"[{avd_name}] Error en el grupo: {e}")
    finally:
        # Cierre driver (una sola vez)
        try:
            if driver is not None:
                await quit_driver()
        except Exception as e:
            log.warning(f"[{avd_name}] Error cerrando driver: {e}")
            print(f"[{avd_name}] Error cerrando driver: {e}")

        # Cierre Emulador + Appium
        if host is not None and appium_port is not None:
            await stop_infra_for_group(host, appium_port, udid)
            await emit(sid, "avd_infra_stopped", {"avd": avd_name})

def run_group_wrapper(sid: str, avd_name: str, port_offset: int, user_list: list[dict]):
    asyncio.run(process_group_async(sid, avd_name, port_offset, user_list))

# =========================
# Lanzar ejecución por usuarios 
# =========================
@app.post("/run/launch")
async def run_launch(request: Request, body: LaunchRequest):
    """
    Ejecuta TODOS los usuarios agrupados por avd_name con un límite de
    'body.job' procesos concurrentes (estilo Pool: cuando uno termina,
    se lanza el siguiente grupo). Cada proceso levanta y reutiliza Appium+AVD
    para TODOS los usuarios de ese grupo, y cierra al finalizar.
    """
    sid = require_session(request)
    st = get_or_init_run_state(sid)

    # Protección: 1 job por sesión
    if st["status"] == "running":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya hay una ejecución en curso para esta sesión.")
    if st["status"] == "finished":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La ejecución ya se realizó para esta sesión y no se puede volver a ejecutar.")
    if st["status"] == "error":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La última ejecución terminó con error. Reinicia la sesión para volver a intentar.")

    # 1) Traer usuarios por status y agrupar por AVD
    rows = controller.get_users_by_status(body.status)
    if not rows:
        raise HTTPException(status_code=400, detail=f"No hay usuarios en la DB para el estado '{body.status}'.")

    from collections import defaultdict
    groups = defaultdict(list)  # avd_name -> [users...]
    total_users = 0
    for r in rows:  # (user, password, key, new_password, avd_name, status, updated_at)
        avd_name = r[4]
        groups[avd_name].append({
            "user": r[0],
            "password": r[1],
            "key": r[2],
            "new_password": r[3],
        })
        total_users += 1

    avd_list = sorted(groups.keys())
    if not avd_list:
        raise HTTPException(status_code=400, detail="No hay AVDs con usuarios asignados para ejecutar.")

    max_parallel = max(1, int(body.job))

    await emit(sid, "run_planned", {
        "status_filter": body.status,
        "max_parallel": max_parallel,
        "total_groups": len(avd_list),
        "total_users": total_users,
        "groups": {a: len(groups[a]) for a in avd_list},
    })

    job_id = str(uuid.uuid4())
    st.update({
        "status": "running",
        "job_id": job_id,
        "started_at": time.time(),
        "finished_at": None,
        "error": None,
    })
    await emit(sid, "run_state_changed", {"status": "running", "job_id": job_id})

    async def run_job_pool_style():
        # Cola de grupos pendientes (orden determinista)
        pending = list(avd_list)

        # Estado de procesos activos
        procs: dict[str, Process] = {}            # avd -> Process
        joins: dict[str, asyncio.Task] = {}       # avd -> join task
        offsets: dict[str, int] = {}              # avd -> port_offset libre
        free_offsets = list(range(max_parallel))  # recicla offsets 0..job-1

        async def start_next_if_possible():
            """Lanza procesos hasta agotar paralelismo o quedarnos sin pendientes."""
            started = 0
            while pending and free_offsets:
                avd = pending.pop(0)
                offset = free_offsets.pop(0)

                p = Process(
                    target=run_group_wrapper,
                    args=(sid, avd, offset, groups[avd]),
                    daemon=True
                )
                p.start()

                procs[avd] = p
                offsets[avd] = offset

                # join del proceso en background
                async def _join(proc: Process):
                    await asyncio.to_thread(proc.join)
                joins[avd] = asyncio.create_task(_join(p))

                await emit(sid, "process_started", {"avd": avd, "offset": offset, "pid": p.pid})
                started += 1
            return started

        async def wait_one_finish():
            """Espera a que termine al menos un proceso activo."""
            if not joins:
                return None
            done, _pending = await asyncio.wait(list(joins.values()), return_when=asyncio.FIRST_COMPLETED)
            # identificar cuál terminó
            finished_avd = None
            for avd, t in joins.items():
                if t in done:
                    finished_avd = avd
                    break
            return finished_avd

        try:
            # Primer “llenado” de workers
            await start_next_if_possible()

            while procs or pending:
                finished_avd = await wait_one_finish()
                if finished_avd is None:
                    break

                # Liberar recursos del que terminó
                p = procs.pop(finished_avd, None)
                joins.pop(finished_avd, None)
                off = offsets.pop(finished_avd, None)
                if off is not None:
                    free_offsets.append(off)

                await emit(sid, "process_finished", {"avd": finished_avd})

                # Inmediatamente intenta arrancar el siguiente (estilo Pool)
                await start_next_if_possible()

            # Terminado todo
            st.update({"status": "finished", "finished_at": time.time(), "error": None})
            await emit(sid, "run_state_changed", {"status": "finished", "job_id": job_id})
            await emit(sid, "run_finished", {"job_id": job_id})

        except Exception as e:
            st.update({"status": "error", "finished_at": time.time(), "error": str(e)})
            await emit(sid, "run_state_changed", {"status": "error", "job_id": job_id, "error": str(e)})
            await emit(sid, "run_error", {"job_id": job_id, "error": str(e)})
        finally:
            # Limpieza defensiva (si quedara algo vivo)
            for avd, p in list(procs.items()):
                if p.is_alive():
                    p.terminate()
                try:
                    p.join(timeout=2)
                except Exception:
                    pass

    # Dispara la orquestación (no bloquea la respuesta HTTP)
    running_jobs[sid] = asyncio.create_task(run_job_pool_style())

    return {
        "status": "scheduled",
        "job_id": job_id,
        "max_parallel": max_parallel,
        "total_groups": len(avd_list),
        "total_users": total_users,
        "note": "Pool por AVD: cada proceso reutiliza Appium+Emulador para su grupo y cierra al finalizar."
    }


# =========================
# Arranque local
# =========================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")))
