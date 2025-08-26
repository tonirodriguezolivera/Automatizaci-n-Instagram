# app/utils/instagram_locators.py
from dataclasses import dataclass
from typing import List

PKG = "com.instagram.android"

@dataclass(frozen=True)
class LoginLocators:
    # Campos
    username_xpath: str = "//android.widget.EditText[@password='false']"
    password_xpath: str = "//android.widget.EditText[@password='true']"
    # Botón login (varios idiomas/atributos)
    login_btn_xpath_variants: List[str] = (
        "//android.widget.Button[contains(@content-desc,'Log in') or contains(@text,'Log in')]",
        "//android.widget.Button[contains(@text,'Iniciar sesión')]",
        "//android.widget.Button[contains(@text,'Acceder')]",
        "//android.widget.Button[contains(@text,'Se connecter')]",
    )

@dataclass(frozen=True)
class DialogsLocators:
    # “Save your login info?”
    save_login_variants: List[str] = (
        "Not now", "Ahora no", "Ahora no, gracias", "Jetzt nicht", "Por ahora no"
    )
    # “Turn on notifications”
    notifications_variants: List[str] = (
        "Not now", "Ahora no", "Más tarde", "No ahora", "Jetzt nicht"
    )
    # Botón genérico "Skip / Omitir"
    skip_variants: List[str] = ("Skip", "Omitir", "Ignorar")

@dataclass(frozen=True)
class NavLocators:
    # Tabs por content-desc (suelen variar por idioma, por eso incluimos fallback por índice)
    home_desc_variants: List[str] = ("Home", "Inicio")
    search_desc_variants: List[str] = ("Search and Explore", "Buscar y Explorar", "Buscar")
    reels_desc_variants: List[str] = ("Reels", )
    profile_desc_variants: List[str] = ("Profile", "Perfil")
    # Fallback por índice (1..5). Instagram usa ImageView con id tab_icon
    tab_icon_xpath_indexed = "(//android.widget.ImageView[@resource-id='com.instagram.android:id/tab_icon'])[{}]"
