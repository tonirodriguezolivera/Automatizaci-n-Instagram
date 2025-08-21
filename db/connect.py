import sqlite3
from typing import List, Tuple

class DB:
    """Clase genérica para manejar conexiones y creación de tablas en SQLite."""
    
    def __init__(self, db_name: str = "surviral_insta.db"):
        """Inicializa la conexión a la base de datos.
        
        Args:
            db_name (str): Nombre del archivo de la base de datos (por defecto 'surviral_insta.db').
        """
        self.db_name = db_name
        self.conn = None
        self.cursor = None
    
    def connect(self):
        """Establece la conexión a la base de datos y crea un cursor."""
        try:
            self.conn = sqlite3.connect(self.db_name)
            self.cursor = self.conn.cursor()
        except sqlite3.Error as e:
            raise Exception(f"Error al conectar a la base de datos: {e}")
    
    def create_table(self, table_name: str, columns: str):
        """Crea una tabla en la base de datos si no existe.
        
        Args:
            table_name (str): Nombre de la tabla.
            columns (str): Definición de columnas en formato SQL (ej. 'id INTEGER PRIMARY KEY, name TEXT').
        """
        try:
            self.cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS {table_name} (
                    {columns}
                )
            ''')
            self.conn.commit()
        except sqlite3.Error as e:
            raise Exception(f"Error al crear la tabla {table_name}: {e}")
    
    def execute_query(self, query: str, params: tuple = ()):
        """Ejecuta una consulta SQL con parámetros opcionales.
        
        Args:
            query (str): Consulta SQL a ejecutar.
            params (tuple): Parámetros para la consulta (para evitar inyecciones SQL).
        
        Returns:
            List[Tuple]: Resultados de la consulta si es SELECT, None en caso contrario.
        """
        try:
            self.cursor.execute(query, params)
            if query.strip().upper().startswith("SELECT"):
                return self.cursor.fetchall()
            self.conn.commit()
            return None
        except sqlite3.Error as e:
            raise Exception(f"Error al ejecutar la consulta: {e}")
    
    def close(self):
        """Cierra la conexión a la base de datos."""
        if self.conn:
            self.conn.close()