import os
import requests
import datetime
from pytz import timezone
from fastapi import FastAPI
from supabase import create_client, Client

URL_STATUS = "https://valladolid.publicbikesystem.net/customer/gbfs/v2/en/station_status"
URL_INFO = "https://valladolid.publicbikesystem.net/customer/gbfs/v2/en/station_information"

app = FastAPI()

# Inicialización de Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

def cargar_nombres_estaciones():
    try:
        response = requests.get(URL_INFO).json()
        return {e["station_id"]: e["name"] for e in response["data"]["stations"]}
    except:
        return {}

@app.get("/")
def home():
    return {"mensaje": "API BIKI 2.0 unificada operativa. Usa /recolectar."}

@app.get("/recolectar")
def lanzar_recoleccion():
    if not supabase: 
        return {"status": "error", "detalle": "Faltan variables de entorno SUPABASE_URL y SUPABASE_KEY"}
    
    try:
        status_data = requests.get(URL_STATUS).json()
        nombres = cargar_nombres_estaciones()
        ahora = datetime.datetime.now(timezone('Europe/Madrid')).isoformat()
        
        registros = []
        for est in status_data['data']['stations']:
            id_est = est['station_id']
            electricas = sum(t['count'] for t in est.get('vehicle_types_available', []) if t['vehicle_type_id'] == "EFIT")
            normales = sum(t['count'] for t in est.get('vehicle_types_available', []) if t['vehicle_type_id'] == "FIT")

            registros.append({
                "id": id_est,
                "nombre": nombres.get(id_est, id_est),
                "timestamp": ahora,
                "num_bikes_available": est['num_bikes_available'],
                "num_docks_available": est['num_docks_available'],
                "num_bikes_disabled": est.get('num_bikes_disabled', 0),
                "num_docks_disabled": est.get('num_docks_disabled', 0),
                "electricas": electricas,
                "normales": normales,
                "total_bicis": electricas + normales
            })
        
        # Inserción batch en Supabase
        supabase.table("estados").insert(registros).execute()
        return {"status": "ok", "registradas": len(registros)}

    except Exception as e:
        return {"status": "error", "detalle": str(e)}