# app/flows/otp_flow.py
import time
import pyotp
from typing import Optional, List
from appium.webdriver.common.appiumby import AppiumBy

from app.core.ui import UI
from app.gramaddict_adapter import GA

OTP_HINT_TEXTS = (
    "Enter the code", "6-digit code", "Authentication code", "Security code",
    "Introduce el código", "Código de 6 dígitos", "Código de seguridad",
    "Two-Factor", "Autenticación en dos pasos",
)

CONFIRM_TEXTS = "Confirm|Submit|Continue|Next|Verify|Confirmar|Enviar|Continuar|Siguiente|Verificar"

def _sanitize_base32(secret: str) -> str:
    # IG suele dar la secret en bloques separados. Quitamos espacios y forzamos upper.
    return (secret or "").replace(" ", "").strip().upper()

class OtpFlow:
    """Maneja la pantalla de 2FA TOTP en Instagram."""
    def __init__(self, driver):
        self.driver = driver
        self.ui = UI(driver)
        self.ga = GA(driver)

    def _generate_totp(self, secret: str) -> str:
        base32 = _sanitize_base32(secret)
        # 6 dígitos, periodo 30s (estándar)
        totp = pyotp.TOTP(base32, digits=6, interval=30)
        return totp.now()

    def _looks_like_otp_screen(self) -> bool:
        # Heurística: por texto en la pantalla o por presencia de EditText "numérico"
        try:
            src = self.driver.page_source.lower()
            if any(k.lower() in src for k in [t.lower() for t in OTP_HINT_TEXTS]):
                return True
        except Exception:
            pass

        # Intento directo: ¿hay EditText para código?
        try:
            edits = self.driver.find_elements(AppiumBy.CLASS_NAME, "android.widget.EditText")
            if edits:
                # Muy frecuente: un único EditText numérico para 6 dígitos
                return True
        except Exception:
            pass
        return False

    def _find_otp_edittext(self):
        # 1) por resource-id que contenga "code"/"two_factor"/"confirmation"
        candidates = self.driver.find_elements(AppiumBy.CLASS_NAME, "android.widget.EditText")
        if candidates:
            # Dar preferencia a los que tengan id con "code"
            with_ids = []
            for e in candidates:
                try:
                    rid = (e.get_attribute("resource-id") or "").lower()
                    if any(k in rid for k in ["code", "two_factor", "2fa", "confirm"]):
                        with_ids.append(e)
                except Exception:
                    pass
            if with_ids:
                return with_ids[0]
            # Si no hay con id alusivo, retornamos el primero visible
            return candidates[0]
        return None

    def _tap_confirm(self) -> bool:
        # Botones típicos
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
        # Fallback: botón por clase + texto
        try:
            el = self.ui.by_xpath("//android.widget.Button[contains(@text,'Confirm') or contains(@text,'Verif') or contains(@text,'Enviar') or contains(@text,'Continu') or contains(@text,'Next')]", timeout=2)
            self.ui.tap(el)
            return True
        except Exception:
            pass
        return False

    def maybe_handle_totp(self, secret_key: Optional[str]) -> Optional[bool]:
        """
        Intenta manejar TOTP si la pantalla actual parece ser 2FA.
        Devuelve:
          - True si se ingresó OTP y se confirmó
          - False si falló el ingreso/confirmación
          - None si no parece ser pantalla de OTP
        """
        if not secret_key:
            return None

        if not self._looks_like_otp_screen():
            return None

        edit = self._find_otp_edittext()
        if not edit:
            print("[OTP] No se encontró campo de código.")
            return False

        # Por seguridad, espera a un nuevo período si quedan <4s del actual
        try:
            base32 = _sanitize_base32(secret_key)
            totp = pyotp.TOTP(base32, digits=6, interval=30)
            remaining = totp.interval - (int(time.time()) % totp.interval)
            if remaining < 4:
                time.sleep(remaining + 1)
            code = totp.now()
            print(f"[OTP] Código TOTP generado: {code} (base32: {base32})")
        except Exception as e:
            print(f"[OTP] Error generando TOTP: {e}")
            return False

        try:
            self.ui.type(edit, code, clear_first=True)
        except Exception as e:
            print(f"[OTP] Error escribiendo el código: {e}")
            return False

        if not self._tap_confirm():
            print("[OTP] Botón de confirmar no encontrado.")
            return False

        # mini espera de transición
        time.sleep(2.0)
        return True
