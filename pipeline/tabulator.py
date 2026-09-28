import os
import json
import pandas as pd
from typing import List, Dict, Any, Optional
from pipeline.config import TABLES_DIR, DATA_EXTRACTION_SPECS_PATH

class Tabulator:
    """Converts extracted daily entities and laboratory reports into human-readable timeline tables and the 199-column CRF database."""

    def __init__(
        self,
        all_patient_extractions: Dict[str, List[Dict[str, Any]]],
        all_patient_microbiology: Optional[Dict[str, List[Dict[str, Any]]]] = None
    ):
        self.patient_extractions = all_patient_extractions
        self.patient_microbiology = all_patient_microbiology or {}

    def generate_timeline_rows(self) -> List[Dict[str, Any]]:
        rows = []
        for patient_id, days in self.patient_extractions.items():
            # 1. Add verified laboratory reports
            for m in self.patient_microbiology.get(patient_id, []):
                if m.get("is_positive"):
                    spec = m.get("specimen") or "COLTURA"
                    p_date = m.get("prelievo_date") or ""
                    isol = ", ".join(m.get("isolates", [])) or "Positivo"
                    cfu_str = f" (CFU: {m['cfu']})" if m.get("cfu") else ""
                    dtp_str = f" (DTP: {m['dtp']})" if m.get("dtp") else ""
                    rows.append({
                        "Paziente": f"Paziente_{patient_id}",
                        "Data": p_date,
                        "Giorno_Degenza": "Referto Lab",
                        "Categoria": "Microbiologia (Referto PDF)",
                        "Parametro": spec,
                        "Valore": f"POSITIVO: {isol}{cfu_str}{dtp_str}",
                        "Evidenza_Testuale": f"File referto: {m.get('filename')}",
                        "Modello": "Microbiologia Ufficiale"
                    })

            # 2. Add LLM extracted entities from each day
            for day in sorted(days, key=lambda x: x.get("day_number", 1)):
                d_date = day.get("date", "")
                d_num = day.get("day_number", 1)
                model = day.get("model", "")
                ent = day.get("entities", {})

                # Vital signs
                sv = ent.get("segni_vitali") or ent.get("segni_vitali_sintomi", {})
                feb = sv.get("febbre") or ent.get("febbre", {})
                if feb.get("presente") and not feb.get("negato"):
                    tc_val = feb.get("tc_valore") or feb.get("tc_max") or feb.get("valore_max") or ">38°C"
                    rows.append({
                        "Paziente": f"Paziente_{patient_id}",
                        "Data": d_date,
                        "Giorno_Degenza": f"Day {d_num}",
                        "Categoria": "Segni Vitali",
                        "Parametro": "FEBBRE",
                        "Valore": str(tc_val),
                        "Evidenza_Testuale": feb.get("testo_estratto") or feb.get("evidenza") or "",
                        "Modello": model
                    })

                hypo = sv.get("ipotensione") or ent.get("ipotensione", {})
                if hypo.get("presente") and not hypo.get("negato"):
                    pas_val = hypo.get("pas_valore") or hypo.get("pas_min") or hypo.get("pressione_sistolica_min") or "≤90"
                    rows.append({
                        "Paziente": f"Paziente_{patient_id}",
                        "Data": d_date,
                        "Giorno_Degenza": f"Day {d_num}",
                        "Categoria": "Segni Vitali",
                        "Parametro": "IPOTENSIONE",
                        "Valore": str(pas_val),
                        "Evidenza_Testuale": hypo.get("testo_estratto") or hypo.get("evidenza") or "",
                        "Modello": model
                    })

                briv = sv.get("brividi") or ent.get("brividi", {})
                if briv.get("presente") and not briv.get("negato"):
                    rows.append({
                        "Paziente": f"Paziente_{patient_id}",
                        "Data": d_date,
                        "Giorno_Degenza": f"Day {d_num}",
                        "Categoria": "Segni Vitali",
                        "Parametro": "BRIVIDI",
                        "Valore": "SI",
                        "Evidenza_Testuale": briv.get("testo_estratto") or briv.get("evidenza") or "",
                        "Modello": model
                    })

                # Devices
                devices = ent.get("catetere_venoso") or ent.get("dispositivi_invasivi", {})
                if devices.get("cvc_in_sede") or devices.get("cvc_presente"):
                    rows.append({
                        "Paziente": f"Paziente_{patient_id}",
                        "Data": d_date,
                        "Giorno_Degenza": f"Day {d_num}",
                        "Categoria": "Dispositivi Invasivi",
                        "Parametro": "CVC_IN_SEDE",
                        "Valore": "SI",
                        "Evidenza_Testuale": devices.get("testo_estratto") or devices.get("evidenza") or "CVC presente",
                        "Modello": model
                    })
                if devices.get("cvc_inserito_oggi"):
                    rows.append({
                        "Paziente": f"Paziente_{patient_id}",
                        "Data": d_date,
                        "Giorno_Degenza": f"Day {d_num}",
                        "Categoria": "Dispositivi Invasivi",
                        "Parametro": "CVC_INSERITO",
                        "Valore": "OGGI",
                        "Evidenza_Testuale": devices.get("testo_estratto") or devices.get("evidenza") or "Inserzione CVC",
                        "Modello": model
                    })
                if devices.get("cvc_rimosso_oggi"):
                    rows.append({
                        "Paziente": f"Paziente_{patient_id}",
                        "Data": d_date,
                        "Giorno_Degenza": f"Day {d_num}",
                        "Categoria": "Dispositivi Invasivi",
                        "Parametro": "CVC_RIMOSSO",
                        "Valore": "OGGI",
                        "Evidenza_Testuale": devices.get("testo_estratto") or devices.get("evidenza") or "Rimozione CVC",
                        "Modello": model
                    })
                if devices.get("segni_infezione_sito_pus_eritema") or devices.get("infezione_sito_inserzione_pus_eritema"):
                    rows.append({
                        "Paziente": f"Paziente_{patient_id}",
                        "Data": d_date,
                        "Giorno_Degenza": f"Day {d_num}",
                        "Categoria": "Dispositivi Invasivi",
                        "Parametro": "CVC_INFEZIONE_SITO",
                        "Valore": "PUS/ERITEMA",
                        "Evidenza_Testuale": devices.get("testo_estratto") or devices.get("evidenza") or "",
                        "Modello": model
                    })

                # Microbiology extracted from diary note
                micro_list = ent.get("microbiologia")
                if micro_list is None and isinstance(ent.get("microbiologia_rilevata"), dict):
                    micro_list = ent.get("microbiologia_rilevata", {}).get("emocolture", [])
                elif not isinstance(micro_list, list):
                    micro_list = []

                for item in micro_list:
                    tipo = str(item.get("tipo_campione") or item.get("tipo", "")).upper()
                    if item.get("esito_positivo"):
                        cfu_str = f" (CFU: {item.get('carica_cfu')})" if item.get("carica_cfu") else ""
                        dtp_str = f" (DTP: {item.get('dtp')})" if item.get("dtp") else ""
                        rows.append({
                            "Paziente": f"Paziente_{patient_id}",
                            "Data": d_date,
                            "Giorno_Degenza": f"Day {d_num}",
                            "Categoria": "Microbiologia (Diario Clinico)",
                            "Parametro": tipo or "COLTURA",
                            "Valore": f"POSITIVO: {item.get('microrganismo')}{cfu_str}{dtp_str}",
                            "Evidenza_Testuale": item.get("testo_estratto") or item.get("evidenza") or "",
                            "Modello": model
                        })

                # Secondary foci
                foci_list = ent.get("focolai_infezione") or ent.get("focolai_secondari", [])
                if isinstance(foci_list, list):
                    for f_item in foci_list:
                        if f_item.get("sospetto_o_conferma"):
                            rows.append({
                                "Paziente": f"Paziente_{patient_id}",
                                "Data": d_date,
                                "Giorno_Degenza": f"Day {d_num}",
                                "Categoria": "Focolaio Secondario Infezione",
                                "Parametro": str(f_item.get("sito", "FOCOLAIO")).upper(),
                                "Valore": "SOSPETTO/CONFERMATO",
                                "Evidenza_Testuale": f_item.get("testo_estratto") or f_item.get("evidenza") or "",
                                "Modello": model
                            })

                # Setting / admission
                adm = ent.get("ammissione") or ent.get("anamnesi_e_setting", {})
                prov = adm.get("provenienza") or adm.get("luogo_provenienza")
                if prov and prov != "SCONOSCIUTA" and d_num == 1:
                    rows.append({
                        "Paziente": f"Paziente_{patient_id}",
                        "Data": d_date,
                        "Giorno_Degenza": f"Day {d_num}",
                        "Categoria": "Setting / Ammissione",
                        "Parametro": "PROVENIENZA",
                        "Valore": str(prov),
                        "Evidenza_Testuale": adm.get("testo_estratto") or adm.get("evidenza") or "",
                        "Modello": model
                    })

        return rows

    def save_timeline_table(self, filename_prefix: str = "master_timeline") -> str:
        rows = self.generate_timeline_rows()
        df = pd.DataFrame(rows)
        if df.empty:
            df = pd.DataFrame(columns=["Paziente", "Data", "Giorno_Degenza", "Categoria", "Parametro", "Valore", "Evidenza_Testuale", "Modello"])

        csv_path = os.path.join(TABLES_DIR, f"{filename_prefix}.csv")
        xlsx_path = os.path.join(TABLES_DIR, f"{filename_prefix}.xlsx")

        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        df.to_excel(xlsx_path, index=False)
        return xlsx_path

    def populate_db_schema(self, classified_results: Dict[str, Dict[str, Any]], filename_prefix: str = "db_populated") -> str:
        """Populates the columns defined in sheet 'DB' of llm-data-extraction v1.3.xlsx."""
        try:
            xl = pd.ExcelFile(DATA_EXTRACTION_SPECS_PATH)
            db_template = pd.read_excel(xl, "DB")
            template_columns = db_template.columns.tolist()
        except Exception:
            template_columns = ["ID paziente", "BSI", "HA-BSI", "S-UTI", "S-SST", "S-DIG", "S-PUL", "SCONOSCIUTA", "CURR"]

        populated_rows = []
        for patient_id, days in self.patient_extractions.items():
            row_dict = {col: "" for col in template_columns}
            row_dict["ID paziente"] = f"Paziente_{patient_id}"

            c_res = classified_results.get(patient_id, {})
            bsi_val = c_res.get("bsi", "NO")
            ha_val = c_res.get("ha_bsi", "NO")
            orig_val = c_res.get("origine", "")
            setting_val = c_res.get("luogo_acquisizione", "")

            if "BSI" in row_dict:
                row_dict["BSI"] = 1 if bsi_val == "SI" else 0
            if "HA-BSI" in row_dict:
                row_dict["HA-BSI"] = 1 if ha_val == "SI" else 0
            if "CA-BSI" in row_dict:
                row_dict["CA-BSI"] = 1 if (bsi_val == "SI" and ha_val == "NO") else 0

            # Source flags
            if orig_val == "S-UTI" and "S-UTI" in row_dict:
                row_dict["S-UTI"] = 1
            elif orig_val == "S-SST" and "S-SST" in row_dict:
                row_dict["S-SST"] = 1
            elif orig_val == "S-DIG" and "S-DIG" in row_dict:
                row_dict["S-DIG"] = 1
            elif orig_val == "S-PUL" and "S-PUL" in row_dict:
                row_dict["S-PUL"] = 1
            elif orig_val == "UO" and "SCONOSCIUTA" in row_dict:
                row_dict["SCONOSCIUTA"] = 1
            elif orig_val == "CRI3-CVC" and "CRI3-CVC" in row_dict:
                row_dict["CRI3-CVC"] = 1

            # Setting flags
            if setting_val == "CURR" and "CURR" in row_dict:
                row_dict["CURR"] = 1
            elif setting_val == "OHOSP" and "OHOSP" in row_dict:
                row_dict["OHOSP"] = 1
            elif setting_val == "LTCF" and "LTCF" in row_dict:
                row_dict["LTCF"] = 1

            if orig_val and orig_val not in ("UO", "") and "Secondarie" in row_dict:
                row_dict["Secondarie"] = 1

            # Isolated pathogens from verified laboratory microbiology
            micro_list = self.patient_microbiology.get(patient_id, [])
            pos_bcs = [
                m for m in micro_list 
                if ("EMOCOLTURA" in str(m.get("specimen", "")).upper() or "PERIFERICA" in str(m.get("specimen", "")).upper()) 
                and m.get("is_positive")
            ]
            if "n_emocolture_positive" in row_dict:
                row_dict["n_emocolture_positive"] = len(pos_bcs)

            for idx, bc in enumerate(pos_bcs):
                isol = ", ".join(bc.get("isolates", [])) or "Isolato emocoltura"
                is_contaminant = any(c in isol.lower() for c in ("staphylococcus coagulasi negativo", "cns", "corynebacterium", "propionibacterium"))
                if idx == 0:
                    if "nome_microrganismo_isolato1" in row_dict:
                        row_dict["nome_microrganismo_isolato1"] = isol
                    if "data_emocoltura_positiva1" in row_dict:
                        row_dict["data_emocoltura_positiva1"] = bc.get("prelievo_date")
                    if "patogeno_riconosciuto1" in row_dict:
                        row_dict["patogeno_riconosciuto1"] = 0 if is_contaminant else 1
                    if "contaminante_pelle1" in row_dict:
                        row_dict["contaminante_pelle1"] = 1 if is_contaminant else 0
                elif idx == 1:
                    if "nome_microrganismo_isolato2" in row_dict:
                        row_dict["nome_microrganismo_isolato2"] = isol
                    if "data_emocoltura_positiva2" in row_dict:
                        row_dict["data_emocoltura_positiva2"] = bc.get("prelievo_date")
                    if "patogeno_riconosciuto2" in row_dict:
                        row_dict["patogeno_riconosciuto2"] = 0 if is_contaminant else 1
                    if "contaminante_pelle2" in row_dict:
                        row_dict["contaminante_pelle2"] = 1 if is_contaminant else 0

            # Fallback for diagnostic pathogen from classification if no lab PDF available
            diag_pathogen = c_res.get("diagnostic_pathogen")
            if diag_pathogen and not row_dict.get("nome_microrganismo_isolato1"):
                if "nome_microrganismo_isolato1" in row_dict:
                    row_dict["nome_microrganismo_isolato1"] = diag_pathogen
                if "data_emocoltura_positiva1" in row_dict:
                    row_dict["data_emocoltura_positiva1"] = c_res.get("diagnostic_date", "")
                if "n_emocolture_positive" in row_dict and not row_dict["n_emocolture_positive"]:
                    row_dict["n_emocolture_positive"] = 1
                if "patogeno_riconosciuto1" in row_dict and row_dict["patogeno_riconosciuto1"] == "":
                    row_dict["patogeno_riconosciuto1"] = 1

            # Urocolture
            pos_uros = [
                m for m in micro_list 
                if ("UROCOLTURA" in str(m.get("specimen", "")).upper() or "URINA" in str(m.get("specimen", "")).upper()) 
                and m.get("is_positive")
            ]
            if pos_uros:
                u = pos_uros[0]
                if "urinocoltura_pos" in row_dict:
                    row_dict["urinocoltura_pos"] = 1
                if "data_urinocoltura_pos" in row_dict:
                    row_dict["data_urinocoltura_pos"] = u.get("prelievo_date")
                if "microrganismo_urinocoltura" in row_dict:
                    row_dict["microrganismo_urinocoltura"] = ", ".join(u.get("isolates", [])) or "Positiva"
            else:
                # Fallback: check if positive urocolture was extracted in daily diaries
                for d in days:
                    ent = d.get("entities", {})
                    for m in ent.get("microbiologia", []):
                        if "URO" in str(m.get("tipo_campione", "")).upper() and m.get("esito_positivo"):
                            if "urinocoltura_pos" in row_dict:
                                row_dict["urinocoltura_pos"] = 1
                            if "data_urinocoltura_pos" in row_dict and not row_dict["data_urinocoltura_pos"]:
                                row_dict["data_urinocoltura_pos"] = d.get("date")
                            if "microrganismo_urinocoltura" in row_dict and not row_dict["microrganismo_urinocoltura"]:
                                row_dict["microrganismo_urinocoltura"] = m.get("microrganismo") or "Positiva"

            # Scan days for vital signs & symptoms from LLM extractions
            for d in days:
                ent = d.get("entities", {})
                sv = ent.get("segni_vitali") or ent.get("segni_vitali_sintomi", {})
                feb = sv.get("febbre") or ent.get("febbre", {})
                if feb.get("presente") and not feb.get("negato") and "Febbre" in row_dict:
                    row_dict["Febbre"] = 1
                    if "valore_temperatura_massima" in row_dict and not row_dict["valore_temperatura_massima"]:
                        row_dict["valore_temperatura_massima"] = feb.get("tc_valore") or feb.get("tc_max")
                    if "data_temperatura_max" in row_dict and not row_dict["data_temperatura_max"]:
                        row_dict["data_temperatura_max"] = d.get("date")

                briv = sv.get("brividi") or ent.get("brividi", {})
                if briv.get("presente") and not briv.get("negato") and "Brividi" in row_dict:
                    row_dict["Brividi"] = 1
                    if "data_brividi" in row_dict and not row_dict["data_brividi"]:
                        row_dict["data_brividi"] = d.get("date")

                hypo = sv.get("ipotensione") or ent.get("ipotensione", {})
                if hypo.get("presente") and not hypo.get("negato") and "ipotensione" in row_dict:
                    row_dict["ipotensione"] = 1
                    if "valore_pressione_sistolica_min" in row_dict and not row_dict["valore_pressione_sistolica_min"]:
                        row_dict["valore_pressione_sistolica_min"] = hypo.get("pas_valore") or hypo.get("pas_min")

                # Admission info from day 1
                if d.get("day_number") == 1:
                    if "data_ingresso_in_ospedale" in row_dict:
                        row_dict["data_ingresso_in_ospedale"] = d.get("date")
                    adm = ent.get("ammissione", {})
                    if "luogo_origine_pz" in row_dict:
                        row_dict["luogo_origine_pz"] = adm.get("provenienza") or "DOMICILIO"

                # Secondary infection foci from daily notes
                foci = ent.get("focolai_infezione", [])
                if isinstance(foci, list):
                    for f in foci:
                        sito = str(f.get("sito", "")).upper()
                        if f.get("sospetto_o_conferma"):
                            if "UTI" in sito and "S-UTI" in row_dict:
                                row_dict["S-UTI"] = 1
                            elif "PUL" in sito and "S-PUL" in row_dict:
                                row_dict["S-PUL"] = 1
                            elif "DIG" in sito and "S-DIG" in row_dict:
                                row_dict["S-DIG"] = 1
                            elif "SST" in sito and "S-SST" in row_dict:
                                row_dict["S-SST"] = 1
                            elif "SSI" in sito and "S-SSI" in row_dict:
                                row_dict["S-SSI"] = 1

            populated_rows.append(row_dict)

        out_df = pd.DataFrame(populated_rows)
        out_path = os.path.join(TABLES_DIR, f"{filename_prefix}.xlsx")
        out_df.to_excel(out_path, index=False)
        return out_path
