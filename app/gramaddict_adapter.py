# app/gramaddict_adapter.py
from typing import List, Tuple
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from app.core.ui import UI

def _split_union(s: str) -> List[str]:
    return [p.strip() for p in s.split("|") if p.strip()]

class _Matcher:
    def __init__(self, ui: UI, by, locator):
        self.ui = ui
        self.by = by
        self.locator = locator

    def exists(self, timeout: int = 2) -> bool:
        return self.ui.exists(self.by, self.locator, timeout=timeout)

    def get(self, timeout: int = 10):
        return self.ui.find(self.by, self.locator, timeout=timeout)

    def click(self, timeout: int = 10):
        el = self.get(timeout)
        self.ui.tap(el)

    def type(self, text: str, clear_first: bool = True, timeout: int = 10):
        el = self.get(timeout)
        self.ui.type(el, text, clear_first=clear_first)

class _AnyMatcher:
    """Soporta múltiples (by, locator); devuelve el primero que aparezca."""
    def __init__(self, ui: UI, candidates: List[Tuple[str, str]]):
        self.ui = ui
        self.candidates = candidates

    def exists(self, timeout: int = 2) -> bool:
        try:
            self.get(timeout=timeout)
            return True
        except Exception:
            return False

    def get(self, timeout: int = 10):
        end = UI.__dict__.get  # micro-opt
        import time
        deadline = time.time() + timeout
        last_err = None
        while time.time() < deadline:
            for by, loc in self.candidates:
                try:
                    return self.ui.find(by, loc, timeout=1)
                except Exception as e:
                    last_err = e
            time.sleep(0.2)
        raise last_err or TimeoutError("Elemento no encontrado en _AnyMatcher")

    def click(self, timeout: int = 10):
        el = self.get(timeout)
        self.ui.tap(el)

    def type(self, text: str, clear_first: bool = True, timeout: int = 10):
        el = self.get(timeout)
        self.ui.type(el, text, clear_first=clear_first)

class GA:
    """
    Adapter estilo GramAddict:
      GA.text("Iniciar sesión").click()
      GA.id("com.instagram.android:id/username").type("kevin")
      GA.id_any("a|b|c").click()
      GA.class_name_any("android.widget.Button|android.widget.TextView").exists()
    """
    def __init__(self, driver):
        self.ui = UI(driver)

    # ---- Single ----
    def text(self, t: str, partial: bool = False) -> _Matcher:
        from appium.webdriver.common.appiumby import AppiumBy
        if partial:
            return _Matcher(self.ui, AppiumBy.XPATH, f"//*[contains(@text,'{t}')]")
        return _Matcher(self.ui, AppiumBy.XPATH, f"//*[@text='{t}']")

    def id(self, rid: str) -> _Matcher:
        return _Matcher(self.ui, AppiumBy.ID, rid)

    def desc(self, d: str, partial: bool = False) -> _Matcher:
        from appium.webdriver.common.appiumby import AppiumBy
        if partial:
            return _Matcher(self.ui, AppiumBy.XPATH, f"//*[contains(@content-desc,'{d}')]")
        return _Matcher(self.ui, AppiumBy.ACCESSIBILITY_ID, d)

    def xpath(self, xp: str) -> _Matcher:
        return _Matcher(self.ui, AppiumBy.XPATH, xp)

    def class_name(self, cls: str) -> _Matcher:
        return _Matcher(self.ui, AppiumBy.CLASS_NAME, cls)

    # ---- Any/Union ----
    def id_any(self, rid_union: str) -> _AnyMatcher:
        ids = _split_union(rid_union)
        return _AnyMatcher(self.ui, [(AppiumBy.ID, r) for r in ids])

    def text_any(self, text_union: str, partial: bool = False) -> _AnyMatcher:
        txts = _split_union(text_union)
        if partial:
            locs = [(AppiumBy.XPATH, f"//*[contains(@text,'{t}')]") for t in txts]
        else:
            locs = [(AppiumBy.XPATH, f"//*[@text='{t}']") for t in txts]
        return _AnyMatcher(self.ui, locs)

    def desc_any(self, desc_union: str, partial: bool = False) -> _AnyMatcher:
        descs = _split_union(desc_union)
        if partial:
            locs = [(AppiumBy.XPATH, f"//*[contains(@content-desc,'{d}')]") for d in descs]
        else:
            locs = [(AppiumBy.ACCESSIBILITY_ID, d) for d in descs]
        return _AnyMatcher(self.ui, locs)

    def class_name_any(self, cls_union: str) -> _AnyMatcher:
        clss = _split_union(cls_union)
        return _AnyMatcher(self.ui, [(AppiumBy.CLASS_NAME, c) for c in clss])

    # ---- Helpers extra ----
    def scroll_until_text(self, text: str, max_swipes: int = 8) -> bool:
        return self.ui.scroll_until_text(text, max_swipes=max_swipes)

    def back(self):
        self.ui.back()
