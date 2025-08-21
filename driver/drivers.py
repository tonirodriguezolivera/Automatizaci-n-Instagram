# src/driver/drivers.py
import os
import asyncio
from pathlib import Path
from typing import Optional

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.options.ios import XCUITestOptions

# Reemplaza este import por tu implementación real:
# from MobileBase.utils.configloader.JsonUtils import getConfig as get_config
def get_config(key: str, default: Optional[str] = "") -> str:
    """
    Stub. Reemplaza por tu getConfig real.
    """
    return os.getenv(key, default or "")

PATH_APP = str(Path(os.getcwd()) / "src" / "main" / "resources")

class DriverInitializationException(Exception):
    pass


# ------------------------- ANDROID ------------------------- #
async def create_android_driver_for_native_app(device_name: str, platform_version: str):
    """
    Sauce Labs (usa storage:filename=*.apk) + opciones comunes.
    """
    try:
        opts = UiAutomator2Options()
        opts.set_capability("platformName", "Android")
        opts.set_capability("appium:deviceName", device_name)
        opts.set_capability("appium:platformVersion", platform_version)

        # Flags desde tu JSON
        opts.set_capability("autoGrantPermissions", _as_bool(get_config("AUTO_GRANT_PERMISSIONS", "true")))
        opts.set_capability("appium:automationName", get_config("AUTOMATION_NAME", "UiAutomator2"))
        opts.set_capability("appium:orientation", get_config("ORIENTATION", "PORTRAIT"))
        opts.set_capability("appium:phoneOnly", _as_bool(get_config("PHONE_ONLY", "false")))
        opts.set_capability("appium:locationServicesAuthorized", _as_bool(get_config("LOCATION_SERVICES_AUTHORIZED", "true")))
        opts.set_capability("appium:locationServicesEnabled", _as_bool(get_config("LOCATION_SERVICES_ENABLED", "true")))
        opts.set_capability("appium:autoDismissAlerts", _as_bool(get_config("AUTO_DISMISS_ALERTS", "false")))
        opts.set_capability("appium:autoAcceptAlerts", _as_bool(get_config("AUTO_ACCEPT_ALERTS", "true")))

        app_name = get_config("APP_ANDROID")
        if app_name:
            opts.set_capability("appium:app", f"storage:filename={app_name}.apk")

        sauce = {
            "username": get_config("USER_SAUCE"),
            "accessKey": get_config("KEY_SAUCE"),
            "appiumVersion": "latest",
        }
        opts.set_capability("sauce:options", sauce)

        url = get_config("APPIUM_URL_SAUCE")
        if not url:
            raise DriverInitializationException("APPIUM_URL_SAUCE no configurado.")
        # Crear el driver en hilo para no bloquear el event loop
        driver = await asyncio.to_thread(webdriver.Remote, command_executor=url, options=opts)
        return driver
    except Exception as e:
        raise DriverInitializationException(f"Error al inicializar Android (native/sauce): {e}") from e


async def create_android_driver_for_fisico(device_name: str, platform_version: str, udid: str):
    """
    Dispositivo físico local.
    """
    try:
        opts = UiAutomator2Options()
        opts.set_capability("platformName", "Android")
        opts.set_capability("appium:deviceName", device_name)
        opts.set_capability("appium:platformVersion", platform_version)
        opts.set_capability("appium:udid", udid)
        opts.set_capability("appium:automationName", get_config("AUTOMATION_NAME", "UiAutomator2"))

        app_name = get_config("APP_ANDROID")
        app_pkg = get_config("APP_PACKAGE")
        app_act = get_config("APP_ACTIVITY")

        if app_name:
            opts.set_capability("appium:app", f"src/{app_name}.apk")
        elif app_pkg and app_act:
            opts.set_capability("appPackage", app_pkg)
            opts.set_capability("appActivity", app_act)

        opts.set_capability("autoGrantPermissions", True)
        opts.set_capability("appium:noReset", False)

        url = get_config("APPIUM_URL_LOCAL", "http://127.0.0.1:4723")
        driver = await asyncio.to_thread(webdriver.Remote, command_executor=url, options=opts)
        return driver
    except Exception as e:
        raise DriverInitializationException(f"Error al inicializar Android (físico): {e}") from e


async def create_android_driver_for_emulator(device_name: str, platform_version: str, udid: str, appium_url:str):
    """
    Emulador local.
    """
    try:
        opts = UiAutomator2Options()
        opts.set_capability("platformName", "Android")
        opts.set_capability("appium:deviceName", device_name)
        opts.set_capability("appium:platformVersion", platform_version)
        opts.set_capability("appium:udid", udid)
        opts.set_capability("appium:automationName", "UiAutomator2")

        app_name = get_config("APP_ANDROID")
        app_pkg = "com.instagram.android"  # Default package for Instagram
        app_act = ".activity.MainTabActivity"  # Default activity for Instagram

        if app_name:
            opts.set_capability("appium:app", f"apk/{app_name}.apk")
        elif app_pkg and app_act:
            opts.set_capability("appPackage", app_pkg)
            opts.set_capability("appActivity", app_act)

        opts.set_capability("autoGrantPermissions", True)

        #url = get_config("APPIUM_URL_LOCAL", "http://127.0.0.1:4723")
        driver = await asyncio.to_thread(webdriver.Remote, command_executor=appium_url, options=opts)
        return driver
    except Exception as e:
        raise DriverInitializationException(f"Error al inicializar Android (emulador): {e}") from e


# --------------------------- iOS --------------------------- #
async def create_ios_driver_for_native_app(device_name: str, platform_version: str):
    """
    iOS en Sauce Labs (app en storage:filename=*.ipa).
    """
    try:
        opts = XCUITestOptions()
        opts.set_capability("platformName", "iOS")
        opts.set_capability("appium:deviceName", device_name)
        opts.set_capability("appium:platformVersion", platform_version)

        opts.set_capability("appium:newCommandTimeout", _as_int(get_config("NEW_COMMAND_TIMEOUT", "120")))
        opts.set_capability("appium:autoAcceptAlerts", _as_bool(get_config("AUTO_ACCEPT_ALERTS", "true")))
        opts.set_capability("appium:locationServicesEnabled", _as_bool(get_config("LOCATION_SERVICES_ENABLED", "true")))
        opts.set_capability("appium:gpsEnabled", True)
        opts.set_capability("updateIosDeviceSettings", '{"LocationServicesEnabled":true}')
        opts.set_capability("appium:locationServicesAuthorized", _as_bool(get_config("LOCATION_SERVICES_AUTHORIZED", "true")))
        opts.set_capability("appium:automationName", get_config("AUTOMATION_NAME_IOS", "XCUITest"))
        opts.set_capability("sauce:orientation", get_config("ORIENTATION", "PORTRAIT"))
        opts.set_capability("appium:phoneOnly", _as_bool(get_config("PHONE_ONLY", "false")))
        opts.set_capability("appium:wdaEventloopIdleDelay", 5)

        app_name = get_config("APP_IOS")
        if app_name:
            opts.set_capability("appium:app", f"storage:filename={app_name}.ipa")

        sauce = {
            "username": get_config("USER_SAUCE"),
            "accessKey": get_config("KEY_SAUCE"),
            "appiumVersion": "latest",
        }
        opts.set_capability("sauce:options", sauce)

        url = get_config("APPIUM_URL_SAUCE")
        if not url:
            raise DriverInitializationException("APPIUM_URL_SAUCE no configurado.")
        driver = await asyncio.to_thread(webdriver.Remote, command_executor=url, options=opts)
        return driver
    except Exception as e:
        raise DriverInitializationException(f"Error al inicializar iOS (native/sauce): {e}") from e


async def create_ios_driver_for_fisico(device_udid: str, platform_version: str):
    """
    iOS físico local (nota: requiere configuración de WebDriverAgent, certificados, etc.).
    """
    try:
        opts = XCUITestOptions()
        opts.set_capability("platformName", "iOS")
        opts.set_capability("appium:udid", device_udid)
        opts.set_capability("appium:platformVersion", platform_version)

        opts.set_capability("appium:newCommandTimeout", _as_int(get_config("NEW_COMMAND_TIMEOUT", "120")))
        opts.set_capability("appium:autoAcceptAlerts", _as_bool(get_config("AUTO_ACCEPT_ALERTS", "true")))
        opts.set_capability("appium:locationServicesEnabled", _as_bool(get_config("LOCATION_SERVICES_ENABLED", "true")))
        opts.set_capability("appium:gpsEnabled", True)
        opts.set_capability("updateIosDeviceSettings", '{"LocationServicesEnabled":true}')
        opts.set_capability("appium:locationServicesAuthorized", _as_bool(get_config("LOCATION_SERVICES_AUTHORIZED", "true")))
        opts.set_capability("appium:automationName", get_config("AUTOMATION_NAME_IOS", "XCUITest"))
        opts.set_capability("appium:xcodeSinginId", "iPhone Developer")  # igual a tu Java (ojo: puede ser xcodeSigningId)
        opts.set_capability("appium:phoneOnly", _as_bool(get_config("PHONE_ONLY", "false")))
        opts.set_capability("appium:wdaEventloopIdleDelay", 5)

        app_ios = get_config("APP_IOS")
        bundle_id = get_config("BUNDLE_ID")
        if app_ios:
            opts.set_capability("appium:app", f"apk/{app_ios}.ipa")
        elif bundle_id:
            opts.set_capability("appium:bundleId", bundle_id)

        url = get_config("APPIUM_URL_LOCAL", "http://127.0.0.1:4723")
        driver = await asyncio.to_thread(webdriver.Remote, command_executor=url, options=opts)
        return driver
    except Exception as e:
        raise DriverInitializationException(f"Error al inicializar iOS (físico): {e}") from e


async def create_ios_driver_for_simulador(device_name: str, platform_version: str):
    """
    iOS simulador local.
    """
    try:
        opts = XCUITestOptions()
        opts.set_capability("platformName", "iOS")
        opts.set_capability("appium:deviceName", device_name)
        opts.set_capability("appium:platformVersion", platform_version)

        opts.set_capability("appium:newCommandTimeout", _as_int(get_config("NEW_COMMAND_TIMEOUT", "120")))
        opts.set_capability("appium:autoAcceptAlerts", _as_bool(get_config("AUTO_ACCEPT_ALERTS", "true")))
        opts.set_capability("appium:locationServicesEnabled", _as_bool(get_config("LOCATION_SERVICES_ENABLED", "true")))
        opts.set_capability("appium:gpsEnabled", True)
        opts.set_capability("updateIosDeviceSettings", '{"LocationServicesEnabled":true}')
        opts.set_capability("appium:locationServicesAuthorized", _as_bool(get_config("LOCATION_SERVICES_AUTHORIZED", "true")))
        opts.set_capability("appium:automationName", get_config("AUTOMATION_NAME_IOS", "XCUITest"))
        opts.set_capability("appium:phoneOnly", _as_bool(get_config("PHONE_ONLY", "false")))
        opts.set_capability("appium:wdaEventloopIdleDelay", 5)

        app_ios = get_config("APP_IOS")
        bundle_id = get_config("BUNDLE_ID")
        if app_ios:
            opts.set_capability("appium:app", str(Path(PATH_APP) / f"{app_ios}.ipa"))
        elif bundle_id:
            opts.set_capability("appium:bundleId", bundle_id)

        url = get_config("APPIUM_URL_LOCAL", "http://127.0.0.1:4723")
        driver = await asyncio.to_thread(webdriver.Remote, command_executor=url, options=opts)
        return driver
    except Exception as e:
        raise DriverInitializationException(f"Error al inicializar iOS (simulador): {e}") from e


# ------------------------- helpers ------------------------- #
def _as_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

def _as_int(value: str, default: int = 60) -> int:
    try:
        return int(value)
    except Exception:
        return default
