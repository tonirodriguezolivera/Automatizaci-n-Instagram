# app/flows/home_scroll_flow.py
from __future__ import annotations
import time
from typing import Optional

from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from app.core.ui import UI
from app.gramaddict_adapter import GA
from app.flows.navigation import NavigationFlow
from app.utils.instagram_selectors import IG_APP_ID, ResourceID


class HomeScrollFlow:
    """
    Scrollea el feed de Home N veces (por defecto 30).
      - Va a Home
      - Hace swipe up del centro-inferior al centro-superior
      - Registra logs de cada paso
      - Corta si detecta "You're all caught up" / "Estás al día"
    """

    # Pistas visuales / ids útiles
    CAUGHT_UP_HINTS = (
        "you're all caught up", "estás al día", "ya estás al día",
        "no hay publicaciones nuevas", "all caught up"
    )

    def __init__(self, driver):
        self.driver = driver
        self.ui = UI(driver)
        self.ga = GA(driver)
        self.rids = ResourceID(IG_APP_ID)
        print("[HomeScroll] Inicializado HomeScrollFlow")

    # ---------- helpers ----------
    def _size(self):
        s = self.driver.get_window_size()
        print(f"[HomeScroll] Tamaño ventana: {s}")
        return s["width"], s["height"]

    def _swipe_up(self, duration_ms: int = 280, y_start_ratio: float = 0.78, y_end_ratio: float = 0.25):
        w, h = self._size()
        x1 = int(w * 0.5)
        y1 = int(h * y_start_ratio)
        x2 = int(w * 0.5)
        y2 = int(h * y_end_ratio)
        print(f"[HomeScroll] Swipe up de ({x1},{y1}) a ({x2},{y2}) dur={duration_ms}ms")
        try:
            self.ui.swipe(x1, y1, x2, y2, duration_ms=duration_ms)
        except Exception as e:
            print(f"[HomeScroll] Error en swipe: {e!r}")

    def _maybe_caught_up(self) -> bool:
        try:
            src = (self.driver.page_source or "").lower()
            if any(h in src for h in self.CAUGHT_UP_HINTS):
                print("[HomeScroll] Detectado mensaje de 'All caught up/Estás al día'.")
                return True
        except Exception as e:
            print(f"[HomeScroll] No se pudo leer page_source para 'caught up': {e!r}")
        return False

    def _ensure_home(self, wait_seconds: int = 8):
        print("[HomeScroll] Navegando a Home…")
        try:
            NavigationFlow(self.driver).go_home()
        except Exception as e:
            print(f"[HomeScroll] NavigationFlow.go_home() lanzó excepción: {e!r} (continúo)")

        # Espera ligera a que cargue algo del feed o la tab bar
        try:
            WebDriverWait(self.driver, wait_seconds).until(
                EC.presence_of_element_located((AppiumBy.ID, self.rids.TAB_BAR))
            )
            print("[HomeScroll] TAB_BAR detectada.")
        except Exception:
            print("[HomeScroll] No se detectó TAB_BAR en el tiempo esperado (continúo de todos modos).")

    # ---------- API ----------
    def scroll_home(self, times: int = 30, delay: float = 0.6) -> bool:
        """
        Scrollea el feed de Home `times` veces con una pausa `delay` entre swipes.
        """
        print(f"[HomeScroll] Iniciando scroll: veces={times}, delay={delay}s")
        self._ensure_home()

        # Si hay un pill de "nuevas publicaciones", lo registramos (no es obligatorio tocarlo)
        try:
            if self.ga.id(self.rids.NEW_FEED_PILL).exists(1):
                print("[HomeScroll] NEW_FEED_PILL visible (nuevas publicaciones disponibles).")
        except Exception:
            pass

        for i in range(1, times + 1):
            if self._maybe_caught_up():
                print(f"[HomeScroll] Corte anticipado por 'caught up' en iteración #{i}.")
                return True

            print(f"[HomeScroll] ---- Swipe #{i}/{times} ----")
            self._swipe_up()
            time.sleep(delay)

        print("[HomeScroll] Scroll completado.")
        return True
