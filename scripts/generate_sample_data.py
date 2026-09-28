import os
import pymupdf
import pandas as pd

def create_pdf_from_text(pdf_path: str, pages_text: list):
    doc = pymupdf.open()
    for text in pages_text:
        page = doc.new_page()
        # insert text at point (50, 72)
        page.insert_text(pymupdf.Point(50, 72), text, fontsize=10, fontname="helv")
    doc.save(pdf_path)
    doc.close()

def generate_samples(base_dir: str):
    sample_dir = os.path.join(base_dir, "sample_data")
    os.makedirs(sample_dir, exist_ok=True)

    # -------------------------------------------------------------
    # 1. SYNTH01: HA-BSI from CVC (Positive)
    # -------------------------------------------------------------
    p1_dir = os.path.join(sample_dir, "Paziente_SYNTH01")
    adm1 = os.path.join(p1_dir, "ADMISSION_EMERGENCY_REPORTS_SYNTH01")
    dia1 = os.path.join(p1_dir, "CLINICAL_DIARIES_SYNTH01")
    mic1 = os.path.join(p1_dir, "MICROBIOLOGY_SYNTH01")
    for d in [adm1, dia1, mic1]:
        os.makedirs(d, exist_ok=True)

    # Admission Report
    create_pdf_from_text(
        os.path.join(adm1, "verbale_pronto_soccorso.pdf"),
        ["VERBALE DI ACCETTAZIONE PRONTO SOCCORSO\nData ammissione: 10/01/2025 09:30\nPaziente SYNTH01, anni 68.\nAccesso per programma chirurgico addominale programmato. Condizioni generali stabili, apiretico."]
    )

    # Diaries (4 days)
    diary_pages = [
        "DIARIO CLINICO REPARTO CHIRURGIA\n10/01/2025 1a giornata\nPaziente ricoverato in reparto. Posizionato CVC (catetere venoso centrale) succlavia destra per nutrizione parenterale e terapia. P.A. 130/80, TC 36.5°C. Apiretico.",
        "DIARIO CLINICO REPARTO CHIRURGIA\n11/01/2025 2a giornata\nDecorso post-operatorio regolare. Medicazione CVC pulita, non segni di flogosi locale. TC 36.8°C.",
        "DIARIO CLINICO REPARTO CHIRURGIA\n12/01/2025 3a giornata\nPaziente vigile, collaborante. Diuresi valida, alvo canalizzato. TC 37.0°C. Si mantiene CVC.",
        "DIARIO CLINICO REPARTO CHIRURGIA\n13/01/2025 4a giornata\nOre 14:30: Comparsa improvvisa di brivido scuotente e febbre elevata (TC 38.9°C). Sospetta sepsi correlata a CVC. Eseguite emocolture periferiche e da CVC. Iniziata terapia antibiotica empirica con Vancomicina."
    ]
    create_pdf_from_text(os.path.join(dia1, "diario_clinico_degenza.pdf"), diary_pages)

    # Microbiology
    create_pdf_from_text(
        os.path.join(mic1, "referto_emocoltura_13012025.pdf"),
        ["AZIENDA OSPEDALIERA - U.O. MICROBIOLOGIA CLINICA\nPrelievo del 13/01/2025 15:00\nMateriale: EMOCOLTURA CVC\n\nESITO: POSITIVO\nIsolamento: Staphylococcus aureus\nValidato da Dott.ssa Rossi il 15/01/2025"]
    )

    # -------------------------------------------------------------
    # 2. SYNTH02: Negative Control (Apiretic, No BSI)
    # -------------------------------------------------------------
    p2_dir = os.path.join(sample_dir, "Paziente_SYNTH02")
    adm2 = os.path.join(p2_dir, "ADMISSION_EMERGENCY_REPORTS_SYNTH02")
    dia2 = os.path.join(p2_dir, "CLINICAL_DIARIES_SYNTH02")
    mic2 = os.path.join(p2_dir, "MICROBIOLOGY_SYNTH02")
    for d in [adm2, dia2, mic2]:
        os.makedirs(d, exist_ok=True)

    create_pdf_from_text(
        os.path.join(adm2, "verbale_ingresso.pdf"),
        ["VERBALE DI INGRESSO REPARTO\nData ammissione: 15/01/2025 10:00\nPaziente SYNTH02, ricovero per ernioplastica inguinale. Parametri vitali nella norma, apiretico."]
    )

    create_pdf_from_text(
        os.path.join(dia2, "diario_degenza.pdf"),
        [
            "15/01/2025 1a giornata: Intervento eseguito senza complicanze. Apiretico, TC 36.4°C.",
            "16/01/2025 2a giornata: Decorso regolare. Ferita chirurgica in ordine. TC 36.6°C. Paziente deambulante.",
            "17/01/2025 3a giornata: Paziente in buone condizioni cliniche, apiretico. Dimesso a domicilio."
        ]
    )

    create_pdf_from_text(
        os.path.join(mic2, "esami_colturali.pdf"),
        ["AZIENDA OSPEDALIERA - U.O. MICROBIOLOGIA CLINICA\nPrelievo del 15/01/2025\nMateriale: EMOCOLTURA PERIFERICA\nESITO: NEGATIVO - Nessuno sviluppo batterico a 5 giorni di incubazione."]
    )

    # -------------------------------------------------------------
    # 3. Gold Standard Excel
    # -------------------------------------------------------------
    gold_rows = [
        {
            "Codice cartella cartella ": "SYNTH01",
            "BSI?": "SI",
            "HA BSI?": "SI",
            "Origine dell'infezione": "C-CVC",
            "Luogo acquisizione": "CURR",
            "Patogeno": "Staphylococcus aureus",
            "Note cliniche": "HA-BSI al Day 4 correlata a CVC succlavia"
        },
        {
            "Codice cartella cartella ": "SYNTH02",
            "BSI?": "NO",
            "HA BSI?": "NO",
            "Origine dell'infezione": "NONE",
            "Luogo acquisizione": "NONE",
            "Patogeno": "",
            "Note cliniche": "Controllo negativo apiretico"
        }
    ]
    df_gold = pd.DataFrame(gold_rows)
    gold_path = os.path.join(sample_dir, "sample_gold_standard.xlsx")
    with pd.ExcelWriter(gold_path, engine="openpyxl") as writer:
        df_gold.to_excel(writer, sheet_name="Suddivisione Cartelle", index=False)

    print(f"[OK] Dati dimostrativi sintetici generati in: {sample_dir}")

if __name__ == "__main__":
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    generate_samples(repo_root)
