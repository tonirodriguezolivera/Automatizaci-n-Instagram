# app/flows/password_change_flow.py
import time
from typing import Optional
from appium.webdriver.common.appiumby import AppiumBy
from app.core.ui import UI
from app.gramaddict_adapter import GA

CHANGE_HINTS = (
    "Change your password", "Create new password", "New password",
    "Cambia tu contraseña", "Crear nueva contraseña", "Nueva contraseña"
)
CONFIRM_TEXTS = "Change|Save|Confirm|Continue|Next|Cambiar|Guardar|Confirmar|Continuar|Siguiente"

class PasswordChangeFlow:
    def __init__(self, driver):
        self.driver = driver
        self.ui = UI(driver)
        self.ga = GA(driver)

    def _looks_like_change_password(self) -> bool:
        try:
            src = self.driver.page_source.lower()
            return any(h.lower() in src for h in CHANGE_HINTS)
        except Exception:
            return False

    def _find_password_edits(self):
        edits = self.driver.find_elements(AppiumBy.CLASS_NAME, "android.widget.EditText")
        # devolvemos todos los EditText password=True si hay, si no, todos
        pwd_eds = []
        for e in edits:
            try:
                if str(e.get_attribute("password")).lower() == "true":
                    pwd_eds.append(e)
            except Exception:
                pass
        return pwd_eds or edits

    def _tap_confirm(self) -> bool:
        try:
            self.ga.text_any(CONFIRM_TEXTS, partial=True).click(timeout=3)
            return True
        except Exception:
            pass
        try:
            self.ga.desc_any(CONFIRM_TEXTS, partial=True).click(timeout=2)
            return True
        except Exception:
            pass
        try:
            el = self.ui.by_xpath("//android.widget.Button[contains(@text,'Cambiar') or contains(@text,'Guardar') or contains(@text,'Change') or contains(@text,'Save') or contains(@text,'Next')]", timeout=2)
            self.ui.tap(el)
            return True
        except Exception:
            pass
        return False

    def maybe_handle_password_change(self, new_password: Optional[str]) -> Optional[bool]:
        if not new_password:
            return None
        if not self._looks_like_change_password():
            return None

        edits = self._find_password_edits()
        if not edits:
            print("[PassChange] No se hallaron campos para nueva contraseña.")
            return False

        # Hay pantallas con 1 campo (nueva), y otras con 2 (nueva + confirmación)
        try:
            self.ui.type(edits[0], new_password, clear_first=True)
            if len(edits) >= 2:
                self.ui.type(edits[1], new_password, clear_first=True)
        except Exception as e:
            print(f"[PassChange] Error escribiendo contraseña: {e}")
            return False

        if not self._tap_confirm():
            print("[PassChange] Botón para confirmar cambio no encontrado.")
            return False

        time.sleep(2.0)
        return True
