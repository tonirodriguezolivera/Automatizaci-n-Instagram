# app/instagram_actions.py
import asyncio
import time
from pathlib import Path

from driver.driver_manager import get_driver
from app.flows.login_flow import LoginFlow
from app.flows.navigation import NavigationFlow
from app.flows.stories_flow import StoriesFlow
from app.flows.home_scroll_flow import HomeScrollFlow
from app.flows.post_login_confirms import PostLoginConfirms  # confirma "OK" antes de stories
from app.utils.instagram_selectors import IG_APP_ID, ResourceID

from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

DEBUG_DIR = Path("debug")
DEBUG_DIR.mkdir(exist_ok=True)

class InstagramActions:

    @staticmethod
    def wait_home_ready(driver, timeout: int = 20, extra_delay: float = 1.5):
        """
        Espera a que Home esté listo:
        - TAB_BAR presente
        - (opcional) carrusel de stories (reels tray container)
        - spinner de refresco oculto
        - pequeño retraso adicional
        """
        rids = ResourceID(IG_APP_ID)
        print(f"[HomeReady] Esperando Home (timeout={timeout}s, extra_delay={extra_delay}s)")
        wait = WebDriverWait(driver, timeout)

        # 1) TAB_BAR presente
        try:
            wait.until(EC.presence_of_element_located((AppiumBy.ID, rids.TAB_BAR)))
            print("[HomeReady] TAB_BAR detectada.")
        except Exception as e:
            print(f"[HomeReady] TAB_BAR no detectada en tiempo: {e!r} (continuo)")

        # 2) (Opcional) carrusel de stories
        try:
            wait.until(EC.presence_of_element_located((AppiumBy.ACCESSIBILITY_ID, "reels tray container")))
            print("[HomeReady] Carrusel de stories visible (reels tray container).")
        except Exception:
            print("[HomeReady] Carrusel no visible aún (no bloqueante).")

        # 3) Spinner de refresco oculto
        try:
            WebDriverWait(driver, 5).until(
                EC.invisibility_of_element_located((AppiumBy.ID, rids.SWIPE_REFRESH_ANIMATED_PROGRESSBAR_CONTAINER))
            )
            print("[HomeReady] Spinner de refresco no visible.")
        except Exception:
            print("[HomeReady] No se pudo confirmar spinner (no bloqueante).")

        # 4) Delay final
        time.sleep(extra_delay)
        print("[HomeReady] Home listo para iniciar Stories.")
        
    @staticmethod
    def dump_debug(driver, tag="init"):
        """Guarda info de depuración: package, activity, page source y screenshot."""
        try:
            pkg = driver.current_package
            act = driver.current_activity
            print(f"[DEBUG] current_package={pkg} current_activity={act}")

            src_path = DEBUG_DIR / f"page_source_{tag}.xml"
            with open(src_path, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print(f"[DEBUG] page source guardado en: {src_path}")

            ss_path = DEBUG_DIR / f"screenshot_{tag}.png"
            driver.save_screenshot(str(ss_path))
            print(f"[DEBUG] screenshot guardado en: {ss_path}")
        except Exception as e:
            print(f"[DEBUG] dump error: {e}")

    @staticmethod
    def wait_instagram_activity(driver, timeout=25):
        """Espera que Instagram esté en una activity conocida."""
        CANDIDATAS = [
            ".activity.MainTabActivity",
            ".activity.MainActivity",
            ".activity.LoginActivity",
            ".activity.LoginLandingActivity",
            ".activity.IgActivity",
            "com.instagram.modal.ModalActivity",
        ]
        end = time.time() + timeout
        while time.time() < end:
            try:
                act = driver.current_activity or ""
                if any(act.endswith(x) for x in CANDIDATAS):
                    return True
            except Exception:
                pass
            time.sleep(0.8)
        return False

    @staticmethod
    async def register_account(
        serial: str,
        user: dict,
        play_stories: bool = True,
        stories_limit: int = 30,
        home_scroll_times: int = 30,
        home_scroll_delay: float = 0.6,
    ):
        """
        user esperado:
          {
            "user": "dianebutler4083",
            "password": "9tsi3tjnc1",
            "key": "BASE32 OTP KEY",
            "new_password": "pass_nuevo2",
            "avd_name": "Nexus_5_API_31_Clone1"
          }
        Flujo:
          - Si ya hay sesión: (opcional) HomeScroll -> confirmar 'OK' -> Stories
          - Si no: login -> confirmar 'OK' -> (opcional) HomeScroll -> Stories
        """
        driver = get_driver()

        def _task():
            flow = LoginFlow(driver)

            # 1) ¿Ya hay sesión?
            if flow.is_logged_in(timeout=3):
                print(f"[{serial}] Sesión activa para {user.get('user')}. Saltando login.")

                if play_stories:
                    # (A) Home scroll antes de stories
                    try:
                        print(f"[{serial}] HomeScroll: iniciando ({home_scroll_times} swipes, delay={home_scroll_delay}s)…")
                        HomeScrollFlow(driver).scroll_home(times=home_scroll_times, delay=home_scroll_delay)
                        print(f"[{serial}] HomeScroll: finalizado.")
                    except Exception as e:
                        print(f"[{serial}] HomeScroll: error no crítico: {e!r}")

                    # (C) Ejecutar Stories
                    try:
                        NavigationFlow(driver).go_home()
                    except Exception:
                        pass
                    
                    InstagramActions.wait_home_ready(driver, timeout=20, extra_delay=1.5)
                    print(f"[{serial}] Stories: iniciando (límite={stories_limit})…")
                    ok_st = StoriesFlow(driver).play_all(delay=1.5, max_stories=stories_limit)
                    print(f"[Stories] {'OK' if ok_st else 'FALLÓ'} en {serial}")
                    return ok_st
                # Si no hay stories por reproducir
                return True

            # 2) Login
            print(f"[{serial}] Iniciando login para {user.get('user')}…")
            ok_login = flow.login(
                username=user.get("user", ""),
                password=user.get("password", ""),
                secret_key=user.get("key"),
                new_password=user.get("new_password")
            )
            print(f"[Login] {'OK' if ok_login else 'FALLÓ'} en {serial} ({user.get('user')})")

            if not ok_login:
                InstagramActions.dump_debug(driver, "login_fail")
                return False

            # 3) Confirmar 'OK' post-login antes de stories
            try:
                PostLoginConfirms(driver).wait_and_press_ok(max_wait_sec=40)
            except Exception:
                pass

            if play_stories:
                # (A) Home scroll antes de stories
                try:
                    print(f"[{serial}] HomeScroll: iniciando ({home_scroll_times} swipes, delay={home_scroll_delay}s)…")
                    HomeScrollFlow(driver).scroll_home(times=home_scroll_times, delay=home_scroll_delay)
                    print(f"[{serial}] HomeScroll: finalizado.")
                except Exception as e:
                    print(f"[{serial}] HomeScroll: error no crítico: {e!r}")

                # (B) Stories
                try:
                    NavigationFlow(driver).go_home()
                except Exception:
                    pass
                
                InstagramActions.wait_home_ready(driver, timeout=20, extra_delay=1.5)
                print(f"[{serial}] Stories: iniciando (límite={stories_limit})…")
                ok_st = StoriesFlow(driver).play_all(delay=1.5, max_stories=stories_limit)
                print(f"[Stories] {'OK' if ok_st else 'FALLÓ'} en {serial}")
                return ok_st

            return True

        return await asyncio.to_thread(_task)
