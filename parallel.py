import os
import sys
import argparse
import asyncio
from datetime import datetime
from multiprocessing import Process, Queue

from adb.appium_server_manager import AppiumServerManager
import adb.emulator as Emulator
from utils.screen_recording import async_start, async_stop
from app.instagram_actions import InstagramActions
from driver.driver_factory import (
    MobilePlatformName,
    initialize_driver_emulador,
    quit_driver
)
from utils.Xls_Reader import XlsReader  # Import the XlsReader class

# ---------- Config ----------
AVD_NAMES = ["Nexus_5_API_31_Clone1", "Nexus_5_API_31_Clone2", "Nexus_5_API_31_Clone3"]
PLATFORM_VERSION = os.getenv("ANDROID_PLATFORM_VERSION", "12")
HEADLESS = os.getenv("EMU_HEADLESS", "false").lower() in {"1", "true", "yes", "y"}
NO_SNAPSHOT = os.getenv("EMU_NO_SNAPSHOT", "true").lower() in {"1", "true", "yes", "y"}
EXCEL_FILE = os.getenv("EXCEL_FILE", "cuentas_instagram.xlsx")  # Path to the Excel file
SHEET_NAME = "Sheet1"  # Name of the sheet containing user data
# ---------- Fin Config ----------

def load_users_from_excel(excel_file, sheet_name):
    """
    Loads user data from the Excel file using XlsReader.

    Args:
        excel_file (str): Path to the Excel file.
        sheet_name (str): Name of the sheet to read.

    Returns:
        list: List of dictionaries containing user data (user, password, key, new_password).
    """
    try:
        reader = XlsReader(excel_file)
        row_count = reader.get_row_count(sheet_name)
        users = []

        for row in range(2, row_count + 1):  # Start from row 2 to skip headers
            username = reader.get_cell_data(sheet_name, col_name="user", row_num=row)
            password = reader.get_cell_data(sheet_name, col_name="password", row_num=row)
            key = reader.get_cell_data(sheet_name, col_name="key", row_num=row)
            new_password = reader.get_cell_data(sheet_name, col_name="new_password", row_num=row)

            if username and password:  # Only add valid users
                users.append({
                    "user": username,
                    "password": password,
                    "key": key,
                    "new_password": new_password
                })

        print(f"Loaded {len(users)} users from {excel_file}, sheet: {sheet_name}")
        return users
    except Exception as e:
        print(f"Error loading users from Excel: {str(e)}")
        return []

async def run_instance(avd_name: str, port_offset: int, user: dict):
    """
    Runs the workflow for a specific emulator and user.

    Args:
        avd_name (str): Name of the AVD.
        port_offset (int): Offset for calculating Appium and ADB ports.
        user (dict): User data to process.
    """
    host = os.getenv("APPIUM_HOST", "127.0.0.1")
    base_port = 4723 + port_offset
    port = await AppiumServerManager.start_appium_server(host=host, port=base_port, wait_timeout=90)
    appium_url = f"http://{host}:{port}"

    adb_port = 5554 + (port_offset * 2)
    expected_udid = f"emulator-{adb_port}"

    print(f"[{avd_name}] Lanzando emulador en ADB {adb_port} (UDID: {expected_udid})")

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
        raise RuntimeError(f"No se detectó el UDID esperado {expected_udid}. Dispositivos: {devices}")

    driver = await initialize_driver_emulador(
        MobilePlatformName.ANDROID,
        avd_name,
        PLATFORM_VERSION,
        expected_udid,
        appium_url
    )

    print(f"\n[{avd_name}] Driver conectado correctamente con sesión {driver.session_id}\n")

    try:
        await async_start({"timeLimit": "120"})
        #await InstagramActions.register_account(expected_udid, user)
        video_name = f"{expected_udid}_{user['user']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        await asyncio.sleep(10)
        await async_stop(video_name)
    finally:
        await quit_driver()
        await Emulator.stop(expected_udid)
        await AppiumServerManager.stop_appium_server(host, port)
        await asyncio.sleep(30) #Time direct

async def runner_loop(avd_name: str, port_offset: int, user_queue: Queue):
    """
    Processes users from the queue for a specific AVD.

    Args:
        avd_name (str): Name of the AVD.
        port_offset (int): Offset for calculating Appium and ADB ports.
        user_queue (Queue): Queue containing user data.
    """
    while not user_queue.empty():
        user = user_queue.get()
        print(f"[{avd_name}] Procesando usuario {user['user']}")
        await run_instance(avd_name, port_offset, user)

def run_wrapper(avd_name: str, port_offset: int, user_queue: Queue):
    """
    Wrapper to run the runner_loop coroutine in a process.

    Args:
        avd_name (str): Name of the AVD.
        port_offset (int): Offset for calculating Appium and ADB ports.
        user_queue (Queue): Queue containing user data.
    """
    asyncio.run(runner_loop(avd_name, port_offset, user_queue))

def main():
    """
    Main function to run Android emulators in parallel with user data from Excel.
    """
    parser = argparse.ArgumentParser(description="Run Android emulators in parallel with user data from Excel.")
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of emulators to run in parallel (default: 1)"
    )
    args = parser.parse_args()

    # Validate the number of processes
    if args.count < 1 or args.count > len(AVD_NAMES):
        print(f"--count inválido. Debe ser entre 1 y {len(AVD_NAMES)}")
        sys.exit(1)

    # Load users from Excel
    users = load_users_from_excel(EXCEL_FILE, SHEET_NAME)
    if not users:
        print("Error: No users loaded from Excel. Exiting.")
        sys.exit(1)

    # Create a queue and populate it with users
    user_queue = Queue()
    for user in users:
        user_queue.put(user)

    selected_avds = AVD_NAMES[:args.count]
    processes = []

    # Start processes for each AVD
    for i, avd_name in enumerate(selected_avds):
        print(f"[{avd_name}] Assigned users: {[u['user'] for u in users]}")
        p = Process(target=run_wrapper, args=(avd_name, i, user_queue))
        processes.append(p)
        p.start()

    for p in processes:
        p.join()

if __name__ == "__main__":
    main()