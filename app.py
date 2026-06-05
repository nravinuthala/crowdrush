"""
Career Shaper™ CrowdRush  –  v4
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FLOW OVERVIEW
─────────────
CONFIGURATOR (default, no role selection needed):
  Step 1 – Create game plan (Day, Topic, Phase labels)
  Step 2 – Add questions continuously until Done
  Step 3 – Questions shown; click "Save & Generate Game" → JSON saved + QR + code
  Step 4 – Load saved game list; pick one to play

PLAYER MODE (launched by Coach):
  Step 1 – Coach clicks "Start Game Session" → lobby opens
  Step 2 – QR + URL + code shown; players join (max 60)
  Step 3 – Players enter unique name; lobby counter + names shown live
  Step 4 – Coach clicks "Start Playing" → first question pushed
  Each Q:  30s timer → top-10 fastest after each answer
  End:     Final leaderboard grouped by correct-count → CSV download
"""

import base64
import csv
import io
import json
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

# ── Brand ─────────────────────────────────────────────────────────────────────
ROYAL    = "#0F5FDC"
CHARCOAL = "#14142A"
LAVENDER = "#E6EBF5"
WHITE    = "#FFFFFF"
GOLD     = "#FFC400"
DANGER   = "#D32F2F"
SUCCESS  = "#1B8A4C"
ORANGE   = "#F26A13"

PHASES      = ["pre", "during", "post"]
PH_LABEL    = {"pre": "Pre-Session", "during": "Live Game", "post": "Post-Session"}
PH_ICON     = {"pre": "🔆", "during": "⚡", "post": "🏁"}
QUIZ_SECS   = 30
MAX_PLAYERS = 60

GAMES_FILE  = Path(__file__).parent / "games_library.json"

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Career Shaper™ CrowdRush",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st_autorefresh(interval=2000, key="auto_refresh")


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _logo_b64() -> str:
    p = Path(__file__).parent / "cs_logo.png"
    return base64.b64encode(p.read_bytes()).decode() if p.exists() else ""


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


def _get_room_param() -> str:
    try:
        v = st.query_params.get("room")
    except Exception:
        v = None
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""


# ── Games library (JSON file) ─────────────────────────────────────────────────

def load_games_library() -> list[dict]:
    if GAMES_FILE.exists():
        try:
            return json.loads(GAMES_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_games_library(games: list[dict]):
    GAMES_FILE.write_text(json.dumps(games, indent=2, ensure_ascii=False), encoding="utf-8")


def save_game_to_library(meta: dict, questions: list[dict]) -> str:
    """Save a configured game. Returns its game_id."""
    games = load_games_library()
    game_id = f"CS-{random.randint(10000,99999)}"
    entry = {
        "game_id": game_id,
        "day": meta.get("day", ""),
        "topic": meta.get("topic", ""),
        "session_name": meta.get("session_name", ""),
        "created_at": datetime.utcnow().isoformat(),
        "questions": questions,
    }
    games.append(entry)
    save_games_library(games)
    return game_id


# ══════════════════════════════════════════════════════════════════════════════
#  SUPABASE
# ══════════════════════════════════════════════════════════════════════════════

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
    return _get_client()


def _q(fn, fallback=None):
    try:
        return fn().execute().data
    except Exception as e:
        st.toast(f"⚠ DB: {e}", icon="🔴")
        return fallback


def _unique_code(client: Client) -> str:
    for _ in range(40):
        code = f"{random.randint(0, 9999):04d}"
        if not _q(lambda: client.table("sessions").select("id").eq("event_code", code), []):
            return code
    raise RuntimeError("Cannot generate unique code.")


def create_live_session(client: Client, game: dict) -> dict | None:
    code = _unique_code(client)
    rows = _q(lambda: client.table("sessions").insert({
        "session_name": game["session_name"],
        "event_code": code,
        "current_phase": "lobby",
        "current_question_index": -1,
        "question_start_time": None,
        "game_id": game["game_id"],
    }).select("*"), [])
    return rows[0] if rows else None


def get_session(client: Client, code: str) -> dict | None:
    rows = _q(lambda: client.table("sessions").select("*").eq("event_code", code).limit(1), [])
    return rows[0] if rows else None


def get_players(client: Client, sid: str) -> list[dict]:
    return _q(lambda: client.table("player_scores").select("*").eq("session_id", sid).order("created_at"), []) or []


def ensure_player(client: Client, sid: str, player: str):
    ex = _q(lambda: client.table("player_scores").select("id")
            .eq("session_id", sid).eq("player_name", player).limit(1), [])
    if not ex:
        _q(lambda: client.table("player_scores").insert(
            {"session_id": sid, "player_name": player, "total_score": 0, "correct_count": 0}), [])


def get_scores(client: Client, sid: str) -> list[dict]:
    return _q(lambda: client.table("player_scores").select("*").eq("session_id", sid)
              .order("total_score", desc=True), []) or []


def get_responses(client: Client, qid: str) -> list[dict]:
    return _q(lambda: client.table("responses").select("*").eq("question_id", qid)
              .order("response_time_ms"), []) or []


def get_existing_resp(client: Client, qid: str, player: str) -> dict | None:
    rows = _q(lambda: client.table("responses").select("*")
              .eq("question_id", qid).eq("player_name", player).limit(1), [])
    return rows[0] if rows else None


def push_question(client: Client, session: dict, phase: str, idx: int):
    _q(lambda: client.table("sessions").update({
        "current_phase": phase,
        "current_question_index": idx,
        "question_start_time": _utc(now_ms()),
    }).eq("id", session["id"]), [])


def freeze_q(client: Client, session: dict):
    _q(lambda: client.table("sessions").update(
        {"question_start_time": None}).eq("id", session["id"]), [])


def set_lobby(client: Client, session: dict):
    _q(lambda: client.table("sessions").update({
        "current_phase": "lobby", "current_question_index": -1,
        "question_start_time": None,
    }).eq("id", session["id"]), [])


def set_finished(client: Client, session: dict):
    _q(lambda: client.table("sessions").update({
        "current_phase": "finished", "question_start_time": None,
    }).eq("id", session["id"]), [])


def submit_answer(client: Client, session: dict, question: dict,
                  player: str, choice: str, rt_ms: int) -> tuple[bool, int]:
    """Returns (is_correct, points). Idempotent via upsert."""
    phase = session["current_phase"]
    correct_opt = question.get("correct_option")
    is_correct = bool(phase == "during" and correct_opt and choice == correct_opt)
    weight = int(question.get("points_weight") or 100)
    bonus  = max(0, 1000 - int(rt_ms / 10)) if is_correct else 0
    points = weight + bonus if is_correct else 0

    try:
        res = client.table("responses").upsert({
            "question_id": question["id"],
            "player_name": player,
            "selected_option": choice,
            "is_correct": is_correct,
            "response_time_ms": rt_ms,
        }, on_conflict="question_id,player_name", ignore_duplicates=True).execute()

        if res.data and phase == "during":
            cur = _q(lambda: client.table("player_scores").select("total_score,correct_count")
                     .eq("session_id", session["id"]).eq("player_name", player).limit(1), [])
            cur_score   = int(cur[0]["total_score"])   if cur else 0
            cur_correct = int(cur[0]["correct_count"]) if cur else 0
            _q(lambda: client.table("player_scores").upsert({
                "session_id": session["id"], "player_name": player,
                "total_score":   cur_score   + points,
                "correct_count": cur_correct + (1 if is_correct else 0),
            }, on_conflict="session_id,player_name"), [])

        return is_correct, points
    except Exception as e:
        st.error(f"Submit error: {e}")
        return False, 0


# ══════════════════════════════════════════════════════════════════════════════
#  CSS + LAYOUT
# ══════════════════════════════════════════════════════════════════════════════

def inject_css():
    logo = _logo_b64()
    logo_html = (
        f'<img src="data:image/png;base64,{logo}" alt="Career Shaper™" '
        f'style="height:36px;">'
        if logo else
        '<span style="font-weight:900;font-size:18px;color:#0F5FDC;">Career Shaper™</span>'
    )
    # Top-right logo bar
    st.markdown(
        f'<div style="position:fixed;top:0;right:0;z-index:9999;'
        f'padding:8px 20px 6px;background:rgba(255,255,255,.92);'
        f'border-bottom-left-radius:12px;box-shadow:-2px 2px 12px rgba(15,95,220,.12);">'
        f'{logo_html}</div>',
        unsafe_allow_html=True,
    )

    st.markdown(f"""
<style>
/* ── base ── */
html,body,.stApp{{
  background:linear-gradient(155deg,#f0f4ff 0%,{LAVENDER} 55%,#d8e4f8 100%);
  color:{CHARCOAL};
  padding-top:4px;
}}
/* hide sidebar toggle & sidebar itself */
section[data-testid="stSidebar"]{{display:none;}}
[data-testid="collapsedControl"]{{display:none;}}
header[data-testid="stHeader"]{{background:transparent;}}

/* ── buttons ── */
div[data-testid="stButton"]>button,
div[data-testid="stFormSubmitButton"]>button{{
  border-radius:9px;
  border:1.5px solid {ROYAL};
  background:linear-gradient(90deg,{ROYAL} 0%,#2a80f5 100%);
  color:{WHITE}!important;
  font-weight:700;font-size:15px;
  min-height:46px;
  box-shadow:0 3px 12px rgba(15,95,220,.22);
  transition:all .15s;
}}
div[data-testid="stButton"]>button *,
div[data-testid="stFormSubmitButton"]>button *{{color:{WHITE}!important;}}
div[data-testid="stButton"]>button:hover{{
  background:linear-gradient(90deg,#0a3ea3 0%,#1466d8 100%);
}}
div[data-testid="stButton"]>button:disabled{{
  background:#c7d4ef!important;border-color:#b0c4e8!important;
  color:#6070a0!important;box-shadow:none;
}}

/* ── green CTA button ── */
.btn-green div[data-testid="stButton"]>button{{
  background:linear-gradient(90deg,#0e6e3a,{SUCCESS})!important;
  border-color:#0e6e3a!important;
}}
/* ── red CTA button ── */
.btn-red div[data-testid="stButton"]>button{{
  background:linear-gradient(90deg,#8b1a1a,{DANGER})!important;
  border-color:#8b1a1a!important;
}}
/* ── orange CTA button ── */
.btn-orange div[data-testid="stButton"]>button{{
  background:linear-gradient(90deg,#c45200,{ORANGE})!important;
  border-color:#c45200!important;
}}

/* ── inputs ── */
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea,
div[data-testid="stNumberInput"] input,
div[data-baseweb="select"]>div{{
  background:#fff;border-color:#b0c4e8;color:{CHARCOAL};
}}
div[data-testid="stTextInput"] label,
div[data-testid="stTextArea"] label,
div[data-testid="stNumberInput"] label,
div[data-testid="stSelectbox"] label,
div[data-testid="stRadio"] label{{color:{CHARCOAL};font-weight:600;}}

/* ── radio answer cards ── */
div[data-testid="stRadio"]>div>label{{
  background:#fff;border:1.5px solid #c7d4ef;border-radius:10px;
  padding:12px 18px;margin-bottom:9px;display:block;cursor:pointer;
  transition:border-color .15s,background .15s;font-size:16px;
}}
div[data-testid="stRadio"]>div>label:hover{{border-color:{ROYAL};background:#f0f4ff;}}
div[data-testid="stRadio"]>div>label span{{color:{CHARCOAL}!important;font-weight:500;}}

/* ── tabs ── */
button[role="tab"]{{font-weight:700;color:#5a6282;}}
button[role="tab"][aria-selected="true"]{{color:{ROYAL}!important;}}
div[data-testid="stTabs"] [data-baseweb="tab-highlight"]{{
  background:linear-gradient(90deg,{ROYAL},{GOLD});
}}

/* ── banner ── */
.cs-banner{{
  display:flex;align-items:center;gap:18px;
  padding:18px 26px;margin:8px 0 22px;
  background:linear-gradient(90deg,{CHARCOAL} 0%,#1e2450 55%,{ROYAL} 100%);
  border-radius:14px;box-shadow:0 6px 24px rgba(15,95,220,.25);
}}
.cs-banner h1{{margin:0;color:#fff;font-size:22px;font-weight:800;}}
.cs-banner p{{margin:3px 0 0;color:#a8beee;font-size:13px;}}

/* ── metric grid ── */
.mg{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:14px 0 20px;}}
.mc{{background:#fff;border:1px solid #c7d4ef;border-radius:10px;
  padding:14px 16px;box-shadow:0 2px 8px rgba(15,95,220,.07);}}
.mc .l{{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#5a6282;}}
.mc .v{{font-size:30px;font-weight:900;color:{ROYAL};line-height:1.1;margin-top:2px;}}
.mc .vs{{font-size:15px;font-weight:700;color:{CHARCOAL};margin-top:4px;}}

/* ── question card ── */
.qc{{
  background:#fff;border:1.5px solid #c7d4ef;border-left:5px solid {ROYAL};
  border-radius:12px;padding:24px 28px;margin:14px 0;
  box-shadow:0 4px 16px rgba(15,95,220,.09);
}}
.qc .ql{{font-size:13px;color:#5a6282;font-weight:600;margin-bottom:10px;}}
.qc h2{{margin:0;color:{CHARCOAL};font-size:22px;line-height:1.4;}}

/* ── timer ── */
.tw{{margin:10px 0 16px;}}
.tl{{font-size:14px;font-weight:700;margin-bottom:5px;}}
.tbg{{height:12px;border-radius:999px;background:#dde4f5;overflow:hidden;}}
.tf{{height:100%;border-radius:999px;transition:width 1s linear;}}

/* ── leaderboard ── */
.lb-row{{display:flex;align-items:center;gap:12px;padding:12px 16px;
  border-radius:10px;margin-bottom:7px;background:#fff;border:1px solid #dde4f5;}}
.lb-row.gold  {{border-left:4px solid #FFD700;background:#fffce8;}}
.lb-row.silver{{border-left:4px solid #B0B0C0;background:#f8f8fc;}}
.lb-row.bronze{{border-left:4px solid #CD7F32;background:#fdf6ee;}}
.lb-rank{{font-size:22px;width:34px;text-align:center;flex-shrink:0;}}
.lb-name{{flex:1;font-weight:700;color:{CHARCOAL};font-size:15px;}}
.lb-rt{{font-size:12px;color:#5a6282;min-width:70px;text-align:right;}}
.lb-score{{font-weight:900;font-size:18px;color:{ROYAL};min-width:60px;text-align:right;}}

/* ── result popup ── */
.pop{{border-radius:14px;padding:26px 30px;margin:14px 0;text-align:center;}}
.pop h3{{margin:0 0 10px;color:#fff;font-size:20px;}}
.pop .big{{font-size:56px;font-weight:900;color:{GOLD};line-height:1;}}
.pop .sub{{font-size:13px;color:rgba(255,255,255,.8);margin-top:8px;}}
.pop-ok {{background:linear-gradient(135deg,#0e6e3a,{SUCCESS});box-shadow:0 8px 28px rgba(27,138,76,.3);}}
.pop-no {{background:linear-gradient(135deg,#8b1a1a,{DANGER});box-shadow:0 8px 28px rgba(211,47,47,.3);}}
.pop-neu{{background:linear-gradient(135deg,{CHARCOAL},#2a3260);box-shadow:0 8px 28px rgba(15,95,220,.2);}}

/* ── waiting ── */
.wait{{min-height:200px;display:grid;place-items:center;
  border:2px dashed #b0c4e8;border-radius:14px;
  background:rgba(230,235,245,.4);text-align:center;padding:30px;}}
.wait h2{{color:{ROYAL};margin-bottom:8px;}}
.wait p{{color:#5a6282;}}

/* ── phase pill ── */
.pp{{display:inline-block;padding:5px 13px;border-radius:999px;
  background:{LAVENDER};color:{ROYAL};font-weight:700;font-size:12px;
  border:1px solid #b0c4e8;}}

/* ── player lobby chip ── */
.chip{{display:inline-block;background:#fff;border:1px solid #c7d4ef;
  border-radius:999px;padding:4px 14px;margin:4px;font-size:13px;font-weight:600;
  color:{CHARCOAL};}}

/* ── game card in library ── */
.gc{{background:#fff;border:1px solid #c7d4ef;border-radius:12px;
  padding:16px 20px;margin-bottom:10px;box-shadow:0 2px 8px rgba(15,95,220,.06);}}
.gc .gid{{font-size:11px;color:#5a6282;letter-spacing:.05em;}}
.gc h3{{margin:4px 0 2px;color:{CHARCOAL};font-size:17px;}}
.gc .gmeta{{font-size:13px;color:#5a6282;}}

/* ── step header ── */
.step-hdr{{display:flex;align-items:center;gap:12px;margin:22px 0 14px;}}
.step-num{{width:32px;height:32px;border-radius:50%;background:{ROYAL};
  color:#fff;font-weight:900;font-size:15px;display:grid;place-items:center;flex-shrink:0;}}
.step-hdr h3{{margin:0;color:{CHARCOAL};font-size:17px;font-weight:700;}}

div[data-testid="stAlert"]{{border-radius:10px;}}
div[data-testid="stExpander"]{{border-radius:10px;}}
</style>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  SHARED UI COMPONENTS
# ══════════════════════════════════════════════════════════════════════════════

def banner(title: str, subtitle: str = ""):
    logo = _logo_b64()
    img  = (f'<img src="data:image/png;base64,{logo}" alt="" style="height:46px;flex-shrink:0;">'
            if logo else "")
    st.markdown(f'<div class="cs-banner">{img}<div><h1>{title}</h1><p>{subtitle}</p></div></div>',
                unsafe_allow_html=True)


def step_header(n: int, title: str):
    st.markdown(f'<div class="step-hdr"><div class="step-num">{n}</div><h3>{title}</h3></div>',
                unsafe_allow_html=True)


def waiting(text="Waiting for coach…"):
    st.markdown(
        f'<div class="wait"><div><h2>{text}</h2>'
        f'<p>Screen refreshes automatically every 2 seconds.</p></div></div>',
        unsafe_allow_html=True)


def qr_for(link: str) -> Image.Image:
    qr = qrcode.QRCode(version=1, box_size=9, border=2)
    qr.add_data(link)
    qr.make(fit=True)
    return qr.make_image(fill_color=CHARCOAL, back_color="white").convert("RGB")


def timer_bar(start_ms: int, secs: int = QUIZ_SECS):
    elapsed = now_ms() - start_ms
    rem_ms  = max(0, secs * 1000 - elapsed)
    rem_s   = rem_ms // 1000
    pct     = max(0, rem_ms / (secs * 1000) * 100)
    color   = ROYAL if pct > 40 else ORANGE if pct > 15 else DANGER
    st.markdown(f"""
<div class="tw">
  <div class="tl" style="color:{color};">⏱ {rem_s}s remaining</div>
  <div class="tbg"><div class="tf" style="width:{pct:.1f}%;background:{color};"></div></div>
</div>""", unsafe_allow_html=True)


def render_leaderboard(scores: list[dict], title="🏆 Leaderboard",
                       show_rt=False, responses: list[dict] | None = None, limit=10):
    if not scores:
        st.caption("No scores yet.")
        return
    st.markdown(f"### {title}")
    medals = ["🥇", "🥈", "🥉"]
    cls    = ["gold", "silver", "bronze"]

    # Build fastest lookup for this question
    ff_map: dict[str, int] = {}
    if responses:
        for r in responses:
            if r.get("is_correct"):
                ff_map[r["player_name"]] = int(r.get("response_time_ms") or 9e9)

    for i, s in enumerate(scores[:limit]):
        r = medals[i] if i < 3 else f"#{i+1}"
        c = cls[i] if i < 3 else ""
        rt_str = ""
        if show_rt and s["player_name"] in ff_map:
            rt_str = f"⚡ {ff_map[s['player_name']]} ms"
        st.markdown(
            f'<div class="lb-row {c}">'
            f'<div class="lb-rank">{r}</div>'
            f'<div class="lb-name">{s["player_name"]}</div>'
            f'<div class="lb-rt">{rt_str}</div>'
            f'<div class="lb-score">{int(s["total_score"]):,}</div>'
            f'</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATOR MODE
# ══════════════════════════════════════════════════════════════════════════════

def cfg_build_questions() -> list[dict]:
    """Continuous question builder. Returns list of question dicts."""
    if "cfg_qs" not in st.session_state:
        st.session_state.cfg_qs = []
    if "cfg_adding" not in st.session_state:
        st.session_state.cfg_adding = True

    qs: list[dict] = st.session_state.cfg_qs

    # ── Add form ──
    if st.session_state.cfg_adding:
        n = len(qs) + 1
        with st.container(border=True):
            st.markdown(f"**Question {n}** — fill in details, then click ➕ Add")
            with st.form("add_q", clear_on_submit=True):
                phase_sel = st.selectbox(
                    "Phase", PHASES,
                    format_func=lambda v: f"{PH_ICON[v]}  {PH_LABEL[v]}")
                q_text = st.text_area("Question text *", placeholder="Type your question here…")
                opts_raw = st.text_area(
                    "Answer options (one per line — leave blank for open-ended)",
                    placeholder="Option A\nOption B\nOption C\nOption D")
                options = [o.strip() for o in opts_raw.splitlines() if o.strip()]
                correct = st.selectbox(
                    "Correct answer (Live Game phase only)",
                    [""] + options,
                    disabled=(phase_sel != "during" or not options))
                weight = st.number_input("Points weight", 0, 5000, 100, 25)

                ca, cb = st.columns(2)
                add_btn  = ca.form_submit_button("➕ Add Question",    use_container_width=True)
                done_btn = cb.form_submit_button("✅ Done Adding",     use_container_width=True)

            if add_btn:
                if not q_text.strip():
                    st.warning("Question text is required.")
                else:
                    qs.append({
                        "phase": phase_sel,
                        "question_text": q_text.strip(),
                        "options_json": options,
                        "correct_option": correct or None,
                        "points_weight": int(weight),
                    })
                    st.session_state.cfg_qs = qs
                    st.success(f"✅ Question {n} added! Form cleared — add Q{n+1} or click Done.")
                    st.rerun()
            if done_btn:
                st.session_state.cfg_adding = False
                st.rerun()
    else:
        if st.button("➕ Add more questions"):
            st.session_state.cfg_adding = True
            st.rerun()

    # ── Preview list ──
    if qs:
        st.divider()
        st.markdown(f"**{len(qs)} question(s) added**")
        for ph in PHASES:
            ph_qs = [q for q in qs if q["phase"] == ph]
            if not ph_qs:
                continue
            st.markdown(f"**{PH_ICON[ph]} {PH_LABEL[ph]}**")
            for i, q in enumerate(ph_qs):
                idx_global = qs.index(q)
                opts = q.get("options_json") or []
                note = "open response" if not opts else " · ".join(opts)
                ca, cb = st.columns([11, 1])
                ca.markdown(f"**{i+1}.** {q['question_text']}  \n_{note}_")
                if cb.button("🗑", key=f"del_q_{idx_global}"):
                    qs.pop(idx_global)
                    st.session_state.cfg_qs = qs
                    st.rerun()

    return qs


def configurator_view():
    banner("CrowdRush Configurator",
           "Career Shaper™  ·  Build your game plan")

    # ── Step 1: Game metadata ─────────────────────────────────────────────────
    step_header(1, "Game Plan Details")
    c1, c2, c3 = st.columns(3)
    day   = c1.text_input("Day / Module", placeholder="e.g. Day 1", key="meta_day")
    topic = c2.text_input("Topic / Theme", placeholder="e.g. AI Fundamentals", key="meta_topic")
    sname = c3.text_input("Session Name", placeholder="e.g. AI Bootcamp – Cohort 3", key="meta_sname")

    st.divider()

    # ── Step 2: Add questions ─────────────────────────────────────────────────
    step_header(2, "Add Questions (Pre / Live / Post-Session)")
    qs = cfg_build_questions()

    # ── Step 3: Save & generate ───────────────────────────────────────────────
    if qs and not st.session_state.get("cfg_adding", True):
        st.divider()
        step_header(3, "Save Game & Generate Access")

        if st.session_state.get("saved_game_id"):
            gid = st.session_state.saved_game_id
            st.success(f"✅ Game saved! Game ID: **{gid}**")
        else:
            st.markdown('<div class="btn-green">', unsafe_allow_html=True)
            if st.button("💾 Save Game & Generate Code", use_container_width=True):
                if not sname.strip():
                    st.warning("Enter a Session Name first.")
                else:
                    meta = {"day": day, "topic": topic, "session_name": sname}
                    gid = save_game_to_library(meta, qs)
                    st.session_state.saved_game_id = gid
                    st.success(f"✅ Saved! Game ID: **{gid}**  — see Game Library below to launch.")
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    st.divider()

    # ── Step 4: Game Library ──────────────────────────────────────────────────
    step_header(4, "Game Library — Load & Launch")
    games = load_games_library()
    if not games:
        st.info("No saved games yet. Create and save one above.")
        return

    for g in reversed(games):
        n_qs = len(g.get("questions", []))
        phases_used = sorted(set(q["phase"] for q in g.get("questions", [])),
                             key=lambda p: PHASES.index(p))
        phase_str = "  ·  ".join(f"{PH_ICON[p]} {PH_LABEL[p]}" for p in phases_used)
        st.markdown(
            f'<div class="gc">'
            f'<div class="gid">🆔 {g["game_id"]}  ·  Saved {g["created_at"][:10]}</div>'
            f'<h3>📅 {g.get("day","")}  ·  {g.get("topic","")}  ·  {g.get("session_name","")}</h3>'
            f'<div class="gmeta">{n_qs} question(s)  ·  {phase_str}</div>'
            f'</div>', unsafe_allow_html=True)

        ca, cb = st.columns([3, 1])
        with ca:
            # Download this game as JSON
            st.download_button(
                "⬇ Download JSON", data=json.dumps(g, indent=2, ensure_ascii=False),
                file_name=f"crowdrush_{g['game_id']}.json",
                mime="application/json", key=f"dl_{g['game_id']}")
        with cb:
            st.markdown('<div class="btn-green">', unsafe_allow_html=True)
            if st.button("🚀 Launch Game", key=f"launch_{g['game_id']}", use_container_width=True):
                st.session_state.launch_game = g
                st.session_state.app_mode = "coach"
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  COACH / GAME-RUNNER MODE
# ══════════════════════════════════════════════════════════════════════════════

def get_pub_url() -> str:
    return st.session_state.get("pub_url", "http://localhost:8501")


def coach_view(client: Client):
    game: dict = st.session_state.get("launch_game", {})
    if not game:
        st.error("No game loaded. Return to Configurator.")
        if st.button("← Back to Configurator"):
            st.session_state.app_mode = "config"
            st.rerun()
        return

    questions = game.get("questions", [])

    # ── Ensure a live session exists ──────────────────────────────────────────
    if not st.session_state.get("live_code"):
        banner(f"🚀 Launch: {game['session_name']}",
               f"📅 {game.get('day','')}  ·  🎯 {game.get('topic','')}  ·  🆔 {game['game_id']}")

        step_header(1, "Set Your Public App URL (for QR code)")
        pub = st.text_input("Public URL", get_pub_url(), key="pub_url")

        st.markdown('<div class="btn-green">', unsafe_allow_html=True)
        if st.button("🟢 Start Game Session — Generate QR & Code", use_container_width=True):
            with st.spinner("Creating live session…"):
                sess = create_live_session(client, game)
            if sess:
                st.session_state.live_code = sess["event_code"]
                st.rerun()
            else:
                st.error("Failed to create session. Check Supabase connection.")
        st.markdown('</div>', unsafe_allow_html=True)

        st.divider()
        if st.button("← Back to Game Library"):
            st.session_state.app_mode = "config"
            st.session_state.pop("launch_game", None)
            st.rerun()
        return

    # ── Session is live ───────────────────────────────────────────────────────
    code    = st.session_state.live_code
    session = get_session(client, code)
    if not session:
        st.error("Session not found in DB.")
        return

    phase   = session["current_phase"]
    pub_url = get_pub_url()
    link    = f"{pub_url.rstrip('/')}/?room={code}"

    banner(f"{game['session_name']}",
           f"📅 {game.get('day','')}  ·  🆔 {game['game_id']}  ·  Room: {code}")

    # Tabs
    t_lobby, t_play, t_results = st.tabs(["🚪 Lobby", "🎮 Play", "🏆 Results"])

    # ── LOBBY TAB ─────────────────────────────────────────────────────────────
    with t_lobby:
        step_header(2, "Share Access — Players Joining")

        c_qr, c_info = st.columns([1, 2])
        with c_qr:
            st.image(qr_for(link), caption="Scan to join", width=200)
        with c_info:
            st.markdown(f"""
<div style="background:#fff;border:1.5px solid #c7d4ef;border-radius:12px;padding:20px;">
  <div style="font-size:11px;color:#5a6282;text-transform:uppercase;letter-spacing:.05em;">Room Code</div>
  <div style="font-size:64px;font-weight:900;color:{ROYAL};line-height:1;letter-spacing:4px;">{code}</div>
  <div style="font-size:12px;color:#5a6282;margin-top:12px;">Or share link:</div>
  <div style="font-size:12px;word-break:break-all;margin-top:4px;">
    <code>{link}</code>
  </div>
  <div style="margin-top:12px;">
    <a href="{link}" target="_blank" style="font-size:13px;color:{ROYAL};font-weight:700;">
      🔗 Open link in new tab
    </a>
  </div>
</div>""", unsafe_allow_html=True)

        st.divider()
        players = get_players(client, session["id"])
        n_players = len(players)
        c1, c2 = st.columns(2)
        c1.metric("Players joined", n_players, delta=None)
        c2.metric("Capacity", MAX_PLAYERS)

        if players:
            step_header(3, f"Connected Players ({n_players}/{MAX_PLAYERS})")
            chips = "".join(f'<span class="chip">👤 {p["player_name"]}</span>' for p in players)
            st.markdown(chips, unsafe_allow_html=True)
        else:
            st.info("Waiting for players to join…")

        if n_players > 0 and phase == "lobby":
            st.divider()
            step_header(4, "Start the Game")
            # Find first question
            first_ph_qs = [q for q in questions if q["phase"] == "pre"] or \
                          [q for q in questions if q["phase"] == "during"] or \
                          questions
            st.markdown('<div class="btn-orange">', unsafe_allow_html=True)
            if st.button("▶ Start Playing — Push First Question", use_container_width=True):
                # We need to push questions to DB first
                _push_questions_to_db(client, session, questions)
                first_phase = first_ph_qs[0]["phase"]
                push_question(client, session, first_phase, 0)
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        elif phase != "lobby":
            st.success("✅ Game is live! Switch to the **Play** tab.")

    # ── PLAY TAB ─────────────────────────────────────────────────────────────
    with t_play:
        if phase == "lobby":
            waiting("Game not started yet — go to Lobby tab.")
            return
        if phase == "finished":
            st.success("🏁 Game complete! See Results tab.")
            return

        # Reload fresh session
        session = get_session(client, code)
        phase   = session["current_phase"]
        idx     = int(session.get("current_question_index") or 0)
        ph_qs   = _get_phase_questions_from_db(client, session)

        if not ph_qs:
            st.warning("No questions found for this phase.")
            return

        idx = max(0, min(idx, len(ph_qs) - 1))
        active_q = ph_qs[idx]
        responses = get_responses(client, active_q["id"])
        frozen = not bool(session.get("question_start_time"))

        # Metric row
        all_qs   = get_all_questions_from_db(client, session)
        players  = get_players(client, session["id"])
        st.markdown(f"""
<div class="mg">
  <div class="mc"><div class="l">Phase</div>
    <div style="margin-top:8px;"><span class="pp">{PH_ICON[phase]} {PH_LABEL[phase]}</span></div></div>
  <div class="mc"><div class="l">Question</div>
    <div class="v" style="font-size:26px;">{idx+1} / {len(ph_qs)}</div></div>
  <div class="mc"><div class="l">Responses</div>
    <div class="v">{len(responses)}</div></div>
  <div class="mc"><div class="l">Players</div>
    <div class="v">{len(players)}</div></div>
</div>""", unsafe_allow_html=True)

        # Active question card
        st.markdown(
            f'<div class="qc"><div class="ql">{PH_ICON[phase]} Q{idx+1} of {len(ph_qs)}</div>'
            f'<h2>{active_q["question_text"]}</h2></div>', unsafe_allow_html=True)

        # Navigation
        n1, n2, n3 = st.columns(3)
        with n1:
            if st.button("⬅ Previous", disabled=(idx <= 0), use_container_width=True, key="cp"):
                push_question(client, session, phase, idx - 1)
                st.rerun()
        with n2:
            if frozen:
                if st.button("▶ Reopen / Restart Timer", use_container_width=True, key="cr"):
                    push_question(client, session, phase, idx)
                    st.rerun()
            else:
                st.markdown('<div class="btn-red">', unsafe_allow_html=True)
                if st.button("🔒 Freeze & Show Leaderboard", use_container_width=True, key="cf"):
                    freeze_q(client, session)
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
        with n3:
            last_in_phase = (idx >= len(ph_qs) - 1)
            # Check if there are more phases
            more_phases   = _has_next_phase(phase, questions)
            if last_in_phase and not more_phases:
                st.markdown('<div class="btn-green">', unsafe_allow_html=True)
                if st.button("🏁 End Game", use_container_width=True, key="cend"):
                    set_finished(client, session)
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                next_label = "Next ➡" if not last_in_phase else f"Next Phase ➡"
                if st.button(next_label, use_container_width=True, key="cn"):
                    if not last_in_phase:
                        push_question(client, session, phase, idx + 1)
                    else:
                        next_ph = _next_phase(phase, questions)
                        if next_ph:
                            push_question(client, session, next_ph, 0)
                    st.rerun()

        # Live results for this question
        if responses:
            st.divider()
            opts = active_q.get("options_json") or []
            if opts:
                df = pd.DataFrame(responses)
                counts = df["selected_option"].value_counts().reindex(opts, fill_value=0)
                st.bar_chart(counts)

            # Top 10 fastest for this question
            correct_resp = sorted(
                [r for r in responses if r.get("is_correct")],
                key=lambda r: int(r.get("response_time_ms") or 9e9))[:10]
            if correct_resp:
                st.markdown("#### ⚡ Top 10 Fastest This Question")
                for i, r in enumerate(correct_resp):
                    medal = ["🥇","🥈","🥉"][i] if i < 3 else f"#{i+1}"
                    st.markdown(
                        f'<div class="lb-row {"gold silver bronze".split()[i] if i<3 else ""}">'
                        f'<div class="lb-rank">{medal}</div>'
                        f'<div class="lb-name">{r["player_name"]}</div>'
                        f'<div class="lb-score">{r["response_time_ms"]} ms</div>'
                        f'</div>', unsafe_allow_html=True)

            st.divider()
            scores = get_scores(client, session["id"])
            render_leaderboard(scores, "📊 Overall Leaderboard", limit=10)

    # ── RESULTS TAB ──────────────────────────────────────────────────────────
    with t_results:
        _render_final_results(client, session, questions)


def _push_questions_to_db(client: Client, session: dict, questions: list[dict]):
    """Insert questions into DB if not already there."""
    existing = _q(lambda: client.table("questions").select("id").eq("session_id", session["id"]), [])
    if existing:
        return  # already pushed
    for q in questions:
        _q(lambda qd=q: client.table("questions").insert({
            "session_id": session["id"],
            "phase": qd["phase"],
            "question_text": qd["question_text"],
            "options_json": qd.get("options_json", []),
            "correct_option": qd.get("correct_option"),
            "points_weight": qd.get("points_weight", 100),
        }), [])


def _get_phase_questions_from_db(client: Client, session: dict) -> list[dict]:
    phase = session["current_phase"]
    return _q(lambda: client.table("questions").select("*")
              .eq("session_id", session["id"]).eq("phase", phase)
              .order("created_at").order("id"), []) or []


def get_all_questions_from_db(client: Client, session: dict) -> list[dict]:
    return _q(lambda: client.table("questions").select("*")
              .eq("session_id", session["id"]).order("created_at").order("id"), []) or []


def _has_next_phase(current_phase: str, questions: list[dict]) -> bool:
    idx = PHASES.index(current_phase) if current_phase in PHASES else -1
    for ph in PHASES[idx+1:]:
        if any(q["phase"] == ph for q in questions):
            return True
    return False


def _next_phase(current_phase: str, questions: list[dict]) -> str | None:
    idx = PHASES.index(current_phase) if current_phase in PHASES else -1
    for ph in PHASES[idx+1:]:
        if any(q["phase"] == ph for q in questions):
            return ph
    return None


def _render_final_results(client: Client, session: dict, questions: list[dict]):
    st.subheader("🏆 Final Results")
    scores = get_scores(client, session["id"])
    if not scores:
        st.info("No scores yet.")
        return

    # Overall leaderboard
    render_leaderboard(scores, "Overall Leaderboard", limit=30)

    st.divider()

    # Grouped by correct count
    st.markdown("### 🎯 Results by Correct Answers")
    by_correct: dict[int, list[str]] = {}
    for s in scores:
        cc = int(s.get("correct_count") or 0)
        by_correct.setdefault(cc, []).append(s["player_name"])
    for cc in sorted(by_correct.keys(), reverse=True):
        names = ", ".join(by_correct[cc])
        emoji = "🏆" if cc == max(by_correct.keys()) else "✅" if cc > 0 else "📝"
        st.markdown(
            f'<div style="background:#fff;border:1px solid #c7d4ef;border-radius:10px;'
            f'padding:14px 18px;margin-bottom:8px;">'
            f'<strong>{emoji} {cc} correct</strong> — {names}</div>',
            unsafe_allow_html=True)

    st.divider()

    # Fastest finger per question
    st.markdown("### ⚡ Fastest Finger Per Question")
    all_qs = get_all_questions_from_db(client, session)
    for q in all_qs:
        if q["phase"] != "during":
            continue
        resp = get_responses(client, q["id"])
        correct = sorted([r for r in resp if r.get("is_correct")],
                         key=lambda r: int(r.get("response_time_ms") or 9e9))
        if correct:
            f = correct[0]
            st.markdown(
                f'<div style="background:#fffce8;border:1px solid {GOLD};border-radius:9px;'
                f'padding:12px 16px;margin-bottom:6px;">'
                f'⚡ <strong>{f["player_name"]}</strong> — {f["response_time_ms"]} ms<br>'
                f'<span style="font-size:13px;color:#5a6282;">{q["question_text"][:80]}</span>'
                f'</div>', unsafe_allow_html=True)

    st.divider()

    # CSV Download
    st.markdown("### ⬇ Download Results")
    csv_rows = []
    for s in scores:
        csv_rows.append({
            "Rank": scores.index(s) + 1,
            "Player Name": s["player_name"],
            "Total Score": s["total_score"],
            "Correct Answers": s.get("correct_count", 0),
            "Session": session["session_name"],
        })
    df_csv = pd.DataFrame(csv_rows)
    csv_buf = io.StringIO()
    df_csv.to_csv(csv_buf, index=False)
    st.download_button(
        "⬇ Download Leaderboard CSV",
        data=csv_buf.getvalue(),
        file_name=f"crowdrush_{session['event_code']}_results.csv",
        mime="text/csv",
        use_container_width=True)

    if session["current_phase"] != "finished":
        st.markdown('<div class="btn-red">', unsafe_allow_html=True)
        if st.button("🏁 Mark Game as Finished", use_container_width=True):
            set_finished(client, session)
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  PLAYER MODE  (QR or manual code join)
# ══════════════════════════════════════════════════════════════════════════════

def player_view(client: Client):
    """Audience/participant experience."""
    # ── Join flow ─────────────────────────────────────────────────────────────
    qp = _get_room_param()
    if qp and not st.session_state.get("aud_code"):
        st.session_state.aud_code = qp

    code = st.session_state.get("aud_code", "")
    if not code:
        banner("Join CrowdRush", "Enter your room code or scan the QR code on screen.")
        entered = st.text_input("4-digit Room Code", max_chars=4, key="aud_code_in")
        if st.button("🚀 Join Room", disabled=(len(entered.strip()) != 4)):
            st.session_state.aud_code = entered.strip()
            st.rerun()
        return

    session = get_session(client, code)
    if not session:
        st.error("Room code not found. Please check and try again.")
        if st.button("Try another code"):
            st.session_state.pop("aud_code", None)
            st.rerun()
        return

    name_key = f"pname_{session['event_code']}"
    if not st.session_state.get(name_key):
        banner(session["session_name"],
               f"Room {session['event_code']} — Welcome!")
        st.markdown(
            '<div style="background:#fff;border:1px solid #c7d4ef;border-radius:10px;'
            'padding:20px;max-width:480px;">'
            '<h3 style="margin:0 0 8px;">👤 Enter your display name</h3>'
            '<p style="color:#5a6282;font-size:14px;margin:0 0 16px;">'
            'Use a unique name so your coach can identify you on the leaderboard. '
            'Your name will be visible to all participants.</p></div>',
            unsafe_allow_html=True)
        name = st.text_input("Your unique name", max_chars=36, key="pname_input",
                             placeholder="e.g. Priya K")
        players = get_players(client, session["id"])
        existing_names = [p["player_name"].lower() for p in players]
        name_taken = name.strip().lower() in existing_names if name.strip() else False

        if name_taken:
            st.warning(f"'{name.strip()}' is already taken. Please choose a different name.")
        if st.button("✅ Join Session",
                     disabled=(not name.strip() or name_taken or len(players) >= MAX_PLAYERS)):
            st.session_state[name_key] = name.strip()
            ensure_player(client, session["id"], name.strip())
            st.rerun()
        if len(players) >= MAX_PLAYERS:
            st.error(f"Session is full ({MAX_PLAYERS} players max).")
        return

    player = st.session_state[name_key]

    # ── Lobby waiting ─────────────────────────────────────────────────────────
    if session["current_phase"] == "lobby":
        banner(session["session_name"], f"👋 {player}  ·  Room {code}")
        players = get_players(client, session["id"])
        st.markdown(f"""
<div style="background:#fff;border:1.5px solid {ROYAL};border-radius:12px;
padding:24px;text-align:center;max-width:500px;margin:20px auto;">
  <div style="font-size:48px;">🎯</div>
  <h2 style="margin:8px 0 4px;color:{ROYAL};">You're in!</h2>
  <p style="color:#5a6282;">Waiting for the coach to start the game…</p>
  <div style="margin-top:16px;font-size:36px;font-weight:900;color:{CHARCOAL};">
    {len(players)} player(s) joined
  </div>
</div>""", unsafe_allow_html=True)
        chips = "".join(f'<span class="chip">👤 {p["player_name"]}</span>' for p in players)
        st.markdown(chips, unsafe_allow_html=True)
        return

    # ── Game finished ─────────────────────────────────────────────────────────
    if session["current_phase"] == "finished":
        banner(session["session_name"], "🏁 Game Complete!")
        scores = get_scores(client, session["id"])
        # Find this player's rank
        for i, s in enumerate(scores):
            if s["player_name"] == player:
                medal = ["🥇","🥈","🥉"][i] if i < 3 else f"#{i+1}"
                pts   = int(s["total_score"])
                cc    = int(s.get("correct_count") or 0)
                st.markdown(f"""
<div class="pop pop-ok">
  <h3>Your Final Result</h3>
  <div class="big">{medal}</div>
  <div class="sub">{pts:,} points  ·  {cc} correct answers</div>
</div>""", unsafe_allow_html=True)
                break
        render_leaderboard(scores, "🏆 Final Leaderboard", limit=30)
        return

    # ── Active question ───────────────────────────────────────────────────────
    # Refresh session
    session = get_session(client, code)
    phase   = session["current_phase"]
    idx     = int(session.get("current_question_index") or 0)
    frozen  = not bool(session.get("question_start_time"))

    ph_qs = _get_phase_questions_from_db(client, session)
    if not ph_qs:
        waiting()
        return

    idx = max(0, min(idx, len(ph_qs) - 1))
    question = ph_qs[idx]

    banner(session["session_name"], f"👋 {player}  ·  Room {code}")
    st.markdown(f'<span class="pp">{PH_ICON[phase]} {PH_LABEL[phase]}  ·  Q{idx+1}/{len(ph_qs)}</span>',
                unsafe_allow_html=True)

    if frozen:
        # Show leaderboard while frozen
        existing = get_existing_resp(client, question["id"], player)
        if existing and phase == "during":
            is_cor  = existing.get("is_correct", False)
            t_ms    = int(existing.get("response_time_ms") or 0)
            w       = int(question.get("points_weight") or 100)
            bonus   = max(0, 1000 - int(t_ms / 10))
            pts     = (w + bonus) if is_cor else 0
            if is_cor:
                st.markdown(f'<div class="pop pop-ok"><h3>✅ Correct!</h3>'
                            f'<div class="big">+{pts:,}</div>'
                            f'<div class="sub">{t_ms} ms · speed bonus +{bonus}</div></div>',
                            unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="pop pop-no"><h3>❌ Not this time</h3>'
                            f'<div class="big" style="font-size:36px;">Keep going! ⚡</div>'
                            f'<div class="sub">{t_ms} ms</div></div>', unsafe_allow_html=True)

        scores = get_scores(client, session["id"], )
        responses = get_responses(client, question["id"])
        render_leaderboard(scores, "⚡ Live Leaderboard", show_rt=True,
                           responses=responses, limit=10)
        waiting("Waiting for coach to move to next question…")
        return

    # Timer
    start_ms = _parse_ms(session.get("question_start_time"))
    if phase == "during":
        timer_bar(start_ms)

    # Question
    st.markdown(f'<div class="qc"><h2>{question["question_text"]}</h2></div>',
                unsafe_allow_html=True)

    # Already answered?
    existing = get_existing_resp(client, question["id"], player)
    if existing:
        if phase == "during":
            is_cor = existing.get("is_correct", False)
            t_ms   = int(existing.get("response_time_ms") or 0)
            w      = int(question.get("points_weight") or 100)
            bonus  = max(0, 1000 - int(t_ms / 10))
            pts    = (w + bonus) if is_cor else 0
            if is_cor:
                st.markdown(f'<div class="pop pop-ok"><h3>✅ Correct!</h3>'
                            f'<div class="big">+{pts:,}</div>'
                            f'<div class="sub">{t_ms} ms · speed bonus +{bonus}</div></div>',
                            unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="pop pop-no"><h3>❌ Not this time</h3>'
                            f'<div class="big" style="font-size:36px;">Stay sharp! ⚡</div>'
                            f'<div class="sub">{t_ms} ms</div></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="pop pop-neu"><h3>✅ Response received!</h3>'
                        '<div class="sub">Thank you — waiting for next question.</div></div>',
                        unsafe_allow_html=True)

        scores    = get_scores(client, session["id"])
        responses = get_responses(client, question["id"])
        render_leaderboard(scores, "⚡ Live Standings", show_rt=True,
                           responses=responses, limit=10)
        waiting("Waiting for next question…")
        return

    # ── Answer form ───────────────────────────────────────────────────────────
    options = question.get("options_json") or []
    if isinstance(options, list) and options:
        selected = st.radio("Choose your answer", options, index=None,
                            key=f"r_{question['id']}")
        can_submit = selected is not None
    else:
        selected = st.text_area("Your response", key=f"t_{question['id']}")
        can_submit = bool((selected or "").strip())

    st.markdown('<div class="btn-green">', unsafe_allow_html=True)
    if st.button("📤 Submit Answer", disabled=not can_submit,
                 use_container_width=True, key=f"sub_{question['id']}"):
        with st.spinner("Submitting…"):
            click_ms = now_ms()
            rt = max(0, click_ms - start_ms) if phase == "during" else 0
            choice = (selected or "").strip() if not options else selected
            submit_answer(client, session, question, player, choice, rt)
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    inject_css()

    client = _get_client()

    # ── Player mode: triggered by ?room= URL param ────────────────────────────
    if _get_room_param():
        if not client:
            st.error("⚠ Supabase not configured.")
            return
        player_view(client)
        return

    # ── App mode routing (no sidebar, no role picker) ─────────────────────────
    mode = st.session_state.get("app_mode", "config")

    # Top-left nav buttons (minimal)
    nav1, nav2, nav3 = st.columns([2, 2, 8])
    if mode == "config":
        with nav1:
            st.markdown('<div class="btn-green">', unsafe_allow_html=True)
            st.button("🔧 Configurator", disabled=True, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
        with nav2:
            if st.button("🚀 Coach / Play", use_container_width=True):
                # Only switch if there's a loaded game
                if st.session_state.get("launch_game") and client:
                    st.session_state.app_mode = "coach"
                    st.rerun()
                else:
                    st.toast("Launch a game from the library first.", icon="ℹ")
    else:
        with nav1:
            if st.button("🔧 Configurator", use_container_width=True):
                st.session_state.app_mode = "config"
                st.rerun()
        with nav2:
            st.markdown('<div class="btn-green">', unsafe_allow_html=True)
            st.button("🚀 Coach / Play", disabled=True, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if mode == "config":
        configurator_view()
    elif mode == "coach":
        if not client:
            st.error("⚠ Supabase not configured — add SUPABASE_URL & SUPABASE_KEY to secrets.")
            with st.expander("Setup SQL"):
                try:
                    st.code(open("supabase_schema.sql").read(), language="sql")
                except Exception:
                    pass
            return
        coach_view(client)


if __name__ == "__main__":
    main()
