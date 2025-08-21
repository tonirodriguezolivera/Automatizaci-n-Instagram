# driver/driver_manager.py
import contextvars
from typing import Optional
from appium.webdriver.webdriver import WebDriver as AppiumWebDriver

_driver_ctx: contextvars.ContextVar[Optional[AppiumWebDriver]] = contextvars.ContextVar(
    "appium_driver", default=None
)

def get_driver() -> Optional[AppiumWebDriver]:
    return _driver_ctx.get()

def set_driver(driver: AppiumWebDriver) -> None:
    if driver is not None:
        _driver_ctx.set(driver)

def unload() -> None:
    _driver_ctx.set(None)
