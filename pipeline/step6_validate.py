"""
GeoBIM Intelligence - step6_validate.py  (v1.0.0)
====================================================
Etape 6 du pipeline : VALIDATE

Role : valider les données structurées (step5) selon NTC 2018.
       Détecte les anomalies, incohérences et valeurs suspectes.

Validations appliquées :
  SPT :
    - Nspt = N2 + N3 (cohérence interne)
    - Nspt dans plage plausible (0-100)
    - Profondeur croissante entre mesures
    - Rifiuto strumentale (Nspt > 50) signalé
  Perméabilité :
    - Valeurs dans plage physique (1e-12 à 1e-2 m/s)
  Sondage :
    - Coordonnées dans emprise Italie (35-48°N, 6-19°E)
    - Altitude plausible (-50 à 3000 m s.l.m.)
    - Au moins une donnée SPT ou perm (sinon warning)

Champs ajoutés par sondage :
  - validation_status : "ok" | "warning" | "error"
  - validation_flags  : liste des anomalies détectées
  - validated_spt     : SPT avec flag individuel

Entree : JSON step5
Sortie : JSON step6 -> resultats/[nom]_step6_validate.json

Usage standalone :
    python pipeline/step6_validate.py resultats/mon_rapport_step5_structure.json
"""

import sys
import json
from pathlib import Path
from datetime import date

VERSION = "1.1.0"


# ======================================================================
# SECTION 1 - REGLES DE VALIDATION NTC 2018
# ======================================================================

# Plages plausibles SPT
SPT_NSPT_MIN   =   0
SPT_NSPT_MAX   = 100    # au-dessus = rifiuto ou valeur suspecte
SPT_RIFIUTO    =  50    # Nspt >= 50 → rifiuto strumentale probable
SPT_N_MIN      =   0
SPT_N_MAX      =  60    # N1/N2/N3 individuels

# Plages perméabilité (m/s)
PERM_MIN = 1e-12
PERM_MAX = 1e-2

# Emprise géographique Italie
LAT_MIN, LAT_MAX = 35.0, 48.0
LON_MIN, LON_MAX =  6.0, 19.0

# Altitude plausible (m s.l.m.)
ELEV_MIN = -50.0
ELEV_MAX = 3000.0


# ======================================================================
# SECTION 2 - VALIDATION SPT
# ======================================================================

def validate_spt_row(row: dict, prev_depth: float | None) -> dict:
    """
    Valide une mesure SPT individuelle.
    Retourne la mesure enrichie avec _flags.
    """
    flags  = []
    status = "ok"

    depth = row.get("depth_m")
    n1    = row.get("N1")
    n2    = row.get("N2")
    n3    = row.get("N3")
    nspt  = row.get("Nspt")
    nspt_rep = row.get("Nspt_reported")

    # ── Profondeur ──
    if depth is None:
        flags.append("depth_missing")
    elif depth < 0:
        flags.append("depth_negative")
        status = "error"
    elif prev_depth is not None and depth < prev_depth:
        # depth STRICTEMENT inférieure = vrai problème
        # depth ÉGALE = même profondeur entre pages = normal, pas un warning
        flags.append(f"depth_not_increasing (prev={prev_depth}m, curr={depth}m)")
        status = "warning"

    # ── Valeurs N1/N2/N3 ──
    for name, val in [("N1", n1), ("N2", n2), ("N3", n3)]:
        if val is None:
            flags.append(f"{name}_missing")
        elif not (SPT_N_MIN <= val <= SPT_N_MAX):
            flags.append(f"{name}_out_of_range ({val})")
            status = "error"

    # ── Cohérence Nspt = N2 + N3 ──
    if n2 is not None and n3 is not None and nspt is not None:
        calc = n2 + n3
        if calc != nspt:
            flags.append(f"nspt_incoherent (N2+N3={calc} != Nspt={nspt})")
            status = "warning"

    # ── Plage Nspt ──
    if nspt is not None:
        if nspt > SPT_NSPT_MAX:
            flags.append(f"nspt_very_high ({nspt})")
            status = "warning"
        elif nspt >= SPT_RIFIUTO:
            flags.append(f"rifiuto_probable (Nspt={nspt}>=50)")
            # pas une erreur — info utile

    # ── Cohérence avec valeur reportée ──
    # On ignore si reported <= 5 car c'est un numéro de battage (1,2,3,4,5)
    # et non un vrai Nspt reporté. Un vrai Nspt est toujours > 5 sauf sols
    # très mous (et dans ce cas on vérifiera manuellement).
    if nspt_rep is not None and nspt is not None and nspt_rep != nspt:
        if nspt_rep > 5:
            flags.append(f"nspt_vs_reported (calc={nspt}, reported={nspt_rep})")

    row_out = {**row, "_valid": status, "_flags": flags}
    return row_out


def validate_spt_list(spt_data: list) -> tuple:
    """
    Valide toute la liste SPT d'un sondage.
    Retourne (spt_validé, flags_globaux, status_global).
    """
    validated  = []
    flags      = []
    prev_depth = None
    has_error  = False
    has_warning = False

    for row in spt_data:
        v_row = validate_spt_row(row, prev_depth)
        validated.append(v_row)

        if v_row["_valid"] == "error":
            has_error = True
        elif v_row["_valid"] == "warning":
            has_warning = True

        row_flags = v_row.get("_flags", [])
        flags.extend(row_flags)

        if row.get("depth_m") is not None:
            prev_depth = row["depth_m"]

    # Stats globales
    nspt_values = [r.get("Nspt") for r in spt_data if r.get("Nspt") is not None]
    if nspt_values:
        flags_stats = {
            "spt_min_nspt": min(nspt_values),
            "spt_max_nspt": max(nspt_values),
            "spt_avg_nspt": round(sum(nspt_values) / len(nspt_values), 1),
        }
    else:
        flags_stats = {}

    status = "error" if has_error else ("warning" if has_warning else "ok")
    return validated, flags, status, flags_stats


# ======================================================================
# SECTION 3 - VALIDATION PERMEABILITE
# ======================================================================

def validate_permeability_list(perm_data: list) -> tuple:
    """
    Valide les mesures de perméabilité.
    Retourne (flags, status).
    """
    flags      = []
    has_error  = False
    has_warning = False

    for i, item in enumerate(perm_data):
        for key in ("permeability", "permeability_h", "permeability_v"):
            perm = item.get(key, {})
            if not perm:
                continue
            val = perm.get("value")
            if val is None:
                continue
            if not (PERM_MIN <= val <= PERM_MAX):
                flags.append(
                    f"perm_out_of_range (mesure {i+1}: {key}={val:.2e} m/s)"
                )
                has_warning = True

    status = "error" if has_error else ("warning" if has_warning else "ok")
    return flags, status


# ======================================================================
# SECTION 4 - VALIDATION SONDAGE
# ======================================================================

def validate_sondage(sondage: dict) -> dict:
    """
    Valide un sondage complet.
    Retourne le sondage enrichi avec validation_status et validation_flags.
    """
    flags      = []
    statuses   = []

    sondage_id   = sondage.get("sondage_id", "?")
    sondage_type = sondage.get("sondage_type", "")
    coords       = sondage.get("coordinates")
    elevation    = sondage.get("elevation_m")
    spt_data     = sondage.get("spt_data", [])
    perm_data    = sondage.get("permeability_data", [])

    # ── Coordonnées ──
    # Manque de coordonnées = soft warning (pas bloquant pour NTC 2018)
    if coords:
        lat = coords.get("lat")
        lon = coords.get("lon")
        if lat and not (LAT_MIN <= lat <= LAT_MAX):
            flags.append(f"coord_lat_out_of_italy ({lat})")
            statuses.append("error")
        if lon and not (LON_MIN <= lon <= LON_MAX):
            flags.append(f"coord_lon_out_of_italy ({lon})")
            statuses.append("error")
    else:
        flags.append("coordinates_missing")
        # Pas de statuses.append ici — coordonnées manquantes = info, pas warning

    # ── Altitude ──
    if elevation is not None:
        if not (ELEV_MIN <= elevation <= ELEV_MAX):
            flags.append(f"elevation_out_of_range ({elevation}m)")
            statuses.append("warning")
    else:
        flags.append("elevation_missing")
        # Pas de statuses.append ici — altitude manquante = info, pas warning

    # ── SPT ──
    spt_flags_global = []
    spt_stats        = {}
    validated_spt    = spt_data  # fallback sans validation

    if sondage_type == "rotary_carotaggio":
        if not spt_data:
            flags.append("spt_data_missing")
            statuses.append("warning")
        else:
            validated_spt, spt_row_flags, spt_status, spt_stats = \
                validate_spt_list(spt_data)
            spt_flags_global = spt_row_flags
            statuses.append(spt_status)
            flags.extend([f"spt:{f}" for f in spt_row_flags])
    else:
        # Sondage bis/R : pas de SPT attendu
        flags.append("distruzione_di_nucleo_no_spt_expected")

    # ── Perméabilité ──
    perm_flags, perm_status = validate_permeability_list(perm_data)
    flags.extend([f"perm:{f}" for f in perm_flags])
    statuses.append(perm_status)

    # ── Données minimales ──
    if not spt_data and not perm_data:
        flags.append("no_data_extracted")
        statuses.append("warning")

    # ── Status final ──
    if "error" in statuses:
        final_status = "error"
    elif "warning" in statuses:
        final_status = "warning"
    else:
        final_status = "ok"

    # Mettre à jour le sondage
    sondage["validated_spt"]      = validated_spt
    sondage["validation_status"]  = final_status
    sondage["validation_flags"]   = flags
    sondage["validation_stats"]   = spt_stats

    return sondage


# ======================================================================
# SECTION 5 - PIPELINE PRINCIPAL
# ======================================================================

def validate_all(step5_json_path: str) -> dict:
    """
    Charge le JSON step5, valide tous les sondages.
    """
    step5_path = Path(step5_json_path)

    if not step5_path.exists():
        return {"status": "error",
                "error": f"Fichier step5 non trouve : {step5_path}"}

    print(f"\n📂 Lecture step5 : {step5_path.name}")
    print("-" * 65)

    try:
        with open(step5_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"status": "error", "error": f"Impossible de lire le JSON : {e}"}

    if data.get("status") != "success":
        return {"status": "error", "error": "Le JSON step5 signale une erreur."}

    sondages = data.get("sondages", [])
    print(f"🕳️  {len(sondages)} sondages à valider\n")

    count_ok      = 0
    count_warning = 0
    count_error   = 0

    STATUS_ICONS = {"ok": "✅", "warning": "⚠️ ", "error": "❌"}

    for sondage in sondages:
        sid = sondage.get("sondage_id", "?")
        validate_sondage(sondage)

        status = sondage.get("validation_status", "?")
        flags  = sondage.get("validation_flags", [])
        stats  = sondage.get("validation_stats", {})
        icon   = STATUS_ICONS.get(status, "?")

        spt_n  = sondage["_stats"]["spt_count"]
        perm_n = sondage["_stats"]["perm_count"]

        # Résumé stats SPT
        stats_str = ""
        if stats:
            stats_str = (f" [Nspt: {stats.get('spt_min_nspt','?')}"
                         f"-{stats.get('spt_max_nspt','?')}"
                         f" moy={stats.get('spt_avg_nspt','?')}]")

        print(f"  {icon} {sid:<12} | {status:<7} | "
              f"SPT={spt_n:2d} perm={perm_n:2d}{stats_str}")

        # Afficher les flags non triviaux
        non_trivial = [
            f for f in flags
            if f not in (
                "coordinates_missing", "elevation_missing",
                "distruzione_di_nucleo_no_spt_expected",
            )
        ]
        for flag in non_trivial[:3]:   # max 3 flags affichés
            print(f"    ↳ {flag}")

        if status == "ok":
            count_ok += 1
        elif status == "warning":
            count_warning += 1
        else:
            count_error += 1

    # Metadata
    data["metadata"]["pipeline_step"] = "step6_validate"
    data["metadata"]["step6_version"] = VERSION
    data["metadata"]["step6_date"]    = str(date.today())

    data["step6_summary"] = {
        "total_sondages":    len(sondages),
        "status_ok":         count_ok,
        "status_warning":    count_warning,
        "status_error":      count_error,
        "ntc2018_compliant": count_error == 0,
    }

    data["status"] = "success"
    return data


# ======================================================================
# SECTION 6 - SAUVEGARDE ET RESUME
# ======================================================================

def save_step6_result(data: dict, step5_path: str) -> Path:
    step5_path  = Path(step5_path)
    base_name   = step5_path.stem.replace("_step5_structure", "")
    output_path = step5_path.parent / (base_name + "_step6_validate.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return output_path


def print_summary(data: dict) -> None:
    if data.get("status") == "error":
        print(f"\n❌ ECHEC : {data['error']}")
        return

    s = data.get("step6_summary", {})
    print("\n" + "=" * 65)
    print(f"📋 RESUME STEP 6 - VALIDATE v{VERSION}")
    print("=" * 65)
    print(f"  🕳️  Sondages validés        : {s.get('total_sondages', 0)}")
    print(f"  ✅ OK                       : {s.get('status_ok', 0)}")
    print(f"  ⚠️  Warnings                : {s.get('status_warning', 0)}")
    print(f"  ❌ Erreurs                  : {s.get('status_error', 0)}")
    ntc = "✅ OUI" if s.get("ntc2018_compliant") else "⚠️  NON (voir flags)"
    print(f"  📐 Conforme NTC 2018        : {ntc}")
    print("=" * 65)


# ======================================================================
# POINT D'ENTREE
# Usage : python pipeline/step6_validate.py resultats/mon_rapport_step5_structure.json
# ======================================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python pipeline/step6_validate.py resultats/mon_rapport_step5_structure.json")
        sys.exit(1)

    step5_path = sys.argv[1]
    result     = validate_all(step5_path)
    print_summary(result)

    if result.get("status") == "success":
        try:
            output_path = save_step6_result(result, step5_path)
            print(f"\n💾 JSON sauvegarde : {output_path}")
        except Exception as e:
            print(f"\n❌ Erreur sauvegarde : {e}")
    else:
        print("\n❌ Pas de sauvegarde.")