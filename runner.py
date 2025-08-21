from db.connect import DB
from db.users import Users
from db.avds import Avds

# Ejemplo de uso
if __name__ == "__main__":
    # Crear instancia de DB
    db = DB("./db/surviral_insta.db")
    
    # Crear instancias de Users y Avds
    users = Users(db)
    avds = Avds(db)
    
    users.close()