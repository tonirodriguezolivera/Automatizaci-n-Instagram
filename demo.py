import asyncio
import multiprocessing
from collections import defaultdict

# El array de usuarios (copiado de la consulta original)
users = [
    {
        "user": "dianebutler4083",
        "password": "9tsi3tjnc1",
        "key": "M3NO VD76 36DM PH6M 5FKV UVPV YXF6 5JPI",
        "new_password": "pass_nuevo2",
        "avd_name": "Nexus_5_API_31_Clone1"
    },
    {
        "user": "sarasnyder1798",
        "password": "6w437kb656",
        "key": "WWQH L5BG FHLO ZDQL 3BJX PMTY EC2G LFPF",
        "new_password": "pass_nuevo3",
        "avd_name": "Nexus_5_API_31_Clone1"
    },
    {
        "user": "lisabarrett3952",
        "password": "2jlvx3yar3",
        "key": "6HSE HFCO JBVN AOTB 3MRK 6434 VDAV RKQU",
        "new_password": "pass_nuevo4",
        "avd_name": "Nexus_5_API_31_Clone1"
    },
    {
        "user": "rachelcarr6206",
        "password": "4i8bh8bzm2",
        "key": "Q5AP 77DS IVIR RGRB JV3M MRBU NV4N XUKS",
        "new_password": "pass_nuevo5",
        "avd_name": "Nexus_5_API_31_Clone1"
    },
    {
        "user": "nancypearson4528",
        "password": "8eofzaosk6",
        "key": "T5YE DPIT W43K Z56T IGV4 YFXU EFPS QJBI",
        "new_password": "pass_nuevo6",
        "avd_name": "Nexus_5_API_31_Clone1"
    },
    {
        "user": "angelamason4501",
        "password": "3dkifyrll4",
        "key": "G5B4 SEYO V7AC M7XR BQXX SRUP O4G3 P3BW",
        "new_password": "pass_nuevo7",
        "avd_name": "Nexus_5_API_31_Clone2"
    },
    {
        "user": "annavaldez861",
        "password": "1sqi4s48v9",
        "key": "FCL3 CKHK AJWT XVNR I4KY CQ2I QOBO A5FA",
        "new_password": "pass_nuevo8",
        "avd_name": "Nexus_5_API_31_Clone2"
    },
    {
        "user": "marthawebb1079",
        "password": "3xglwea8h0",
        "key": "GJCQ 7WH2 GX77 7G5H RVLX W2CS 7MRJ MAGD",
        "new_password": "pass_nuevo9",
        "avd_name": "Nexus_5_API_31_Clone2"
    },
    {
        "user": "dorisguerrero141",
        "password": "36x7in1mz1",
        "key": "LPUU VZZT U2WM FY6J 4J62 EA27 7WNB HHAA",
        "new_password": "pass_nuevo10",
        "avd_name": "Nexus_5_API_31_Clone2"
    },
    {
        "user": "joantran940",
        "password": "94bxhijfm2",
        "key": "Z6VB ZBYC TK4V HMCG KAEZ AX5M NQ6O HTRX",
        "new_password": "pass_nuevo11",
        "avd_name": "Nexus_5_API_31_Clone2"
    },
    {
        "user": "francesjohnston90",
        "password": "3o5sp1zve6",
        "key": "TIJS G65E IVFZ 3VX5 6UBG JW6I SUVV AKC7",
        "new_password": "pass_nuevo12",
        "avd_name": "Nexus_5_API_31_Clone4"
    },
    {
        "user": "betty3739williams",
        "password": "8xn7ci9qr0",
        "key": "PPS6 JETO GX7G 7YUG XCII 2WTA BCJ2 TVOQ",
        "new_password": "pass_nuevo13",
        "avd_name": "Nexus_5_API_31_Clone4"
    },
    {
        "user": "dorothypatterson97",
        "password": "7w5kvhrq82",
        "key": "Z4WO UNU2 NP7D CPA2 HJON S3HE F7GW ZJKY",
        "new_password": "pass_nuevo14",
        "avd_name": "Nexus_5_API_31_Clone4"
    },
    {
        "user": "emmagonzalez3111",
        "password": "104jp46tn3",
        "key": "A2UH TUAL 53LI TP3D TNUX VNNL 4VHL 3VJV",
        "new_password": "pass_nuevo15",
        "avd_name": "Nexus_5_API_31_Clone4"
    },
    {
        "user": "catherinehill5495",
        "password": "8pjuapfmo6",
        "key": "5P2D 6LOK EDA7 ALPR HJ46 SJQI YGGM YV5O",
        "new_password": "pass_nuevo16",
        "avd_name": "Nexus_5_API_31_Clone4"
    },
    {
        "user": "victoriabanks734",
        "password": "9n5pqt0ut4",
        "key": "43NV HAWQ 6TQN LIAL 25QL SP7Y RSEM 2GXH",
        "new_password": "pass_nuevo17",
        "avd_name": "Nexus_5_API_31_Clone5"
    },
    {
        "user": "bettylarson312",
        "password": "1dqrua8wl4",
        "key": "BFCW P7YD HM47 T2F6 EVBE RGZY 72RX UPMQ",
        "new_password": "pass_nuevo18",
        "avd_name": "Nexus_5_API_31_Clone5"
    }
]

# Función asíncrona para procesar un usuario
async def process_user(user, avd_name):
    # Aquí va tu lógica real (ej: cambiar contraseña usando user, password, key, new_password)
    # Simulación: imprimir y esperar 1 segundo
    print(f"Iniciando procesamiento de {user['user']} en {avd_name}")
    await asyncio.sleep(1)  # Simula el tiempo de lanzamiento del AVD y operación
    print(f"Terminado procesamiento de {user['user']} en {avd_name}")

# Función asíncrona para procesar un grupo de usuarios secuencialmente
async def process_group_async(avd_name, user_list):
    for user in user_list:
        await process_user(user, avd_name)
        

# Función síncrona para ejecutar el bucle de eventos en un proceso
def process_group_sync(avd_name, user_list):
    asyncio.run(process_group_async(avd_name, user_list))

def main():
    # Agrupar usuarios por avd_name
    groups = defaultdict(list)
    for user in users:
        groups[user['avd_name']].append(user)

    print(f"Procesando {len(users)} usuarios en {len(groups)} grupos por AVD.")
    # Ejecutar en paralelo con máximo 3 procesos
    with multiprocessing.Pool(processes=2) as pool:
        # Preparar los argumentos para cada grupo
        tasks = [(avd_name, user_list) for avd_name, user_list in groups.items()]
        # Ejecutar los procesos
        pool.starmap(process_group_sync, tasks)

    print("Todos los usuarios procesados.")

if __name__ == '__main__':
    main()