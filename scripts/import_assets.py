import os
import re
from pathlib import Path
import pandas as pd
import chardet
from pyproj import Transformer
from db_client import supabase

def process_and_upload_assets():
    print("Loading statis asset data...")

    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent
    csv_path = project_root/"data"/"repd_data.csv"

    with open(csv_path, 'rb') as raw_file:
        raw_data = raw_file.read(10000) #for guessing the encoding
        result = chardet.detect(raw_data)
        detected_encoding = result['encoding']

    try:
        df = pd.read_csv(csv_path, encoding=detected_encoding)
    except FileNotFoundError:
        print("Error: Please place the repd_data.csv file in the data/ directory")
        return

    # filter the data only for operational wind, solar and battery site
    target_techs = ['Wind Onshore', 'Wind Offshore', 'Solar Photovoltaics', 'Battery']
    df = df[df['Technology Type'].isin(target_techs)]
    df = df[df['Development Status'] == 'Operational']

    #transform and map the data to SQL schema
    transfromer = Transformer.from_crs("EPSG:27700", "EPSG:4326")
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
        x_val = str(row.get('X-coordinate', ''))
        y_val = str(row.get('Y-coordinate', ''))

        x_clean = re.sub(r'[^\d.-]', '', x_val)
        y_clean = re.sub(r'[^\d.-]', '', y_val)

        if not x_clean or not y_clean:
            continue
        
        try:
            x = float(x_clean)
            y = float(y_clean)
        except ValueError:
            print(f"Warning: Skipping unreadable coordinates at row {index} -> X:{x_val}, Y: {y_val}")
            continue

        lat, lon = transfromer.transform(x,y)
        postgis_point = f"Point({lon} {lat})"

        raw_cap = row.get('Installed Capacity (MWelec)')

        if pd.isna(raw_cap):
            capacity_mw = 0.0
        else:
            capacity_raw = str(raw_cap)
            capacity_clean = re.sub(r'[^\d.]', '', capacity_raw)

            try:
                capacity_mw = float(capacity_clean) if capacity_clean else 0.0

                if pd.isna(capacity_mw):
                    capacity_mw = 0.0

            except ValueError:
                print(f"Warning: Defaulting capacity to 0 for row {index} due to unreadable data: {capacity_raw}")
                capacity_mw = 0.0

        #construction the dictonary
        record = {
            "asset_name": str(row.get('Site Name', 'Unknown')),
            "type": asset_type,
            "capacity_mw": capacity_mw,
            "location": postgis_point,
            "operator": str(row.get('Operator (or Applicant)', 'Unknown'))
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