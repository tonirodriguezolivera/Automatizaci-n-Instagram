# src/driver/driver_factory.py
import asyncio
from enum import Enum
from typing import Optional
from appium.webdriver.webdriver import WebDriver as AppiumWebDriver

from .drivers import (
    create_android_driver_for_native_app,
    create_android_driver_for_fisico,
    create_android_driver_for_emulator,
    create_ios_driver_for_native_app,
    create_ios_driver_for_fisico,
    create_ios_driver_for_simulador,
    DriverInitializationException,
)
from .driver_manager import set_driver, get_driver, unload

class MobilePlatformName(Enum):
    ANDROID = "ANDROID"
    IOS = "IOS"

# --------- inicializaciones equivalentes a tu Java (async) --------- #
async def initialize_driver(mobile_platform: MobilePlatformName, device_name: str, platform_version: str) -> Optional[AppiumWebDriver]:
    try:
        if mobile_platform == MobilePlatformName.ANDROID:
            driver = await create_android_driver_for_native_app(device_name, platform_version)
        elif mobile_platform == MobilePlatformName.IOS:
            driver = await create_ios_driver_for_native_app(device_name, platform_version)
        else:
            raise DriverInitializationException(f"Platform name {mobile_platform} not found.")
        set_driver(driver)
        return driver
    except DriverInitializationException as e:
        # Equivalente a Assert.fail: en async, relanzamos
        raise

async def initialize_driver_fisico(mobile_platform: MobilePlatformName, device_name: str, platform_version: str, udid: str) -> Optional[AppiumWebDriver]:
    try:
        if mobile_platform == MobilePlatformName.ANDROID:
            driver = await create_android_driver_for_fisico(device_name, platform_version, udid)
        elif mobile_platform == MobilePlatformName.IOS:
            # En tu Java llamas a createIOSDriverForNativeApp para Físico; aquí ofrezco el dedicado
            driver = await create_ios_driver_for_fisico(device_name, platform_version)
        else:
            raise DriverInitializationException(f"Platform name {mobile_platform} not found.")
        set_driver(driver)
        return driver
    except DriverInitializationException as e:
        raise

async def initialize_driver_emulador(mobile_platform: MobilePlatformName, device_name: str, platform_version: str, udid: str, appium_url: str) -> Optional[AppiumWebDriver]:
    try:
        if mobile_platform == MobilePlatformName.ANDROID:
            driver = await create_android_driver_for_emulator(device_name, platform_version, udid, appium_url)
        elif mobile_platform == MobilePlatformName.IOS:
            driver = await create_ios_driver_for_simulador(device_name, platform_version)
        else:
            raise DriverInitializationException(f"Platform name {mobile_platform} not found.")
        set_driver(driver)
        return driver
    except DriverInitializationException as e:
        raise

async def quit_driver() -> None:
    driver = get_driver()
    if driver:
        await asyncio.to_thread(driver.quit)
        unload()
