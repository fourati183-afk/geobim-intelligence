"""
GeoBIM Intelligence — Extracteur LLM v1.0.0
Envoie les chunks de pages à Claude Sonnet 4.6 via tool use.
Produit exactement le schéma Pydantic défini dans schema.py.
"""
import os
import json
from typing import List, Dict, Optional
from dotenv import load_dotenv
import anthropic
from .schema import ExtractionResult, Sondaggio, SPTMeasure, PermeabilityMeasure, Coordinates, Falda, PermeabilityValue

load_dotenv()

MODEL_ID   = "claude-sonnet-4-6"
MAX_TOKENS = 8000

# ── Tool definition (function calling) ──────────────────────────────────────

EXTRACTION_TOOL = {
    "name": "extract_geotechnical_data",
    "description": (
        "Estrai i dati geotecnici ESATTAMENTE come presenti nelle pagine fornite. "
        "REGOLE ASSOLUTE: "
        "1) null se il dato non è presente — MAI inferire, MAI usare valori tipici. "
        "2) source_verbatim = testo esatto copiato dalla pagina (non parafrasare). "
        "3) page = numero di pagina (1-indexed) dove hai trovato il dato. "
        "4) Nspt = N2 + N3 (verifica prima di inserire). "
        "5) Se un sondaggio appare su più pagine, unisci i dati. "
        "6) Non inventare sondaggi non presenti nelle pagine fornite."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sondaggi": {
                "type": "array",
                "description": "Lista dei sondaggi trovati in queste pagine",
                "items": {
                    "type": "object",
                    "required": ["sondage_id", "sondage_type"],
                    "properties": {
                        "sondage_id": {"type": "string", "description": "Es: S01, S01BIS, S06R"},
                        "sondage_type": {"type": "string", "enum": ["rotary_carotaggio", "distruzione_di_nucleo"]},
                        "campaign_year": {"type": ["string", "null"]},
                        "cup": {"type": ["string", "null"], "description": "Codice CUP es. J21G24000050001"},
                        "data_esecuzione": {"type": ["string", "null"]},
                        "profondita_totale_m": {"type": ["number", "null"]},
                        "elevation_m": {"type": ["number", "null"], "description": "Quota in m s.l.m."},
                        "coordinates": {
                            "type": ["object", "null"],
                            "properties": {
                                "lat": {"type": ["number", "null"]},
                                "lng": {"type": ["number", "null"]},
                                "source_verbatim": {"type": ["string", "null"]},
                                "page": {"type": ["integer", "null"]}
                            }
                        },
                        "falda": {
                            "type": ["object", "null"],
                            "properties": {
                                "depth_m": {"type": ["number", "null"]},
                                "absent": {"type": "boolean"},
                                "date": {"type": ["string", "null"]},
                                "source_verbatim": {"type": ["string", "null"]},
                                "pages": {"type": "array", "items": {"type": "integer"}}
                            }
                        },
                        "pages_source": {"type": "array", "items": {"type": "integer"}},
                        "spt": {
                            "type": "array",
                            "description": "Misure SPT. Nspt DEVE essere N2+N3.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "prof": {"type": ["number", "null"]},
                                    "N1": {"type": ["integer", "null"]},
                                    "N2": {"type": ["integer", "null"]},
                                    "N3": {"type": ["integer", "null"]},
                                    "Nspt": {"type": ["integer", "null"]},
                                    "page": {"type": ["integer", "null"]},
                                    "source_verbatim": {"type": ["string", "null"]}
                                }
                            }
                        },
                        "permeability": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "prof": {"type": ["number", "null"]},
                                    "permeability": {
                                        "type": ["object", "null"],
                                        "properties": {"value": {"type": ["number", "null"]}, "unit": {"type": "string"}}
                                    },
                                    "page": {"type": ["integer", "null"]},
                                    "source_verbatim": {"type": ["string", "null"]}
                                }
                            }
                        }
                    }
                }
            },
            "cup_global": {"type": ["string", "null"], "description": "CUP trovato nelle prime pagine"},
            "campaign_year_global": {"type": ["string", "null"]},
            "detected_profile": {"type": ["string", "null"], "description": "italferr | aspi | generic"}
        },
        "required": ["sondaggi"]
    }
}


def build_prompt(chunk: List[Dict], chunk_index: int, total_chunks: int) -> List[Dict]:
    """Construit le message à envoyer à Claude pour un chunk de pages."""
    
    # Assembler le texte des pages natives
    text_parts = []
    image_parts = []
    
    for page in chunk:
        pnum = page["page_num"]
        if page["has_text_layer"]:
            text_parts.append(f"=== PAGINA {pnum} ===\n{page['text']}")
        else:
            # Page image-only : envoyer l'image
            if page.get("image_b64"):
                image_parts.append({
                    "page_num": pnum,
                    "b64": page["image_b64"]
                })
                text_parts.append(f"=== PAGINA {pnum} === [PAGINA IMMAGINE - vedi immagine allegata]")

    text_content = "\n\n".join(text_parts)
    
    # Construire le message multipart
    content = []
    
    # Ajouter les images des pages image-only
    for img in image_parts:
        content.append({
            "type": "text",
            "text": f"Pagina {img['page_num']} (immagine):"
        })
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": img["b64"]
            }
        })
    
    # Instruction principale
    content.append({
        "type": "text",
        "text": f"""Sei un esperto di geotecnica italiana specializzato in rapporti Italferr/RFI. Estrai i dati geotecnici dalle seguenti pagine (chunk {chunk_index+1}/{total_chunks}).

FORMATO ID SONDAGGIO (CRITICO — rispettare sempre):
- SEMPRE 2 cifre con zero davanti: S01, S02, S03 ... S09
- BIS: S01BIS, S02BIS ... S09BIS
- R: S06R
- MAI scrivere S1, S2, S3 senza zero!

REGOLE ASSOLUTE:
- Estrai SOLO ciò che è letteralmente presente nelle pagine fornite
- source_verbatim = copia ESATTA del testo dalla pagina (non parafrasare)
- null se il dato non c'è — MAI inventare, MAI usare valori tipici
- Nspt DEVE essere N2 + N3 (verifica!)
- Per le coordinate DMS (es. 43°13'45.13''N), converti in decimale
- Per la permeabilità k, usa la notazione scientifica (es. 6.15e-7)
- Sondaggi tipo "BIS" o con "R" finale = distruzione_di_nucleo
- Un sondaggio può essere su più pagine — raccoglie tutti i dati disponibili
- IGNORARE COMPLETAMENTE: CPTU, DPSH, prove penetrometriche statiche/dinamiche
- Quota: cerca "metri" E "mertri" (errore di battitura frequente nel PDF)

PAGINE:
{text_content}"""
    })
    
    return content


def extract_chunk(
    client: anthropic.Anthropic,
    chunk: List[Dict],
    chunk_index: int,
    total_chunks: int
) -> Dict:
    """Extrait les données d'un chunk de pages via Claude."""
    
    content = build_prompt(chunk, chunk_index, total_chunks)
    
    response = client.messages.create(
        model=MODEL_ID,
        max_tokens=MAX_TOKENS,
        temperature=0,
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": content}]
    )
    
    # Récupérer le résultat du tool use
    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_geotechnical_data":
            return block.input
    
    return {"sondaggi": []}


def merge_sondaggi(all_chunks_results: List[Dict], source_file: str) -> Dict:
    """
    Fusionne les résultats de tous les chunks.
    Un même sondage_id peut apparaître dans plusieurs chunks — on fusionne les données.
    """
    merged: Dict[str, Dict] = {}
    cup_global        = None
    campaign_year     = None
    detected_profile  = None
    
    for chunk_result in all_chunks_results:
        if chunk_result.get("cup_global"):
            cup_global = chunk_result["cup_global"]
        if chunk_result.get("campaign_year_global"):
            campaign_year = chunk_result["campaign_year_global"]
        if chunk_result.get("detected_profile"):
            detected_profile = chunk_result["detected_profile"]
        
        for s in chunk_result.get("sondaggi", []):
            sid = s.get("sondage_id", "").upper().strip()
            if not sid:
                continue
            
            if sid not in merged:
                merged[sid] = {
                    "sondage_id":          sid,
                    "sondage_type":        s.get("sondage_type", "rotary_carotaggio"),
                    "source_file":         source_file,
                    "campaign_year":       s.get("campaign_year") or campaign_year,
                    "cup":                 s.get("cup") or cup_global,
                    "data_esecuzione":     s.get("data_esecuzione"),
                    "profondita_totale_m": s.get("profondita_totale_m"),
                    "elevation_m":         s.get("elevation_m"),
                    "coordinates":         s.get("coordinates"),
                    "falda":               s.get("falda"),
                    "pages_source":        s.get("pages_source", []),
                    "spt":                 s.get("spt", []),
                    "permeability":        s.get("permeability", []),
                    "parametri":           [],
                }
            else:
                # Fusionner les données du même sondage
                existing = merged[sid]
                
                # Compléter les champs None
                for field in ["data_esecuzione", "profondita_totale_m",
                              "elevation_m", "coordinates", "falda",
                              "campaign_year", "cup"]:
                    if existing.get(field) is None and s.get(field) is not None:
                        existing[field] = s[field]
                
                # Fusionner SPT (éviter doublons par prof+N1+N2+N3)
                existing_spt_keys = {
                    (r.get("prof"), r.get("N1"), r.get("N2"), r.get("N3"))
                    for r in existing["spt"]
                }
                for spt in s.get("spt", []):
                    key = (spt.get("prof"), spt.get("N1"), spt.get("N2"), spt.get("N3"))
                    if key not in existing_spt_keys:
                        existing["spt"].append(spt)
                        existing_spt_keys.add(key)
                
                # Fusionner Permeability
                existing_perm_pages = {r.get("page") for r in existing["permeability"]}
                for perm in s.get("permeability", []):
                    if perm.get("page") not in existing_perm_pages:
                        existing["permeability"].append(perm)
                
                # Fusionner pages_source
                all_pages = set(existing["pages_source"]) | set(s.get("pages_source", []))
                existing["pages_source"] = sorted(all_pages)
    
    return {
        "sondaggi":         list(merged.values()),
        "cup":              cup_global,
        "campaign_year":    campaign_year,
        "detected_profile": detected_profile,
    }


def run_extraction(pdf_path: str, chunk_size: int = 40) -> Dict:
    """
    Pipeline d'extraction complet : ingestion → chunks → Claude → fusion.
    """
    from .ingestor import load_pdf, chunk_pages
    from datetime import date
    
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    print(f"\n[Extractor] PDF : {pdf_path}")
    pages  = load_pdf(pdf_path)
    chunks = chunk_pages(pages, chunk_size=chunk_size)
    
    print(f"[Extractor] {len(chunks)} chunks de ~{chunk_size} pages")
    
    all_results = []
    for i, chunk in enumerate(chunks):
        print(f"[Extractor] Chunk {i+1}/{len(chunks)} "
              f"(pages {chunk[0]['page_num']}-{chunk[-1]['page_num']})...")
        result = extract_chunk(client, chunk, i, len(chunks))
        all_results.append(result)
        print(f"  → {len(result.get('sondaggi', []))} sondaggi trovati")
    
    print("[Extractor] Fusione risultati...")
    merged = merge_sondaggi(all_results, source_file=pdf_path)
    
    final = {
        "source_file":      pdf_path,
        "detected_profile": merged.get("detected_profile"),
        "cup":              merged.get("cup"),
        "campaign_year":    merged.get("campaign_year"),
        "extraction_date":  str(date.today()),
        "pipeline_version": "v1a-llm",
        "sondaggi":         merged["sondaggi"],
    }
    
    print(f"\n[Extractor] ✅ Terminato : {len(final['sondaggi'])} sondaggi estratti")
    return final
