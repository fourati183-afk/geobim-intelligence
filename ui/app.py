"""
GeoBIM Intelligence — Streamlit App V1a
Upload PDF → Extraction → Vérification humaine → Excel + Chat
"""
import streamlit as st
import json
import os
import sys
import tempfile
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Ajouter le dossier racine au path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))

st.set_page_config(
    page_title="GeoBIM Intelligence",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── CSS Professionnel ────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Palette professionnelle géotechnique */
  :root {
    --blue-dark:  #1F4E79;
    --blue-mid:   #2E75B6;
    --blue-light: #BDD7EE;
    --green-ok:   #375623;
    --orange-warn:#7F5B00;
    --red-err:    #9C0006;
    --bg-alt:     #F0F6FF;
  }

  .main { background: #FAFBFF; }

  .hero-banner {
    background: linear-gradient(135deg, #1F4E79 0%, #2E75B6 100%);
    color: white;
    padding: 1.5rem 2rem;
    border-radius: 10px;
    margin-bottom: 1.5rem;
  }
  .hero-banner h1 { margin: 0; font-size: 1.8rem; }
  .hero-banner p  { margin: 0.3rem 0 0; opacity: 0.85; font-size: 0.95rem; }

  .metric-card {
    background: white;
    border: 1px solid #D6E4F0;
    border-left: 4px solid #2E75B6;
    padding: 1rem;
    border-radius: 8px;
    text-align: center;
  }
  .metric-card .val { font-size: 2rem; font-weight: 700; color: #1F4E79; }
  .metric-card .lbl { font-size: 0.8rem; color: #666; text-transform: uppercase; }

  .status-ok      { color: #375623; font-weight: 600; }
  .status-warning { color: #7F5B00; font-weight: 600; }
  .status-error   { color: #9C0006; font-weight: 600; }

  .flag-warning { background: #FFEB9C; border-left: 3px solid #F0A500; padding: 0.5rem 1rem; border-radius: 4px; margin: 0.3rem 0; }
  .flag-info    { background: #D6E4F0; border-left: 3px solid #2E75B6; padding: 0.5rem 1rem; border-radius: 4px; margin: 0.3rem 0; }
  .flag-error   { background: #FFC7CE; border-left: 3px solid #C00000; padding: 0.5rem 1rem; border-radius: 4px; margin: 0.3rem 0; }

  .chat-user { background: #1F4E79; color: white; padding: 0.7rem 1rem; border-radius: 12px 12px 4px 12px; margin: 0.5rem 0; }
  .chat-ai   { background: white; border: 1px solid #D6E4F0; padding: 0.7rem 1rem; border-radius: 12px 12px 12px 4px; margin: 0.5rem 0; }

  .disclaimer {
    background: #FFF9E6;
    border: 1px solid #F0A500;
    padding: 0.7rem 1rem;
    border-radius: 6px;
    font-size: 0.82rem;
    color: #5C4000;
    margin: 0.5rem 0;
  }

  div[data-testid="stSidebar"] { background: #F0F6FF; }
</style>
""", unsafe_allow_html=True)


# ── État de la session ───────────────────────────────────────────────────────
if "report_data"   not in st.session_state: st.session_state.report_data   = None
if "pages"         not in st.session_state: st.session_state.pages         = None
if "pages_text"    not in st.session_state: st.session_state.pages_text    = None
if "report_id"     not in st.session_state: st.session_state.report_id     = None
if "chat_history"  not in st.session_state: st.session_state.chat_history  = []
if "processing"    not in st.session_state: st.session_state.processing    = False
if "summary_text"  not in st.session_state: st.session_state.summary_text  = None
if "risk_flags"    not in st.session_state: st.session_state.risk_flags    = None


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏗️ GeoBIM V1a")
    st.markdown("*Copilote IA Géotechnique*")
    st.divider()

    # Historique des rapports
    try:
        from db.database import init_db, list_reports, load_report
        init_db()
        reports = list_reports()
        if reports:
            st.markdown("### 📂 Rapports précédents")
            for r in reports[:5]:
                if st.button(f"📄 {r['filename'][:30]}", key=f"hist_{r['report_id']}"):
                    loaded = load_report(r["report_id"])
                    if loaded:
                        st.session_state.report_data  = loaded["json_data"]
                        st.session_state.pages_text   = loaded["pages_text"]
                        st.session_state.report_id    = r["report_id"]
                        st.session_state.chat_history = []
                        st.rerun()
    except Exception:
        pass

    st.divider()
    st.markdown("### ⚙️ Paramètres")
    chunk_size = st.slider("Pages par chunk IA", 20, 60, 40, 5)
    st.caption("Plus grand = moins d'appels mais plus lent")


# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero-banner">
  <h1>🏗️ GeoBIM Intelligence</h1>
  <p>Estrazione automatica dati geotecnici · PDF → Excel BIM · Strutturato per l'esploitazione geotecnica</p>
</div>
""", unsafe_allow_html=True)


# ── Upload zone ──────────────────────────────────────────────────────────────
if st.session_state.report_data is None:
    st.markdown("### 📤 Carica il tuo rapporto geotecnico")

    uploaded = st.file_uploader(
        "PDF geotecnico italiano (Italferr, RFI, ANAS, ASPI, BET privati...)",
        type=["pdf"],
        help="Il file rimane privato — non viene mai inviato a GitHub"
    )

    if uploaded:
        col1, col2 = st.columns(2)
        with col1:
            mode_excel = st.button("📊 Genera Excel + Estrai dati", type="primary", use_container_width=True)
        with col2:
            mode_chat  = st.button("💬 Solo domande (senza Excel)", use_container_width=True)

        if mode_excel or mode_chat:
            with st.spinner("📖 Lettura PDF..."):
                # Sauvegarder le PDF temporairement
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded.read())
                    tmp_path = tmp.name

                from extractors.ingestor import load_pdf
                pages = load_pdf(tmp_path)
                st.session_state.pages = pages

                # Texte pour le chat
                pages_text = "\n\n".join(
                    f"=== PAGINA {p['page_num']} ===\n{p['text']}"
                    for p in pages if p.get("text")
                )
                st.session_state.pages_text = pages_text

                # Garde-fou : vérifier que c'est bien un rapport géotechnique
                first_text = " ".join(p["text"] for p in pages[:5] if p.get("text"))
                from utils.chat import check_if_geotechnical
                if not check_if_geotechnical(first_text):
                    st.error("❌ Ce PDF ne semble pas être un rapport géotechnique. Veuillez charger le bon fichier.")
                    os.unlink(tmp_path)
                    st.stop()

            if mode_excel:
                # Mode A : Extraction complète
                with st.spinner("🤖 Extraction IA en cours (Claude Sonnet 4.6)..."):
                    progress = st.progress(0, text="Analyse des pages...")

                    from extractors.llm_extractor import run_extraction, extract_chunk
                    from extractors.ingestor import chunk_pages
                    from extractors.verifier import verify_verbatim
                    from pipeline_new.adapter import llm_to_step5_format
                    from db.database import save_report

                    chunks = chunk_pages(pages, chunk_size=chunk_size)
                    all_results = []

                    import anthropic, os as _os
                    client = anthropic.Anthropic(api_key=_os.getenv("ANTHROPIC_API_KEY"))

                    from extractors.llm_extractor import extract_chunk, merge_sondaggi
                    from datetime import date

                    for i, chunk in enumerate(chunks):
                        progress.progress(
                            int((i/len(chunks))*80),
                            text=f"Chunk {i+1}/{len(chunks)} (pagine {chunk[0]['page_num']}-{chunk[-1]['page_num']})..."
                        )
                        result = extract_chunk(client, chunk, i, len(chunks))
                        all_results.append(result)

                    progress.progress(85, text="Fusione risultati...")
                    merged = merge_sondaggi(all_results, uploaded.name)
                    llm_result = {
                        "source_file":      uploaded.name,
                        "detected_profile": merged.get("detected_profile"),
                        "cup":              merged.get("cup"),
                        "campaign_year":    merged.get("campaign_year"),
                        "extraction_date":  str(date.today()),
                        "pipeline_version": "v1a-llm",
                        "sondaggi":         merged["sondaggi"],
                    }

                    progress.progress(90, text="Verifica verbatim...")
                    sondaggi_v, anomalies = verify_verbatim(llm_result["sondaggi"], pages)
                    llm_result["sondaggi"] = sondaggi_v

                    progress.progress(95, text="Salvataggio...")
                    report_id = save_report(
                        filename=uploaded.name,
                        json_data=llm_result,
                        pages_text=pages_text
                    )

                    progress.progress(100, text="✅ Completato!")

                st.session_state.report_data = llm_result
                st.session_state.report_id   = report_id
                os.unlink(tmp_path)
                st.rerun()

            elif mode_chat:
                # Mode B : Seulement le chat, extraction légère
                with st.spinner("📖 Préparation du chat..."):
                    from db.database import save_report
                    # Extraction minimale sans LLM pour le chat seul
                    minimal_data = {
                        "source_file":      uploaded.name,
                        "sondaggi":         [],
                        "pipeline_version": "v1a-chat-only"
                    }
                    report_id = save_report(
                        filename=uploaded.name,
                        json_data=minimal_data,
                        pages_text=pages_text
                    )
                    st.session_state.report_data = minimal_data
                    st.session_state.report_id   = report_id
                    os.unlink(tmp_path)
                    st.rerun()


# ── Dashboard rapport ─────────────────────────────────────────────────────────
else:
    data     = st.session_state.report_data
    sondaggi = data.get("sondaggi", [])

    # Métriques en haut
    spt_tot   = sum(len(s.get("spt") or s.get("spt_data") or []) for s in sondaggi)
    perm_tot  = sum(len(s.get("permeability") or s.get("permeability_data") or []) for s in sondaggi)
    falda_tot = sum(1 for s in sondaggi if s.get("falda") and
                   (s["falda"].get("profondita_m") or s["falda"].get("depth_m") or s["falda"].get("absent")))
    gps_tot   = sum(1 for s in sondaggi if s.get("coordinates"))

    col1, col2, col3, col4, col5 = st.columns(5)
    for col, val, lbl in [
        (col1, len(sondaggi), "Sondaggi"),
        (col2, spt_tot,       "SPT"),
        (col3, perm_tot,      "Lefranc"),
        (col4, falda_tot,     "Falda"),
        (col5, gps_tot,       "GPS"),
    ]:
        with col:
            st.markdown(f"""
            <div class="metric-card">
              <div class="val">{val}</div>
              <div class="lbl">{lbl}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown(f"**📄 {data.get('source_file','?')}** · "
                f"Profilo: `{data.get('detected_profile','N/D')}` · "
                f"CUP: `{data.get('cup','N/D')}` · "
                f"Anno: `{data.get('campaign_year','N/D')}`")
    st.divider()

    # Onglets
    tab_data, tab_verify, tab_excel, tab_chat, tab_summary, tab_risk = st.tabs([
        "📊 Dati", "✅ Verifica", "📥 Excel", "💬 Chat", "📋 Summary", "⚠️ Risk"
    ])

    # ── TAB 1 : Données ──────────────────────────────────────────────────
    with tab_data:
        st.markdown("### Dati estratti per sondaggio")
        for s in sondaggi:
            sid      = s.get("sondage_id", "?")
            spt_list = s.get("spt") or s.get("spt_data") or []
            perm_list= s.get("permeability") or s.get("permeability_data") or []

            with st.expander(f"🕳️ {sid} — {len(spt_list)} SPT · {len(perm_list)} Lefranc · quota={s.get('elevation_m','?')}m"):
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f"**Tipo:** {s.get('sondage_type','?')}")
                    st.markdown(f"**Profondità:** {s.get('profondita_totale_m','?')} m")
                    st.markdown(f"**Data:** {s.get('data_esecuzione','N/D')}")
                    falda = s.get("falda") or {}
                    fd    = falda.get("profondita_m") or falda.get("depth_m")
                    st.markdown(f"**Falda:** {fd if fd else 'ASSENTE' if falda.get('absent') or falda.get('assente') else 'N/D'} m")
                with col_b:
                    coords = s.get("coordinates") or {}
                    st.markdown(f"**Lat:** {coords.get('lat','N/D')}")
                    st.markdown(f"**Lon:** {coords.get('lon') or coords.get('lng','N/D')}")
                    st.markdown(f"**Quota:** {s.get('elevation_m','N/D')} m s.l.m.")
                    st.markdown(f"**Pagine:** {s.get('pages_source',[][:5])}")

                if spt_list:
                    st.markdown("**Misure SPT:**")
                    import pandas as pd
                    spt_df = pd.DataFrame([{
                        "Profondità (m)": r.get("prof") or r.get("depth_m"),
                        "N1": r.get("N1"), "N2": r.get("N2"), "N3": r.get("N3"),
                        "Nspt": r.get("Nspt"), "Pagina": r.get("page"),
                        "✓": "✅" if r.get("_verified") == "OK" else "⚠️" if r.get("_verified") else ""
                    } for r in spt_list])
                    st.dataframe(spt_df, use_container_width=True, hide_index=True)

                if perm_list:
                    st.markdown("**Permeabilità:**")
                    perm_df = pd.DataFrame([{
                        "Prof (m)": r.get("prof") or r.get("depth_m"),
                        "k (m/s)": (r.get("permeability") or {}).get("value"),
                        "Pagina": r.get("page")
                    } for r in perm_list])
                    st.dataframe(perm_df, use_container_width=True, hide_index=True)

    # ── TAB 2 : Vérification humaine ─────────────────────────────────────
    with tab_verify:
        st.markdown("### ✅ Verifica umana prima del download")
        st.markdown("""
        <div class="disclaimer">
        ⚠️ <strong>Richiesta verifica ingegnere:</strong> Controlla i valori estratti dall'IA prima di scaricare l'Excel. 
        I valori con ⚠️ non sono stati trovati esattamente nella pagina citata e richiedono controllo manuale.
        </div>""", unsafe_allow_html=True)

        # Statistiques verbatim
        all_spt = [spt for s in sondaggi for spt in (s.get("spt") or s.get("spt_data") or [])]
        verified_ok   = sum(1 for r in all_spt if r.get("_verified") == "OK")
        verified_fail = sum(1 for r in all_spt if r.get("_verified") == "FAIL")
        unverified    = sum(1 for r in all_spt if not r.get("_verified"))

        col1, col2, col3 = st.columns(3)
        col1.metric("✅ SPT vérifiés", verified_ok)
        col2.metric("⚠️ À confirmer", verified_fail)
        col3.metric("❓ Non vérifiés", unverified)

        # Tableau éditables des valeurs à confirmer
        suspicious = [
            {"Sondaggio": s.get("sondage_id"), **spt}
            for s in sondaggi
            for spt in (s.get("spt") or s.get("spt_data") or [])
            if spt.get("_verified") in ["FAIL", "IMAGE_ONLY"]
        ]
        if suspicious:
            st.warning(f"⚠️ {len(suspicious)} valeurs à vérifier manuellement :")
            import pandas as pd
            df_sus = pd.DataFrame([{
                "Sondaggio": r.get("Sondaggio"),
                "Prof (m)":  r.get("prof") or r.get("depth_m"),
                "N1": r.get("N1"), "N2": r.get("N2"), "N3": r.get("N3"),
                "Nspt": r.get("Nspt"),
                "Pagina": r.get("page"),
                "Status": r.get("_verified"),
                "Verbatim": str(r.get("source_verbatim",""))[:50]
            } for r in suspicious])
            st.dataframe(df_sus, use_container_width=True)
        else:
            st.success("✅ Tutti i valori verificati automaticamente!")

        human_ok = st.checkbox("✅ Ho verificato i dati. Procedi al download Excel.", value=False)
        st.session_state["human_verified"] = human_ok

    # ── TAB 3 : Excel ────────────────────────────────────────────────────
    with tab_excel:
        st.markdown("### 📥 Generazione Excel")

        if not st.session_state.get("human_verified", False):
            st.warning("⚠️ Completare la verifica nel tab **Verifica** prima di scaricare.")
        else:
            if st.button("🔄 Genera Excel maestre (7 feuilles)", type="primary"):
                with st.spinner("Generazione Excel..."):
                    try:
                        # Sauvegarder le JSON pour step9a
                        import tempfile, os
                        from pipeline_new.adapter import llm_to_step5_format
                        from step7_save import save_final
                        from step9a_excel import build_excel

                        step5 = llm_to_step5_format(data)
                        with tempfile.NamedTemporaryFile(mode="w", suffix="_step5.json",
                                                          delete=False, encoding="utf-8") as f:
                            json.dump(step5, f, ensure_ascii=False)
                            step5_tmp = f.name

                        # Adapter step6 comme step5 puis step7
                        step6 = step5  # Validation déjà faite
                        with tempfile.NamedTemporaryFile(mode="w", suffix="_step6.json",
                                                          delete=False, encoding="utf-8") as f:
                            json.dump(step6, f, ensure_ascii=False)
                            step6_tmp = f.name

                        step7 = save_final(step6_tmp)
                        with tempfile.NamedTemporaryFile(mode="w", suffix="_step7.json",
                                                          delete=False, encoding="utf-8") as f:
                            json.dump(step7, f, ensure_ascii=False)
                            step7_tmp = f.name

                        excel_path = build_excel(step7_tmp)

                        # Nettoyer
                        for tmp in [step5_tmp, step6_tmp, step7_tmp]:
                            try: os.unlink(tmp)
                            except: pass

                        # Proposer le téléchargement
                        with open(excel_path, "rb") as f:
                            st.download_button(
                                "📥 Scarica Excel GeoBIM",
                                data=f.read(),
                                file_name=Path(excel_path).name,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                type="primary"
                            )
                        st.success(f"✅ Excel pronto: {Path(excel_path).name}")

                    except Exception as e:
                        st.error(f"❌ Errore: {e}")
                        import traceback
                        st.code(traceback.format_exc())

    # ── TAB 4 : Chat ─────────────────────────────────────────────────────
    with tab_chat:
        st.markdown("### 💬 Chat con il rapporto")
        st.markdown("""
        <div class="disclaimer">
        🔒 Il chatbot risponde <strong>esclusivamente</strong> dai dati del rapporto caricato. 
        Cita sempre le pagine sorgente. Non usa conoscenze generali.
        </div>""", unsafe_allow_html=True)

        # Afficher l'historique
        for msg in st.session_state.chat_history:
            css_class = "chat-user" if msg["role"] == "user" else "chat-ai"
            prefix    = "👤" if msg["role"] == "user" else "🤖"
            content   = msg["content"] if isinstance(msg["content"], str) else str(msg["content"])
            st.markdown(f'<div class="{css_class}">{prefix} {content}</div>', unsafe_allow_html=True)

        # Input
        question = st.chat_input("Domanda sul rapporto... (es: Qual è la profondità di S01?)")
        if question:
            # Garde-fou chat : vérifier que la question est sur le rapport
            if any(kw in question.lower() for kw in ["meteo", "notizie", "politica", "ricetta", "calcio"]):
                st.warning("⚠️ Posso rispondere solo a domande sul rapporto geotecnico.")
            else:
                st.session_state.chat_history.append({"role": "user", "content": question})

                with st.spinner("🤖 Rispondo..."):
                    from utils.chat import chat_with_report

                    # Historique sans le dernier message (déjà ajouté)
                    history_for_api = st.session_state.chat_history[:-1]
                    response = chat_with_report(
                        question=question,
                        json_data=data,
                        pages_text=st.session_state.pages_text,
                        history=history_for_api
                    )

                st.session_state.chat_history.append({"role": "assistant", "content": response})

                # Sauvegarder session
                try:
                    from db.database import save_qa_session
                    save_qa_session(
                        st.session_state.report_id,
                        st.session_state.chat_history
                    )
                except Exception:
                    pass

                st.rerun()

        if st.button("🗑️ Svuota chat"):
            st.session_state.chat_history = []
            st.rerun()

    # ── TAB 5 : Executive Summary ─────────────────────────────────────────
    with tab_summary:
        st.markdown("### 📋 Executive Summary")

        if st.button("🔄 Genera Summary in italiano", type="primary"):
            with st.spinner("Generazione summary..."):
                from utils.chat import generate_executive_summary
                st.session_state.summary_text = generate_executive_summary(data)

        if st.session_state.summary_text:
            st.markdown(st.session_state.summary_text)
            st.download_button(
                "📥 Scarica Summary (TXT)",
                data=st.session_state.summary_text,
                file_name=f"summary_{data.get('source_file','rapport')}.txt",
                mime="text/plain"
            )

    # ── TAB 6 : Risk Flags ───────────────────────────────────────────────
    with tab_risk:
        st.markdown("### ⚠️ Segnalazioni di Attenzione")
        st.markdown("""
        <div class="disclaimer">
        ⚠️ <strong>Analisi preliminare — verificare con un ingegnere abilitato.</strong>
        Queste segnalazioni sono generate da regole deterministiche sui dati estratti, 
        non da giudizio libero dell'IA.
        </div>""", unsafe_allow_html=True)

        if st.button("🔄 Calcola Risk Flags", type="primary"):
            from utils.chat import generate_risk_flags
            st.session_state.risk_flags = generate_risk_flags(data)

        if st.session_state.risk_flags is not None:
            flags = st.session_state.risk_flags
            if not flags:
                st.success("✅ Nessuna segnalazione di attenzione rilevata.")
            else:
                warnings = [f for f in flags if f["severity"] == "WARNING"]
                errors   = [f for f in flags if f["severity"] == "ERROR"]
                infos    = [f for f in flags if f["severity"] == "INFO"]

                if errors:
                    st.error(f"❌ {len(errors)} errori critici")
                    for f in errors:
                        st.markdown(f'<div class="flag-error">❌ <b>{f["sondage"]}</b> — {f["campo"]}: {f["msg"]}</div>', unsafe_allow_html=True)

                if warnings:
                    st.warning(f"⚠️ {len(warnings)} segnalazioni di attenzione")
                    for f in warnings:
                        st.markdown(f'<div class="flag-warning">⚠️ <b>{f["sondage"]}</b> — {f["campo"]}: {f["msg"]} {("(pag."+str(f["pagina"])+")") if f["pagina"] else ""}</div>', unsafe_allow_html=True)

                if infos:
                    st.info(f"ℹ️ {len(infos)} informazioni")
                    for f in infos:
                        st.markdown(f'<div class="flag-info">ℹ️ <b>{f["sondage"]}</b> — {f["campo"]}: {f["msg"]}</div>', unsafe_allow_html=True)

    # Bouton reset
    st.divider()
    if st.button("🔄 Carica nuovo rapporto"):
        for key in ["report_data", "pages", "pages_text", "report_id",
                    "chat_history", "summary_text", "risk_flags", "human_verified"]:
            st.session_state[key] = None if key != "chat_history" else []
        st.rerun()
