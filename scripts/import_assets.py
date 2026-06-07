import os
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client

#loading .env variables
load_dotenv()
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def process_and_upload_assets():
    print("Loading statis asset data...")

    #reading the csv file
    try:
        df = pd.read_csv('../data/repd_data.csv')
    except FileNotFoundError:
        print("Error: Please place the repd_data.csv file in the data/ directory")
        return

    # filter the data only for operational wind, solar and battery site
    target_techs = ['Wind Onshore', 'Wind Offshore', 'Solar Photovoltaics', 'Battery']
    df = df[df['Technology Type'].isin(target_techs)]
    df = df[df['Development Status'] == 'Operational']

    #transform and map the data to SQL schema
    records_to_insert = []

    for index, row in df.iterrows():
        #standarization to match SQL ENUM
        tech_type = str(row['Technology Type'].lower())
        if 'wind' in tech_type:
            asset_type = 'wind'
        elif 'solar' in tech_type:
            asset_type = 'solar'
        else:
            asset_type = 'battery'

        # coordinates for PostGIS
        lon = row['Longitude']
        lat = row['Latitude']
        postgis_point = f"Point({lon} {lat})"

        #construction the dictonary
        record = {
            "asset_name": str(row['Site Name']),
            "type": asset_type,
            "capacity_mw": float(row['Installed Capacity (MWe)']),
            "location": postgis_point,
            "operator": str(row['Operator (or Applicant)']) if pd.notna(row['Operator (or Apllicant)']) else "Unknown"
        }
        records_to_insert.append(record)

    print(f"Prepared {len(records_to_insert)} records. Pushing too Supabase...")

    #pushing the data to supabase
    batch_size = 500 #processing batch of 500 to avoid overwhelmig of the network
    for i in range(0, len(records_to_insert), batch_size):
        batch = records_to_insert[i:i + batch_size]
        response = supabase.table('energy_assets').insert(batch).execute()
        print(f"Successfully inserted batch {i // batch_size + 1}")

    print("Static infrastructure upload complete.")

if __name__  == "__main__":
    process_and_upload_assets()