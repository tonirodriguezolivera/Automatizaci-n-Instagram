# app/flows/dialogs.py
from typing import Iterable
from appium.webdriver.common.appiumby import AppiumBy
from . import login_flow  # circular-safe, only types used at runtime
from app.core.ui import UI
from app.utils.instagram_locators import DialogsLocators

class DialogsFlow:
    def __init__(self, ui: UI):
        self.ui = ui
        self.loc = DialogsLocators()

    def _tap_first_text_found(self, candidates: Iterable[str], partial=False, timeout_each=2) -> bool:
        for text in candidates:
            try:
                el = self.ui.by_text(text, partial=partial, timeout=timeout_each)
                self.ui.tap(el)
                return True
            except Exception:
                continue
        return False

    def dismiss_post_login(self):
        # “Save your login info?” dialogs
        self._tap_first_text_found(self.loc.save_login_variants, partial=False, timeout_each=2)
        # “Turn on notifications”
        self._tap_first_text_found(self.loc.notifications_variants, partial=False, timeout_each=2)
        # “Skip / Omitir”
        self._tap_first_text_found(self.loc.skip_variants, partial=False, timeout_each=2)
