# app/flows/stories_flow.py
from __future__ import annotations
import time
from typing import List

from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from app.core.ui import UI
from app.gramaddict_adapter import GA
from app.flows.navigation import NavigationFlow
from app.utils.instagram_selectors import IG_APP_ID, ResourceID


class StoriesFlow:
    """
    Ver stories con espera fija y avance inmediato (con detección de anuncios).
      - Navega a Home
      - Abre la primera storie desde el carrusel
      - Cada 1.5s avanza: tap derecha; si es anuncio, swipe izquierda
    """

    # Selectores (de Appium Inspector provistos)
    REELS_TRAY_DESC = "reels tray container"
    OUTER_CONTAINER_RID = "com.instagram.android:id/outer_container"
    OUTER_CONTAINER_XP_GLOBAL = f"(//android.widget.LinearLayout[@resource-id='{OUTER_CONTAINER_RID}'])[1]"
    OUTER_CONTAINER_XP_REL = f".//android.widget.LinearLayout[@resource-id='{OUTER_CONTAINER_RID}']"

    def __init__(self, driver):
        self.driver = driver
        self.ui = UI(driver)
        self.ga = GA(driver)
        self.rids = ResourceID(IG_APP_ID)
        print("[Stories] Inicializado StoriesFlow (modo simple 1.5s + ads)")

    # ------- utils básicos -------
    def _size(self):
        s = self.driver.get_window_size()
        print(f"[Stories] Tamaño de ventana: {s}")
        return s["width"], s["height"]

    def _tap_at(self, x: int, y: int):
        print(f"[Stories] Tap en coordenadas ({x}, {y})")
        # 1) Gesto nativo de Appium
        try:
            self.driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
            print("[Stories] Tap con 'mobile: clickGesture' OK")
            return
        except Exception:
            print("[Stories] 'mobile: clickGesture' no disponible; intento W3C Actions")

        # 2) W3C Actions
        try:
            from selenium.webdriver.common.actions import interaction
            from selenium.webdriver.common.actions.pointer_input import PointerInput
            from selenium.webdriver.common.actions.action_builder import ActionBuilder
            finger = PointerInput(interaction.POINTER_TOUCH, "finger")
            actions = ActionBuilder(self.driver, mouse=finger)
            actions.pointer_action.move_to_location(x, y)
            actions.pointer_action.pointer_down()
            actions.pointer_action.pause(0.05)
            actions.pointer_action.pointer_up()
            actions.perform()
            print("[Stories] Tap por W3C Actions OK")
            return
        except Exception as e:
            print(f"[Stories] W3C Actions falló: {e!r}. Fallback a click de contenedor o back()")
            try:
                el = self.ga.id_any(self.rids.REEL_VIEWER_MEDIA_CONTAINER).get(timeout=1)
                el.click()
                print("[Stories] Fallback: click en REEL_VIEWER_MEDIA_CONTAINER OK")
            except Exception:
                print("[Stories] Fallback final: back()")
                try:
                    self.driver.back()
                except Exception:
                    pass

    def _tap_right(self):
        w, h = self._size()
        x = int(w * 0.95)
        y = int(h * 0.5)
        print(f"[Stories] Avanzar storie → tap derecha ({x}, {y})")
        self._tap_at(x, y)

    def _swipe_left(self):
        print("[Stories] Swipe izquierda (pasar storie)")
        try:
            w, h = self._size()
            self.ui.swipe(int(w * 0.85), int(h * 0.5), int(w * 0.15), int(h * 0.5), duration_ms=300)
            print("[Stories] Swipe izquierda OK")
        except Exception as e:
            print(f"[Stories] Swipe izquierda falló: {e!r}")

    def _is_viewer_open(self) -> bool:
        # Señales suficientes de visor activo (con prints)
        try:
            if self.ga.id_any(self.rids.REEL_VIEWER_MEDIA_CONTAINER).exists(1):
                print("[Stories] Visor activo: REEL_VIEWER_MEDIA_CONTAINER")
                return True
            if self.ga.id_any(self.rids.MEDIA_CONTAINER).exists(1):
                print("[Stories] Visor activo: MEDIA_CONTAINER")
                return True
        except Exception as e:
            print(f"[Stories] _is_viewer_open() excepción: {e!r}")
        print("[Stories] Visor NO detectado")
        return False

    def _close_viewer(self):
        print("[Stories] Intentando cerrar visor…")
        try:
            btn = self.ga.id(self.rids.ACTION_BAR_BUTTON_BACK).get(timeout=1)
            btn.click()
            print("[Stories] Visor cerrado con botón BACK del action bar")
            return
        except Exception:
            print("[Stories] No se encontró botón BACK del action bar; intento back() del sistema")
        try:
            self.driver.back()
            print("[Stories] Visor cerrado con back() del sistema")
        except Exception as e:
            print(f"[Stories] No se pudo cerrar el visor: {e!r}")

    # ------- detección de anuncios -------
    def _looks_like_ad(self) -> bool:
        """
        Devuelve True si la storie actual parece ser un anuncio:
        - por contenedor SPONSORED_CONTENT_SERVER_RENDERED_ROOT
        - o por texto en page_source (sponsored/publicidad/patrocinado)
        """
        try:
            if self.ga.id_any(self.rids.SPONSORED_CONTENT_SERVER_RENDERED_ROOT).exists(1):
                print("[Stories] Anuncio detectado por SPONSORED_CONTENT_SERVER_RENDERED_ROOT")
                return True
        except Exception as e:
            print(f"[Stories] Error comprobando SPONSORED root: {e!r}")

        try:
            src = (self.driver.page_source or "").lower()
            if "sponsored" in src or "publicidad" in src or "patrocinado" in src:
                print("[Stories] Anuncio detectado por page_source")
                return True
        except Exception as e:
            print(f"[Stories] Error leyendo page_source para anuncios: {e!r}")

        return False

    # ------- apertura desde carrusel -------
    def _open_first_story_from_home(self) -> bool:
        print("[Stories] Ir a Home y abrir primera storie…")
        try:
            NavigationFlow(self.driver).go_home()
        except Exception as e:
            print(f"[Stories] NavigationFlow.go_home() lanzó excepción: {e!r} (continúo)")

        # Buscar carrusel
        try:
            print(f"[Stories] Esperando carrusel por ACCESSIBILITY_ID='{self.REELS_TRAY_DESC}'")
            tray = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((AppiumBy.ACCESSIBILITY_ID, self.REELS_TRAY_DESC))
            )
            print("[Stories] Carrusel encontrado por ACCESSIBILITY_ID")
        except Exception:
            print("[Stories] No se encontró por ACCESSIBILITY_ID; intento XPath exacto…")
            try:
                tray = WebDriverWait(self.driver, 8).until(
                    EC.presence_of_element_located(
                        (AppiumBy.XPATH, f"//androidx.recyclerview.widget.RecyclerView[@content-desc='{self.REELS_TRAY_DESC}']")
                    )
                )
                print("[Stories] Carrusel encontrado por XPath")
            except Exception as e:
                print(f"[Stories] No se encontró el carrusel de stories: {e!r}")
                return False

        # outer_container dentro del carrusel (o global)
        try:
            inner: List = tray.find_elements(AppiumBy.XPATH, self.OUTER_CONTAINER_XP_REL)
            print(f"[Stories] outer_container dentro del carrusel: {len(inner)} candidatos")
        except Exception as e:
            print(f"[Stories] Error buscando inner outer_container: {e!r}")
            inner = []

        target = inner[0] if inner else None
        if target is None:
            print("[Stories] Sin inner candidates; intento XPath GLOBAL del outer_container")
            try:
                target = WebDriverWait(self.driver, 6).until(
                    EC.presence_of_element_located((AppiumBy.XPATH, self.OUTER_CONTAINER_XP_GLOBAL))
                )
                print("[Stories] outer_container encontrado por XPath GLOBAL")
            except Exception as e:
                print(f"[Stories] No se encontró outer_container: {e!r}")
                return False

        # abrir visor
        try:
            clickable_attr = str(target.get_attribute("clickable")).lower()
            print(f"[Stories] outer_container clickable={clickable_attr}")
        except Exception:
            clickable_attr = "unknown"

        try:
            if clickable_attr == "true":
                target.click()
                print("[Stories] Click en outer_container OK")
            else:
                r = target.rect
                cx, cy = int(r["x"] + r["width"]/2), int(r["y"] + r["height"]/2)
                print(f"[Stories] outer_container no clickable; tap centro ({cx}, {cy})")
                self._tap_at(cx, cy)
            time.sleep(1.0)
            opened = self._is_viewer_open()
            print(f"[Stories] ¿Visor abierto? {opened}")
            return opened
        except Exception as e:
            print(f"[Stories] No se pudo abrir el visor desde el carrusel: {e!r}")
            return False

    # ------- API principal (simple + ads) -------
    def play_all(self, delay: float = 1.5, max_stories: int = 30) -> bool:
        """
        Avanza stories con espera fija.
        - delay: segundos a esperar entre stories (por defecto 1.5)
        - max_stories: tope de stories a ver (por defecto 30)
        """
        print(f"[Stories] Reproducción simple: delay={delay}s, max_stories={max_stories}")

        if not self._is_viewer_open():
            print("[Stories] Visor no está abierto al inicio; abriendo primera storie…")
            if not self._open_first_story_from_home():
                print("[Stories] No se pudo abrir la primera storie.")
                return False

        seen = 0
        while seen < max_stories and self._is_viewer_open():
            print(f"[Stories] Esperando {delay:.1f}s antes de avanzar… (story #{seen + 1})")
            time.sleep(delay)

            if self._looks_like_ad():
                print("[Stories] Anuncio detectado → usar swipe izquierda")
                self._swipe_left()
            else:
                self._tap_right()

            seen += 1
            print(f"[Stories] Avanzado → {seen}/{max_stories}")

        # Cerrar si sigue abierto
        if self._is_viewer_open():
            print("[Stories] Límite alcanzado o fin no detectado automáticamente; cierro visor.")
            self._close_viewer()

        print("[Stories] Finalizado.")
        return True
