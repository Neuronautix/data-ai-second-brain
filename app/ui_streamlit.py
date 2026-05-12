from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from app.query_decision import decide

st.set_page_config(page_title="CHU Data/AI Second Brain", layout="wide")
st.title("CHU / University Hospital Data-AI Second Brain (MVP)")

kb_path = Path("data/kb/kb.json")


tab_ingest, tab_kb, tab_analyze, tab_brief = st.tabs(
    ["Ingest source", "View KB", "Analyze project", "Generate DPO/legal brief"]
)

with tab_ingest:
    st.write("Use CLI scripts for ingestion in MVP:")
    st.code("python -m app.ingest_pdf\npython -m app.ingest_web")

with tab_kb:
    if kb_path.exists():
        st.json(json.loads(kb_path.read_text(encoding="utf-8")))
    else:
        st.warning("KB not found. Run normalization first.")

with tab_analyze:
    project_text = st.text_area("Paste project description", height=220)
    if st.button("Analyze"):
        if not project_text.strip():
            st.error("Please provide a project description.")
        else:
            output = decide(project_text, kb_path=kb_path)
            st.json(output.model_dump(mode="json"))

with tab_brief:
    project_text = st.text_area("Project text for DPO/legal note", key="brief")
    if st.button("Generate brief"):
        result = decide(project_text, kb_path=kb_path)
        st.markdown("### DPO/Legal brief (draft)")
        st.write(
            {
                "project_finality": "unknown"
                if "Project finality is unclear" in result.missing_information
                else "to validate",
                "data_categories": "to validate",
                "data_source": "to validate",
                "actors": "to validate",
                "processing_operations": "to validate",
                "external_partners": "condition.has_external_partner" in result.activated_conditions,
                "unknowns": result.missing_information,
                "proposed_legal_questions": [
                    "What legal basis applies?",
                    "What contractual framework is required?",
                ],
                "points_requiring_validation": [
                    "Requires DPO/legal validation",
                    "No legal approval is issued by this assistant",
                ],
            }
        )
