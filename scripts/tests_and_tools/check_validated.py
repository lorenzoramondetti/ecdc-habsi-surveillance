import os
import pandas as pd

excel_path = "Etichette cartelle_validazione umana.xlsx"
df = pd.read_excel(excel_path, sheet_name="Suddivisione Cartelle")

valid = df[df["BSI?"].notna() & (df["BSI?"].astype(str).str.strip() != "")].copy()
valid["clean_id"] = valid["Codice cartella cartella "].astype(str).str.strip()

pdir = "Prime cartelle cliniche anonimizzate"
existing_dirs = set(os.listdir(pdir))

found = []
missing = []

for idx, row in valid.iterrows():
    cid = row["clean_id"]
    folder_name = cid if cid.startswith("Paziente_") else f"Paziente_{cid}"
    folder_path = os.path.join(pdir, folder_name)
    has_folder = os.path.isdir(folder_path)
    
    info = {
        "excel_row": idx + 2,
        "record_db": row["Record DB Medcap"],
        "code": cid,
        "folder": folder_name,
        "folder_exists": has_folder,
        "bsi": row["BSI?"],
        "ha_bsi": row.get("HA BSI?"),
        "origine": row.get("Origine dell'infezione"),
        "luogo": row.get("Luogo acquisizione")
    }
    if has_folder:
        found.append(info)
    else:
        missing.append(info)

print(f"Total validated in Excel: {len(valid)}")
print(f"Found in '{pdir}': {len(found)}")
print(f"Missing from '{pdir}': {len(missing)}")

print("\nMissing items:")
for m in missing:
    print(m)

print("\nFound items summary:")
df_found = pd.DataFrame(found)
print("BSI distribution:")
print(df_found["bsi"].value_counts())
print("\nHA BSI distribution:")
print(df_found["ha_bsi"].value_counts(dropna=False))
