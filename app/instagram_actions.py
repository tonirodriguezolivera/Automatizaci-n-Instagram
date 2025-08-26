# app/instagram_actions.py (fragmento relevante)
import asyncio
from app.flows.login_flow import LoginFlow
from driver.driver_manager import get_driver

class InstagramActions:

    # ... dump_debug y wait_instagram_activity se mantienen ...

    @staticmethod
    async def register_account(serial: str, user: dict):
        """
        user dict esperado:
        {
          "user": "dianebutler4083",
          "password": "9tsi3tjnc1",
          "key": "M3NO VD76 36DM PH6M 5FKV UVPV YXF6 5JPI",
          "new_password": "pass_nuevo2",
          "avd_name": "Nexus_5_API_31_Clone1"
        }
        """
        driver = get_driver()

        def _task():
            flow = LoginFlow(driver)
            ok = flow.login(
                username=user.get("user", ""),
                password=user.get("password", ""),
                secret_key=user.get("key"),          
                new_password=user.get("new_password")  
            )
            print(f"[+] Login {'OK' if ok else 'FALLÓ'} en {serial} ({user.get('user')})")

        await asyncio.to_thread(_task)
