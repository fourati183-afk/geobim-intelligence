"""
GeoBIM Intelligence — Adaptateur LLM → STEP 6/7/9a v1.0.0
Convertit la sortie du LLM extractor vers le format attendu par les STEPS existants.
Les STEPS 6/7/9a ne sont PAS modifiés.
"""
from typing import List, Dict


def llm_to_step5_format(llm_result: Dict) -> Dict:
    """
    Convertit le résultat LLM au format attendu par STEP 5/6/7/9a.
    Compatible avec clean_sondage() de STEP 7.
    """
    sondages = []
    
    for s in llm_result.get("sondaggi", []):
        # Convertir SPT au format STEP 5
        spt_data = []
        for spt in s.get("spt", []):
            n2 = spt.get("N2")
            n3 = spt.get("N3")
            nspt_calc = (n2 or 0) + (n3 or 0) if (n2 is not None and n3 is not None) else spt.get("Nspt")
            spt_data.append({
                "depth_m":       spt.get("prof"),
                "N1":            spt.get("N1"),
                "N2":            n2,
                "N3":            n3,
                "Nspt":          nspt_calc,
                "Nspt_reported": spt.get("Nspt"),
                "coherent":      nspt_calc == spt.get("Nspt") if (nspt_calc is not None and spt.get("Nspt") is not None) else None,
                "_source": {
                    "page":          spt.get("page"),
                    "method":        "llm_vision",
                    "source_verbatim": spt.get("source_verbatim"),
                    "_verified":     spt.get("_verified", "NOT_CHECKED"),
                }
            })
        
        # Convertir permeabilité
        perm_data = []
        for perm in s.get("permeability", []):
            entry = {
                "depth_m": perm.get("prof"),
                "_source": {
                    "page":          perm.get("page"),
                    "method":        "llm_vision",
                    "source_verbatim": perm.get("source_verbatim"),
                }
            }
            if perm.get("permeability") and perm["permeability"].get("value") is not None:
                entry["permeability"] = {
                    "value": perm["permeability"]["value"],
                    "unit":  perm["permeability"].get("unit", "m/s"),
                }
            if perm.get("permeability_h") and perm["permeability_h"].get("value") is not None:
                entry["permeability_h"] = {
                    "value": perm["permeability_h"]["value"],
                    "unit":  "m/s",
                }
            perm_data.append(entry)
        
        # Convertir falda
        falda = s.get("falda")
        falda_converted = None
        if falda:
            falda_converted = {
                "profondita_m": falda.get("depth_m"),
                "assente":      falda.get("absent", False),
                "data":         falda.get("date"),
                "_source":      {
                    "page":          falda.get("pages", [None])[0],
                    "source_verbatim": falda.get("source_verbatim"),
                }
            }
        
        # Convertir coordinates
        coords = s.get("coordinates")
        coords_converted = None
        if coords and (coords.get("lat") or coords.get("lng")):
            coords_converted = {
                "lat":    coords.get("lat"),
                "lon":    coords.get("lng"),  # STEP existant utilise "lon"
                "crs":    "EPSG:4326",
                "format": "dms",
                "raw":    coords.get("source_verbatim", ""),
            }
        
        sondage = {
            "sondage_id":          s.get("sondage_id"),
            "sondage_type":        s.get("sondage_type", "rotary_carotaggio"),
            "source_file":         s.get("source_file", ""),
            "campaign_year":       s.get("campaign_year") or llm_result.get("campaign_year"),
            "cup":                 s.get("cup") or llm_result.get("cup"),
            "data_esecuzione":     s.get("data_esecuzione"),
            "profondita_totale_m": s.get("profondita_totale_m"),
            "coordinates":         coords_converted,
            "elevation_m":         s.get("elevation_m"),
            "falda":               falda_converted,
            "pages_source":        s.get("pages_source", []),
            "spt_data":            spt_data,
            "permeability_data":   perm_data,
            "parametri_data":      [],
            "detected_profile":    llm_result.get("detected_profile"),
            "_stats": {
                "spt_count":       len(spt_data),
                "perm_count":      len(perm_data),
                "parametri_count": 0,
                "pages_count":     len(s.get("pages_source", [])),
                "has_coordinates": coords_converted is not None,
                "has_elevation":   s.get("elevation_m") is not None,
                "has_falda":       falda_converted is not None,
            },
        }
        sondages.append(sondage)
    
    # Format compatible avec ce qu'attend STEP 6
    return {
        "status":       "success",
        "sondages":     sondages,
        "metadata": {
            "source_file":         llm_result.get("source_file", ""),
            "detected_profile":    llm_result.get("detected_profile"),
            "profile_confidence":  0.95,  # LLM vision = haute confiance
            "cup":                 llm_result.get("cup"),
            "campaign_year":       llm_result.get("campaign_year"),
            "pipeline_version":    "v1a-llm",
            "extraction_date":     llm_result.get("extraction_date"),
        },
        "step5_summary": {
            "total_sondages":   len(sondages),
            "total_spt_rows":   sum(len(s["spt_data"]) for s in sondages),
            "total_perm_rows":  sum(len(s["permeability_data"]) for s in sondages),
            "total_param_rows": 0,
            "campaign_year":    llm_result.get("campaign_year"),
        }
    }
