# RFP Intelligence Portal

An AI-powered RFP review tool for SPS. Upload a Request for Proposal (PDF, DOCX
or TXT) and the portal automatically extracts:

1. **Deliverables** - a clear list of what we need to provide.
2. **Evaluation Criteria** - a weighted summary of how the client will judge our proposal.
3. **Compliance Checklist** - department tasks (Financial/Accounting, Legal,
   Operations, Technical) built directly on the SPS RFP review checklist,
   each with a confidence score, supporting evidence, and automatic GO / NO-GO flags.

## How the AI works (important)

The extraction is done by a small neural model (`all-MiniLM-L6-v2` sentence
embeddings) that **runs locally on the CPU**. It understands the *meaning* of
each clause, so it still finds a requirement even when the RFP words it
differently - unlike simple keyword search.

- **No API and no API key.** Nothing is sent to any external service.
- **No internet needed at run time.** The model is bundled inside `models/`,
  so it works fully offline on any machine.
- **Graceful fallback.** If the model folder is ever missing, the portal
  automatically falls back to a rule-based engine so it always runs.
- **Scanned PDFs supported.** If a PDF has no selectable text (an image/scanned
  document), the app automatically runs on-device OCR (PyMuPDF + RapidOCR) to
  read it - again with no external software and no internet.

---

## Project structure

```
RFP_Automation/
  app.py             Streamlit web portal (the interface)
  ai_extractor.py    Local AI engine (semantic extraction)
  rfp_analyzer.py    Document parsing + rule-based fallback + decision rules
  make_sample.py     Generates a dummy RFP for testing
  setup_model.py     (Optional) re-downloads the AI model into models/
  requirements.txt   Dependencies
  models/            Bundled offline AI model (all-MiniLM-L6-v2)
  sample_rfp/        Dummy RFP (sample_rfp.docx + sample_rfp.txt)
  README.md
```

---

## How to run

> Note: installing (steps 1 and 2 below) needs an internet connection once.
> After that, the app runs fully offline with no API and no internet.

**0. Install Python (first time only):**

Install Python 3.10 or newer from python.org, then open a terminal (PowerShell)
in this folder.

**1. Install the dependencies (first time only, needs internet):**

```powershell
pip install -r requirements.txt
```

This installs Streamlit, PyTorch, and the other tools used by the app.

**2. Download the local AI model (first time only, needs internet):**

```powershell
python setup_model.py
```

This saves the model into `models/` (about 88 MB). After this one-time step
the app runs fully offline. If you skip it, the model still downloads
automatically the first time you analyse a document.

**3. Launch the portal:**

```powershell
python -m streamlit run app.py
```

(If `streamlit` is on your PATH, `streamlit run app.py` also works.)
Your browser opens at `http://localhost:8501`.

> The AI model lives in `models/`. It is downloaded once by `setup_model.py`
> (or automatically on first use), and after that the app runs fully offline
> with no API and no internet.

---

## How to use

1. Click **Browse files** and upload an RFP (PDF / DOCX / TXT) - or click
   **Load sample RFP** in the sidebar to test the workflow immediately.
2. The portal compares the RFP against the built-in SPS checklist and shows a
   **Compliance score (%)**, matched vs missing counts, and a GO / NO-GO banner,
   then five tabs:
   - **Matches** - checklist requirements the RFP addresses (with evidence + confidence).
   - **Missing Requirements** - checklist items the RFP does not address (the gaps to review).
   - **Deliverables** - everything the vendor must provide (AI-ranked).
   - **Evaluation Criteria** - scored criteria with weights.
   - **Decision Rules** - the automatic GO / NO-GO logic that fired.
3. Export results as CSV, JSON, or TXT using the buttons at the bottom.

To analyse the real 70+ page RFP, just upload that PDF in step 1 - no other
changes needed.

---

## Decision rules (from the SPS checklist)

| Area           | Rule                                                        |
|----------------|-------------------------------------------------------------|
| Payment Terms  | NET30 -> GO; beyond NET30 -> escalate to Accounting         |
| Insurance      | up to \$5M -> GO; above \$5M -> NO-GO                       |
| E-Verify / MBE / Bonds / Registration | flagged for departmental review |

The overall recommendation is NO-GO if any hard limit is exceeded, ESCALATE if
a term needs Accounting sign-off, otherwise GO.
