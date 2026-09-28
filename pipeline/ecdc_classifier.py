import os
import re
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from pipeline.config import SKIN_CONTAMINANTS

class ECDCClassifier:
    """Deterministic, rule-based classifier implementing ECDC PPS case definitions for BSI and HA-BSI."""

    def __init__(
        self,
        patient_id: str,
        daily_extractions: List[Dict[str, Any]],
        parsed_microbiology: Optional[List[Dict[str, Any]]] = None,
        is_neonate: bool = False,
        admission_reports: Optional[List[Dict[str, Any]]] = None
    ):
        self.patient_id = patient_id
        self.extractions = sorted(daily_extractions, key=lambda x: x.get("day_number", 1))
        self.parsed_microbiology = parsed_microbiology or []
        self.is_neonate = is_neonate
        self.admission_reports = admission_reports or []

    def _parse_date(self, d_str: str) -> Optional[datetime]:
        try:
            return datetime.strptime(d_str.strip(), "%d/%m/%Y")
        except Exception:
            return None

    def _normalize_organism(self, org_name: Optional[str]) -> str:
        if not org_name:
            return ""
        clean = org_name.strip().lower().replace("-", " ")
        clean = re.sub(r"\bs\.\s*", "staphylococcus ", clean)
        clean = re.sub(r"\bsp\.?$|\bspp\.?$", "", clean).strip()
        if "coagulasi negativo" in clean or "coagulasi negativa" in clean or "coagulase negative" in clean or clean in ["cns", "scns"]:
            return "staphylococcus coagulasi negativo"
        return clean

    def _is_skin_contaminant(self, org_name: Optional[str]) -> bool:
        if not org_name:
            return False
        clean = org_name.strip().lower().replace("-", " ")
        if clean in ["cns", "scns"] or "coagulasi negativo" in clean or "coagulasi negativa" in clean or "coagulase negative" in clean:
            return True
        for cont in SKIN_CONTAMINANTS:
            cont_clean = cont.replace("-", " ").lower()
            if cont_clean in clean or clean in cont_clean:
                return True
        if re.search(r"\bs\.\s*(?:hominis|epidermidis|haemolyticus|capitis|warneri|lugdunensis|saprophyticus)\b", clean):
            return True
        return False

    def classify(self) -> Dict[str, Any]:
        audit_trail = []

        blood_cultures = []
        other_cultures = []
        symptoms_by_day = {}
        catheters_by_day = {}
        foci_by_day = {}
        admission_info = {}

        # 1. Integrate directly parsed laboratory microbiology reports
        for m in self.parsed_microbiology:
            spec = str(m.get("specimen", "")).upper()
            p_date = m.get("prelievo_date") or ""
            d_dt = self._parse_date(p_date)
            day_num = 1
            if d_dt and self.extractions:
                first_dt = self._parse_date(self.extractions[0].get("date", ""))
                if first_dt and d_dt >= first_dt:
                    day_num = (d_dt - first_dt).days + 1

            if ("EMOCOLTURA" in spec or "SANGUE" in spec or spec == "PERIFERICA" or spec == "CVC") and m.get("is_positive"):
                isolates = m.get("isolates", [])
                if not isolates:
                    isolates = ["Patogeno emocoltura non tipizzato"]
                for iso in isolates:
                    blood_cultures.append({
                        "day_number": day_num,
                        "date": p_date,
                        "tipo": spec,
                        "microrganismo": iso,
                        "cfu": m.get("cfu"),
                        "dtp": m.get("dtp"),
                        "evidenza": f"Referto microbiologico: {m.get('filename')}"
                    })
            elif m.get("is_positive"):
                isolates = m.get("isolates", []) or ["Positivo"]
                for iso in isolates:
                    other_cultures.append({
                        "day_number": day_num,
                        "date": p_date,
                        "sito": spec,
                        "microrganismo": iso,
                        "cfu": m.get("cfu"),
                        "evidenza": f"Referto microbiologico: {m.get('filename')}"
                    })

        # 2. Extract findings from daily clinical text via LLM
        for day in self.extractions:
            d_num = day.get("day_number", 1)
            d_date = day.get("date", "")
            entities = day.get("entities", {})

            # Vital signs
            sv = entities.get("segni_vitali") or entities.get("segni_vitali_sintomi", {})
            feb = sv.get("febbre") or entities.get("febbre", {})
            hypo = sv.get("ipotensione") or entities.get("ipotensione", {})
            briv = sv.get("brividi") or entities.get("brividi", {})
            ipoterm = sv.get("ipotermia") or entities.get("ipotermia", {})

            is_feb = bool(feb.get("presente") and not feb.get("negato"))
            is_hypo = bool(hypo.get("presente") and not hypo.get("negato"))
            is_briv = bool(briv.get("presente") and not briv.get("negato"))
            is_ipoterm = bool(ipoterm.get("presente") and not ipoterm.get("negato"))

            symptoms_by_day[d_num] = {
                "date": d_date,
                "febbre": is_feb,
                "febbre_val": feb.get("tc_valore") or feb.get("tc_max") or feb.get("valore_max"),
                "ipotermia": is_ipoterm,
                "brividi": is_briv,
                "ipotensione": is_hypo,
            }

            # Catheters
            cvc = entities.get("catetere_venoso") or entities.get("dispositivi_invasivi", {})
            cvc_pres = bool(cvc.get("cvc_in_sede") or cvc.get("cvc_presente"))
            cvc_ins = bool(cvc.get("cvc_inserito_oggi"))
            cvc_rem = bool(cvc.get("cvc_rimosso_oggi"))
            pvc_ins = bool(cvc.get("pvc_inserito_oggi"))
            pus_eritema = bool(cvc.get("segni_infezione_sito_pus_eritema") or cvc.get("infezione_sito_inserzione_pus_eritema"))
            migl_48h = bool(cvc.get("miglioramento_48h_post_rimozione") or cvc.get("miglioramento_clinico_post_rimozione", {}).get("presente"))

            catheters_by_day[d_num] = {
                "cvc_presente": cvc_pres,
                "cvc_inserito_oggi": cvc_ins,
                "cvc_rimosso_oggi": cvc_rem,
                "pvc_inserito_oggi": pvc_ins,
                "segni_infezione_sito": pus_eritema,
                "miglioramento_post_rimozione": migl_48h,
                "evidenza": cvc.get("testo_estratto") or cvc.get("evidenza")
            }

            # Secondary foci
            foci_list = entities.get("focolai_infezione") or entities.get("focolai_secondari", [])
            foci_dict = entities.get("focolai_secondari_infezione", {})
            foci_normalized = {}

            if isinstance(foci_list, list):
                for item in foci_list:
                    sito = str(item.get("sito", "")).upper()
                    if item.get("sospetto_o_conferma"):
                        ev = item.get("testo_estratto") or item.get("evidenza")
                        if "PUL" in sito:
                            ev_lower = (ev or "").lower()
                            if any(k in ev_lower for k in ["crepitii", "murmure", "mv diffuso", "ipofonesi"]) and not any(k in ev_lower for k in ["polmonite", "focolaio", "addensamento", "infiltrat", "tosse", "espettorato"]):
                                pass
                            else:
                                foci_normalized["polmonare_S_PUL"] = {"sospetto_o_conferma": True, "evidenza": ev}
                        elif "UTI" in sito:
                            foci_normalized["urinario_S_UTI"] = {"sospetto_o_conferma": True, "evidenza": ev}
                        elif "DIG" in sito:
                            foci_normalized["digestivo_addominale_S_DIG"] = {"sospetto_o_conferma": True, "evidenza": ev}
                        elif "SSI" in sito:
                            foci_normalized["sito_chirurgico_S_SSI"] = {"sospetto_o_conferma": True, "evidenza": ev}
                        elif "SST" in sito:
                            foci_normalized["cute_tessuti_molli_S_SST"] = {"sospetto_o_conferma": True, "evidenza": ev}

            if isinstance(foci_dict, dict):
                for k, v in foci_dict.items():
                    if isinstance(v, dict) and v.get("sospetto_o_conferma"):
                        foci_normalized[k] = v

            foci_by_day[d_num] = foci_normalized

            # Admission
            anamnesi = entities.get("ammissione") or entities.get("anamnesi_e_setting", {})
            if anamnesi and not admission_info:
                testo_anamnesi = (anamnesi.get("testo_estratto") or "").lower()
                dimesso_48h = bool(anamnesi.get("dimesso_recente_48h") or anamnesi.get("dimesso_altra_struttura_ultime_48h", False))
                if not dimesso_48h and any(k in testo_anamnesi for k in ["recente dimissione", "dimesso ieri", "dimessa ieri", "dimesso nelle", "dimessa nelle", "dimissione (ieri)"]):
                    dimesso_48h = True
                admission_info = {
                    "luogo_provenienza": anamnesi.get("provenienza") or anamnesi.get("luogo_provenienza", "DOMICILIO"),
                    "dimesso_altra_struttura_ultime_48h": dimesso_48h
                }

            # Microbiology from daily note
            micro_entries = entities.get("microbiologia")
            if micro_entries is None and isinstance(entities.get("microbiologia_rilevata"), dict):
                micro_entries = entities.get("microbiologia_rilevata", {}).get("emocolture", [])
            elif not isinstance(micro_entries, list):
                micro_entries = []

            for item in micro_entries:
                tipo = str(item.get("tipo_campione") or item.get("tipo", "")).upper()
                org = item.get("microrganismo")
                if ("EMOCOLTURA" in tipo or "SANGUE" in tipo or tipo == "PERIFERICA" or tipo == "CVC") and item.get("esito_positivo"):
                    if not any(b["microrganismo"] == org and b["day_number"] == d_num for b in blood_cultures if org):
                        blood_cultures.append({
                            "day_number": d_num,
                            "date": d_date,
                            "tipo": tipo,
                            "microrganismo": org,
                            "cfu": item.get("carica_cfu"),
                            "dtp": item.get("dtp"),
                            "evidenza": item.get("testo_estratto") or item.get("evidenza")
                        })
                elif item.get("esito_positivo"):
                    if not any(o["microrganismo"] == org and o["day_number"] == d_num for o in other_cultures if org):
                        other_cultures.append({
                            "day_number": d_num,
                            "date": d_date,
                            "sito": tipo or item.get("sito"),
                            "microrganismo": org,
                            "cfu": item.get("carica_cfu"),
                            "evidenza": item.get("testo_estratto") or item.get("evidenza")
                        })
        # Direct scan of admission reports text if provided
        adm_combined_text = " ".join(rep.get("text", "") for rep in self.admission_reports).lower()
        if adm_combined_text:
            dimesso_48h = any(k in adm_combined_text for k in [
                "recente dimissione", "dimesso ieri", "dimessa ieri", "dimesso nelle", "dimessa nelle",
                "dimissione (ieri)", "dimissione ieri", "dimesso da"
            ])
            luogo = "DOMICILIO"
            if any(k in adm_combined_text for k in ["altro nosocomio", "altra struttura", "altro ospedale", "proveniente da ospedale", "trasferit"]):
                luogo = "ALTRO_OSPEDALE"
            elif "rsa" in adm_combined_text or "lungodegenza" in adm_combined_text:
                luogo = "RSA"

            if not admission_info:
                admission_info = {
                    "luogo_provenienza": luogo,
                    "dimesso_altra_struttura_ultime_48h": dimesso_48h
                }
            else:
                if dimesso_48h:
                    admission_info["dimesso_altra_struttura_ultime_48h"] = True
                if luogo != "DOMICILIO" and admission_info.get("luogo_provenienza") in ["DOMICILIO", "SCONOSCIUTA", None]:
                    admission_info["luogo_provenienza"] = luogo

        # --- EVALUATE BSI CASE DEFINITION ---
        has_bsi = False
        diagnostic_day = None
        diagnostic_date = None
        diagnostic_pathogen = None

        # Criterio 1: 1 emocoltura positiva per patogeno riconosciuto (non contaminante cutaneo)
        recognized_bc = [bc for bc in blood_cultures if bc.get("microrganismo") and not self._is_skin_contaminant(bc["microrganismo"])]
        if recognized_bc:
            has_bsi = True
            first_rec = recognized_bc[0]
            diagnostic_day = first_rec["day_number"]
            diagnostic_date = first_rec["date"]
            diagnostic_pathogen = first_rec["microrganismo"]
            audit_trail.append(
                f"[BSI: SI] Criterio 1 soddisfatto: isolato patogeno riconosciuto '{diagnostic_pathogen}' "
                f"in emocoltura del {diagnostic_date} (Giorno {diagnostic_day})."
            )
        else:
            # Criterio 2: >= 2 emocolture positive per lo STESSO contaminante cutaneo entro 48h (<= 2 giorni) + sintomi
            contaminant_bc = [bc for bc in blood_cultures if self._is_skin_contaminant(bc.get("microrganismo"))]
            
            # Group contaminant cultures by normalized organism
            contam_by_org = {}
            for bc in contaminant_bc:
                norm_org = self._normalize_organism(bc.get("microrganismo"))
                contam_by_org.setdefault(norm_org, []).append(bc)

            valid_contam_pair = None
            for org, bcs in contam_by_org.items():
                if len(bcs) >= 2:
                    for i in range(len(bcs)):
                        for j in range(i + 1, len(bcs)):
                            d1 = self._parse_date(bcs[i].get("date", ""))
                            d2 = self._parse_date(bcs[j].get("date", ""))
                            day1 = bcs[i].get("day_number", 1)
                            day2 = bcs[j].get("day_number", 1)
                            is_within_48h = False
                            if d1 and d2:
                                is_within_48h = abs((d2 - d1).days) <= 2
                            else:
                                is_within_48h = abs(day2 - day1) <= 2

                            if is_within_48h:
                                valid_contam_pair = (bcs[i], bcs[j])
                                break
                        if valid_contam_pair:
                            break
                if valid_contam_pair:
                    break

            if valid_contam_pair:
                has_symptom = False
                symptom_evidence = []
                c_day1 = valid_contam_pair[0].get("day_number", 1)
                c_day2 = valid_contam_pair[1].get("day_number", 1)
                window_days = range(min(c_day1, c_day2) - 1, max(c_day1, c_day2) + 2)

                for d_num in window_days:
                    s = symptoms_by_day.get(d_num)
                    if s:
                        if s["febbre"]:
                            has_symptom = True
                            symptom_evidence.append(f"febbre a Giorno {d_num}")
                        if s["brividi"]:
                            has_symptom = True
                            symptom_evidence.append(f"brividi a Giorno {d_num}")
                        if s["ipotensione"]:
                            has_symptom = True
                            symptom_evidence.append(f"ipotensione a Giorno {d_num}")

                if has_symptom:
                    has_bsi = True
                    diagnostic_day = valid_contam_pair[0]["day_number"]
                    diagnostic_date = valid_contam_pair[0]["date"]
                    diagnostic_pathogen = valid_contam_pair[0]["microrganismo"]
                    audit_trail.append(
                        f"[BSI: SI] Criterio 2 soddisfatto: 2 emocolture positive entro 48h per lo stesso contaminante cutaneo "
                        f"('{diagnostic_pathogen}') con sintomi presenti ({', '.join(symptom_evidence)})."
                    )
                else:
                    audit_trail.append(
                        f"[BSI: NO] Rilevate 2 emocolture per lo stesso contaminante cutaneo ('{valid_contam_pair[0]['microrganismo']}') "
                        f"entro 48h ma assenti i sintomi richiesti (febbre, brividi, ipotensione)."
                    )
            elif contaminant_bc:
                audit_trail.append(
                    f"[BSI: NO] Rilevate emocolture per contaminante cutaneo ({len(contaminant_bc)}) "
                    f"ma non soddisfano il criterio ECDC di 2 prelievi per lo STESSO microrganismo entro 48h."
                )
            else:
                audit_trail.append("[BSI: NO] Nessuna emocoltura positiva conforme ai criteri ECDC.")

        if not has_bsi:
            return {
                "patient_id": self.patient_id,
                "bsi": "NO",
                "ha_bsi": None,
                "origine": None,
                "luogo_acquisizione": None,
                "diagnostic_date": None,
                "diagnostic_pathogen": None,
                "audit_trail": audit_trail
            }

        # --- EVALUATE HEALTHCARE ASSOCIATION (HA-BSI vs CA-BSI) ---
        is_ha_bsi = False
        ha_reason = ""

        if diagnostic_day is not None and diagnostic_day >= 3:
            is_ha_bsi = True
            ha_reason = f"Emocoltura diagnostica prelevata a Giorno {diagnostic_day} (>= Day 3 di ricovero, oltre 48h dall'ammissione)."
        elif diagnostic_day in [1, 2]:
            if admission_info.get("dimesso_altra_struttura_ultime_48h"):
                is_ha_bsi = True
                ha_reason = "Insorgenza a Day 1-2 ma paziente dimesso da altra struttura sanitaria nelle 48h precedenti."
            elif any(catheters_by_day.get(d, {}).get("cvc_inserito_oggi") for d in range(1, diagnostic_day)):
                # Strictly prior to onset (insertion_day < diagnostic_day)
                is_ha_bsi = True
                ha_reason = f"Insorgenza a Giorno {diagnostic_day} con dispositivo vascolare (CVC) inserito in questa degenza prima dell'insorgenza."
            else:
                is_ha_bsi = False
                ha_reason = f"Emocoltura diagnostica a Giorno {diagnostic_day} (< Day 3) senza precedente dimissione o dispositivo antecedente (CA-BSI)."

        audit_trail.append(f"[HA-BSI: {'SI' if is_ha_bsi else 'NO'}] {ha_reason}")

        if not is_ha_bsi:
            return {
                "patient_id": self.patient_id,
                "bsi": "SI",
                "ha_bsi": "NO",
                "origine": None,
                "luogo_acquisizione": None,
                "diagnostic_date": diagnostic_date,
                "diagnostic_pathogen": diagnostic_pathogen,
                "audit_trail": audit_trail
            }

        # --- EVALUATE SOURCE OF INFECTION (HA-BSI) ---
        source = "UO"
        source_reason = "Nessun focolaio alternativo né correlazione catetere confermata; classificata come Origine Sconosciuta (UO)."

        dtp_cvc = any("cvc" in bc.get("tipo", "").lower() and bc.get("dtp") and any(k in str(bc["dtp"]).lower() for k in [">", "120", "2h", "2 h", "2 ore", "anticipo", "positivo"]) for bc in blood_cultures)
        tip_match = any(
            oc.get("sito") == "PUNTA_CATETERE" and oc.get("microrganismo") and diagnostic_pathogen and
            (self._normalize_organism(diagnostic_pathogen) in self._normalize_organism(oc["microrganismo"]) or
             self._normalize_organism(oc["microrganismo"]) in self._normalize_organism(diagnostic_pathogen))
            for oc in other_cultures
        )
        pus_match = any(
            ("pus" in str(oc.get("sito", "")).lower() or "catetere" in str(oc.get("sito", "")).lower()) and
            oc.get("microrganismo") and diagnostic_pathogen and
            (self._normalize_organism(diagnostic_pathogen) in self._normalize_organism(oc["microrganismo"]))
            for oc in other_cultures
        )
        has_catheter_pus_erythema = any(catheters_by_day.get(d, {}).get("segni_infezione_sito") for d in catheters_by_day)

        if dtp_cvc or tip_match or pus_match:
            source = "CRI3-CVC"
            source_reason = "Correlazione catetere confermata microbiologicamente (DTP, coltura punta o pus da sito CVC con stesso patogeno)."
        else:
            matching_foci = []
            non_matching_sites = set()
            for oc in other_cultures:
                oc_norm = self._normalize_organism(oc.get("microrganismo"))
                diag_norm = self._normalize_organism(diagnostic_pathogen)
                is_micro_match = bool(oc_norm and diag_norm and (oc_norm in diag_norm or diag_norm in oc_norm))

                sito = str(oc.get("sito", "")).upper()
                site_code = None
                if "URIN" in sito or "UROCOLTURA" in sito:
                    site_code = "S-UTI"
                elif any(k in sito for k in ["POLM", "RESP", "BAL", "ESCREATO"]):
                    site_code = "S-PUL"
                elif any(k in sito for k in ["FERITA", "CHIRURG"]):
                    site_code = "S-SSI"
                elif any(k in sito for k in ["CUTE", "TESSUTI"]):
                    site_code = "S-SST"
                elif any(k in sito for k in ["DIGEST", "ADDOM", "PERITON"]):
                    site_code = "S-DIG"

                if site_code:
                    if is_micro_match:
                        matching_foci.append((site_code, is_micro_match, f"Coltura positiva per {oc['microrganismo']}"))
                    else:
                        # Non-matching isolate rules out this site as source of this specific bacteremia
                        non_matching_sites.add(site_code)

            exact_foci = [f for f in matching_foci if f[1]]
            if exact_foci:
                source = exact_foci[0][0]
                source_reason = f"Isolamento dello stesso microrganismo ({diagnostic_pathogen}) dal sito secondario: {exact_foci[0][2]}."
            elif self._is_skin_contaminant(diagnostic_pathogen):
                # Skin contaminants (CNS, etc.) do NOT cause pulmonary or abdominal secondary BSI without micro proof
                has_improvement = any(catheters_by_day.get(d, {}).get("miglioramento_post_rimozione") for d in catheters_by_day)
                if has_catheter_pus_erythema or has_improvement:
                    source = "C-CVC"
                    source_reason = "Sospetto clinico correlato a catetere con segni locali al sito o defervescenza entro 48h da rimozione."
                else:
                    source = "UO"
                    source_reason = "Contaminante cutaneo in assenza di correlazione catetere o focolaio microbiologico; Origine Sconosciuta (UO)."
            else:
                # Restrict clinical foci to active window near diagnostic day (+- 3 days)
                target_day = diagnostic_day if diagnostic_day is not None else 1
                near_days = set(range(max(1, target_day - 3), target_day + 4))

                clinical_foci_detected = []
                for d_num in sorted(near_days):
                    f = foci_by_day.get(d_num, {})
                    for site_key, site_label in [
                        ("sito_chirurgico_S_SSI", "S-SSI"),
                        ("cute_tessuti_molli_S_SST", "S-SST"),
                        ("digestivo_addominale_S_DIG", "S-DIG"),
                        ("urinario_S_UTI", "S-UTI"),
                        ("polmonare_S_PUL", "S-PUL"),
                    ]:
                        if site_label not in non_matching_sites and f.get(site_key, {}).get("sospetto_o_conferma"):
                            clinical_foci_detected.append((site_label, f[site_key].get("evidenza")))

                if adm_combined_text and target_day <= 3:
                    if "S-UTI" not in non_matching_sites and any(k in adm_combined_text for k in ["ostruzione urinaria", "catetere vescicale", "cistite", "pielonefrite", "urologia"]):
                        clinical_foci_detected.append(("S-UTI", "Segni anamnestici di patologia urinaria/catetere vescicale da verbale di ingresso"))
                    if "S-DIG" not in non_matching_sites and any(k in adm_combined_text for k in ["k colecisti", "colangite", "ascessi epatici", "ascesso epatico", "peritonite", "epatectomia"]):
                        clinical_foci_detected.append(("S-DIG", "Segni anamnestici addominali/biliari da verbale di ingresso"))
                    if "S-SST" not in non_matching_sites and any(k in adm_combined_text for k in ["fascite", "lrinec"]):
                        clinical_foci_detected.append(("S-SST", "Segni anamnestici di fascite necrotizzante"))

                # Biological correlation heuristic:
                diag_lower = (diagnostic_pathogen or "").lower()
                is_sst_pathogen = any(b in diag_lower for b in ["pseudomonas", "aureus", "pyogenes", "streptococcus"])
                is_enteric = any(b in diag_lower for b in ["coli", "klebsiella", "proteus", "enterococcus", "enterobacter", "citrobacter", "aeromonas"])
                is_candida = "candida" in diag_lower

                chosen = None
                if is_sst_pathogen:
                    sst_foci = [cf for cf in clinical_foci_detected if cf[0] in ["S-SST", "S-SSI"]]
                    if sst_foci:
                        chosen = sst_foci[0]
                elif is_enteric:
                    # Prefer abdominal or surgical or urinary based on clinical findings
                    ent_foci = [cf for cf in clinical_foci_detected if cf[0] in ["S-DIG", "S-SSI", "S-UTI"]]
                    if ent_foci:
                        chosen = ent_foci[0]
                elif is_candida:
                    cand_foci = [cf for cf in clinical_foci_detected if cf[0] in ["S-PUL", "S-UTI"]]
                    if cand_foci:
                        chosen = cand_foci[0]

                if not chosen and clinical_foci_detected:
                    chosen = clinical_foci_detected[0]

                if chosen:
                    source = chosen[0]
                    source_reason = f"Evidenza clinica documentata di focolaio secondario correlato: {chosen[1]}."
                else:
                    has_improvement = any(catheters_by_day.get(d, {}).get("miglioramento_post_rimozione") for d in catheters_by_day)
                    if has_catheter_pus_erythema or has_improvement:
                        source = "C-CVC"
                        source_reason = "Sospetto clinico correlato a catetere con segni locali al sito o defervescenza entro 48h da rimozione."
                    else:
                        source = "UO"
                        source_reason = "Nessun focolaio secondario documentato; classificazione: Origine Sconosciuta (UO)."

        audit_trail.append(f"[Origine: {source}] {source_reason}")

        # --- EVALUATE SETTING / PLACE OF ACQUISITION ---
        # ECDC PPS rule:
        # Infections with onset on Day 3+ of current hospitalization belong to the CURRENT hospital (CURR).
        # Only infections with onset at Day 1 or Day 2 can be attributed to another hospital (OHOSP) or nursing home (LTCF).
        setting = "CURR"
        prov = str(admission_info.get("luogo_provenienza", "")).upper()
        if is_ha_bsi and diagnostic_day in [1, 2]:
            if "ALTRO_OSPEDALE" in prov or admission_info.get("dimesso_altra_struttura_ultime_48h"):
                setting = "OHOSP"
            elif "RSA" in prov or "LUNGO_DEGENZA" in prov:
                setting = "LTCF"
            else:
                setting = "CURR"
        else:
            setting = "CURR"

        audit_trail.append(f"[Luogo di Acquisizione: {setting}] Setting definito in base all'anamnesi e degenza.")

        return {
            "patient_id": self.patient_id,
            "bsi": "SI",
            "ha_bsi": "SI" if is_ha_bsi else "NO",
            "origine": source,
            "luogo_acquisizione": setting,
            "diagnostic_date": diagnostic_date,
            "diagnostic_pathogen": diagnostic_pathogen,
            "audit_trail": audit_trail
        }
