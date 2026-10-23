import os
import requests
import datetime
from pytz import timezone
from fastapi import FastAPI
from supabase import create_client, Client

URL_STATUS = "https://valladolid.publicbikesystem.net/customer/gbfs/v2/en/station_status"
URL_INFO = "https://valladolid.publicbikesystem.net/customer/gbfs/v2/en/station_information"

app = FastAPI()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

def sincronizar_estaciones():
    """Actualiza o inserta la información fija (coordenadas, capacidad, nombre)."""
    try:
        response = requests.get(URL_INFO, timeout=10).json()
        estaciones_data = []
        for est in response['data']['stations']:
            estaciones_data.append({
                "id": str(est['station_id']),
                "nombre": est.get('name'),
                "lat": est.get('lat'),
                "lon": est.get('lon'),
                "capacity": est.get('capacity')
            })
        # Upsert: inserta si no existe, actualiza si ya existe por 'id'
        supabase.table("estaciones").upsert(estaciones_data).execute()
        return True
    except Exception as e:
        print(f"Error sincronizando estaciones: {e}")
        return False

@app.get("/")
def home():
    return {"mensaje": "API BIKI 2.0 (Arquitectura 2 tablas) operativa."}

@app.get("/sync-estaciones")
def endpoint_sync():
    ok = sincronizar_estaciones()
    return {"status": "ok" if ok else "error"}

@app.get("/recolectar")
def lanzar_recoleccion():
    if not supabase:
        return {"status": "error", "detalle": "Variables de entorno Supabase no configuradas"}
    
    try:
        status_data = requests.get(URL_STATUS, timeout=10).json()
        ahora = datetime.datetime.now(timezone('Europe/Madrid')).isoformat()
        
        registros_estados = []
        for est in status_data['data']['stations']:
            # Conteo discriminado de vehículos
            electricas = sum(t['count'] for t in est.get('vehicle_types_available', []) if t.get('vehicle_type_id') == "EFIT")
            normales = sum(t['count'] for t in est.get('vehicle_types_available', []) if t.get('vehicle_type_id') == "FIT")
            
            # Conversión de timestamp nativo Unix a ISO (si existe)
            last_reported_ts = est.get('last_reported')
            last_rep_iso = datetime.datetime.fromtimestamp(last_reported_ts, tz=datetime.timezone.utc).isoformat() if last_reported_ts else None

            # Estados operativos booleanos (1 = True, 0 = False)
            is_renting = bool(est.get('is_renting', 1))
            is_returning = bool(est.get('is_returning', 1))

            registros_estados.append({
                "id": str(est['station_id']),
                "timestamp": ahora,
                "last_reported": last_rep_iso,
                "num_bikes_available": est.get('num_bikes_available', 0),
                "num_docks_available": est.get('num_docks_available', 0),
                "num_bikes_disabled": est.get('num_bikes_disabled', 0),
                "num_docks_disabled": est.get('num_docks_disabled', 0),
                "electricas": electricas,
                "normales": normales,
                "total_bicis": electricas + normales,
                "is_renting": is_renting,
                "is_returning": is_returning
            })
        
        # Volcado de telemetría a la tabla 'estados'
        supabase.table("estados").insert(registros_estados).execute()
        return {"status": "ok", "registradas": len(registros_estados)}

    except Exception as e:
        return {"status": "error", "detalle": str(e)}
