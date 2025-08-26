# app/core/ui.py
from __future__ import annotations
import time
from typing import Optional, Tuple
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class UI:
    def __init__(self, driver):
        self.driver = driver

    # ---------- Waiters / Finders ----------
    def find(self, by, locator, timeout: int = 10):
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((by, locator))
        )

    def visible(self, by, locator, timeout: int = 10):
        return WebDriverWait(self.driver, timeout).until(
            EC.visibility_of_element_located((by, locator))
        )

    def exists(self, by, locator, timeout: int = 3) -> bool:
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, locator))
            )
            return True
        except Exception:
            return False

    # ---------- Convenience selectors ----------
    def by_id(self, rid: str, timeout: int = 10):
        return self.find(AppiumBy.ID, rid, timeout)

    def by_text(self, text: str, partial: bool = False, timeout: int = 10):
        if partial:
            xp = f"//*[contains(@text, '{text}')]"
        else:
            xp = f"//*[@text='{text}']"
        return self.find(AppiumBy.XPATH, xp, timeout)

    def by_desc(self, desc: str, partial: bool = False, timeout: int = 10):
        if partial:
            return self.find(AppiumBy.XPATH, f"//*[contains(@content-desc,'{desc}')]", timeout)
        return self.find(AppiumBy.ACCESSIBILITY_ID, desc, timeout)

    def by_xpath(self, xp: str, timeout: int = 10):
        return self.find(AppiumBy.XPATH, xp, timeout)

    # ---------- Actions ----------
    def tap(self, el) -> None:
        el.click()

    def type(self, el, text: str, clear_first: bool = True) -> None:
        if clear_first:
            try:
                el.clear()
            except Exception:
                pass
        el.send_keys(text)

    def back(self):
        self.driver.back()

    # ---------- Gestures ----------
    def _size(self) -> Tuple[int, int]:
        size = self.driver.get_window_size()
        return size["width"], size["height"]

    def swipe(self, start_x, start_y, end_x, end_y, duration_ms: int = 400):
        # Compat: usar W3C actions si swipe no está disponible
        try:
            self.driver.swipe(start_x, start_y, end_x, end_y, duration_ms)
        except Exception:
            # Fallback con acciones W3C
            from selenium.webdriver.common.actions.pointer_input import PointerInput
            from selenium.webdriver.common.actions.action_builder import ActionBuilder
            finger = PointerInput(PointerInput.TOUCH, "finger")
            actions = ActionBuilder(self.driver, mouse=finger)
            actions.pointer_action.move_to_location(start_x, start_y)
            actions.pointer_action.pointer_down()
            actions.pointer_action.pause(duration_ms/1000.0)
            actions.pointer_action.move_to_location(end_x, end_y)
            actions.pointer_action.pointer_up()
            actions.perform()

    def swipe_up(self, factor: float = 0.75, duration_ms: int = 400):
        w, h = self._size()
        x = int(w * 0.5)
        start_y = int(h * (0.5 + factor/2))
        end_y = int(h * (0.5 - factor/2))
        self.swipe(x, start_y, x, end_y, duration_ms)

    def swipe_down(self, factor: float = 0.75, duration_ms: int = 400):
        w, h = self._size()
        x = int(w * 0.5)
        start_y = int(h * (0.5 - factor/2))
        end_y = int(h * (0.5 + factor/2))
        self.swipe(x, start_y, x, end_y, duration_ms)

    def scroll_until_text(self, text: str, max_swipes: int = 8) -> bool:
        for _ in range(max_swipes):
            if self.exists(AppiumBy.XPATH, f"//*[@text='{text}']", timeout=1):
                return True
            self.swipe_up(factor=0.65)
        return False
