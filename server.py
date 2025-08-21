# api.py
import os
import time
import json
import uuid
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# =========================
# Tu lógica existente (imports reales)
# =========================
from adb.appium_server_manager import AppiumServerManager
import adb.emulator as Emulator
from utils.screen_recording import async_start, async_stop
from app.instagram_actions import InstagramActions  # opcional si lo usas dentro
from driver.driver_factory import (
    MobilePlatformName,
    initialize_driver_emulador,
    quit_driver,
)
from utils.Xls_Reader import XlsReader
from db.controller import Controller
from utils.emulator_cloner import EmulatorCloner
from collections import Counter
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
    # Lanza por AVDs con usuarios asignados en DB (controller)
    count: Optional[int] = None              # limita a N AVDs (según asignación en DB)
    avd_filter: Optional[List[str]] = None   # limita a AVDs específicos

class CloneManyRequest(BaseModel):
    count: int = 1

# =========================
# Helpers AVD / capacidad
# =========================
async def ensure_avd_capacity(sid: str, required_users: int) -> List[str]:
    """
    Asegura capacidad de AVDs 'active' suficiente (5 usuarios por AVD).

    Regla solicitada:
    - Si NO hay AVDs en DB -> registrar primero los clones existentes en FS (1,2,4,5, ...)
      y SOLO si aún falta, clonar nuevos AVDs.
    - Si SÍ hay AVDs en DB -> NO registrar desde FS; solo calcular capacidad y clonar si falta.

    Devuelve la lista de NUEVOS clones creados (los registrados desde FS no se devuelven).
    """
    # --- Estado inicial de DB ---
    avds_db = controller.avds.read_all()          # [(avd_name, status, ...), ...]
    users_db = controller.users.read_all()         # [(user, pass, key, new_pass, avd_name), ...]
    used_by_avd: Dict[str, int] = {}
    for u in users_db:
        avd = u[4]
        used_by_avd[avd] = used_by_avd.get(avd, 0) + 1

    def calc_capacity(rows) -> int:
        cap = 0
        for name, status, *_ in rows:
            if status == "active":
                used = used_by_avd.get(name, 0)
                cap += max(0, 5 - used)
        return cap

    # --- Caso 1: DB vacía -> bootstrap desde FS ---
    if len(avds_db) == 0:
        await emit(sid, "capacity_plan", {
            "required_users": required_users,
            "current_capacity": 0,
            "phase": "bootstrap_fs"
        })

        try:
            await EmulatorCloner.verify_base_files()
        except Exception as e:
            await emit(sid, "avd_base_verify_error", {"error": str(e)})
            # si no existe el base, no podemos registrar clones; pasaremos a clonar directamente (fallará igual)
        
        try:
            existing_nums = await EmulatorCloner.get_existing_clones()  # p.ej. [1,2,4,5]
        except Exception as e:
            await emit(sid, "avd_existing_scan_error", {"error": str(e)})
            existing_nums = []

        # Registrar TODOS los clones válidos del FS en orden numérico ascendente
        registered_from_fs: List[str] = []
        for n in existing_nums:
            name = f"{EmulatorCloner.BASE_NAME}_Clone{n}"
            avd_path = os.path.join(EmulatorCloner.AVD_DIR, name + ".avd")
            ini_path = os.path.join(EmulatorCloner.AVD_DIR, name + ".ini")

            # Validación mínima: existe directorio .avd y archivo .ini
            if os.path.isdir(avd_path) and os.path.isfile(ini_path):
                try:
                    avd_created = controller.create_avd(name)  # se registra como 'active'
                    print(f"AVD '{avd_created}' registrado desde FS.")
                    registered_from_fs.append(name)
                    await emit(sid, "avd_existing_registered", {"avd_name": name})
                except Exception as e:
                    await emit(sid, "avd_existing_register_error", {"avd_name": name, "error": str(e)})
            else:
                await emit(sid, "avd_existing_skip_invalid", {"avd_name": name, "avd_path": avd_path, "ini_path": ini_path})

        # Recalcular capacidad después del bootstrap desde FS
        avds_db = controller.avds.read_all()
        print(f"AVDs registrados desde FS: {avds_db}")
        capacity = calc_capacity(avds_db)

        await emit(sid, "capacity_plan", {
            "required_users": required_users,
            "current_capacity": capacity,
            "registered_from_fs": registered_from_fs,
            "phase": "after_bootstrap_fs"
        })

        if capacity >= required_users:
            return []  # no necesitamos clonar

    else:
        # --- Caso 2: DB NO vacía -> NO bootstrap desde FS; solo capacidad/clone ---
        capacity = calc_capacity(avds_db)
        await emit(sid, "capacity_plan", {
            "required_users": required_users,
            "current_capacity": capacity,
            "phase": "db_only"
        })
        if capacity >= required_users:
            return []

    # --- Si llegamos aquí, aún falta capacidad -> clonar físicos y registrar en DB ---
    deficit = required_users - capacity
    clones_needed = math.ceil(deficit / 5)  # 5 usuarios por AVD
    await emit(sid, "capacity_plan", {
        "required_users": required_users,
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
            # seguimos intentando crear los demás; si prefieres, puedes 'raise' aquí

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
# Lógica de ejecución con eventos (tu código adaptado)
# =========================
async def run_instance_eventful(sid: str, avd_name: str, port_offset: int, user: Dict[str, Any]):
    """
    Igual a tu run_instance pero emitiendo eventos SSE y con manejo robusto.
    """
    host = APPIUM_HOST
    base_port = BASE_APPIUM_PORT + port_offset
    adb_port = BASE_ADB_PORT + (port_offset * 2)
    expected_udid = f"emulator-{adb_port}"

    port: Optional[int] = None
    driver = None

    await emit(sid, "appium_starting", {"avd": avd_name, "base_port": base_port})
    try:
        port = await AppiumServerManager.start_appium_server(host=host, port=base_port, wait_timeout=90)
        appium_url = f"http://{host}:{port}"
        await emit(sid, "appium_started", {"port": port})
    except Exception as e:
        await emit(sid, "appium_start_error", {"error": str(e)})
        raise

    await emit(sid, "emulator_launching", {"avd": avd_name, "adb_port": adb_port, "udid": expected_udid})
    try:
        await Emulator.launch(
            avd_name,
            port=adb_port,
            headless=HEADLESS,
            no_snapshot=NO_SNAPSHOT,
            optimize=True
        )
        await Emulator.wait_for_ready(serial=expected_udid, timeout=300)
        await emit(sid, "emulator_ready", {"avd": avd_name, "udid": expected_udid})
    except Exception as e:
        await emit(sid, "emulator_launch_error", {"avd": avd_name, "error": str(e)})
        # intentar parar appium si ya arrancó
        if port:
            try:
                await AppiumServerManager.stop_appium_server(host, port)
            except Exception:
                pass
        raise

    # Validar device
    devices = await Emulator.list_devices()
    if expected_udid not in devices:
        msg = f"No se detectó el UDID esperado {expected_udid}. Dispositivos: {devices}"
        await emit(sid, "device_udid_mismatch", {"expected": expected_udid, "devices": devices})
        raise RuntimeError(msg)

    # Conectar driver
    try:
        driver = await initialize_driver_emulador(
            MobilePlatformName.ANDROID,
            avd_name,
            PLATFORM_VERSION,
            expected_udid,
            appium_url
        )
        await emit(sid, "driver_connected", {"avd": avd_name, "session_id": driver.session_id, "user": user.get("user")})
    except Exception as e:
        await emit(sid, "driver_connect_error", {"avd": avd_name, "error": str(e)})
        raise

    try:
        # Grabación
        await async_start({"timeLimit": "120"})
        # Tu flujo real (opcional):
        # await InstagramActions.register_account(expected_udid, user)
        await emit(sid, "user_processing", {"avd": avd_name, "user": user.get("user")})

        # Simulación breve (sustituye con tu lógica)
        video_name = f"{expected_udid}_{user['user']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        await asyncio.sleep(10)

        await async_stop(video_name)
        await emit(sid, "user_processed", {"avd": avd_name, "user": user.get("user"), "video": video_name})
    finally:
        # Cierre ordenado
        try:
            await quit_driver()
            await emit(sid, "driver_closed", {"avd": avd_name})
        except Exception as e:
            await emit(sid, "driver_close_error", {"avd": avd_name, "error": str(e)})
        try:
            await Emulator.stop(expected_udid)
            await emit(sid, "emulator_stopped", {"avd": avd_name, "udid": expected_udid})
        except Exception as e:
            await emit(sid, "emulator_stop_error", {"avd": avd_name, "error": str(e)})
        try:
            if port:
                await AppiumServerManager.stop_appium_server(host, port)
                await emit(sid, "appium_stopped", {"port": port})
        except Exception as e:
            await emit(sid, "appium_stop_error", {"error": str(e)})

        await asyncio.sleep(30)  # pausa como en tu script original

async def runner_loop_eventful(sid: str, avd_name: str, port_offset: int, users: List[Dict[str, Any]]):
    await emit(sid, "runner_start", {"avd": avd_name, "users": len(users)})
    for u in users:
        await emit(sid, "user_start", {"avd": avd_name, "user": u.get("user")})
        try:
            await run_instance_eventful(sid, avd_name, port_offset, u)
            await emit(sid, "user_done", {"avd": avd_name, "user": u.get("user")})
        except Exception as e:
            await emit(sid, "user_error", {"avd": avd_name, "user": u.get("user"), "error": str(e)})
    await emit(sid, "runner_done", {"avd": avd_name})

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
        job = running_jobs.pop(sid, None)
        if job and not job.done():
            job.cancel()
        event_queues.pop(sid, None)
        active_sessions.pop(sid, None)
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
            created_avds = await ensure_avd_capacity(sid, required_users=len(users))
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
    # (user, password, key, new_password, avd_name)
    users = [{"user": u[0], "password": u[1], "key": u[2], "new_password": u[3], "avd_name": u[4]} for u in rows]
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
# Lanzar ejecución por usuarios (paralelo por AVD)
# =========================
@app.post("/run/launch")
async def run_launch(request: Request, body: LaunchRequest):
    """
    Lanza emuladores para los AVDs que ya tienen usuarios asignados en la DB (Controller).
    Respeta la asignación (máx 5 usuarios por AVD). Emite eventos en tiempo real.
    Mantiene 1 job activo por sesión (una nueva llamada cancela la anterior).
    """
    sid = require_session(request)

    # 1) Agrupa usuarios por AVD, según DB
    rows = controller.get_all_users()
    if not rows:
        raise HTTPException(status_code=400, detail="No hay usuarios en la DB. Sube primero un Excel.")

    buckets_by_avd: Dict[str, List[Dict[str, Any]]] = {}
    for u in rows:
        avd_name = u[4]
        buckets_by_avd.setdefault(avd_name, []).append({
            "user": u[0], "password": u[1], "key": u[2], "new_password": u[3]
        })

    # 2) Filtrar AVDs si se solicita
    avds_all = list(buckets_by_avd.keys())
    if body.avd_filter:
        avds = [a for a in avds_all if a in set(body.avd_filter)]
    else:
        avds = avds_all

    if body.count is not None:
        avds = avds[:max(0, body.count)]

    if not avds:
        raise HTTPException(status_code=400, detail="No hay AVDs con usuarios asignados para lanzar.")

    await emit(sid, "run_planned", {
        "avds": avds,
        "buckets": {a: len(buckets_by_avd[a]) for a in avds},
        "total_users": sum(len(buckets_by_avd[a]) for a in avds)
    })

    job_id = str(uuid.uuid4())

    async def run_job():
        try:
            tasks = []
            for i, avd in enumerate(avds):
                users_for_avd = buckets_by_avd.get(avd, [])
                if not users_for_avd:
                    continue
                tasks.append(asyncio.create_task(runner_loop_eventful(sid, avd, i, users_for_avd)))
            if tasks:
                await asyncio.gather(*tasks)
            await emit(sid, "run_finished", {"job_id": job_id})
        except Exception as e:
            await emit(sid, "run_error", {"job_id": job_id, "error": str(e)})

    # 1 job activo por sesión
    old = running_jobs.get(sid)
    if old and not old.done():
        old.cancel()
    running_jobs[sid] = asyncio.create_task(run_job())

    return {"status": "scheduled", "job_id": job_id, "avds": avds}

# =========================
# Arranque local
# =========================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")))
