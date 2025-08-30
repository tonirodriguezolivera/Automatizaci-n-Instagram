# app/flows/navigation.py
from app.core.ui import UI
from app.utils.instagram_locators import NavLocators
from appium.webdriver.common.appiumby import AppiumBy

class NavigationFlow:
    def __init__(self, driver):
        self.driver = driver
        self.ui = UI(driver)
        self.loc = NavLocators()

    def _tap_by_desc_variants(self, variants):
        for d in variants:
            try:
                el = self.ui.by_desc(d, partial=False, timeout=2)
                self.ui.tap(el)
                return True
            except Exception:
                continue
        return False

    def _tap_tab_index(self, index: int):
        xp = self.loc.tab_icon_xpath_indexed.format(index)
        el = self.ui.by_xpath(xp, timeout=5)
        self.ui.tap(el)
    

    def go_home(self):
        if not self._tap_by_desc_variants(self.loc.home_desc_variants):
            self._tap_tab_index(1)

    def go_search(self):
        if not self._tap_by_desc_variants(self.loc.search_desc_variants):
            self._tap_tab_index(2)

    def go_reels(self):
        if not self._tap_by_desc_variants(self.loc.reels_desc_variants):
            self._tap_tab_index(3)

    def go_profile(self):
        if not self._tap_by_desc_variants(self.loc.profile_desc_variants):
            self._tap_tab_index(5)
