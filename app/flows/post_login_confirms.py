# app/flows/post_login_confirms.py
from __future__ import annotations
import time
from app.core.ui import UI
from app.gramaddict_adapter import GA

OK_UNION = "SAVE|Save"  # puedes extender a "Aceptar" si lo ves necesario

class PostLoginConfirms:
    """Confirma popups post-login que piden guardar perfil, etc."""
    def __init__(self, driver):
        self.driver = driver
        self.ui = UI(driver)
        self.ga = GA(driver)

    def wait_and_press_ok(self, max_wait_sec: int = 40) -> bool:
        """Espera hasta max_wait_sec a que aparezca el botón 'OK' y lo pulsa."""
        deadline = time.time() + max_wait_sec
        while time.time() < deadline:
            # Intento por texto
            try:
                self.ga.text_any(OK_UNION, partial=False).click(timeout=1)
                print("[Confirm] Se confirmó con 'OK'.")
                return True
            except Exception:
                pass
            # Intento por content-desc (algunos builds lo usan)
            try:
                self.ga.desc_any(OK_UNION, partial=False).click(timeout=1)
                print("[Confirm] Se confirmó con 'OK' (content-desc).")
                return True
            except Exception:
                pass
            time.sleep(1)
        print("[Confirm] No apareció 'OK' en el tiempo esperado (40s).")
        return False
