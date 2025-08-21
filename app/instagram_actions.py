# instagram_actions.py
import asyncio
import time
from pathlib import Path
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from driver.driver_manager import get_driver

DEBUG_DIR = Path("debug")
DEBUG_DIR.mkdir(exist_ok=True)

class InstagramActions:

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
            act = driver.current_activity or ""
            if any(act.endswith(x) for x in CANDIDATAS):
                return True
            time.sleep(0.8)
        return False

    @staticmethod
    async def register_account(serial: str):
        """Realiza login en Instagram."""
        driver = get_driver()

        def _task():
            wait = WebDriverWait(driver, 20)

            if not InstagramActions.wait_instagram_activity(driver, timeout=30):
                print("[WARN] No se detectó una activity conocida de Instagram tras 30s")
                InstagramActions.dump_debug(driver, "no_activity")
            else:
                InstagramActions.dump_debug(driver, "activity_ok")

            try:
                username_field = wait.until(
                    EC.presence_of_element_located(
                        (AppiumBy.XPATH, "//android.widget.EditText[@password='false']")
                    )
                )
                password_field = driver.find_element(
                    AppiumBy.XPATH, "//android.widget.EditText[@password='true']"
                )
                login_button = driver.find_element(
                    AppiumBy.XPATH,
                    "//android.widget.Button[contains(@content-desc,'Log in') or contains(@text,'Log in')]"
                )

                username_field.send_keys("zorem")
                password_field.send_keys("zorem")
                login_button.click()

                print(f"[+] Iniciando registro en {serial}")
            except Exception as e:
                print(f"[-] No se encontró pantalla de login en {serial}: {str(e)}")

        await asyncio.to_thread(_task)
