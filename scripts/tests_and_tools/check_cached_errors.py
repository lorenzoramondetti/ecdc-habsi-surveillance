import os, json, glob

# Check all cached extractions
cached_files = glob.glob(r"output\extractions\*\Paziente_*\*.json")
print(f"Total cached extraction files found: {len(cached_files)}")

error_count = 0
for f in cached_files:
    try:
        with open(f, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
            ent = data.get("entities", {})
            if "error" in ent:
                error_count += 1
                print(f"File with error: {os.path.basename(f)} -> {ent['error'][:60]}")
    except Exception as e:
        print("Corrupt file:", f, e)

print(f"Total files with errors: {error_count} / {len(cached_files)}")
