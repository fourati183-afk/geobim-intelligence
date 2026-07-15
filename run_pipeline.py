"""
GeoBIM Intelligence — run_pipeline.py v1.0.0
Usage : python run_pipeline.py pdfs/rapport.pdf
"""
import sys, json, os, time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def main():
    if len(sys.argv) < 2:
        print("Usage : python run_pipeline.py <rapport.pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not Path(pdf_path).exists():
        print(f"❌ Fichier non trouvé : {pdf_path}")
        sys.exit(1)

    t0 = time.time()
    pdf_name = Path(pdf_path).stem

    print("\n" + "="*65)
    print("🚀 GeoBIM Intelligence — Pipeline IA v1.0.0")
    print("="*65)

    # STEP 1 : Extraction IA
    print("\n📄 STEP 1 — Extraction IA (Claude Sonnet 4.6)...")
    from extractors import extract_pdf
    from extractors.verbatim_check import verify_verbatim, verification_report
    from extractors.ingestion import load_pdf

    result = extract_pdf(pdf_path)
    pages  = load_pdf(pdf_path)

    # STEP 2 : Vérification verbatim
    print("\n🔍 STEP 2 — Vérification verbatim...")
    sondaggi_raw = [s.model_dump() for s in result.sondaggi]
    sondaggi_raw = verify_verbatim(sondaggi_raw, pages)
    verif = verification_report(sondaggi_raw)
    print(f"  Score verbatim : {verif['score_pct']}% vérifié "
          f"({verif['verified']}/{verif['total']})")

    # STEP 3 : Adapter vers format steps 5/6/7/9a
    print("\n🔀 STEP 3 — Adaptation format pipeline...")
    from steps import extraction_to_pipeline_json
    pipeline_json = extraction_to_pipeline_json(result)

    # STEP 4 : Validation (step6) + Nettoyage (step7)
    print("\n✅ STEP 4 — Validation + Nettoyage...")
    # Importer les fonctions de GEOBIM_ALL_STEPS.py
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from pipeline.step6_validate import validate_all
        from pipeline.step7_save import save_final

        # Sauvegarder JSON intermédiaire pour step6
        step5_path = f"resultats/{pdf_name}_step5_llm.json"
        os.makedirs("resultats", exist_ok=True)
        with open(step5_path, "w", encoding="utf-8") as f:
            json.dump(pipeline_json, f, ensure_ascii=False, indent=2)

        step6_result = validate_all(step5_path)
        step6_path = f"resultats/{pdf_name}_step6_llm.json"
        with open(step6_path, "w", encoding="utf-8") as f:
            json.dump(step6_result, f, ensure_ascii=False, indent=2)

        step7_result = save_final(step6_path)
        step7_path = f"resultats/{pdf_name}_step7_llm_final.json"
        with open(step7_path, "w", encoding="utf-8") as f:
            json.dump(step7_result, f, ensure_ascii=False, indent=2)

    except ImportError as e:
        print(f"  ⚠️  Steps 6/7 non disponibles ({e}) — sauvegarde directe")
        step7_path = f"resultats/{pdf_name}_step7_llm_final.json"
        with open(step7_path, "w", encoding="utf-8") as f:
            json.dump(pipeline_json, f, ensure_ascii=False, indent=2)
        step7_result = pipeline_json

    # STEP 5 : Excel (step9a)
    print("\n📊 STEP 5 — Génération Excel...")
    try:
        from pipeline.step9a_excel import build_excel
        os.makedirs("outputs", exist_ok=True)
        excel_path = build_excel(step7_path)
        print(f"  ✅ Excel : {excel_path}")
    except ImportError as e:
        print(f"  ⚠️  step9a non disponible ({e})")
        excel_path = None

    # STEP 6 : Test ground truth
    print("\n🔬 STEP 6 — Test ground truth...")
    gt_path = "validation/italferr_NF3900P69/ground_truth.json"
    if Path(gt_path).exists():
        try:
            import subprocess
            r = subprocess.run(["python", "tests/test_against_truth.py"],
                               capture_output=True, text=True)
            last_lines = r.stdout.strip().split("\n")[-5:]
            for line in last_lines:
                print(f"  {line}")
        except Exception as e:
            print(f"  ⚠️  Test non lancé : {e}")
    else:
        print("  ℹ️  ground_truth.json non trouvé — test ignoré")

    # STEP 7 : Sauvegarde SQLite
    print("\n💾 STEP 7 — Sauvegarde SQLite...")
    from db import init_db, save_report
    init_db()
    save_report(pdf_name, Path(pdf_path).name, step7_result, pages)
    print(f"  ✅ Rapport sauvegardé : {pdf_name}")

    # Résumé final
    elapsed = round(time.time() - t0, 1)
    sondaggi = step7_result.get("sondages", step7_result.get("sondaggi", []))
    spt_tot  = sum(len(s.get("spt_data", s.get("spt", []))) for s in sondaggi)
    perm_tot = sum(len(s.get("permeability_data", s.get("permeability", []))) for s in sondaggi)

    print(f"\n{'='*65}")
    print(f"✅ GeoBIM Pipeline — TERMINÉ en {elapsed}s")
    print(f"{'='*65}")
    print(f"  🕳️  Sondaggi    : {len(sondaggi)}")
    print(f"  🔨 SPT          : {spt_tot}")
    print(f"  💧 Lefranc      : {perm_tot}")
    print(f"  🔍 Verbatim     : {verif['score_pct']}%")
    if excel_path:
        print(f"  📊 Excel        : {excel_path}")
    print(f"{'='*65}\n")

if __name__ == "__main__":
    main()
