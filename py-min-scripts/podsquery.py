import pandas as pd

def find_miners_by_giga(file_name, gigas):
    # Load and normalize column names
    site_map_scan = pd.read_csv(file_name)
    site_map_scan.columns = [c.strip().lower() for c in site_map_scan.columns]

    gigas = [g.strip().upper() for g in gigas]
    filtered = site_map_scan[site_map_scan["location"].str.upper().isin(gigas)]

    final_map = [
        f"{row['location']}:{row['serial']}"
        for _, row in filtered.iterrows()
    ]

    output_df = filtered[["location", "serial"]]
    output_file = "miners_by_giga_output.csv"
    output_df.to_csv(output_file, index=False)

    print("Matches found:", final_map)
    print(f"CSV created: {output_file}")



def find_miners_by_serial_number(file_name, serial_numbers):
    if isinstance(serial_numbers, str):
        serial_numbers = [serial_numbers]
    site_map_scan = pd.read_csv(file_name)
    site_map_scan.columns = [c.strip().lower() for c in site_map_scan.columns]

    serial_numbers = [str(s).strip().upper() for s in serial_numbers]
    
    filtered = site_map_scan[site_map_scan["serial"].astype(str).str.upper().isin(serial_numbers)]

    if not filtered.empty:
        # Create a list of results in 'serial:location' format
        results = [
            f"{row['location']}:{row['serial']}" 
            for _, row in filtered.iterrows()
        ]
        print("Matches found:", results)
        output_file = "found_serials_locations.csv"
        filtered[["location", "serial"]].to_csv(output_file, index=False)
        print(f"Results exported to {output_file}")
        
        return results
    else:
        print("No matches found for the provided serial numbers.")
        return []

