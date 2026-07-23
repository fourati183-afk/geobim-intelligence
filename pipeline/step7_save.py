"""
GeoBIM Intelligence - step7_save.py  (v1.0.0)
===============================================
Etape 7 du pipeline : SAVE

Role : produire le JSON final propre et normalisé,
       prêt pour step9a (Excel) et step9b (Dynamo).

Ce que fait step7 :
  - Nettoie les champs internes (_source, _valid, _flags step-level)
  - Normalise les valeurs nulles
  - Ajoute un champ "geobim_id" unique par mesure (tracabilité)
  - Produit un JSON compact et lisible

Structure du JSON final :
{
  "geobim_version": "1.0",
  "source_file": "mon_rapport.pdf",
  "campaign_year": "2025",
  "extraction_date": "2025-01-15",
  "sondages": [
    {
      "sondage_id": "S01",
      "sondage_type": "rotary_carotaggio",
      "coordinates": {"lat": 43.24, "lon": 11.85, "crs": "EPSG:4326"},
      "elevation_m": 247.12,
      "validation_status": "warning",
      "spt": [
        {
          "geobim_id": "S01_SPT_001",
          "depth_m": 2.0,
          "N1": 1, "N2": 2, "N3": 4,
          "Nspt": 6,
          "page_source": 29
        }
      ],
      "permeability": [...],
      "parametri": [...]
    }
  ]
}

Entree : JSON step6
Sortie : JSON final -> resultats/[nom]_step7_final.json

Usage standalone :
    python pipeline/step7_save.py resultats/mon_rapport_step6_validate.json
"""

import sys
import json
from pathlib import Path
from datetime import date

VERSION = "1.0.0"


# ======================================================================
# SECTION 1 - NETTOYAGE ET NORMALISATION
# ======================================================================

def clean_spt_row(row: dict, sondage_id: str, idx: int) -> dict:
    """
    Nettoie une mesure SPT et ajoute un geobim_id unique.
    """
    geobim_id  = f"{sondage_id}_SPT_{idx+1:03d}"
    page_source = None

    source = row.get("_source", {})
    if isinstance(source, dict):
        page_source = source.get("page")

    return {
        "geobim_id":      geobim_id,
        "depth_m":        row.get("depth_m"),
        "N1":             row.get("N1"),
        "N2":             row.get("N2"),
        "N3":             row.get("N3"),
        "Nspt":           row.get("Nspt"),
        "Nspt_reported":  row.get("Nspt_reported"),
        "coherent":       row.get("coherent"),
        "validation":     row.get("_valid", "ok"),
        "flags":          row.get("_flags", []),
        "page_source":    page_source,
    }


def clean_perm_row(row: dict, sondage_id: str, idx: int) -> dict:
    """
    Nettoie une mesure de perméabilité.
    """
    geobim_id   = f"{sondage_id}_PERM_{idx+1:03d}"
    page_source = None

    source = row.get("_source", {})
    if isinstance(source, dict):
        page_source = source.get("page")

    result = {
        "geobim_id":   geobim_id,
        "depth_m":     row.get("depth_m"),
        "page_source": page_source,
    }

    for key in ("permeability", "permeability_h", "permeability_v"):
        perm = row.get(key)
        if perm and isinstance(perm, dict):
            val = perm.get("value")
            if val is not None:
                result[key] = {"value": val, "unit": perm.get("unit", "m/s")}

    return result


def clean_param_row(row: dict, sondage_id: str, idx: int) -> dict:
    """
    Nettoie une unité géotechnique avec ses paramètres.
    """
    geobim_id   = f"{sondage_id}_PARAM_{idx+1:03d}"
    page_source = None

    source = row.get("_source", {})
    if isinstance(source, dict):
        page_source = source.get("page")

    params_clean = {}
    for param_name, param_data in row.get("parameters", {}).items():
        if not isinstance(param_data, dict):
            continue
        entry = {}
        if "value" in param_data:
            entry["value"] = param_data["value"]
        if "min" in param_data:
            entry["min"] = param_data["min"]
        if "max" in param_data:
            entry["max"] = param_data["max"]
        if "unit" in param_data:
            entry["unit"] = param_data["unit"]
        if entry:
            params_clean[param_name] = entry

    return {
        "geobim_id":   geobim_id,
        "unit_id":     row.get("unit_id"),
        "parameters":  params_clean,
        "page_source": page_source,
    }


def clean_sondage(sondage: dict) -> dict:
    """
    Produit la version finale et propre d'un sondage.
    """
    sid = sondage.get("sondage_id", "?")

    # SPT — utiliser validated_spt si disponible
    spt_raw    = sondage.get("validated_spt") or sondage.get("spt_data", [])
    perm_raw   = sondage.get("permeability_data", [])
    param_raw  = sondage.get("parametri_data", [])

    spt_clean   = [clean_spt_row(r, sid, i) for i, r in enumerate(spt_raw)]
    perm_clean  = [clean_perm_row(r, sid, i) for i, r in enumerate(perm_raw)]
    param_clean = [clean_param_row(r, sid, i) for i, r in enumerate(param_raw)]

    # Filtrer les SPT sans aucune donnée utile
    spt_clean = [
        r for r in spt_clean
        if any(r.get(k) is not None for k in ["N1", "N2", "N3", "Nspt"])
    ]

    # Filtrer les perméabilités sans valeur
    perm_clean = [
        r for r in perm_clean
        if any(
            k in r and isinstance(r[k], dict) and r[k].get("value") is not None
            for k in ["permeability", "permeability_h", "permeability_v"]
        )
    ]

    return {
        "sondage_id":          sid,
        "sondage_type":        sondage.get("sondage_type", "unknown"),
        "source_file":         sondage.get("source_file", ""),
        "campaign_year":       sondage.get("campaign_year"),
        "cup":                 sondage.get("cup"),
        "data_esecuzione":     sondage.get("data_esecuzione"),
        "profondita_totale_m": sondage.get("profondita_totale_m"),
        "coordinates":         sondage.get("coordinates"),
        "elevation_m":         sondage.get("elevation_m"),
        "falda":               sondage.get("falda"),
        "pages_source":        sondage.get("pages_source", []),
        "validation_status":   sondage.get("validation_status", "unknown"),
        "validation_flags":  [
            f for f in sondage.get("validation_flags", [])
            if f not in (
                "coordinates_missing", "elevation_missing",
                "distruzione_di_nucleo_no_spt_expected",
            )
        ],
        "spt":          spt_clean,
        "permeability": perm_clean,
        "parametri":    param_clean,
        "_stats": {
            "spt_count":   len(spt_clean),
            "perm_count":  len(perm_clean),
            "param_count": len(param_clean),
        },
    }


# ======================================================================
# SECTION 2 - PIPELINE PRINCIPAL
# ======================================================================

def save_final(step6_json_path: str) -> dict:
    """
    Charge le JSON step6, produit le JSON final propre.
    """
    step6_path = Path(step6_json_path)

    if not step6_path.exists():
        return {"status": "error",
                "error": f"Fichier step6 non trouve : {step6_path}"}

    print(f"\n📂 Lecture step6 : {step6_path.name}")
    print("-" * 65)

    try:
        with open(step6_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"status": "error", "error": f"Impossible de lire le JSON : {e}"}

    if data.get("status") != "success":
        return {"status": "error", "error": "Le JSON step6 signale une erreur."}

    sondages_raw = data.get("sondages", [])
    meta         = data.get("metadata", {})

    print(f"🕳️  {len(sondages_raw)} sondages à finaliser\n")

    sondages_final = []
    total_spt      = 0
    total_perm     = 0
    total_param    = 0

    for sondage in sondages_raw:
        clean = clean_sondage(sondage)
        sondages_final.append(clean)

        spt_n   = clean["_stats"]["spt_count"]
        perm_n  = clean["_stats"]["perm_count"]
        param_n = clean["_stats"]["param_count"]
        sid     = clean["sondage_id"]
        coords  = "📍" if clean.get("coordinates") else "  "
        elev    = f"z={clean['elevation_m']}m" if clean.get("elevation_m") else ""
        vstatus = clean.get("validation_status", "?")
        vicon   = {"ok": "✅", "warning": "⚠️ ", "error": "❌"}.get(vstatus, "?")

        total_spt   += spt_n
        total_perm  += perm_n
        total_param += param_n

        print(
            f"  {coords}{vicon} {sid:<12} | "
            f"SPT={spt_n:2d} | perm={perm_n:2d} | "
            f"param={param_n} {elev}"
        )

    # JSON final
    final = {
        "geobim_version":  "1.0",
        "schema_version":  "step7_v1.0.0",
        "source_file":     meta.get("source_file", ""),
        "detected_profile": meta.get("detected_profile"),
        "campaign_year":   data.get("step5_summary", {}).get("campaign_year"),
        "cup":             data.get("step5_summary", {}).get("cup"),
        "extraction_date": str(date.today()),
        "pipeline_steps":  ["step1", "step2", "step3", "step4b",
                            "step5", "step6", "step7"],
        "ntc2018_compliant": data.get("step6_summary", {}).get("ntc2018_compliant", False),
        "sondages":        sondages_final,
        "_summary": {
            "total_sondages": len(sondages_final),
            "total_spt":      total_spt,
            "total_perm":     total_perm,
            "total_param":    total_param,
        },
        "status": "success",
    }

    return final


# ======================================================================
# SECTION 3 - SAUVEGARDE ET RESUME
# ======================================================================

def save_step7_result(data: dict, step6_path: str) -> Path:
    step6_path  = Path(step6_path)
    base_name   = step6_path.stem.replace("_step6_validate", "")
    output_path = step6_path.parent / (base_name + "_step7_final.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return output_path


def print_summary(data: dict) -> None:
    if data.get("status") == "error":
        print(f"\n❌ ECHEC : {data['error']}")
        return

    s = data.get("_summary", {})
    print("\n" + "=" * 65)
    print(f"📋 RESUME STEP 7 - SAVE FINAL v{VERSION}")
    print("=" * 65)
    print(f"  🕳️  Sondages finalisés      : {s.get('total_sondages', 0)}")
    print(f"  🔨 Mesures SPT             : {s.get('total_spt', 0)}")
    print(f"  💧 Mesures perméabilité    : {s.get('total_perm', 0)}")
    print(f"  📐 Paramètres géotech.     : {s.get('total_param', 0)}")
    ntc = "✅ OUI" if data.get("ntc2018_compliant") else "⚠️  NON"
    print(f"  📐 Conforme NTC 2018       : {ntc}")
    print(f"  📅 Année campagne          : {data.get('campaign_year', '?')}")
    print(f"  🏷️  Profil détecté          : {data.get('detected_profile', 'générique')}")
    print("=" * 65)
    print("\n✅ JSON final prêt pour step9a (Excel) et step9b (Dynamo)")


# ======================================================================
# POINT D'ENTREE
# Usage : python pipeline/step7_save.py resultats/mon_rapport_step6_validate.json
# ======================================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python pipeline/step7_save.py resultats/mon_rapport_step6_validate.json")
        sys.exit(1)

    step6_path = sys.argv[1]
    result     = save_final(step6_path)
    print_summary(result)

    if result.get("status") == "success":
        try:
            output_path = save_step7_result(result, step6_path)
            print(f"\n💾 JSON final sauvegarde : {output_path}")
        except Exception as e:
            print(f"\n❌ Erreur sauvegarde : {e}")
    else:
        print("\n❌ Pas de sauvegarde.")