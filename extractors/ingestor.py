"""
GeoBIM Intelligence — Ingestion PyMuPDF v1.0.0
Lit le PDF page par page, détecte si la page a une couche texte ou est image-only.
"""
import fitz  # PyMuPDF
import base64
from pathlib import Path
from typing import List, Dict


def load_pdf(pdf_path: str) -> List[Dict]:
    """
    Charge le PDF et retourne une liste de pages.
    Chaque page : {page_num, text, has_text_layer, image_b64 (si image-only), word_count}
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF non trouvé : {pdf_path}")

    doc   = fitz.open(str(pdf_path))
    pages = []

    for i, page in enumerate(doc):
        text       = page.get_text("text").strip()
        word_count = len(text.split()) if text else 0
        has_text   = word_count >= 30  # seuil : <30 mots = image-only

        page_data = {
            "page_num":      i + 1,
            "text":          text if has_text else "",
            "has_text_layer": has_text,
            "word_count":    word_count,
            "image_b64":     None,
        }

        # Rasteriser les pages sans couche texte (logs graphiques, etc.)
        if not has_text:
            mat  = fitz.Matrix(2.0, 2.0)  # 2x zoom pour qualité
            pix  = page.get_pixmap(matrix=mat)
            page_data["image_b64"] = base64.b64encode(pix.tobytes("png")).decode()

        pages.append(page_data)

    doc.close()
    print(f"[Ingestor] {len(pages)} pages | "
          f"texte natif: {sum(1 for p in pages if p['has_text_layer'])} | "
          f"image-only: {sum(1 for p in pages if not p['has_text_layer'])}")
    return pages


def chunk_pages(pages: List[Dict], chunk_size: int = 40) -> List[List[Dict]]:
    """Découpe la liste de pages en chunks de ~40 pages."""
    return [pages[i:i+chunk_size] for i in range(0, len(pages), chunk_size)]
