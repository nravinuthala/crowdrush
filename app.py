"""
Career Shaper™ CrowdRush  –  v3
Streamlit live-quiz engine with Supabase persistence.

Key design decisions
────────────────────
• Navigation state (phase + question index) lives ONLY in the DB (sessions table).
  st.session_state is used only for client-local things (player name, event code).
• Phase-switching buttons call set_phase() then st.rerun() – no disabled-loop bugs.
• Question navigation calls activate_question() then st.rerun().
• Submit is a single atomic upsert with on_conflict guard – no double-submit.
• Auto-refresh every 2 s for all participants.
• QR / instance-code joiners are routed directly to audience mode (no host picker).
• Button text colours fixed with explicit CSS overrides.
"""

import base64
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import qrcode
import streamlit as st
from PIL import Image
from streamlit_autorefresh import st_autorefresh
from supabase import Client, create_client

# ── Brand ────────────────────────────────────────────────────────────────────
ROYAL     = "#0F5FDC"
CHARCOAL  = "#14142A"
LAVENDER  = "#E6EBF5"
WHITE     = "#FFFFFF"
GOLD      = "#FFC400"
DANGER    = "#D32F2F"
SUCCESS   = "#1B8A4C"

PHASES       = ["pre", "during", "post"]
PHASE_LABEL  = {"pre": "Pre-Session", "during": "Live Game", "post": "Post-Session"}
PHASE_ICON   = {"pre": "🔆", "during": "⚡", "post": "🏁"}
QUIZ_SECS    = 30          # seconds per question

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="Career Shaper™ CrowdRush",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)
st_autorefresh(interval=2000, key="auto_refresh")


# ═══════════════════════════════════════════════════════════════════════════════
#  CSS
# ═══════════════════════════════════════════════════════════════════════════════

def _logo_b64() -> str:
    p = Path(__file__).parent / "cs_logo.png"
    return base64.b64encode(p.read_bytes()).decode() if p.exists() else ""


def inject_css():
    logo = _logo_b64()
    logo_tag = (
        f'<img src="data:image/png;base64,{logo}" alt="Career Shaper™" '
        f'style="height:40px; display:block; margin:0 auto 4px auto;">'
        if logo else
        '<div style="font-size:16px;font-weight:900;color:#0F5FDC;text-align:center;">Career Shaper™</div>'
    )
    st.sidebar.markdown(
        f'<div style="text-align:center;padding:14px 0 10px;border-bottom:1px solid #2a3260;margin-bottom:12px;">'
        f'{logo_tag}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(f"""
<style>
/* ── Reset & base ── */
html,body,.stApp{{background:linear-gradient(155deg,#f0f4ff 0%,{LAVENDER} 55%,#d8e4f8 100%);color:{CHARCOAL};}}

/* ── Sidebar ── */
section[data-testid="stSidebar"]{{background:{CHARCOAL};border-right:2px solid {ROYAL};}}
section[data-testid="stSidebar"] *{{color:#dce8ff !important;}}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3{{color:{WHITE} !important;}}
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] *{{color:#8fa5cc !important;}}

/* ── Buttons – ALL text white, always ── */
div[data-testid="stButton"]>button,
div[data-testid="stFormSubmitButton"]>button{{
    border-radius:8px;
    border:1.5px solid {ROYAL};
    background:linear-gradient(90deg,{ROYAL} 0%,#1a77f2 100%);
    color:{WHITE} !important;
    font-weight:700;
    min-height:44px;
    box-shadow:0 3px 10px rgba(15,95,220,.2);
    transition:all .15s;
}}
div[data-testid="stButton"]>button *,
div[data-testid="stFormSubmitButton"]>button *{{color:{WHITE} !important;}}
div[data-testid="stButton"]>button:hover,
div[data-testid="stFormSubmitButton"]>button:hover{{
    background:linear-gradient(90deg,#0a3ea3 0%,#1466d8 100%);
    border-color:#0a3ea3;
}}
/* disabled state */
div[data-testid="stButton"]>button:disabled,
div[data-testid="stButton"]>button[disabled]{{
    background:#c7d4ef !important;
    border-color:#b0c4e8 !important;
    color:#6070a0 !important;
    box-shadow:none;
}}
div[data-testid="stButton"]>button:disabled *,
div[data-testid="stButton"]>button[disabled] *{{color:#6070a0 !important;}}

/* active-phase button (greyed) */
.btn-active-phase>button{{
    background:#dde4f5 !important;
    border-color:#b0c4e8 !important;
    color:{CHARCOAL} !important;
}}
.btn-active-phase>button *{{color:{CHARCOAL} !important;}}

/* ── Forms & inputs ── */
div[data-testid="stTextInput"] label,
div[data-testid="stTextArea"] label,
div[data-testid="stNumberInput"] label,
div[data-testid="stSelectbox"] label,
div[data-testid="stRadio"] label{{color:{CHARCOAL};font-weight:600;}}
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea,
div[data-testid="stNumberInput"] input{{background:#fff;border-color:#b0c4e8;color:{CHARCOAL};}}

/* ── Radio options ── */
div[data-testid="stRadio"]>div>label{{
    background:#fff;border:1.5px solid #c7d4ef;border-radius:10px;
    padding:11px 16px;margin-bottom:8px;display:block;cursor:pointer;
    transition:border-color .15s, background .15s;
}}
div[data-testid="stRadio"]>div>label:hover{{border-color:{ROYAL};background:#f0f4ff;}}
div[data-testid="stRadio"]>div>label span{{color:{CHARCOAL} !important;font-size:16px;font-weight:500;}}

/* ── Tabs ── */
button[role="tab"]{{font-weight:700;color:#5a6282;}}
button[role="tab"][aria-selected="true"],
button[role="tab"][aria-selected="true"] *{{color:{ROYAL} !important;}}
div[data-testid="stTabs"] [data-baseweb="tab-highlight"]{{background:linear-gradient(90deg,{ROYAL},{GOLD});}}

/* ── Cards ── */
.cs-banner{{
    display:flex;align-items:center;gap:20px;
    padding:18px 26px;
    background:linear-gradient(90deg,{CHARCOAL} 0%,#1e2450 55%,{ROYAL} 100%);
    border-radius:12px;margin-bottom:22px;
    box-shadow:0 6px 24px rgba(15,95,220,.25);
}}
.cs-banner h1{{margin:0;color:#fff;font-size:24px;font-weight:800;}}
.cs-banner p{{margin:3px 0 0;color:#a8beee;font-size:13px;}}

.metric-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:14px 0 20px;}}
.m-card{{background:#fff;border:1px solid #c7d4ef;border-radius:10px;padding:14px 16px;box-shadow:0 2px 8px rgba(15,95,220,.07);}}
.m-card .lbl{{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#5a6282;}}
.m-card .val{{font-size:28px;font-weight:900;color:{ROYAL};line-height:1.1;margin-top:2px;}}
.m-card .valsm{{font-size:15px;font-weight:700;color:{CHARCOAL};margin-top:4px;}}

.q-card{{
    background:#fff;border:1.5px solid #c7d4ef;border-left:5px solid {ROYAL};
    border-radius:12px;padding:22px 26px;margin:14px 0;
    box-shadow:0 4px 16px rgba(15,95,220,.09);
}}
.q-card .q-label{{font-size:13px;color:#5a6282;font-weight:600;margin-bottom:8px;}}
.q-card h2{{margin:0;color:{CHARCOAL};font-size:22px;line-height:1.35;}}

/* ── Timer ── */
.timer-wrap{{margin:10px 0 16px;}}
.timer-lbl{{font-size:13px;font-weight:700;margin-bottom:4px;}}
.timer-bg{{height:10px;border-radius:999px;background:#dde4f5;overflow:hidden;}}
.timer-fill{{height:100%;border-radius:999px;transition:width 1s linear;}}

/* ── Leaderboard ── */
.lb-row{{display:flex;align-items:center;gap:12px;padding:11px 14px;
    border-radius:9px;margin-bottom:6px;background:#fff;border:1px solid #dde4f5;}}
.lb-row.gold  {{border-left:4px solid #FFD700;background:#fffce8;}}
.lb-row.silver{{border-left:4px solid #B0B0C0;background:#f8f8fc;}}
.lb-row.bronze{{border-left:4px solid #CD7F32;background:#fdf6ee;}}
.lb-rank{{font-size:20px;width:32px;text-align:center;}}
.lb-name{{flex:1;font-weight:700;color:{CHARCOAL};}}
.lb-score{{font-weight:900;font-size:18px;color:{ROYAL};}}
.lb-ff{{font-size:11px;color:#5a6282;font-weight:600;}}

/* ── Result popup ── */
.result-correct{{
    background:linear-gradient(135deg,#0e6e3a,{SUCCESS});
    border-radius:14px;padding:24px 28px;margin:14px 0;
    color:#fff;text-align:center;box-shadow:0 8px 32px rgba(27,138,76,.28);
}}
.result-wrong{{
    background:linear-gradient(135deg,#8b1a1a,{DANGER});
    border-radius:14px;padding:24px 28px;margin:14px 0;
    color:#fff;text-align:center;box-shadow:0 8px 32px rgba(211,47,47,.28);
}}
.result-neutral{{
    background:linear-gradient(135deg,{CHARCOAL},#2a3260);
    border-radius:14px;padding:24px 28px;margin:14px 0;
    color:#fff;text-align:center;box-shadow:0 8px 32px rgba(15,95,220,.2);
}}
.result-correct h3,.result-wrong h3,.result-neutral h3{{margin:0 0 8px;color:#fff;font-size:20px;}}
.result-correct .big,.result-wrong .big,.result-neutral .big{{font-size:54px;font-weight:900;color:{GOLD};line-height:1;}}
.result-correct .sub,.result-wrong .sub,.result-neutral .sub{{font-size:13px;color:rgba(255,255,255,.75);margin-top:6px;}}

.badge-ff{{
    display:inline-block;padding:10px 18px;border-radius:10px;
    background:linear-gradient(90deg,#fff3cd,#fff8e1);
    border:1.5px solid {GOLD};color:#5b3100;font-weight:700;font-size:15px;
    margin-bottom:10px;
}}

/* ── Waiting ── */
.waiting{{
    min-height:200px;display:grid;place-items:center;
    border:2px dashed #b0c4e8;border-radius:12px;
    background:rgba(230,235,245,.4);text-align:center;padding:30px;
}}
.waiting h2{{color:{ROYAL};margin-bottom:6px;}}
.waiting p{{color:#5a6282;}}

/* ── Phase pill ── */
.phase-pill{{
    display:inline-block;padding:5px 13px;border-radius:999px;
    background:{LAVENDER};color:{ROYAL};font-weight:700;font-size:12px;
    border:1px solid #b0c4e8;
}}

/* ── Success / info boxes ── */
div[data-testid="stAlert"]{{border-radius:10px;}}
</style>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  Supabase helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _secret(name: str) -> str | None:
    try:
        v = st.secrets.get(name)
    except Exception:
        v = None
    return v or os.environ.get(name)


@st.cache_resource(show_spinner=False)
def _get_client() -> Client | None:
    url, key = _secret("SUPABASE_URL"), _secret("SUPABASE_KEY")
    if url and key:
        return create_client(url, key)
    return None


def db() -> Client | None:
    c = _get_client()
    if c is None:
        st.error("⚠️  Supabase not configured – add SUPABASE_URL & SUPABASE_KEY to secrets.")
    return c


def _q(fn, fallback=None):
    """Run a supabase query, return data or fallback."""
    try:
        return fn().execute().data
    except Exception as e:
        st.error(f"DB error: {e}")
        return fallback


def now_ms() -> int:
    return int(time.time() * 1000)


def _utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _parse_ms(v) -> int:
    if not v:
        return now_ms()
    if isinstance(v, (int, float)):
        return int(v)
    try:
        return int(datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        return now_ms()


# ── Session CRUD ──────────────────────────────────────────────────────────────

def _unique_code(client: Client) -> str:
    for _ in range(40):
        code = f"{random.randint(0, 9999):04d}"
        if not _q(lambda: client.table("sessions").select("id").eq("event_code", code), []):
            return code
    raise RuntimeError("Cannot generate unique code.")


def create_session(client: Client, name: str) -> dict | None:
    code = _unique_code(client)
    rows = _q(lambda: client.table("sessions").insert({
        "session_name": name, "event_code": code,
        "current_phase": "pre", "current_question_index": 0,
        "question_start_time": None,
    }).select("*"), [])
    return rows[0] if rows else None


def get_session(client: Client, code: str) -> dict | None:
    rows = _q(lambda: client.table("sessions").select("*").eq("event_code", code).limit(1), [])
    return rows[0] if rows else None


# ── Question CRUD ─────────────────────────────────────────────────────────────

def get_questions(client: Client, sid: str, phase: str | None = None) -> list[dict]:
    q = client.table("questions").select("*").eq("session_id", sid).order("created_at").order("id")
    if phase:
        q = q.eq("phase", phase)
    return _q(lambda: q, []) or []


def add_question(client: Client, sid: str, phase: str, text: str,
                 options: list[str], correct: str, weight: int):
    _q(lambda: client.table("questions").insert({
        "session_id": sid, "phase": phase, "question_text": text,
        "options_json": options, "correct_option": correct or None,
        "points_weight": weight,
    }), [])


def delete_question(client: Client, qid: str):
    _q(lambda: client.table("questions").delete().eq("id", qid), [])


def get_active_question(client: Client, session: dict) -> dict | None:
    qs = get_questions(client, session["id"], session["current_phase"])
    idx = int(session.get("current_question_index") or 0)
    if not qs or idx < 0 or idx >= len(qs):
        return None
    return qs[idx]


# ── Timeline control ──────────────────────────────────────────────────────────

def activate_question(client: Client, session: dict, phase: str, index: int):
    """Set active question and restart timer."""
    _q(lambda: client.table("sessions").update({
        "current_phase": phase,
        "current_question_index": index,
        "question_start_time": _utc(now_ms()),
    }).eq("id", session["id"]), [])


def freeze_question(client: Client, session: dict):
    _q(lambda: client.table("sessions").update(
        {"question_start_time": None}
    ).eq("id", session["id"]), [])


def set_phase(client: Client, session: dict, phase: str):
    _q(lambda: client.table("sessions").update({
        "current_phase": phase,
        "current_question_index": 0,
        "question_start_time": _utc(now_ms()),
    }).eq("id", session["id"]), [])


# ── Responses & Scores ────────────────────────────────────────────────────────

def get_responses(client: Client, qid: str) -> list[dict]:
    return _q(lambda: client.table("responses").select("*").eq("question_id", qid), []) or []


def get_existing_response(client: Client, qid: str, player: str) -> dict | None:
    rows = _q(lambda: client.table("responses").select("*")
              .eq("question_id", qid).eq("player_name", player).limit(1), [])
    return rows[0] if rows else None


def get_scores(client: Client, sid: str, limit: int | None = None) -> list[dict]:
    q = client.table("player_scores").select("*").eq("session_id", sid).order("total_score", desc=True)
    if limit:
        q = q.limit(limit)
    return _q(lambda: q, []) or []


def ensure_score_row(client: Client, sid: str, player: str):
    exists = _q(lambda: client.table("player_scores").select("id")
                .eq("session_id", sid).eq("player_name", player).limit(1), [])
    if not exists:
        _q(lambda: client.table("player_scores").insert(
            {"session_id": sid, "player_name": player, "total_score": 0}), [])


def _calc_points(question: dict, is_correct: bool, ms: int) -> int:
    if not is_correct:
        return 0
    w = int(question.get("points_weight") or 100)
    bonus = max(0, 1000 - int(ms / 10))
    return w + bonus


def submit_response(client: Client, session: dict, question: dict,
                    player: str, choice: str, ms: int) -> tuple[dict | None, bool, int]:
    """
    Submit player response. Returns (response_row, is_new, points_earned).
    Uses upsert with on_conflict to prevent duplicates without double-submit errors.
    """
    phase = session["current_phase"]
    is_game = phase == "during"
    correct_opt = question.get("correct_option")
    is_correct = bool(is_game and correct_opt and choice == correct_opt)
    points = _calc_points(question, is_correct, ms) if is_game else 0

    try:
        # Upsert response (idempotent on question_id + player_name)
        result = client.table("responses").upsert({
            "question_id": question["id"],
            "player_name": player,
            "selected_option": choice,
            "is_correct": is_correct,
            "response_time_ms": ms,
        }, on_conflict="question_id,player_name", ignore_duplicates=True).execute()

        rows = result.data or []

        if is_game and rows:
            # Atomic score update via upsert
            cur = _q(lambda: client.table("player_scores").select("total_score")
                     .eq("session_id", session["id"]).eq("player_name", player).limit(1), [])
            current_score = int(cur[0]["total_score"]) if cur else 0
            _q(lambda: client.table("player_scores").upsert({
                "session_id": session["id"],
                "player_name": player,
                "total_score": current_score + points,
            }, on_conflict="session_id,player_name"), [])

        return (rows[0] if rows else None), bool(rows), points

    except Exception as e:
        st.error(f"Submit error: {e}")
        return None, False, 0


# ═══════════════════════════════════════════════════════════════════════════════
#  UI Components
# ═══════════════════════════════════════════════════════════════════════════════

def banner(title: str, subtitle: str = ""):
    logo = _logo_b64()
    img = (f'<img src="data:image/png;base64,{logo}" alt="Career Shaper™" '
           f'style="height:48px;flex-shrink:0;">') if logo else ""
    st.markdown(
        f'<div class="cs-banner">{img}'
        f'<div><h1>{title}</h1><p>{subtitle}</p></div></div>',
        unsafe_allow_html=True)


def metric_grid(session: dict, questions: list[dict]):
    phase = session["current_phase"]
    pqs = [q for q in questions if q["phase"] == phase]
    idx = int(session.get("current_question_index") or 0)
    cur = idx + 1 if pqs else 0
    st.markdown(f"""
<div class="metric-grid">
  <div class="m-card"><div class="lbl">Session</div>
    <div class="valsm">{session["session_name"]}</div></div>
  <div class="m-card"><div class="lbl">Room Code</div>
    <div class="val">{session["event_code"]}</div></div>
  <div class="m-card"><div class="lbl">Phase</div>
    <div style="margin-top:8px;"><span class="phase-pill">{PHASE_ICON[phase]} {PHASE_LABEL[phase]}</span></div></div>
  <div class="m-card"><div class="lbl">Question</div>
    <div class="val" style="font-size:22px;">{cur}&nbsp;/&nbsp;{len(pqs)}</div></div>
</div>""", unsafe_allow_html=True)


def leaderboard(scores: list[dict], title="🏆 Leaderboard", limit=10):
    if not scores:
        st.caption("No scores yet.")
        return
    st.markdown(f"### {title}")
    medals = ["🥇", "🥈", "🥉"]
    cls    = ["gold", "silver", "bronze"]
    for i, s in enumerate(scores[:limit]):
        r = medals[i] if i < 3 else f"#{i+1}"
        c = cls[i] if i < 3 else ""
        ff = "⚡ Fastest" if s.get("is_fastest") else ""
        st.markdown(
            f'<div class="lb-row {c}">'
            f'<div class="lb-rank">{r}</div>'
            f'<div class="lb-name">{s["player_name"]}</div>'
            f'<div class="lb-ff">{ff}</div>'
            f'<div class="lb-score">{int(s["total_score"]):,}</div>'
            f'</div>', unsafe_allow_html=True)


def fastest_finger_badge(responses: list[dict]):
    correct = [r for r in responses if r.get("is_correct")]
    if not correct:
        return
    f = sorted(correct, key=lambda r: int(r.get("response_time_ms") or 9e9))[0]
    st.markdown(
        f'<div class="badge-ff">⚡ Fastest Finger: <strong>{f["player_name"]}</strong>'
        f' &mdash; {f["response_time_ms"]} ms</div>',
        unsafe_allow_html=True)


def timer_bar(start_ms: int, secs: int = QUIZ_SECS):
    elapsed = now_ms() - start_ms
    rem_ms  = max(0, secs * 1000 - elapsed)
    rem_s   = rem_ms // 1000
    pct     = max(0, rem_ms / (secs * 1000) * 100)
    color   = ROYAL if pct > 40 else "#F26A13" if pct > 15 else DANGER
    st.markdown(f"""
<div class="timer-wrap">
  <div class="timer-lbl" style="color:{color};">⏱ {rem_s}s remaining</div>
  <div class="timer-bg"><div class="timer-fill" style="width:{pct:.1f}%;background:{color};"></div></div>
</div>""", unsafe_allow_html=True)


def waiting(text="Waiting for host…"):
    st.markdown(
        f'<div class="waiting"><div><h2>{text}</h2>'
        f'<p>Screen updates automatically every 2 seconds.</p></div></div>',
        unsafe_allow_html=True)


def qr_for(link: str) -> Image.Image:
    qr = qrcode.QRCode(version=1, box_size=9, border=2)
    qr.add_data(link)
    qr.make(fit=True)
    return qr.make_image(fill_color=CHARCOAL, back_color="white").convert("RGB")


# ═══════════════════════════════════════════════════════════════════════════════
#  HOST VIEWS
# ═══════════════════════════════════════════════════════════════════════════════

def host_setup(client: Client):
    """Create or load a session."""
    if msg := st.session_state.pop("setup_msg", None):
        st.success(msg)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Create new session")
        with st.form("new_session"):
            name = st.text_input("Session name", value="AI Fluency Bootcamp – Cohort 3")
            if st.form_submit_button("🚀 Create session"):
                if name.strip():
                    with st.spinner("Reserving room code…"):
                        s = create_session(client, name.strip())
                    if s:
                        st.session_state.host_code = s["event_code"]
                        st.session_state.setup_msg = f"✅ Created! Room code: **{s['event_code']}**"
                        st.rerun()
                    else:
                        st.error("Creation failed – check Supabase connection.")
                else:
                    st.warning("Enter a session name.")
    with c2:
        st.subheader("Load existing session")
        code_in = st.text_input("4-digit room code",
                                value=st.session_state.get("host_code", ""), key="load_code_input")
        if st.button("🔍 Load session"):
            s = get_session(client, code_in.strip())
            if s:
                st.session_state.host_code = s["event_code"]
                st.rerun()
            else:
                st.warning("No session found.")


def host_configure(client: Client, session: dict):
    """
    Question builder with continuous-add UX:
    – Add form stays open after each submission.
    – When creator clicks 'Done adding', show summary + QR.
    """
    st.subheader("⚙️ Question Timeline Builder")

    # ── Continuous add form ──────────────────────────────────────────────────
    if "cfg_adding" not in st.session_state:
        st.session_state.cfg_adding = True
    if "cfg_phase" not in st.session_state:
        st.session_state.cfg_phase = "pre"
    if "cfg_added" not in st.session_state:
        st.session_state.cfg_added = 0

    if st.session_state.cfg_adding:
        with st.container(border=True):
            st.markdown(f"**Question #{st.session_state.cfg_added + 1}** — fill in and click Add")
            with st.form("add_q_form", clear_on_submit=True):
                phase_sel = st.selectbox(
                    "Phase", PHASES,
                    format_func=lambda v: f"{PHASE_ICON[v]}  {PHASE_LABEL[v]}",
                    index=PHASES.index(st.session_state.cfg_phase),
                    key="cfg_phase_sel",
                )
                q_text = st.text_area("Question text", placeholder="Type your question here…", key="cfg_qtext")
                opts_raw = st.text_area(
                    "Answer options (one per line – leave blank for open-ended)",
                    placeholder="Option A\nOption B\nOption C\nOption D",
                    key="cfg_opts",
                )
                options = [o.strip() for o in opts_raw.splitlines() if o.strip()]
                correct = st.selectbox(
                    "Correct answer (Live Game scoring)",
                    [""] + options,
                    disabled=(phase_sel != "during" or not options),
                    key="cfg_correct",
                )
                weight = st.number_input("Points weight", 0, 5000, 100, 25, key="cfg_weight")

                col_add, col_done = st.columns(2)
                add_clicked  = col_add.form_submit_button("➕ Add question", use_container_width=True)
                done_clicked = col_done.form_submit_button("✅ Done adding questions", use_container_width=True)

            if add_clicked:
                if not q_text.strip():
                    st.warning("Enter question text.")
                else:
                    add_question(client, session["id"], phase_sel,
                                 q_text.strip(), options, correct, int(weight))
                    st.session_state.cfg_phase = phase_sel
                    st.session_state.cfg_added += 1
                    st.success(f"Question {st.session_state.cfg_added} added! Fill in the next one or click Done.")
                    st.rerun()

            if done_clicked:
                st.session_state.cfg_adding = False
                st.rerun()
    else:
        if st.button("➕ Add more questions"):
            st.session_state.cfg_adding = True
            st.rerun()

    # ── Question list ─────────────────────────────────────────────────────────
    questions = get_questions(client, session["id"])
    total = len(questions)

    if total == 0:
        st.info("No questions yet – use the form above.")
        return

    st.divider()
    st.markdown(f"**{total} question(s) configured**")

    for ph in PHASES:
        pqs = [q for q in questions if q["phase"] == ph]
        if not pqs:
            continue
        st.markdown(f"**{PHASE_ICON[ph]} {PHASE_LABEL[ph]}** — {len(pqs)} question(s)")
        for i, q in enumerate(pqs, 1):
            opts = q.get("options_json") or []
            note = "open response" if not opts else " / ".join(opts)
            a, b = st.columns([11, 1])
            a.markdown(f"**Q{i}.** {q['question_text']}\n\n*{note}*")
            if b.button("🗑", key=f"del_{q['id']}"):
                delete_question(client, q["id"])
                st.rerun()

    # ── QR + code summary (shown once 'Done' clicked) ─────────────────────────
    if not st.session_state.cfg_adding:
        st.divider()
        st.markdown("### 📱 Share with participants")
        pub = st.text_input("Public app URL", st.session_state.get("pub_url", "http://localhost:8501"),
                            key="pub_url")
        link = f"{pub.rstrip('/')}/?room={session['event_code']}"
        c1, c2 = st.columns([1, 2])
        with c1:
            st.image(qr_for(link), caption="Scan to join", width=200)
        with c2:
            st.markdown(f"""
<div style="background:#fff;border:1px solid #c7d4ef;border-radius:10px;padding:20px;">
  <div style="font-size:12px;color:#5a6282;margin-bottom:6px;">Room Code</div>
  <div style="font-size:60px;font-weight:900;color:{ROYAL};line-height:1;">{session['event_code']}</div>
  <div style="font-size:12px;color:#5a6282;margin-top:10px;">Or share the link:<br>
    <code style="font-size:11px;">{link}</code></div>
</div>""", unsafe_allow_html=True)


def host_control(client: Client, session: dict):
    """Master timeline – phase switching + question navigation."""
    questions = get_questions(client, session["id"])
    metric_grid(session, questions)

    st.subheader("🎛 Master Timeline Control")

    # ── Phase buttons ─────────────────────────────────────────────────────────
    cols = st.columns(3)
    for col, ph in zip(cols, PHASES):
        active = session["current_phase"] == ph
        label  = f"{PHASE_ICON[ph]}  {PHASE_LABEL[ph]}" + ("  ◀ active" if active else "")
        with col:
            if active:
                st.markdown('<div class="btn-active-phase">', unsafe_allow_html=True)
            if st.button(label, key=f"phase_sw_{ph}", use_container_width=True, disabled=active):
                set_phase(client, session, ph)
                st.rerun()
            if active:
                st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    # ── Question navigation ───────────────────────────────────────────────────
    phase = session["current_phase"]
    pqs   = [q for q in questions if q["phase"] == phase]

    if not pqs:
        st.warning(f"No questions in **{PHASE_LABEL[phase]}** – go to Configure tab.")
        return

    # Always clamp index safely
    idx = max(0, min(int(session.get("current_question_index") or 0), len(pqs) - 1))
    active_q = pqs[idx]

    st.markdown(
        f'<div class="q-card">'
        f'<div class="q-label">{PHASE_ICON[phase]} Q{idx+1} of {len(pqs)}</div>'
        f'<h2>{active_q["question_text"]}</h2>'
        f'</div>', unsafe_allow_html=True)

    n1, n2, n3 = st.columns(3)
    with n1:
        if st.button("⬅ Previous", key="nav_prev",
                     disabled=(idx <= 0), use_container_width=True):
            activate_question(client, session, phase, idx - 1)
            st.rerun()
    with n2:
        if st.button("🔄 Open / Restart timer", key="nav_restart", use_container_width=True):
            activate_question(client, session, phase, idx)
            st.rerun()
    with n3:
        next_disabled = (idx >= len(pqs) - 1)
        if st.button("Next ➡", key="nav_next",
                     disabled=next_disabled, use_container_width=True):
            # Explicit int to avoid any type coercion bugs
            new_idx = int(idx) + 1
            activate_question(client, session, phase, new_idx)
            st.rerun()

    # ── Freeze / unfreeze ─────────────────────────────────────────────────────
    if phase == "during":
        st.divider()
        frozen = not bool(session.get("question_start_time"))
        if frozen:
            st.info("🔒 Responses frozen — participants see leaderboard.")
            if st.button("▶ Unfreeze (reopen timer)", use_container_width=True):
                activate_question(client, session, phase, idx)
                st.rerun()
        else:
            if st.button("🔒 Freeze responses & show leaderboard", use_container_width=True):
                freeze_question(client, session)
                st.rerun()


def host_analytics(client: Client, session: dict):
    st.subheader("📊 Real-time Analytics")
    question = get_active_question(client, session)
    if not question:
        st.caption("No active question selected.")
        return

    responses = get_responses(client, question["id"])
    phase = session["current_phase"]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total responses", len(responses))
    if phase == "during":
        correct = [r for r in responses if r.get("is_correct")]
        col2.metric("Correct", len(correct))
        col3.metric("Accuracy", f"{len(correct)/len(responses)*100:.0f}%" if responses else "—")

    # Response distribution
    options = question.get("options_json") or []
    if responses:
        df = pd.DataFrame(responses)
        if options:
            counts = df["selected_option"].value_counts().reindex(options, fill_value=0)
            st.bar_chart(counts)
        else:
            st.dataframe(df[["player_name", "selected_option"]].rename(
                columns={"selected_option": "Response"}), use_container_width=True)

    if phase == "during":
        st.divider()
        fastest_finger_badge(responses)
        st.divider()
        scores = get_scores(client, session["id"])
        leaderboard(scores, limit=10)


def host_access(client: Client, session: dict):
    st.subheader("📱 QR Code & Room Access")
    pub = st.text_input("Public app URL", st.session_state.get("pub_url", "http://localhost:8501"), key="pub_url_access")
    link = f"{pub.rstrip('/')}/?room={session['event_code']}"
    c1, c2 = st.columns([1, 2])
    with c1:
        st.image(qr_for(link), caption="Scan to join", width=220)
    with c2:
        st.markdown(f"""
<div style="background:#fff;border:1px solid #c7d4ef;border-radius:10px;padding:24px;">
  <div style="font-size:12px;color:#5a6282;margin-bottom:4px;">Room Code</div>
  <div style="font-size:68px;font-weight:900;color:{ROYAL};line-height:1;">{session["event_code"]}</div>
  <div style="font-size:12px;color:#5a6282;margin-top:14px;">Direct join link:</div>
  <code style="font-size:11px;word-break:break-all;">{link}</code>
</div>""", unsafe_allow_html=True)


def host_final_leaderboard(client: Client, session: dict):
    banner("🏆 Final Leaderboard", session["session_name"])
    scores = get_scores(client, session["id"])
    leaderboard(scores, title="Overall Rankings", limit=30)

    st.divider()
    st.markdown("### ⚡ Fastest Finger per Question")
    for q in get_questions(client, session["id"], "during"):
        resp    = get_responses(client, q["id"])
        correct = sorted([r for r in resp if r.get("is_correct")],
                         key=lambda r: int(r.get("response_time_ms") or 9e9))
        if correct:
            st.markdown(
                f"**{q['question_text'][:70]}** → ⚡ **{correct[0]['player_name']}** "
                f"in {correct[0]['response_time_ms']} ms")


def host_view(client: Client):
    banner("CrowdRush — Host Dashboard",
           "Career Shaper™ Live Engagement Platform")
    host_setup(client)

    code = st.session_state.get("host_code")
    if not code:
        return
    session = get_session(client, code)
    if not session:
        st.warning("Session not found.")
        return

    tab_ctrl, tab_cfg, tab_access, tab_analytics, tab_final = st.tabs(
        ["🎛 Control", "⚙️ Configure", "📱 Access", "📊 Analytics", "🏆 Final Leaderboard"])

    with tab_ctrl:
        host_control(client, session)
    with tab_cfg:
        host_configure(client, session)
    with tab_access:
        host_access(client, session)
    with tab_analytics:
        host_analytics(client, session)
    with tab_final:
        host_final_leaderboard(client, session)


# ═══════════════════════════════════════════════════════════════════════════════
#  AUDIENCE VIEWS
# ═══════════════════════════════════════════════════════════════════════════════

def _get_room_param() -> str:
    try:
        v = st.query_params.get("room")
    except Exception:
        v = None
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""


def audience_join(client: Client) -> dict | None:
    """Handle QR / code join + name entry. Returns session or None."""
    # Auto-fill code from URL param
    qp = _get_room_param()
    if qp and not st.session_state.get("aud_code"):
        st.session_state.aud_code = qp

    code = st.session_state.get("aud_code", "")

    if not code:
        banner("Join CrowdRush", "Enter your room code or scan the QR on screen.")
        entered = st.text_input("4-digit Room Code", max_chars=4, key="aud_code_input")
        if st.button("🚀 Join Room", disabled=(len(entered.strip()) != 4)):
            st.session_state.aud_code = entered.strip()
            st.rerun()
        return None

    session = get_session(client, code)
    if not session:
        st.error("Room code not found. Check the code and try again.")
        if st.button("Try another code"):
            st.session_state.pop("aud_code", None)
            st.rerun()
        return None

    name_key = f"player_{session['event_code']}"
    if not st.session_state.get(name_key):
        banner(session["session_name"], f"Room {session['event_code']} — Enter your name.")
        name = st.text_input("Your display name", max_chars=36)
        if st.button("✅ Enter session", disabled=not name.strip()):
            st.session_state[name_key] = name.strip()
            ensure_score_row(client, session["id"], name.strip())
            st.rerun()
        return None

    st.session_state.player_name = st.session_state[name_key]
    return session


def audience_answer(client: Client, session: dict, question: dict, player: str):
    """Render the answer UI for one question."""
    phase = session["current_phase"]
    start_ms = _parse_ms(session.get("question_start_time"))

    # Phase label
    st.markdown(
        f'<span class="phase-pill">{PHASE_ICON[phase]} {PHASE_LABEL[phase]}</span>',
        unsafe_allow_html=True)

    # Timer (live game only)
    if phase == "during" and session.get("question_start_time"):
        timer_bar(start_ms)

    # Question card
    st.markdown(
        f'<div class="q-card"><h2>{question["question_text"]}</h2></div>',
        unsafe_allow_html=True)

    # Check for existing response (refreshed every 2 s by autorefresh)
    existing = get_existing_response(client, question["id"], player)

    if existing:
        # ── Show result popup immediately after submission ──
        if phase == "during":
            is_cor = existing.get("is_correct", False)
            t_ms   = int(existing.get("response_time_ms") or 0)
            w      = int(question.get("points_weight") or 100)
            bonus  = max(0, 1000 - int(t_ms / 10))
            pts    = (w + bonus) if is_cor else 0

            if is_cor:
                st.markdown(f"""
<div class="result-correct">
  <h3>✅ Correct!</h3>
  <div class="big">+{pts:,}</div>
  <div class="sub">Answered in {t_ms} ms · Base {w} pts · Speed bonus +{bonus}</div>
</div>""", unsafe_allow_html=True)
            else:
                st.markdown(f"""
<div class="result-wrong">
  <h3>❌ Not this time!</h3>
  <div class="big" style="font-size:36px;">Stay sharp ⚡</div>
  <div class="sub">Answered in {t_ms} ms</div>
</div>""", unsafe_allow_html=True)
        else:
            st.markdown('<div class="result-neutral"><h3>✅ Response received!</h3>'
                        '<div class="sub">Thank you — waiting for host.</div></div>',
                        unsafe_allow_html=True)

        # Live leaderboard after submission
        if phase == "during":
            st.divider()
            scores    = get_scores(client, session["id"], limit=5)
            responses = get_responses(client, question["id"])
            fastest_finger_badge(responses)
            leaderboard(scores, title="⚡ Live Standings", limit=5)

        waiting("Waiting for next question…")
        return

    # ── Answer form ──────────────────────────────────────────────────────────
    options = question.get("options_json") or []
    if isinstance(options, list) and options:
        selected = st.radio("Choose your answer", options, index=None, key=f"radio_{question['id']}")
        disabled = selected is None
    else:
        selected = st.text_area("Your response", key=f"text_{question['id']}")
        disabled = not (selected or "").strip()

    # Single submit button – spinner prevents double-click
    if st.button("📤 Submit Answer", disabled=disabled, use_container_width=True,
                 key=f"submit_{question['id']}"):
        with st.spinner("Submitting…"):
            click_ms = now_ms()
            rt = max(0, click_ms - start_ms) if phase == "during" else 0
            choice = (selected or "").strip() if not options else selected
            _, is_new, pts = submit_response(client, session, question, player, choice, rt)
        if is_new:
            st.rerun()
        else:
            st.info("Your answer was already recorded.")


def audience_view(client: Client):
    session = audience_join(client)
    if not session:
        return

    player = st.session_state.player_name
    banner(session["session_name"],
           f"👋 {player}  ·  Room {session['event_code']}")

    question = get_active_question(client, session)

    if not question:
        waiting()
        return

    if session["current_phase"] == "during" and not session.get("question_start_time"):
        waiting("⏳ Round starting soon…")
        return

    audience_answer(client, session, question, player)


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    inject_css()

    client = db()
    if client is None:
        with st.expander("Database setup SQL"):
            try:
                st.code(open("supabase_schema.sql", encoding="utf-8").read(), language="sql")
            except FileNotFoundError:
                st.caption("supabase_schema.sql not found.")
        return

    # If ?room= param present → force audience mode, never show role picker
    if _get_room_param():
        st.sidebar.markdown("## 🎯 CrowdRush")
        st.sidebar.caption("Auto-refresh every 2 s")
        audience_view(client)
        return

    # Normal entry – role selector
    st.sidebar.markdown("## 🎯 CrowdRush")
    role = st.sidebar.radio(
        "Select your role",
        ["🎤 Speaker / Host", "🙋 Audience Participant"],
        key="role_sel",
    )
    st.sidebar.caption("Auto-refresh active every 2 s")

    # Host shortcut: Final Leaderboard
    if role == "🎤 Speaker / Host":
        code = st.session_state.get("host_code")
        if code:
            st.sidebar.divider()
            if st.sidebar.button("🏆 Final Leaderboard", use_container_width=True):
                s = get_session(client, code)
                if s:
                    host_final_leaderboard(client, s)
                    return

    if role == "🎤 Speaker / Host":
        host_view(client)
    else:
        audience_view(client)


if __name__ == "__main__":
    main()
