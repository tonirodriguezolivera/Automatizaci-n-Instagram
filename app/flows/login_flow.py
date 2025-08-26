# app/flows/login_flow.py
from __future__ import annotations
import time
from typing import Optional

from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from app.core.ui import UI
from app.gramaddict_adapter import GA
from app.utils.instagram_locators import LoginLocators
from app.utils.instagram_selectors import IG_APP_ID, ResourceID, TabBarText
from app.flows.otp_flow import OtpFlow                 # requiere pyotp instalado
from app.flows.password_change_flow import PasswordChangeFlow  # opcional

# Activities típicas de IG
CANDIDATE_ACTIVITIES = [
    ".activity.MainTabActivity",
    ".activity.MainActivity",
    ".activity.LoginActivity",
    ".activity.LoginLandingActivity",
    ".activity.IgActivity",
    "com.instagram.modal.ModalActivity",
]

# Variantes para detectar la pantalla/botón de login
LOGIN_TEXT_UNION = (
    "Log in|Iniciar sesión|Acceder|Se connecter|Continuer|Continuar|Continue"
)

# Popup de credenciales incorrectas
LOGIN_FAIL_TITLE_UNION = (
    "That login info didn't work|"
    "Login info didn't work|"
    "La información de inicio de sesión no funcionó|"
    "La información de inicio de sesión no es correcta|"
    "Credenciales incorrectas"
)
TRY_AGAIN_UNION = "TRY AGAIN|Try again|Reintentar|Intentar de nuevo|VOLVER A INTENTAR|INTENTAR DE NUEVO"


class LoginFlow:
    """
    Flujo de login para Instagram:
      - Detecta si ya estás dentro (tab bar)
      - Abre el formulario si estás en la landing
      - Completa usuario/contraseña usando XPaths con atributo @password
      - Pulsa login
      - Si aparece el popup 'That login info didn’t work', reintenta con new_password
      - Maneja OTP TOTP (pyotp) si corresponde
      - (Opcional) Maneja cambio de contraseña
    """
    def __init__(self, driver):
        self.driver = driver
        self.ui = UI(driver)
        self.ga = GA(driver)
        self.loc = LoginLocators()          # trae username_xpath, password_xpath, login_btn_xpath_variants
        self.rids = ResourceID(IG_APP_ID)
        self.otp = OtpFlow(driver)
        self.pass_change = PasswordChangeFlow(driver)

    # ---------- Helpers de contexto/estado ----------
    def wait_instagram_activity(self, timeout: int = 25) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            try:
                act = self.driver.current_activity or ""
                if any(act.endswith(x) for x in CANDIDATE_ACTIVITIES):
                    return True
            except Exception:
                pass
            time.sleep(0.6)
        return False

    def _already_logged_in(self) -> bool:
        # Heurística: si vemos la tab bar o un content-desc de Home/Profile
        if self.ga.id(self.rids.TAB_BAR).exists(2):
            return True
        if self.ga.desc_any(f"{TabBarText.HOME_CONTENT_DESC}|{TabBarText.PROFILE_CONTENT_DESC}").exists(2):
            return True
        return False

    def _open_login_form_if_needed(self):
        # Algunos builds muestran un botón/link para entrar al formulario
        try:
            self.ga.text_any(LOGIN_TEXT_UNION, partial=True).click(timeout=3)
            return
        except Exception:
            pass
        try:
            self.ga.desc_any(LOGIN_TEXT_UNION, partial=True).click(timeout=2)
        except Exception:
            pass

    # ---------- Helpers de popup fallo de credenciales ----------
    def _has_login_failed_popup(self) -> bool:
        try:
            src = (self.driver.page_source or "").lower()
            if any(t.lower() in src for t in LOGIN_FAIL_TITLE_UNION.split("|")):
                return True
            if any(t.lower() in src for t in TRY_AGAIN_UNION.split("|")):
                return True
        except Exception:
            pass
        return False

    def _dismiss_login_failed_popup(self) -> bool:
        try:
            self.ga.text_any(TRY_AGAIN_UNION, partial=True).click(timeout=2)
            return True
        except Exception:
            pass
        try:
            self.ga.desc_any(TRY_AGAIN_UNION, partial=True).click(timeout=2)
            return True
        except Exception:
            pass
        try:
            self.ui.back()
            return True
        except Exception:
            return False

    def _tap_login_button(self) -> bool:
        for xp in self.loc.login_btn_xpath_variants:
            try:
                btn = self.ui.by_xpath(xp, timeout=4)
                self.ui.tap(btn)
                return True
            except Exception:
                continue
        return False

    def _retry_with_new_password(self, new_password: str) -> bool:
        try:
            pass_el = self.ui.by_xpath(self.loc.password_xpath, timeout=8)
            self.ui.type(pass_el, new_password, clear_first=True)
        except Exception as e:
            print(f"[Login] No se pudo colocar la nueva contraseña: {e}")
            return False
        return self._tap_login_button()

    # ---------- API principal ----------
    def login(
        self,
        username: str,
        password: str,
        secret_key: Optional[str] = None,
        new_password: Optional[str] = None
    ) -> bool:
        # Espera a que IG esté activo (no abortamos si tarda)
        if not self.wait_instagram_activity(30):
            print("[Login] Activity IG no detectada (continuando de todos modos).")

        # Si ya hay sesión, no hacemos nada
        if self._already_logged_in():
            print("[Login] Ya dentro (tab bar).")
            return True

        # Abrir formulario si estamos en landing
        #self._open_login_form_if_needed()

        # Campos (XPaths con atributo @password)
        try:
            user_el = self.ui.by_xpath(self.loc.username_xpath, timeout=60)
            pass_el = self.ui.by_xpath(self.loc.password_xpath, timeout=60)
        except Exception as e:
            print(f"[Login] No se hallaron campos user/pass por XPaths password=true/false: {e}")
            try:
                from app.instagram_actions import InstagramActions
                InstagramActions.dump_debug(self.driver, "login_no_fields")
            except Exception:
                pass
            return False

        # Escribir credenciales y pulsar login
        self.ui.type(user_el, username)
        self.ui.type(pass_el, password)

        if not self._tap_login_button():
            print("[Login] Botón de inicio de sesión no encontrado.")
            return False

        # --- Manejo de popup 'That login info didn't work' ---
        time.sleep(10)  # margen para que aparezca el diálogo
        if self._has_login_failed_popup():
            if new_password and new_password != password:
                print("[Login] Credenciales rechazadas. Reintentando con 'new_password'...")
                self._dismiss_login_failed_popup()
                if not self._retry_with_new_password(new_password):
                    print("[Login] Reintento con 'new_password' no pudo ejecutarse.")
                    try:
                        from app.instagram_actions import InstagramActions
                        InstagramActions.dump_debug(self.driver, "login_retry_prepare_fail")
                    except Exception:
                        pass
                    return False

                time.sleep(2)
                if self._has_login_failed_popup():
                    print("[Login] Error: 'new_password' también rechazado (That login info didn't work).")
                    try:
                        from app.instagram_actions import InstagramActions
                        InstagramActions.dump_debug(self.driver, "login_retry_failed")
                    except Exception:
                        pass
                    return False
            else:
                print("[Login] Error: credenciales rechazadas y no se proporcionó 'new_password'.")
                try:
                    from app.instagram_actions import InstagramActions
                    InstagramActions.dump_debug(self.driver, "login_fail_no_new_password")
                except Exception:
                    pass
                return False

        # --- OTP (TOTP) si corresponde ---
        handled = self.otp.maybe_handle_totp(secret_key)
        if handled is False:
            print("[Login] OTP detectado pero falló la verificación.")
            try:
                from app.instagram_actions import InstagramActions
                InstagramActions.dump_debug(self.driver, "otp_fail")
            except Exception:
                pass
            return False

        # --- Cambio de contraseña (opcional) ---
        changed = self.pass_change.maybe_handle_password_change(new_password)
        if changed is False:
            print("[Login] Se pidió cambiar contraseña, pero falló el flujo.")
            try:
                from app.instagram_actions import InstagramActions
                InstagramActions.dump_debug(self.driver, "password_change_fail")
            except Exception:
                pass
            return False

        # Verificación final de que estamos dentro
        time.sleep(3)
        if self._already_logged_in():
            return True

        try:
            WebDriverWait(self.driver, 8).until(
                EC.presence_of_element_located((AppiumBy.ID, self.rids.TAB_BAR))
            )
            return True
        except Exception:
            pass

        try:
            from app.instagram_actions import InstagramActions
            InstagramActions.dump_debug(self.driver, "login_after_all_fail")
        except Exception:
            pass
        return False
