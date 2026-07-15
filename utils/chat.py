"""
GeoBIM Intelligence — Chat IA v1.0.0
Q&A sur le rapport avec prompt caching.
Répond UNIQUEMENT depuis le JSON + texte du rapport.
"""
import os
import json
import anthropic
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

MODEL_CHAT  = "claude-sonnet-4-6"
MODEL_GUARD = "claude-haiku-4-5-20251001"
MAX_TOKENS  = 2000


def build_system_prompt(json_data: Dict, pages_text: Optional[str]) -> str:
    """Construit le system prompt avec les données du rapport."""
    sondaggi_summary = []
    for s in json_data.get("sondaggi", []):
        spt_count  = len(s.get("spt", []) or s.get("spt_data", []))
        perm_count = len(s.get("permeability", []) or s.get("permeability_data", []))
        sondaggi_summary.append(
            f"- {s['sondage_id']} ({s.get('sondage_type','?')}): "
            f"{spt_count} SPT, {perm_count} Lefranc, "
            f"quota={s.get('elevation_m','?')}m, "
            f"falda={s.get('falda',{}).get('profondita_m','?') if s.get('falda') else '?'}m"
        )
    
    system = f"""Sei un assistente tecnico specializzato in geotecnica italiana. 
Rispondi ESCLUSIVAMENTE in base ai dati del rapporto fornito.
NON usare conoscenze generali, NON inventare dati non presenti nel rapporto.
Se un dato non è nel rapporto, di' chiaramente "Non presente nel rapporto".
Cita sempre la pagina sorgente quando disponibile.
Rispondi in italiano tecnico, in modo preciso e conciso.

=== RAPPORTO: {json_data.get('source_file', 'N/D')} ===
Profilo: {json_data.get('detected_profile', 'N/D')}
CUP: {json_data.get('cup', 'N/D')}
Anno campagna: {json_data.get('campaign_year', 'N/D')}
Sondaggi ({len(json_data.get('sondaggi', []))} totali):
{chr(10).join(sondaggi_summary)}

=== DATI STRUTTURATI (JSON) ===
{json.dumps(json_data, ensure_ascii=False, indent=2)[:15000]}"""
    
    if pages_text:
        system += f"\n\n=== TESTO COMPLETO DEL RAPPORTO ===\n{pages_text[:30000]}"
    
    return system


def chat_with_report(
    question: str,
    json_data: Dict,
    pages_text: Optional[str],
    history: List[Dict]
) -> str:
    """
    Répond à une question sur le rapport avec prompt caching.
    history = liste de {role, content} pour la continuité du chat.
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    system = build_system_prompt(json_data, pages_text)
    
    # Construire les messages avec cache sur le system prompt
    messages = list(history) + [{"role": "user", "content": question}]
    
    response = client.messages.create(
        model=MODEL_CHAT,
        max_tokens=MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"}  # Prompt caching ← clé
            }
        ],
        messages=messages
    )
    
    return response.content[0].text


def generate_executive_summary(json_data: Dict) -> str:
    """
    Génère un résumé exécutif en italien depuis le JSON structuré.
    """
    client  = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    sondaggi = json_data.get("sondaggi", [])
    
    # Calculs statistiques
    all_nspt = []
    for s in sondaggi:
        for spt in (s.get("spt") or s.get("spt_data") or []):
            if spt.get("Nspt") is not None:
                all_nspt.append(spt["Nspt"])
    
    prof_max = max(
        (s.get("profondita_totale_m") or 0) for s in sondaggi
    ) if sondaggi else 0
    
    falda_depths = [
        s["falda"].get("profondita_m") or s["falda"].get("depth_m")
        for s in sondaggi
        if s.get("falda") and not (s["falda"].get("assente") or s["falda"].get("absent"))
        and (s["falda"].get("profondita_m") or s["falda"].get("depth_m"))
    ]
    
    prompt = f"""Genera un Executive Summary professionale in italiano per questa relazione geotecnica.
Struttura: [Progetto] [Campagna indagini] [Sondaggi] [Profondità] [Prove SPT] [Permeabilità] [Falda] [Risultati principali] [Criticità] [Dati mancanti] [Conclusione]
Stile: tecnico, sintetico, ~300 parole. NON scrivere "conforme NTC 2018" — usa "strutturato per l'esploitazione geotecnica".

DATI:
- File: {json_data.get('source_file')}
- CUP: {json_data.get('cup', 'N/D')}
- Sondaggi: {len(sondaggi)} totali
- Profondità max: {prof_max}m
- SPT totali: {sum(len(s.get('spt') or s.get('spt_data') or []) for s in sondaggi)}
- Nspt range: {min(all_nspt) if all_nspt else 'N/D'} - {max(all_nspt) if all_nspt else 'N/D'}
- Lefranc totali: {sum(len(s.get('permeability') or s.get('permeability_data') or []) for s in sondaggi)}
- Falda: {len(falda_depths)} sondaggi con falda, profondità {round(sum(falda_depths)/len(falda_depths),1) if falda_depths else 'N/D'}m media
- JSON completo: {json.dumps(json_data, ensure_ascii=False)[:8000]}"""
    
    response = client.messages.create(
        model=MODEL_CHAT,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


def generate_risk_flags(json_data: Dict) -> List[Dict]:
    """
    Calcule les risk flags de manière DÉTERMINISTE (0 appel IA).
    Règles métier fixes — pas de jugement libre de l'IA.
    """
    flags = []
    sondaggi = json_data.get("sondaggi", [])
    
    NSPT_SOGLIA_BASSA  = 5    # Nspt molto basso
    NSPT_SOGLIA_ALTA   = 50   # Rifiuto strumentale
    FALDA_SOGLIA       = 2.0  # Falda superficiale
    
    for s in sondaggi:
        sid = s.get("sondage_id", "?")
        spt_list = s.get("spt") or s.get("spt_data") or []
        
        # SPT bassi
        for spt in spt_list:
            nspt = spt.get("Nspt")
            prof = spt.get("prof") or spt.get("depth_m")
            if nspt is not None and nspt <= NSPT_SOGLIA_BASSA:
                flags.append({
                    "severity": "WARNING",
                    "sondage":  sid,
                    "campo":    "SPT",
                    "msg":      f"Nspt={nspt} ≤ {NSPT_SOGLIA_BASSA} a prof.={prof}m — suolo molto soffice",
                    "pagina":   spt.get("page")
                })
            if nspt is not None and nspt >= NSPT_SOGLIA_ALTA:
                flags.append({
                    "severity": "INFO",
                    "sondage":  sid,
                    "campo":    "SPT",
                    "msg":      f"Nspt={nspt} ≥ {NSPT_SOGLIA_ALTA} a prof.={prof}m — possibile rifiuto strumentale",
                    "pagina":   spt.get("page")
                })
        
        # Falda superficiale
        falda = s.get("falda") or {}
        falda_depth = falda.get("profondita_m") or falda.get("depth_m")
        if falda_depth is not None and falda_depth <= FALDA_SOGLIA:
            flags.append({
                "severity": "WARNING",
                "sondage":  sid,
                "campo":    "FALDA",
                "msg":      f"Falda a {falda_depth}m dal p.c. — quota critica per fondazioni superficiali",
                "pagina":   (falda.get("pages") or [None])[0]
            })
        
        # Coordinate mancanti
        if not s.get("coordinates") or not (s.get("coordinates") or {}).get("lat"):
            flags.append({
                "severity": "INFO",
                "sondage":  sid,
                "campo":    "COORDINATE",
                "msg":      "Coordinate GPS non disponibili",
                "pagina":   None
            })
        
        # Quota mancante
        if s.get("elevation_m") is None:
            flags.append({
                "severity": "INFO",
                "sondage":  sid,
                "campo":    "QUOTA",
                "msg":      "Quota s.l.m. non disponibile",
                "pagina":   None
            })
    
    # Nessun sondaggio
    if len(sondaggi) == 0:
        flags.append({
            "severity": "ERROR",
            "sondage":  "TUTTI",
            "campo":    "ESTRAZIONE",
            "msg":      "Nessun sondaggio estratto — verificare il PDF",
            "pagina":   None
        })
    
    return flags


def check_if_geotechnical(pdf_first_pages_text: str) -> bool:
    """
    Garde-fou upload : vérifie que le PDF est bien un rapport géotechnique.
    Utilise Haiku (cheap) sur les premières pages.
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    response = client.messages.create(
        model=MODEL_GUARD,
        max_tokens=10,
        messages=[{
            "role": "user",
            "content": f"""Il seguente testo proviene da un rapporto geotecnico italiano 
(sondaggi, prove SPT, permeabilità, stratigrafie, etc.) ? 
Rispondi SOLO "SI" o "NO".

TESTO:
{pdf_first_pages_text[:2000]}"""
        }]
    )
    answer = response.content[0].text.strip().upper()
    return "SI" in answer
