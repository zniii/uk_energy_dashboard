import os
from datetime import datetime, timezone
import requests
from db_client import supabase

def fetch_live_metrics():
    print("Initiating live generation pipeline...")

    response = supabase.table('energy_assets').select('id, type, capacity_mw').execute()
    assets = response.data

    if not assets:
        print("Error: No assets found in the database")
        return
    
    #fetching live national telemetry from Grid API
    try:
        grid_url = "https://api.carbonintensity.org.uk/generation"
        grid_response = requests.get(grid_url)
        grid_response.raise_for_status()
        live_data = grid_response.json()

        generation_mix = live_data['data']['generationmix']

        #extracting current percentage output for fuel type
        wind_pct = next((item['perc'] for item in generation_mix if item['fuel'] == 'wind'),0)
        solar_pct = next((item['perc'] for item in generation_mix if item['fuel'] == 'solar'),0)

        battery_pct = 15.0

        print(f"Grid Status -> Wind: {wind_pct}%, Solar: {solar_pct}%, Battery: {battery_pct}%")

    except requests.exceptions.RequestException as e:
        print(f"Critical Error: Fail to connect to National Grid API. {e}")
        return
    
    #calculating proportional distribution
    current_time = datetime.now(timezone.utc).isoformat()
    metrics_to_insert = []

    for asset in assets:
        asset_type = asset['type']
        max_cap = asset['capacity_mw']

        if asset_type == 'wind':
            cur_gen = max_cap * (wind_pct / 100.0)
        elif asset_type == 'solar':
            cur_gen = max_cap * (solar_pct / 100.0)
        else:
            cur_gen = max_cap * (battery_pct / 100.0)


        metrics_to_insert.append({
            "asset_id": asset['id'],
            "generation_mw": round(cur_gen, 2),
            "recorded_at": current_time
        }) 

    print(f"Uploading {len(metrics_to_insert)} live metric records...")

    batch_size = 500
    for i in range(0, len(metrics_to_insert), batch_size):
        batch = metrics_to_insert[i:i + batch_size]
        supabase.table('generation_metrics').insert(batch).execute()

    print("Live data pipeline executed successfully.")



if __name__ == "__main__":
    fetch_live_metrics()
