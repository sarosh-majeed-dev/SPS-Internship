"""
Local AI extraction engine
--------------------------
Uses a small on-device neural model (all-MiniLM-L6-v2 sentence embeddings) to
*semantically* understand an RFP, instead of matching keywords. It runs fully
offline on CPU - the model ships inside  models/all-MiniLM-L6-v2  so there is no
API, no API key, and no internet needed at run time.

It extracts the three items required by the SPS RFP checklist:
  1. Deliverables          - what the vendor must provide
  2. Evaluation Criteria   - how the client scores proposals
  3. Compliance Checklist  - department tasks (Financial/Accounting, Legal,
                             Operations, Technical) with GO / NO-GO decisions

If the model cannot be loaded, the engine transparently falls back to the
rule-based analyzer so the portal always works.
"""

import os
import re

import rfp_analyzer as base   # text extraction, templates, decision rules, fallback

_MODEL = None
_MODEL_DIR = os.path.join(os.path.dirname(__file__), "models", "all-MiniLM-L6-v2")


# --------------------------------------------------------------------------- #
#  Model loading
# --------------------------------------------------------------------------- #

def load_model():
    """Load the bundled embedding model once. Returns None if unavailable."""
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    try:
        from sentence_transformers import SentenceTransformer
        source = _MODEL_DIR if os.path.isdir(_MODEL_DIR) else "all-MiniLM-L6-v2"
        _MODEL = SentenceTransformer(source, device="cpu")
    except Exception:
        _MODEL = None
    return _MODEL


def ai_available():
    return load_model() is not None


# --------------------------------------------------------------------------- #
#  Semantic helpers
# --------------------------------------------------------------------------- #

def _candidate_sentences(text):
    """Sentences worth analysing - filter out very short / very long noise."""
    out = []
    for s in base._sentences(text):
        words = s.split()
        if 4 <= len(words) <= 60 and not (s.upper() == s and len(words) <= 7):
            out.append(s)
    # de-duplicate, preserve order
    seen, uniq = set(), []
    for s in out:
        k = s.lower()[:90]
        if k not in seen:
            seen.add(k)
            uniq.append(s)
    return uniq


def _cos(model, sentences, prototypes):
    """Return cosine-similarity matrix [len(sentences) x len(prototypes)]."""
    from sentence_transformers import util
    emb_s = model.encode(sentences, convert_to_tensor=True, normalize_embeddings=True,
                         batch_size=64, show_progress_bar=False)
    emb_p = model.encode(prototypes, convert_to_tensor=True, normalize_embeddings=True,
                         show_progress_bar=False)
    return util.cos_sim(emb_s, emb_p).cpu().numpy()


# --------------------------------------------------------------------------- #
#  Prototypes (what each concept "means")
# --------------------------------------------------------------------------- #

DELIVERABLE_PROTOTYPES = [
    "The vendor shall provide a product, service or solution.",
    "The contractor must deliver, implement, develop, install or maintain a system.",
    "Scope of work: services the contractor is required to perform and submit.",
]

OBLIGATION_CUES = ("shall", "must", "will ", "required to", "responsible for",
                   "provide", "deliver", "implement", "furnish", "maintain",
                   "develop", "install", "perform", "supply", "submit")

EVAL_PROTOTYPE = "A criterion used to evaluate, score, weight or award the proposal."


def _compliance_prototypes():
    """One descriptive prototype per checklist item, grouped by department."""
    protos, index = [], []
    for dept, items in base.COMPLIANCE_TEMPLATE.items():
        for entry in items:
            text = entry["item"] + ". " + ", ".join(entry["keywords"])
            protos.append(text)
            index.append((dept, entry["item"]))
    return protos, index


# --------------------------------------------------------------------------- #
#  AI extractors
# --------------------------------------------------------------------------- #

# compliance/legal-flavoured obligations that are NOT deliverables
NON_DELIVERABLE = ("comply with", "registered to do business", "e-verify",
                   "laws and regulations", "terms and conditions",
                   "eligibility", "insurance coverage", "liability insurance",
                   "general liability", "insurance of", "bid bond", "performance bond")

# intro / header phrases that introduce a list but are not deliverables themselves
HEADER_PHRASES = ("following deliverables", "the following", "as follows",
                  "scope of work", "scope of services", "are as follows",
                  "include the following", "consist of the following")

_SUBJECT_PREFIX = re.compile(
    r"^(the\s+)?(selected\s+|successful\s+|awarded\s+)?"
    r"(contractor|vendor|bidder|offeror|proposer|firm|consultant|company|"
    r"supplier|provider|respondent)\s+"
    r"(shall|must|will|is required to|agrees to|is expected to)\s+",
    re.I,
)


def _clean_deliverable(s: str) -> str:
    """Turn a raw RFP sentence into a crisp action item."""
    s = s.strip().rstrip(".")
    s = _SUBJECT_PREFIX.sub("", s)                 # drop "The vendor shall ..."
    s = re.sub(r"^(shall|must|will)\s+", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:1].upper() + s[1:] if s else s


# a cleaned deliverable should read as an action: "Provide ...", "Deliver ..."
ACTION_STARTS = {
    "provide", "deliver", "furnish", "supply", "implement", "develop", "design",
    "install", "perform", "maintain", "conduct", "produce", "deploy", "configure",
    "integrate", "build", "support", "establish", "create", "manage", "operate",
    "host", "migrate", "train", "prepare", "develop", "ensure",
}


def _is_action_item(cleaned: str) -> bool:
    first = re.sub(r"[^a-z]", "", cleaned.split()[0].lower()) if cleaned.split() else ""
    return first in ACTION_STARTS


def _is_header(s: str) -> bool:
    low = s.lower().strip()
    if low.endswith(":"):
        return True
    if len(low.split()) <= 9 and any(h in low for h in HEADER_PHRASES):
        return True
    return False


# --- section-based deliverable extraction (bulleted lists under a heading) --- #

# note: no trailing \b after "deliverab" so it also matches "deliverables"
DELIV_HEADING = re.compile(
    r"\b(deliverab|scope of work|scope of services|services to be provided|"
    r"required services|tasks and deliverables|statement of work|"
    r"project deliverables|work products)", re.I)

_BULLET = re.compile(r"^\s*([-•*–·▪◦‣]|\(?[a-zA-Z0-9]{1,3}[.)])\s+")

_INTRO_FIRST_WORDS = {"the", "this", "these", "all", "proposals", "proposal",
                      "vendors", "vendor", "bidders", "please", "note", "each",
                      "any", "as", "below", "following", "responses"}


def _clean_listitem(t: str) -> str:
    t = _BULLET.sub("", t).strip().rstrip(".;:")
    t = re.sub(r"\s+", " ", t)
    return t[:1].upper() + t[1:] if t else t


def _is_stop_heading(t: str) -> bool:
    """A new ALL-CAPS section heading (e.g. 'EVALUATION CRITERIA') ends the list."""
    core = _BULLET.sub("", t).strip()
    letters = [c for c in core if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.8 \
            and len(core.split()) <= 8:
        return True
    return False


def _accept_listitem(t: str) -> bool:
    """Bulleted lines, or short title-style lines that aren't intro sentences."""
    if t.endswith(":") or _is_header(t):
        return False
    if _BULLET.match(t):
        return True
    first = re.sub(r"[^a-z]", "", t.split()[0].lower()) if t.split() else ""
    return (2 <= len(t.split()) <= 14 and not t.endswith(".")
            and t[:1].isupper() and first not in _INTRO_FIRST_WORDS)


def _section_deliverables(text: str):
    lines = text.splitlines()
    items, seen = [], set()
    n = len(lines)
    for i, line in enumerate(lines):
        if not (DELIV_HEADING.search(line) and len(line.split()) <= 10):
            continue
        j, taken, blanks = i + 1, 0, 0
        while j < n and taken < 30:
            t = lines[j].strip()
            if not t:
                blanks += 1
                if blanks >= 2 and taken > 0:
                    break
                j += 1
                continue
            blanks = 0
            if _is_stop_heading(t):              # next section -> stop
                break
            if _accept_listitem(t):
                # clean the same way as prose items so duplicates collapse
                c = _clean_deliverable(_BULLET.sub("", t).strip())
                k = c.lower()[:70]
                if c and 2 <= len(c.split()) <= 20 and k not in seen:
                    seen.add(k)
                    items.append(c)
                    taken += 1
            j += 1
    return items, seen


def _ai_deliverables(model, text, sentences, threshold=0.35):
    # 1) explicit bulleted/section deliverables (noun phrases are fine here)
    kept, seen = _section_deliverables(text)

    # 2) prose deliverables ("The contractor shall provide X" -> "Provide X")
    sims = _cos(model, sentences, DELIVERABLE_PROTOTYPES)
    for i, s in enumerate(sentences):           # document order for readability
        score = float(sims[i].max())
        low = s.lower()
        has_cue = any(c in low for c in OBLIGATION_CUES)
        is_compliance = any(p in low for p in NON_DELIVERABLE)
        if score < threshold or not has_cue or is_compliance or _is_header(s):
            continue
        cleaned = _clean_deliverable(s)
        if not _is_action_item(cleaned):
            continue
        key = cleaned.lower()[:70]
        if key not in seen:
            seen.add(key)
            kept.append(cleaned)
    return kept[:40]


def _ai_evaluation(model, text, sentences, threshold=0.34):
    # 1) keep the reliable weighted-section extraction
    results = base.extract_evaluation_criteria(text)
    have = {r["criterion"].lower()[:60] for r in results}

    # 2) only fall back to a semantic pass when the document does not list
    #    weighted criteria (avoids adding intro/award sentences as noise)
    if len(results) >= 3:
        return results[:30]

    # meta lines that talk *about* the scoring rather than being a criterion
    meta = ("will be evaluated", "will be scored", "will be awarded",
            "best overall value", "following criteria", "following weighted")
    sims = _cos(model, sentences, [EVAL_PROTOTYPE])
    extra = sorted(
        ((float(sims[i][0]), s) for i, s in enumerate(sentences)),
        reverse=True,
    )
    for score, s in extra:
        if score < threshold:
            break
        low = s.lower()
        if any(mw in low for mw in meta):
            continue
        key = base._clean_criterion(s).lower()[:60]
        if key and key not in have:
            have.add(key)
            m = re.search(r"(\d{1,3})\s?(%|percent|points|pts)", low)
            results.append({"criterion": base._clean_criterion(s),
                            "weight": m.group(0) if m else None})
    return results[:30]


def _ai_compliance(model, text, sentences, threshold=0.33):
    protos, index = _compliance_prototypes()
    sims = _cos(model, sentences, protos)   # [sentences x items]

    # best sentence per checklist item
    best = {}
    for j, (dept, item) in enumerate(index):
        col = sims[:, j]
        i = int(col.argmax())
        best[(dept, item)] = (float(col[i]), sentences[i])

    report, decisions = {}, []
    for dept, items in base.COMPLIANCE_TEMPLATE.items():
        rows = []
        for entry in items:
            item = entry["item"]
            score, evidence = best[(dept, item)]
            found = score >= threshold
            status = "Found in RFP" if found else "Not addressed - confirm N/A"
            decision = ""
            decision_reason = ""

            if item == "Payment Terms":
                d, reason = base._payment_decision(text)
                if d:
                    decision, decision_reason = d, reason
                    decisions.append(("Payment Terms", d, reason))
            if item == "Insurance Requirements":
                d, reason = base._insurance_decision(text)
                if d:
                    decision, decision_reason = d, reason
                    decisions.append(("Insurance", d, reason))

            verdict, why = _item_verdict(item, found, decision, decision_reason, evidence)
            rows.append({
                "Department": dept,
                "Checklist Item": item,
                "Status": status,
                "Verdict": verdict,
                "Reason": why,
                "Confidence": f"{score*100:.0f}%" if found else "-",
                "Decision": decision,
                "Evidence": evidence if found else "-",
            })
        report[dept] = rows
    return report, decisions


def _item_verdict(item, found, decision, decision_reason, evidence):
    """Per-item GO / REVIEW / NO-GO verdict plus a plain-English reason.

    NO-GO and ESCALATE reasons cite the specific SPS policy rule that was
    triggered; GO cites the RFP evidence; REVIEW flags a gap to confirm.
    """
    if decision == "NO-GO":
        return "NO-GO", decision_reason
    if decision == "ESCALATE":
        return "REVIEW", decision_reason
    if found:
        return "GO", f"Addressed in the RFP: {evidence}"
    return "REVIEW", (
        f"No specific {item.lower()} found in the RFP. Confirm with the responsible "
        f"department or mark as not applicable per the SPS checklist before bidding.")


# --------------------------------------------------------------------------- #
#  Top-level
# --------------------------------------------------------------------------- #

def analyze(file_bytes, filename, use_ai=True):
    text = base.extract_text(file_bytes, filename)
    model = load_model() if use_ai else None

    if model is None:
        # graceful fallback to the rule-based engine
        result = base.analyze(file_bytes, filename)
        result["engine"] = "Rule-based (fallback)"
        for rows in result["compliance"].values():
            for r in rows:
                r.setdefault("Confidence", "-")
                found = r["Status"] == "Found in RFP"
                verdict, why = _item_verdict(
                    r["Checklist Item"], found, r.get("Decision", ""),
                    r.get("Decision", ""), r.get("Evidence", "-"))
                r.setdefault("Verdict", verdict)
                r.setdefault("Reason", why)
        return result

    sentences = _candidate_sentences(text)
    if not sentences:
        sentences = ["(no readable text found)"]

    compliance, decisions = _ai_compliance(model, text, sentences)
    rec, rec_reason = base.overall_recommendation(decisions)

    return {
        "engine": "Local AI (MiniLM embeddings)",
        "char_count": len(text),
        "word_count": len(text.split()),
        "deliverables": _ai_deliverables(model, text, sentences),
        "evaluation": _ai_evaluation(model, text, sentences),
        "compliance": compliance,
        "decisions": decisions,
        "recommendation": rec,
        "recommendation_reason": rec_reason,
        "raw_text": text,
    }
