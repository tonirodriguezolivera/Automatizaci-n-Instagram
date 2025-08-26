import os
import sys
import argparse
import asyncio
from datetime import datetime
from multiprocessing import Process
from collections import defaultdict
from app.instagram_actions import InstagramActions

from adb.appium_server_manager import AppiumServerManager
import adb.emulator as Emulator
from utils.screen_recording import async_start, async_stop
# from app.instagram_actions import InstagramActions
from driver.driver_factory import (
    MobilePlatformName,
    initialize_driver_emulador,
    quit_driver
)

# ---------- Datos de prueba ----------
users = [
    {"user":"dianebutler4083","password":"9tsi3tjnc1","key":"M3NO VD76 36DM PH6M 5FKV UVPV YXF6 5JPI","new_password":"pass_nuevo2","avd_name":"Nexus_5_API_31_Clone1"},
    {"user":"sarasnyder1798","password":"6w437kb656","key":"WWQH L5BG FHLO ZDQL 3BJX PMTY EC2G LFPF","new_password":"pass_nuevo3","avd_name":"Nexus_5_API_31_Clone1"},
    {"user":"lisabarrett3952","password":"2jlvx3yar3","key":"6HSE HFCO JBVN AOTB 3MRK 6434 VDAV RKQU","new_password":"pass_nuevo4","avd_name":"Nexus_5_API_31_Clone1"},
    {"user":"rachelcarr6206","password":"4i8bh8bzm2","key":"Q5AP 77DS IVIR RGRB JV3M MRBU NV4N XUKS","new_password":"pass_nuevo5","avd_name":"Nexus_5_API_31_Clone1"},
    {"user":"nancypearson4528","password":"8eofzaosk6","key":"T5YE DPIT W43K Z56T IGV4 YFXU EFPS QJBI","new_password":"pass_nuevo6","avd_name":"Nexus_5_API_31_Clone1"},
    {"user":"angelamason4501","password":"3dkifyrll4","key":"G5B4 SEYO V7AC M7XR BQXX SRUP O4G3 P3BW","new_password":"pass_nuevo7","avd_name":"Nexus_5_API_31_Clone1"},
    {"user":"annavaldez861","password":"1sqi4s48v9","key":"FCL3 CKHK AJWT XVNR I4KY CQ2I QOBO A5FA","new_password":"pass_nuevo8","avd_name":"Nexus_5_API_31_Clone1"},
    {"user":"marthawebb1079","password":"3xglwea8h0","key":"GJCQ 7WH2 GX77 7G5H RVLX W2CS 7MRJ MAGD","new_password":"pass_nuevo9","avd_name":"Nexus_5_API_31_Clone1"},
    {"user":"dorisguerrero141","password":"36x7in1mz1","key":"LPUU VZZT U2WM FY6J 4J62 EA27 7WNB HHAA","new_password":"pass_nuevo10","avd_name":"Nexus_5_API_31_Clone1"},
    {"user":"joantran940","password":"94bxhijfm2","key":"Z6VB ZBYC TK4V HMCG KAEZ AX5M NQ6O HTRX","new_password":"pass_nuevo11","avd_name":"Nexus_5_API_31_Clone1"},
    {"user":"francesjohnston90","password":"3o5sp1zve6","key":"TIJS G65E IVFZ 3VX5 6UBG JW6I SUVV AKC7","new_password":"pass_nuevo12","avd_name":"Nexus_5_API_31_Clone1"},
    {"user":"betty3739williams","password":"8xn7ci9qr0","key":"PPS6 JETO GX7G 7YUG XCII 2WTA BCJ2 TVOQ","new_password":"pass_nuevo13","avd_name":"Nexus_5_API_31_Clone1"},
    {"user":"dorothypatterson97","password":"7w5kvhrq82","key":"Z4WO UNU2 NP7D CPA2 HJON S3HE F7GW ZJKY","new_password":"pass_nuevo14","avd_name":"Nexus_5_API_31_Clone1"},
    {"user":"emmagonzalez3111","password":"104jp46tn3","key":"A2UH TUAL 53LI TP3D TNUX VNNL 4VHL 3VJV","new_password":"pass_nuevo15","avd_name":"Nexus_5_API_31_Clone1"},
    {"user":"catherinehill5495","password":"8pjuapfmo6","key":"5P2D 6LOK EDA7 ALPR HJ46 SJQI YGGM YV5O","new_password":"pass_nuevo16","avd_name":"Nexus_5_API_31_Clone1"},
    {"user":"victoriabanks734","password":"9n5pqt0ut4","key":"43NV HAWQ 6TQN LIAL 25QL SP7Y RSEM 2GXH","new_password":"pass_nuevo17","avd_name":"Nexus_5_API_31_Clone1"},
    {"user":"bettylarson312","password":"1dqrua8wl4","key":"BFCW P7YD HM47 T2F6 EVBE RGZY 72RX UPMQ","new_password":"pass_nuevo18","avd_name":"Nexus_5_API_31_Clone1"}
]
# -------------------------------------

PLATFORM_VERSION = os.getenv("ANDROID_PLATFORM_VERSION", "12")
HEADLESS = os.getenv("EMU_HEADLESS", "false").lower() in {"1", "true", "yes", "y"}
NO_SNAPSHOT = os.getenv("EMU_NO_SNAPSHOT", "true").lower() in {"1", "true", "yes", "y"}

# Helpers infra por AVD (levantar/derribar solo una vez por grupo)
async def start_infra_for_group(avd_name: str, port_offset: int):
    host = os.getenv("APPIUM_HOST", "127.0.0.1")
    appium_port = 4723 + (port_offset * 10)   # separación por grupo
    adb_port    = 5554 + (port_offset * 20)
    expected_udid = f"emulator-{adb_port}"

    # Appium
    appium_bound_port = await AppiumServerManager.start_appium_server(
        host=host, port=appium_port, wait_timeout=90
    )
    appium_url = f"http://{host}:{appium_bound_port}"

    print(f"[{avd_name}] Lanzando emulador en ADB {adb_port} (UDID: {expected_udid})")
    # Emulador
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
        await AppiumServerManager.stop_appium_server(host, appium_bound_port)
        raise RuntimeError(f"No se detectó el UDID esperado {expected_udid}. Dispositivos: {devices}")

    return host, appium_bound_port, appium_url, expected_udid

async def stop_infra_for_group(host: str, appium_port: int, expected_udid: str):
    # Cierre ordenado del emulador y Appium
    try:
        await Emulator.stop(expected_udid)
    finally:
        await AppiumServerManager.stop_appium_server(host, appium_port)

async def create_driver(avd_name: str, udid: str, appium_url: str):
    driver = await initialize_driver_emulador(
        MobilePlatformName.ANDROID,
        avd_name,
        PLATFORM_VERSION,
        udid,
        appium_url
    )
    print(f"[{avd_name}] Driver iniciado. session_id={driver.session_id}")
    return driver

async def reset_instagram_app_safely(driver):
    """
    Opcional: limpia estado entre usuarios sin cerrar driver.
    Puedes ajustarlo según tu `initialize_driver_emulador` (noReset, fullReset, etc).
    """
    try:
        pkg = "com.instagram.android"
        await asyncio.to_thread(driver.terminate_app, pkg)
        await asyncio.sleep(1)
        await asyncio.to_thread(driver.activate_app, pkg)
        await asyncio.sleep(1)
    except Exception as e:
        print(f"[reset] No se pudo reiniciar Instagram de forma segura: {e}")

async def process_group_async(avd_name: str, port_offset: int, user_list: list[dict]):
    """
    Levanta Appium + Emulador UNA SOLA VEZ para el grupo `avd_name`.
    Reutiliza (idealmente) el mismo driver para todos los usuarios, reseteando la app entre cada uno.
    Al finalizar el grupo, cierra todo.
    """
    print(f"[{avd_name}] Iniciando grupo con {len(user_list)} usuarios…")
    host = None
    appium_port = None
    driver = None
    try:
        # Infra única por grupo
        host, appium_port, appium_url, udid = await start_infra_for_group(avd_name, port_offset)
        # Driver único por grupo (puedes re-crear por usuario si prefieres)
        driver = await create_driver(avd_name, udid, appium_url)

        for user in user_list:
            print(f"[{avd_name}] Procesando usuario {user['user']}")
            # Reset suave de la app entre usuarios (opcional/recomendado)
            await reset_instagram_app_safely(driver)

            # Grabar cada ejecución de usuario
            await async_start({"timeLimit": "120"})
            try:
                # Aquí va tu flujo real por usuario:
                await InstagramActions.register_account(udid, user)
                await asyncio.sleep(5)  # Simula trabajo real
            finally:
                video_name = f"{udid}_{user['user']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                await async_stop(video_name)

        print(f"[{avd_name}] Grupo finalizado.")
    except Exception as e:
        print(f"[{avd_name}] Error en el grupo: {e}")
    finally:
        # Cierre del driver una sola vez
        try:
            if driver is not None:
                await quit_driver()
        except Exception as e:
            print(f"[{avd_name}] Error cerrando driver: {e}")
        # Cierre de emulador + appium
        if host is not None and appium_port is not None:
            await stop_infra_for_group(host, appium_port, udid)

def run_group_wrapper(avd_name: str, port_offset: int, user_list: list[dict]):
    asyncio.run(process_group_async(avd_name, port_offset, user_list))

def group_users_by_avd(users_list: list[dict]) -> dict[str, list[dict]]:
    groups = defaultdict(list)
    for u in users_list:
        groups[u["avd_name"]].append(u)
    return groups

def main():
    parser = argparse.ArgumentParser(description="Run Android emulators grouped by AVD with users (infra per group).")
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        help="Cantidad de AVDs a ejecutar en paralelo (0 = todos)."
    )
    args = parser.parse_args()

    if not users:
        print("No hay usuarios definidos.")
        sys.exit(1)

    groups = group_users_by_avd(users)
    avd_names = list(groups.keys())
    total_groups = len(avd_names)
    if total_groups == 0:
        print("No hay grupos por AVD.")
        sys.exit(1)

    concurrency = args.count if args.count and args.count > 0 else total_groups
    concurrency = min(concurrency, total_groups)

    print(f"Procesando {len(users)} usuarios en {total_groups} grupos por AVD: {avd_names}")
    print(f"Concurrencia (AVDs en paralelo): {concurrency}")

    # Ejecutar en lotes de 'concurrency'
    batch = []
    for idx, avd_name in enumerate(avd_names):
        p = Process(target=run_group_wrapper, args=(avd_name, idx, groups[avd_name]))
        batch.append(p)

        if len(batch) == concurrency:
            for pr in batch: pr.start()
            for pr in batch: pr.join()
            batch = []

    if batch:
        for pr in batch: pr.start()
        for pr in batch: pr.join()

if __name__ == "__main__":
    main()
