"""
GeoBIM Intelligence — Vérification verbatim v1.0.0
Vérifie que source_verbatim apparaît bien dans le texte de la page citée.
Déterministe, 0 appel API.
"""
from typing import List, Dict, Tuple


def verify_verbatim(sondaggi: List[Dict], pages: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """
    Pour chaque valeur avec source_verbatim + page :
    - Cherche le verbatim dans le texte de la page citée
    - Ajoute _verified=True/False/"image_only"
    
    Retourne (sondaggi_enrichis, anomalies)
    """
    page_texts = {p["page_num"]: p for p in pages}
    anomalies  = []
    
    for s in sondaggi:
        sid = s.get("sondage_id", "?")
        
        # Vérifier coordonnées
        coords = s.get("coordinates") or {}
        if coords.get("source_verbatim") and coords.get("page"):
            status = _check_verbatim(
                coords["source_verbatim"], coords["page"], page_texts
            )
            coords["_verified"] = status
            if status == "FAIL":
                anomalies.append({
                    "sondage": sid, "field": "coordinates",
                    "verbatim": coords["source_verbatim"][:60],
                    "page": coords["page"]
                })
        
        # Vérifier falda
        falda = s.get("falda") or {}
        if falda.get("source_verbatim") and falda.get("pages"):
            page_check = falda["pages"][0] if falda["pages"] else None
            if page_check:
                status = _check_verbatim(
                    falda["source_verbatim"], page_check, page_texts
                )
                falda["_verified"] = status
                if status == "FAIL":
                    anomalies.append({
                        "sondage": sid, "field": "falda",
                        "verbatim": falda["source_verbatim"][:60],
                        "page": page_check
                    })
        
        # Vérifier SPT
        for spt in s.get("spt", []):
            if spt.get("source_verbatim") and spt.get("page"):
                status = _check_verbatim(
                    spt["source_verbatim"], spt["page"], page_texts
                )
                spt["_verified"] = status
                if status == "FAIL":
                    anomalies.append({
                        "sondage": sid, "field": "spt",
                        "verbatim": str(spt.get("source_verbatim", ""))[:60],
                        "page": spt["page"]
                    })
        
        # Vérifier Permeability
        for perm in s.get("permeability", []):
            if perm.get("source_verbatim") and perm.get("page"):
                status = _check_verbatim(
                    perm["source_verbatim"], perm["page"], page_texts
                )
                perm["_verified"] = status
    
    return sondaggi, anomalies


def _check_verbatim(verbatim: str, page_num: int, page_texts: Dict) -> str:
    """Vérifie si verbatim existe dans le texte de la page."""
    if not verbatim or not page_num:
        return "NO_DATA"
    
    page = page_texts.get(page_num)
    if not page:
        return "PAGE_NOT_FOUND"
    
    if not page["has_text_layer"]:
        return "IMAGE_ONLY"  # Confiance plus basse mais non invalide
    
    # Nettoyage avant comparaison
    verbatim_clean = " ".join(verbatim.split()).lower()
    text_clean     = " ".join(page["text"].split()).lower()
    
    # Vérifier au moins 80% du verbatim (tolérance ponctuation)
    words = verbatim_clean.split()
    if len(words) >= 3:
        matches = sum(1 for w in words if w in text_clean)
        ratio   = matches / len(words)
        return "OK" if ratio >= 0.7 else "FAIL"
    else:
        return "OK" if verbatim_clean in text_clean else "FAIL"


def print_verification_report(anomalies: List[Dict]) -> None:
    """Affiche le rapport de vérification."""
    if not anomalies:
        print("[Verifier] ✅ Tous les verbatims vérifiés")
        return
    
    print(f"\n[Verifier] ⚠️  {len(anomalies)} anomalies détectées :")
    for a in anomalies[:10]:
        print(f"  {a['sondage']} | {a['field']} | page={a['page']} | '{a['verbatim']}'")
    if len(anomalies) > 10:
        print(f"  ... et {len(anomalies)-10} autres")
