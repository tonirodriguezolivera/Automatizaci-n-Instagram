# appium_server_manager.py
import os
import asyncio
import socket
from pathlib import Path
from typing import Optional, Dict, Tuple
from http.client import HTTPConnection
from appium.webdriver.appium_service import AppiumService

# Registro de instancias: clave = (host, port)
_services: Dict[Tuple[str, int], AppiumService] = {}
_services_lock = asyncio.Lock()


async def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    def _check() -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    return await asyncio.to_thread(_check)


async def _check_appium_status(host: str, port: int, timeout: float = 2.0) -> bool:
    def _check() -> bool:
        try:
            conn = HTTPConnection(host, port, timeout=timeout)
            conn.request("GET", "/status")
            resp = conn.getresponse()
            return resp.status == 200
        except Exception:
            return False
    return await asyncio.to_thread(_check)


async def wait_for_appium_ready(host: str, port: int, timeout: int = 60, interval: float = 0.5) -> bool:
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        if await _port_open(host, port) and await _check_appium_status(host, port):
            return True
        await asyncio.sleep(interval)
    return False


def _find_free_port(host: str = "127.0.0.1", start: int = 4723, max_tries: int = 200) -> int:
    port = start
    for _ in range(max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            if s.connect_ex((host, port)) != 0:
                return port
        port += 1
    raise RuntimeError("No hay puertos libres para Appium en el rango solicitado.")


class AppiumServerManager:
    @staticmethod
    async def start_appium_server(
        host: Optional[str] = None,
        port: Optional[int] = None,
        logs_path: Optional[str] = None,
        start_flag: Optional[str] = None,
        wait_timeout: int = 60,
        allow_reuse: bool = False,
    ) -> int:
        """
        Arranca una instancia de Appium y devuelve el **puerto** en el que quedó escuchando.
        - Si port es None -> elige un puerto libre automáticamente.
        - Si allow_reuse=True y ya existe una instancia viva en (host,port), la reutiliza.

        Uso:
            port = await AppiumServerManager.start_appium_server()
            url = f"http://{host}:{port}"
        """
        start_flag = (start_flag or os.getenv("START_APPIUM_SERVER", "yes")).lower()
        if start_flag != "yes":
            raise RuntimeError("START_APPIUM_SERVER != 'yes'")

        host = host or os.getenv("APPIUM_HOST", "127.0.0.1")
        base_port = int(os.getenv("APPIUM_PORT", "4723"))
        port = int(port) if port is not None else _find_free_port(host, base_port)

        # Logs
        default_log = f"logs/appium_{port}.log"
        logs_path = logs_path or os.getenv("APPIUM_LOG_PATH", default_log)
        Path(logs_path).parent.mkdir(parents=True, exist_ok=True)

        async with _services_lock:
            key = (host, port)

            # Reusar si ya está operativo
            if allow_reuse and await wait_for_appium_ready(host, port, timeout=2):
                print(f"[AppiumServerManager] Reusando Appium en {host}:{port}")
                return port

            # Si ya tenemos un objeto service registrado, valida si sigue vivo
            existing = _services.get(key)
            if existing and await wait_for_appium_ready(host, port, timeout=2):
                print(f"[AppiumServerManager] Appium ya está en ejecución en {host}:{port}")
                return port

            # Crear y arrancar
            service = AppiumService()
            args = [
                "--address", host,
                "-p", str(port),
                "--allow-cors",
                "--session-override",
                "--log", str(logs_path),
            ]
            try:
                await asyncio.to_thread(service.start, args=args)
                _services[key] = service
            except Exception as e:
                raise RuntimeError(f"No se pudo iniciar Appium en {host}:{port}: {e}") from e

        # Wait until ready
        ready = await wait_for_appium_ready(host, port, timeout=wait_timeout)
        if not ready:
            # Si no quedó listo, limpiamos el registro
            async with _services_lock:
                _services.pop((host, port), None)
            raise RuntimeError(f"Appium no respondió a tiempo en {host}:{port}")

        print(f"[AppiumServerManager] Appium está listo en http://{host}:{port}")
        return port

    @staticmethod
    async def stop_appium_server(host: Optional[str] = None, port: Optional[int] = None, timeout: float = 5.0, retry_interval: float = 0.5) -> None:
        """
        Detiene la instancia de Appium en (host, port) y verifica que el puerto se libere.

        Args:
            host (Optional[str]): Dirección del host donde está corriendo Appium. Por defecto, usa APPIUM_HOST o '127.0.0.1'.
            port (Optional[int]): Puerto donde está corriendo Appium. Obligatorio.
            timeout (float): Tiempo máximo (en segundos) para esperar a que el puerto se libere. Por defecto, 5 segundos.
            retry_interval (float): Intervalo entre reintentos (en segundos) para verificar el puerto. Por defecto, 0.5 segundos.

        Raises:
            ValueError: Si no se proporciona el puerto.
            RuntimeError: Si no se puede detener Appium o el puerto no se libera dentro del tiempo especificado.
        """
        host = host or os.getenv("APPIUM_HOST", "127.0.0.1")
        if port is None:
            raise ValueError("Debes indicar 'port' para detener una instancia específica.")

        key = (host, int(port))
        async with _services_lock:
            service = _services.pop(key, None)

        if not service:
            print(f"[AppiumServerManager] No hay instancia registrada en {host}:{port}")
            return

        try:
            # Detener el servicio de Appium
            await asyncio.to_thread(service.stop)
            print(f"[AppiumServerManager] Solicitud enviada para detener Appium en {host}:{port}.")

            # Verificar si el puerto se ha liberado
            start_time = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - start_time < timeout:
                try:
                    # Intentar conectar al puerto para verificar si está en uso
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                        sock.settimeout(0.1)
                        result = sock.connect_ex((host, port))
                        if result != 0:  # Puerto libre (no se pudo conectar)
                            print(f"[AppiumServerManager] Appium detenido correctamente en {host}:{port}. Puerto liberado.")
                            return
                except Exception as e:
                    print(f"[AppiumServerManager] Error al verificar el puerto {host}:{port}: {e}")
                    break
                await asyncio.sleep(retry_interval)

            raise RuntimeError(f"No se pudo confirmar que Appium se detuvo en {host}:{port}. El puerto sigue en uso.")

        except Exception as e:
            print(f"[AppiumServerManager] Error al detener Appium en {host}:{port}: {e}")
            raise RuntimeError(f"Fallo al detener Appium en {host}:{port}: {e}")

    @staticmethod
    async def stop_all() -> None:
        """
        Detiene todas las instancias registradas.
        """
        async with _services_lock:
            items = list(_services.items())
            _services.clear()

        for (host, port), service in items:
            try:
                await asyncio.to_thread(service.stop)
                print(f"[AppiumServerManager] Appium detenido en {host}:{port}.")
            except Exception as e:
                print(f"[AppiumServerManager] Error al detener {host}:{port}: {e}")
