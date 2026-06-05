import base64
import io
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


PHASES = ["pre", "during", "post"]
PHASE_LABELS = {
    "pre": "Pre-Session",
    "during": "Live Game",
    "post": "Post-Session",
}
PHASE_ICONS = {"pre": "🔆", "during": "⚡", "post": "🏁"}

# HCLTech Career Shaper brand colours
CS_ROYAL   = "#0F5FDC"
CS_CHARCOAL = "#14142A"
CS_LAVENDER = "#E6EBF5"
CS_WHITE    = "#FFFFFF"
CS_ACCENT   = "#F26A13"   # keep energy for timers / CTAs
CS_GOLD     = "#FFC400"


st.set_page_config(
    page_title="Career Shaper™ CrowdRush",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

st_autorefresh(interval=2500, key="live_refresh")


# ─── helpers ────────────────────────────────────────────────────────────────

def logo_b64() -> str:
    logo_path = Path(__file__).parent / "cs_logo.png"
    if logo_path.exists():
        return base64.b64encode(logo_path.read_bytes()).decode()
    return ""


def inject_css():
    logo = logo_b64()
    logo_html = f'<img src="data:image/png;base64,{logo}" alt="Career Shaper™" style="height:38px; margin-bottom:4px;">' if logo else '<span style="font-size:22px; font-weight:900; color:#0F5FDC; letter-spacing:-0.5px;">Career Shaper™</span>'
    st.markdown(
        f"""
        <style>
        :root {{
            --cs-royal:   {CS_ROYAL};
            --cs-charcoal:{CS_CHARCOAL};
            --cs-lavender:{CS_LAVENDER};
            --accent:     {CS_ACCENT};
            --gold:       {CS_GOLD};
            --ink:        {CS_CHARCOAL};
            --muted:      #5a6282;
            --surface:    #f4f6fc;
        }}
        html, body {{ scroll-behavior: smooth; }}
        .stApp {{
            background: linear-gradient(160deg, #f4f6fc 0%, {CS_LAVENDER} 55%, #dde4f5 100%);
            color: var(--ink);
        }}
        /* sidebar */
        section[data-testid="stSidebar"] {{
            background: {CS_CHARCOAL};
            border-right: 2px solid {CS_ROYAL};
        }}
        section[data-testid="stSidebar"] * {{ color: #e8ecf8 !important; }}
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {{
            color: {CS_WHITE} !important;
        }}
        section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] * {{
            color: #8fa5cc !important;
        }}
        .sidebar-logo {{
            text-align: center;
            padding: 18px 0 10px 0;
            border-bottom: 1px solid #2a3055;
            margin-bottom: 14px;
        }}
        /* banner */
        .cs-banner {{
            display: flex;
            align-items: center;
            gap: 18px;
            padding: 18px 24px;
            background: linear-gradient(90deg, {CS_CHARCOAL} 0%, #1e2450 60%, {CS_ROYAL} 100%);
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 6px 24px rgba(15,95,220,0.22);
        }}
        .cs-banner .title-block h1 {{
            margin: 0;
            color: #ffffff;
            font-size: 26px;
            font-weight: 800;
            letter-spacing: -0.3px;
        }}
        .cs-banner .title-block p {{
            margin: 2px 0 0 0;
            color: #a8beee;
            font-size: 14px;
        }}
        /* metric row */
        .metric-row {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 12px;
            margin: 14px 0 18px 0;
        }}
        .pulse-card {{
            border: 1px solid #c7d4ef;
            border-radius: 10px;
            background: #ffffff;
            padding: 16px;
            box-shadow: 0 2px 8px rgba(15,95,220,0.07);
        }}
        .pulse-card label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .05em; }}
        .big-code {{
            font-size: clamp(34px, 7vw, 64px);
            font-weight: 900;
            color: {CS_ROYAL};
            line-height: 1;
        }}
        /* phase pill */
        .phase-pill {{
            display: inline-block;
            padding: 5px 12px;
            border-radius: 999px;
            background: {CS_LAVENDER};
            color: {CS_ROYAL};
            font-weight: 700;
            font-size: 13px;
            border: 1px solid #b0c4e8;
        }}
        /* question card */
        .q-card {{
            background: #ffffff;
            border: 1px solid #c7d4ef;
            border-left: 5px solid {CS_ROYAL};
            border-radius: 10px;
            padding: 22px 24px;
            margin-bottom: 18px;
            box-shadow: 0 4px 16px rgba(15,95,220,0.08);
        }}
        .q-card h2 {{ margin: 0; color: {CS_CHARCOAL}; font-size: 22px; }}
        /* timer bar */
        .timer-wrap {{ margin: 12px 0; }}
        .timer-bar-bg {{
            height: 8px;
            border-radius: 999px;
            background: #dde4f5;
            overflow: hidden;
        }}
        .timer-bar-fill {{
            height: 100%;
            border-radius: 999px;
            transition: width 1s linear;
        }}
        /* waiting */
        .waiting {{
            min-height: 220px;
            display: grid;
            place-items: center;
            border: 2px dashed #b0c4e8;
            border-radius: 10px;
            background: rgba(230,235,245,0.4);
            text-align: center;
            padding: 30px;
        }}
        .waiting h2 {{ color: {CS_ROYAL}; margin-bottom: 6px; }}
        .waiting p {{ color: var(--muted); }}
        /* badge / fastest finger */
        .badge {{
            display: inline-block;
            padding: 10px 16px;
            border-radius: 10px;
            background: linear-gradient(90deg, #fff3cd, #fff8e1);
            border: 1px solid {CS_GOLD};
            color: #5b3100;
            font-weight: 700;
            font-size: 15px;
        }}
        /* leaderboard rows */
        .lb-row {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 14px;
            border-radius: 8px;
            margin-bottom: 6px;
            background: #ffffff;
            border: 1px solid #dde4f5;
        }}
        .lb-rank {{ font-size: 20px; width: 30px; text-align: center; }}
        .lb-name {{ flex: 1; font-weight: 700; color: {CS_CHARCOAL}; }}
        .lb-score {{
            font-weight: 800;
            font-size: 18px;
            color: {CS_ROYAL};
        }}
        .lb-row.gold   {{ border-left: 4px solid #FFD700; background: #fffce8; }}
        .lb-row.silver {{ border-left: 4px solid #C0C0C0; background: #f8f8fb; }}
        .lb-row.bronze {{ border-left: 4px solid #CD7F32; background: #fdf6ee; }}
        /* result popup */
        .result-pop {{
            background: linear-gradient(135deg, #0F5FDC 0%, #0a3ea3 100%);
            border-radius: 14px;
            padding: 24px 28px;
            margin: 16px 0;
            color: #ffffff;
            text-align: center;
            box-shadow: 0 8px 32px rgba(15,95,220,0.3);
        }}
        .result-pop h3 {{ margin: 0 0 8px 0; font-size: 20px; color: #ffffff; }}
        .result-pop .big-num {{ font-size: 52px; font-weight: 900; color: #FFD700; line-height: 1; }}
        .result-pop .sub {{ font-size: 14px; color: #a8beee; margin-top: 4px; }}
        /* buttons */
        div[data-testid="stButton"] > button,
        div[data-testid="stFormSubmitButton"] > button {{
            border-radius: 8px;
            border: 1px solid {CS_ROYAL};
            background: linear-gradient(90deg, {CS_ROYAL} 0%, #1a77f2 100%);
            color: #ffffff !important;
            font-weight: 700;
            min-height: 42px;
            box-shadow: 0 3px 10px rgba(15,95,220,0.22);
        }}
        div[data-testid="stButton"] > button:hover,
        div[data-testid="stFormSubmitButton"] > button:hover {{
            background: linear-gradient(90deg, #0a3ea3 0%, #1466d8 100%);
            border-color: #0a3ea3;
        }}
        div[data-testid="stButton"] > button:disabled {{
            background: #c7d4ef;
            border-color: #b0c4e8;
            color: #8090b0 !important;
            box-shadow: none;
        }}
        /* radio buttons */
        div[data-testid="stRadio"] label span {{ color: {CS_CHARCOAL} !important; font-size: 16px; }}
        div[data-testid="stRadio"] > div > label {{
            background: #ffffff;
            border: 1px solid #c7d4ef;
            border-radius: 8px;
            padding: 10px 14px;
            margin-bottom: 8px;
            transition: border-color 0.15s;
        }}
        /* inputs */
        div[data-testid="stTextInput"] label,
        div[data-testid="stTextArea"] label,
        div[data-testid="stNumberInput"] label,
        div[data-testid="stSelectbox"] label {{ color: {CS_CHARCOAL}; font-weight: 700; }}
        div[data-testid="stTextInput"] input,
        div[data-testid="stTextArea"] textarea,
        div[data-testid="stNumberInput"] input {{
            background: #ffffff;
            border-color: #b0c4e8;
            color: {CS_CHARCOAL};
        }}
        /* tabs */
        button[role="tab"] {{ font-weight: 700; color: var(--muted); }}
        button[role="tab"][aria-selected="true"],
        button[role="tab"][aria-selected="true"] * {{ color: {CS_ROYAL}; }}
        div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {{
            background: linear-gradient(90deg, {CS_ROYAL}, {CS_GOLD});
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Sidebar logo
    logo = logo_b64()
    if logo:
        st.sidebar.markdown(
            f'<div class="sidebar-logo"><img src="data:image/png;base64,{logo}" alt="Career Shaper™" style="height:44px;"></div>',
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.markdown('<div class="sidebar-logo"><span style="font-size:18px; font-weight:900; color:#0F5FDC;">Career Shaper™</span></div>', unsafe_allow_html=True)


# ─── Supabase ────────────────────────────────────────────────────────────────

def get_secret(name: str) -> str | None:
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    return value or os.environ.get(name)


@st.cache_resource(show_spinner=False)
def get_supabase() -> Client | None:
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


def db_required() -> Client | None:
    client = get_supabase()
    if client is None:
        st.error(
            "Supabase is not configured. Add SUPABASE_URL and SUPABASE_KEY to Streamlit secrets "
            "or environment variables, then run the SQL in supabase_schema.sql."
        )
    return client


# ─── Time helpers ─────────────────────────────────────────────────────────────

def now_ms() -> int:
    return int(time.time() * 1000)


def parse_epoch_ms(value) -> int:
    if not value:
        return now_ms()
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).replace("Z", "+00:00")
    try:
        return int(datetime.fromisoformat(text).timestamp() * 1000)
    except ValueError:
        return now_ms()


def utc_iso_from_ms(epoch_ms: int) -> str:
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).isoformat()


def random_code() -> str:
    return f"{random.randint(0, 9999):04d}"


# ─── DB helpers ──────────────────────────────────────────────────────────────

def run_query(fn, fallback=None):
    try:
        return fn().execute().data
    except Exception as exc:
        st.error(f"Database error: {exc}")
        return fallback


def generate_unique_code(client: Client) -> str:
    for _ in range(30):
        code = random_code()
        rows = run_query(lambda: client.table("sessions").select("id").eq("event_code", code), [])
        if not rows:
            return code
    raise RuntimeError("Could not generate a unique event code.")


def create_session(client: Client, session_name: str) -> dict | None:
    code = generate_unique_code(client)
    rows = run_query(
        lambda: client.table("sessions")
        .insert(
            {
                "session_name": session_name,
                "event_code": code,
                "current_phase": "pre",
                "current_question_index": 0,
                "question_start_time": None,
            }
        )
        .select("*"),
        [],
    )
    return rows[0] if rows else None


def get_session_by_code(client: Client, code: str) -> dict | None:
    rows = run_query(lambda: client.table("sessions").select("*").eq("event_code", code).limit(1), [])
    return rows[0] if rows else None


def get_questions(client: Client, session_id: str, phase: str | None = None) -> list[dict]:
    query = client.table("questions").select("*").eq("session_id", session_id).order("created_at").order("id")
    if phase:
        query = query.eq("phase", phase)
    return run_query(lambda: query, []) or []


def get_active_question(client: Client, session: dict) -> dict | None:
    questions = get_questions(client, session["id"], session["current_phase"])
    index = int(session.get("current_question_index") or 0)
    if not questions or index < 0 or index >= len(questions):
        return None
    return questions[index]


def normalize_options(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def add_question(client: Client, session_id: str, phase: str, text: str, options: list[str], correct: str, weight: int):
    run_query(
        lambda: client.table("questions").insert(
            {
                "session_id": session_id,
                "phase": phase,
                "question_text": text,
                "options_json": options,
                "correct_option": correct or None,
                "points_weight": weight,
            }
        ),
        [],
    )


def delete_question(client: Client, question_id: str):
    run_query(lambda: client.table("questions").delete().eq("id", question_id), [])


def activate_question(client: Client, session: dict, phase: str, index: int):
    run_query(
        lambda: client.table("sessions")
        .update(
            {
                "current_phase": phase,
                "current_question_index": index,
                "question_start_time": utc_iso_from_ms(now_ms()),
            }
        )
        .eq("id", session["id"]),
        [],
    )


def freeze_question(client: Client, session: dict):
    run_query(
        lambda: client.table("sessions").update({"question_start_time": None}).eq("id", session["id"]),
        [],
    )


def set_phase(client: Client, session: dict, phase: str):
    run_query(
        lambda: client.table("sessions")
        .update({"current_phase": phase, "current_question_index": 0, "question_start_time": utc_iso_from_ms(now_ms())})
        .eq("id", session["id"]),
        [],
    )


def get_responses(client: Client, question_id: str) -> list[dict]:
    return run_query(lambda: client.table("responses").select("*").eq("question_id", question_id), []) or []


def get_scores(client: Client, session_id: str, limit: int | None = None) -> list[dict]:
    query = client.table("player_scores").select("*").eq("session_id", session_id).order("total_score", desc=True)
    if limit:
        query = query.limit(limit)
    return run_query(lambda: query, []) or []


def ensure_player_score(client: Client, session_id: str, player_name: str):
    existing = run_query(
        lambda: client.table("player_scores")
        .select("id")
        .eq("session_id", session_id)
        .eq("player_name", player_name)
        .limit(1),
        [],
    )
    if existing:
        return
    run_query(
        lambda: client.table("player_scores").insert(
            {"session_id": session_id, "player_name": player_name, "total_score": 0}
        ),
        [],
    )


def get_existing_response(client: Client, question_id: str, player_name: str) -> dict | None:
    rows = run_query(
        lambda: client.table("responses").select("*").eq("question_id", question_id).eq("player_name", player_name).limit(1),
        [],
    )
    return rows[0] if rows else None


def score_for_answer(question: dict, is_correct: bool, response_time_ms: int) -> int:
    if not is_correct:
        return 0
    weight = int(question.get("points_weight") or 100)
    speed_bonus = max(0, 1000 - int(response_time_ms / 10))
    return weight + speed_bonus


def submit_response(client: Client, session: dict, question: dict, player_name: str, selected_option: str, response_time_ms: int):
    existing = get_existing_response(client, question["id"], player_name)
    if existing:
        return existing, False

    correct_option = question.get("correct_option")
    is_game = session["current_phase"] == "during"
    is_correct = bool(is_game and correct_option and selected_option == correct_option)
    points = score_for_answer(question, is_correct, response_time_ms) if is_game else 0

    rows = run_query(
        lambda: client.table("responses")
        .insert(
            {
                "question_id": question["id"],
                "player_name": player_name,
                "selected_option": selected_option,
                "is_correct": is_correct,
                "response_time_ms": response_time_ms,
            }
        )
        .select("*"),
        [],
    )
    if is_game:
        current_rows = run_query(
            lambda: client.table("player_scores")
            .select("*")
            .eq("session_id", session["id"])
            .eq("player_name", player_name)
            .limit(1),
            [],
        )
        current = current_rows[0]["total_score"] if current_rows else 0
        run_query(
            lambda: client.table("player_scores")
            .upsert(
                {
                    "session_id": session["id"],
                    "player_name": player_name,
                    "total_score": int(current) + int(points),
                },
                on_conflict="session_id,player_name",
            ),
            [],
        )
    return (rows[0] if rows else None), True


# ─── QR ──────────────────────────────────────────────────────────────────────

def qr_image(link: str) -> Image.Image:
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(link)
    qr.make(fit=True)
    return qr.make_image(fill_color=CS_CHARCOAL, back_color="white").convert("RGB")


# ─── Shared UI components ─────────────────────────────────────────────────────

def render_banner(title: str, subtitle: str):
    logo = logo_b64()
    img_tag = f'<img src="data:image/png;base64,{logo}" alt="Career Shaper™" style="height:46px; flex-shrink:0;">' if logo else ''
    st.markdown(
        f"""
        <div class="cs-banner">
            {img_tag}
            <div class="title-block">
                <h1>{title}</h1>
                <p>{subtitle}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_session_metrics(session: dict, questions: list[dict]):
    phase = session["current_phase"]
    phase_count = len([q for q in questions if q["phase"] == phase])
    current_q = int(session.get("current_question_index") or 0) + 1 if phase_count else 0
    st.markdown(
        f"""
        <div class="metric-row">
            <div class="pulse-card">
                <label>Session</label>
                <div style="font-weight:800; font-size:16px; margin-top:4px;">{session["session_name"]}</div>
            </div>
            <div class="pulse-card">
                <label>Room Code</label>
                <div class="big-code">{session["event_code"]}</div>
            </div>
            <div class="pulse-card">
                <label>Phase</label>
                <div style="margin-top:6px;"><span class="phase-pill">{PHASE_ICONS[phase]} {PHASE_LABELS[phase]}</span></div>
            </div>
            <div class="pulse-card">
                <label>Question</label>
                <h2 style="margin:4px 0 0 0; color:{CS_ROYAL};">{current_q} / {phase_count}</h2>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_leaderboard(scores: list[dict], title: str = "🏆 Leaderboard", limit: int = 10):
    st.markdown(f"### {title}")
    medals = ["🥇", "🥈", "🥉"]
    row_classes = ["gold", "silver", "bronze"]
    for i, s in enumerate(scores[:limit]):
        rank = medals[i] if i < 3 else f"#{i+1}"
        cls = row_classes[i] if i < 3 else ""
        st.markdown(
            f"""<div class="lb-row {cls}">
                <div class="lb-rank">{rank}</div>
                <div class="lb-name">{s['player_name']}</div>
                <div class="lb-score">{s['total_score']:,}</div>
            </div>""",
            unsafe_allow_html=True,
        )
    if not scores:
        st.caption("No scores yet.")


def render_fastest_finger(responses: list[dict]):
    correct = [r for r in responses if r.get("is_correct")]
    if not correct:
        return None
    fastest = sorted(correct, key=lambda r: int(r.get("response_time_ms") or 999999999))[0]
    st.markdown(
        f"<div class='badge'>⚡ Fastest Finger: <strong>{fastest['player_name']}</strong> &mdash; {fastest['response_time_ms']} ms</div>",
        unsafe_allow_html=True,
    )
    return fastest


def render_timer_bar(start_ms: int, duration_ms: int = 30_000):
    elapsed = now_ms() - start_ms
    remaining_ms = max(0, duration_ms - elapsed)
    remaining_s = remaining_ms // 1000
    pct = max(0, min(100, remaining_ms / duration_ms * 100))
    color = CS_ROYAL if pct > 40 else CS_ACCENT if pct > 15 else "#e53935"
    st.markdown(
        f"""
        <div class="timer-wrap">
            <div style="font-size:13px; color:{color}; font-weight:700; margin-bottom:4px;">
                ⏱ {remaining_s}s remaining
            </div>
            <div class="timer-bar-bg">
                <div class="timer-bar-fill" style="width:{pct}%; background:{color};"></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─── HOST VIEW ────────────────────────────────────────────────────────────────

def host_configuration(client: Client):
    st.subheader("Create or load a session")
    notice = st.session_state.pop("host_event_created_notice", None)
    if notice:
        st.success(notice)
    left, right = st.columns(2)
    with left:
        with st.form("create_session"):
            session_name = st.text_input("Session Name", value="AI Fluency Boot Camp – Cohort 3")
            submitted = st.form_submit_button("🚀 Create session")
        if submitted and session_name.strip():
            with st.spinner("Reserving your room code…"):
                started = time.perf_counter()
                session = create_session(client, session_name.strip())
                elapsed = time.perf_counter() - started
            if session:
                st.session_state.host_event_code = session["event_code"]
                st.session_state.host_event_created_notice = (
                    f"Session created! Room code: {session['event_code']} ({elapsed:.1f}s)"
                )
                st.rerun()
            else:
                st.error("Session not created — check your Supabase connection.")
        elif submitted:
            st.warning("Enter a session name first.")
    with right:
        code = st.text_input("Load existing 4-digit code", value=st.session_state.get("host_event_code", ""))
        if st.button("🔍 Load session") and code.strip():
            session = get_session_by_code(client, code.strip())
            if session:
                st.session_state.host_event_code = session["event_code"]
                st.rerun()
            else:
                st.warning("No session found for that code.")


def question_builder(client: Client, session: dict):
    st.subheader("Question timeline builder")
    with st.expander("➕ Add question / poll / icebreaker", expanded=True):
        with st.form("add_question"):
            phase = st.selectbox(
                "Phase",
                PHASES,
                format_func=lambda v: f"{PHASE_ICONS[v]}  {PHASE_LABELS[v]}",
            )
            question_text = st.text_area("Question text", placeholder="Type your question here…")
            options_text = st.text_area(
                "Answer options (one per line — leave blank for open-ended)",
                placeholder="Option A\nOption B\nOption C\nOption D",
            )
            options = normalize_options(options_text)
            correct = st.selectbox(
                "Correct option (for Live Game scoring)",
                [""] + options,
                disabled=(phase != "during" or not options),
            )
            weight = st.number_input("Points weight", min_value=0, max_value=5000, value=100, step=25)
            if st.form_submit_button("Add to timeline"):
                if not question_text.strip():
                    st.warning("Enter question text first.")
                else:
                    add_question(client, session["id"], phase, question_text.strip(), options, correct, int(weight))
                    st.success("Question added ✅")
                    st.rerun()

    questions = get_questions(client, session["id"])
    for phase in PHASES:
        phase_qs = [q for q in questions if q["phase"] == phase]
        st.markdown(f"**{PHASE_ICONS[phase]} {PHASE_LABELS[phase]}** — {len(phase_qs)} question(s)")
        if not phase_qs:
            st.caption("No questions yet.")
            continue
        for idx, q in enumerate(phase_qs, start=1):
            options = q.get("options_json") or []
            note = "open response" if not options else " / ".join(options)
            col1, col2 = st.columns([10, 1])
            with col1:
                st.write(f"**Q{idx}.** {q['question_text']}  \n_{note}_")
            with col2:
                if st.button("🗑", key=f"del_{q['id']}", help="Delete this question"):
                    delete_question(client, q["id"])
                    st.rerun()


def timeline_controls(client: Client, session: dict):
    questions = get_questions(client, session["id"])
    render_session_metrics(session, questions)

    st.subheader("Master timeline control")

    # Phase switcher
    phase_cols = st.columns(3)
    for col, ph in zip(phase_cols, PHASES):
        with col:
            active = session["current_phase"] == ph
            label = f"{PHASE_ICONS[ph]} {PHASE_LABELS[ph]}" + (" ◀ active" if active else "")
            if st.button(label, use_container_width=True, disabled=active, key=f"phase_btn_{ph}"):
                set_phase(client, session, ph)
                st.rerun()

    st.divider()

    phase = session["current_phase"]
    phase_questions = [q for q in questions if q["phase"] == phase]
    current_index = int(session.get("current_question_index") or 0)
    if phase_questions:
        current_index = min(current_index, len(phase_questions) - 1)
        active = phase_questions[current_index]

        st.markdown(
            f"<div class='q-card'><div class='phase-pill'>{PHASE_ICONS[phase]} Q{current_index+1}/{len(phase_questions)}</div><h2 style='margin-top:10px;'>{active['question_text']}</h2></div>",
            unsafe_allow_html=True,
        )

        nav_left, nav_mid, nav_right = st.columns(3)
        with nav_left:
            if st.button("⬅ Previous", disabled=(current_index <= 0), use_container_width=True, key="prev_q"):
                activate_question(client, session, phase, current_index - 1)
                st.rerun()
        with nav_mid:
            if st.button("🔄 Open / Restart timer", use_container_width=True, key="restart_q"):
                activate_question(client, session, phase, current_index)
                st.rerun()
        with nav_right:
            # FIX: next question now correctly advances the index
            if st.button("Next ➡", disabled=(current_index >= len(phase_questions) - 1), use_container_width=True, key="next_q"):
                next_index = current_index + 1
                activate_question(client, session, phase, next_index)
                st.rerun()

        if phase == "during":
            st.divider()
            frozen = not bool(session.get("question_start_time"))
            if frozen:
                st.info("🔒 Timer frozen — leaderboard visible to participants.")
            else:
                if st.button("🔒 Freeze responses & show leaderboard", use_container_width=True, key="freeze_q"):
                    freeze_question(client, session)
                    st.rerun()
    else:
        st.warning(f"No questions in {PHASE_LABELS[phase]} phase yet — go to Configure tab.")


def host_qr_panel(session: dict):
    st.subheader("📱 QR code room access")
    default_url = st.session_state.get("public_app_url", "http://localhost:8501")
    public_url = st.text_input("Public app URL (shown in QR + link)", value=default_url, key="public_app_url")
    join_link = f"{public_url.rstrip('/')}/?room={session['event_code']}"
    st.markdown(f"**Direct join link:** `{join_link}`")
    col1, col2 = st.columns([1, 2])
    with col1:
        st.image(qr_image(join_link), caption="Scan to join instantly", width=220)
    with col2:
        st.markdown(
            f"""
            <div style="padding:20px; background:#fff; border:1px solid #c7d4ef; border-radius:10px;">
                <div style="font-size:13px; color:#5a6282; margin-bottom:8px;">Room Code</div>
                <div class="big-code">{session['event_code']}</div>
                <div style="font-size:13px; color:#5a6282; margin-top:12px;">Participants can join by entering this code<br>or scanning the QR code.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def chart_responses(client: Client, question: dict):
    responses = get_responses(client, question["id"])
    if not responses:
        st.caption("No submissions yet.")
        return
    options = question.get("options_json") or []
    df = pd.DataFrame(responses)
    if options:
        counts = df["selected_option"].value_counts().reindex(options, fill_value=0)
        st.bar_chart(counts)
    else:
        st.dataframe(
            df[["player_name", "selected_option"]].rename(columns={"selected_option": "Response"}),
            use_container_width=True,
        )


def host_analytics(client: Client, session: dict):
    st.subheader("📊 Real-time analytics")
    question = get_active_question(client, session)
    if not question:
        st.caption("No active question.")
        return

    responses = get_responses(client, question["id"])
    total = len(responses)

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Submissions", total)
    with col2:
        correct_count = len([r for r in responses if r.get("is_correct")])
        if session["current_phase"] == "during":
            st.metric("Correct answers", correct_count)

    chart_responses(client, question)

    if session["current_phase"] == "during":
        st.divider()
        render_fastest_finger(responses)
        st.divider()
        scores = get_scores(client, session["id"])
        render_leaderboard(scores)


def host_view(client: Client):
    render_banner("CrowdRush Live — Host", "Run polls, live game rounds, and post-event feedback from one dashboard.")
    host_configuration(client)

    code = st.session_state.get("host_event_code")
    if not code:
        return
    session = get_session_by_code(client, code)
    if not session:
        st.warning("The selected event code no longer exists.")
        return

    tabs = st.tabs(["🎛 Control", "⚙️ Configure", "📱 Access", "📊 Analytics"])
    with tabs[0]:
        timeline_controls(client, session)
    with tabs[1]:
        question_builder(client, session)
    with tabs[2]:
        host_qr_panel(session)
    with tabs[3]:
        host_analytics(client, session)


# ─── AUDIENCE VIEW ────────────────────────────────────────────────────────────

def get_query_room() -> str:
    try:
        value = st.query_params.get("room")
    except Exception:
        value = None
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""


def audience_join(client: Client) -> dict | None:
    # FIX: participants arriving via room URL or QR code see NO host option
    query_room = get_query_room()
    if query_room and not st.session_state.get("audience_event_code"):
        st.session_state.audience_event_code = query_room

    code = st.session_state.get("audience_event_code", "")
    if not code:
        render_banner("Join CrowdRush", "Enter your room code or scan the QR on screen to begin.")
        entered = st.text_input("4-digit Room Code", max_chars=4)
        if st.button("🚀 Join Room", disabled=len(entered.strip()) != 4):
            st.session_state.audience_event_code = entered.strip()
            st.rerun()
        return None

    session = get_session_by_code(client, code)
    if not session:
        st.warning("That room code is not active.")
        if st.button("Try another code"):
            st.session_state.pop("audience_event_code", None)
            st.rerun()
        return None

    player_key = f"player_name_{session['event_code']}"
    if not st.session_state.get(player_key):
        render_banner(session["session_name"], f"Room {session['event_code']} — Enter your name to join.")
        name = st.text_input("Your name", max_chars=36)
        if st.button("✅ Enter session", disabled=not name.strip()):
            st.session_state[player_key] = name.strip()
            ensure_player_score(client, session["id"], name.strip())
            st.rerun()
        return None

    st.session_state.player_name = st.session_state[player_key]
    return session


def waiting_graphic(text: str = "Waiting for host…"):
    st.markdown(
        f"""
        <div class="waiting">
            <div>
                <h2>{text}</h2>
                <p>The screen will update automatically when the next question opens.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def answer_options(question: dict) -> list[str]:
    options = question.get("options_json") or []
    return options if isinstance(options, list) else []


def audience_question(client: Client, session: dict, question: dict, player_name: str):
    phase = session["current_phase"]
    st.markdown(f"<div class='phase-pill'>{PHASE_ICONS[phase]} {PHASE_LABELS[phase]}</div>", unsafe_allow_html=True)

    # Show timer for live game phase
    if phase == "during" and session.get("question_start_time"):
        start_ms = parse_epoch_ms(session["question_start_time"])
        render_timer_bar(start_ms, duration_ms=30_000)

    st.markdown(f"<div class='q-card'><h2>{question['question_text']}</h2></div>", unsafe_allow_html=True)

    existing = get_existing_response(client, question["id"], player_name)

    if existing:
        # FIX: Show immediate result popup after submission, refreshed for each question
        if phase == "during":
            is_correct = existing.get("is_correct", False)
            t_ms = existing.get("response_time_ms", 0)
            if is_correct:
                # Calculate the points earned
                weight = int(question.get("points_weight") or 100)
                speed_bonus = max(0, 1000 - int(t_ms / 10))
                pts = weight + speed_bonus
                st.markdown(
                    f"""<div class="result-pop">
                        <h3>✅ Correct!</h3>
                        <div class="big-num">+{pts:,}</div>
                        <div class="sub">answered in {t_ms} ms · speed bonus {speed_bonus:,} pts</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"""<div class="result-pop" style="background:linear-gradient(135deg,#7b1e1e,#b71c1c);">
                        <h3>❌ Not quite!</h3>
                        <div class="big-num" style="font-size:38px;">Better luck<br>next round</div>
                        <div class="sub">answered in {t_ms} ms</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
        else:
            st.success("✅ Response received — thank you!")

        # Live leaderboard while waiting for next question
        if phase == "during":
            st.divider()
            scores = get_scores(client, session["id"], limit=5)
            render_leaderboard(scores, title="⚡ Live Standings", limit=5)

            responses = get_responses(client, question["id"])
            render_fastest_finger(responses)

        waiting_graphic("Waiting for the next question…")
        return

    # Still answering
    options = answer_options(question)
    start_ms = parse_epoch_ms(session.get("question_start_time"))

    if options:
        selected = st.radio("Choose your answer", options, index=None)
        disabled = selected is None
    else:
        selected = st.text_area("Your response")
        disabled = not selected.strip()

    if st.button("📤 Submit", disabled=disabled, use_container_width=True):
        click_ms = now_ms()
        response_time = max(0, click_ms - start_ms) if phase == "during" else 0
        submit_response(
            client, session, question, player_name,
            selected.strip() if isinstance(selected, str) else selected,
            response_time,
        )
        st.rerun()


def audience_view(client: Client):
    session = audience_join(client)
    if not session:
        return

    player_name = st.session_state.player_name
    render_banner(session["session_name"], f"👋 {player_name}  ·  Room {session['event_code']}")

    question = get_active_question(client, session)
    if not question:
        waiting_graphic()
        return

    if session["current_phase"] == "during" and not session.get("question_start_time"):
        waiting_graphic("⏳ Round starting soon…")
        return

    audience_question(client, session, question, player_name)


# ─── FINAL LEADERBOARD ────────────────────────────────────────────────────────

def final_leaderboard_view(client: Client, session: dict):
    render_banner("🏆 Final Leaderboard", f"{session['session_name']} · Room {session['event_code']}")
    scores = get_scores(client, session["id"])
    render_leaderboard(scores, title="Overall Rankings", limit=20)

    # Fastest finger across all questions
    questions = get_questions(client, session["id"], phase="during")
    all_correct = []
    for q in questions:
        resp = get_responses(client, q["id"])
        all_correct.extend([r for r in resp if r.get("is_correct")])

    if all_correct:
        st.divider()
        st.markdown("### ⚡ Fastest Fingers by Question")
        for q in questions:
            resp = get_responses(client, q["id"])
            correct = sorted(
                [r for r in resp if r.get("is_correct")],
                key=lambda r: int(r.get("response_time_ms") or 999999999)
            )
            if correct:
                st.markdown(
                    f"**{q['question_text'][:60]}…** → ⚡ {correct[0]['player_name']} in {correct[0]['response_time_ms']} ms",
                    unsafe_allow_html=False,
                )


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    inject_css()
    client = db_required()
    if client is None:
        with st.expander("Database setup SQL"):
            try:
                st.code(open("supabase_schema.sql", encoding="utf-8").read(), language="sql")
            except FileNotFoundError:
                st.caption("supabase_schema.sql is missing.")
        return

    # FIX: participants joining via ?room= query param NEVER see the host option
    query_room = get_query_room()

    if query_room:
        # Force audience mode — no sidebar role picker shown
        st.sidebar.markdown("## 🎯 CrowdRush")
        st.sidebar.caption(f"Joined room: **{query_room}**")
        st.sidebar.caption("Auto-refresh active every 2.5 s")
        audience_view(client)
        return

    # Normal flow: show role picker only when no ?room= param
    st.sidebar.markdown("## 🎯 CrowdRush")
    role = st.sidebar.radio("Select your role", ["🎤 Speaker / Host", "🙋 Audience Participant"])
    st.sidebar.caption("Auto-refresh active every 2.5 s")

    # Final leaderboard shortcut in sidebar (host only)
    if role == "🎤 Speaker / Host":
        code = st.session_state.get("host_event_code")
        if code:
            st.sidebar.divider()
            if st.sidebar.button("🏆 Show Final Leaderboard", use_container_width=True):
                session = get_session_by_code(client, code)
                if session:
                    final_leaderboard_view(client, session)
                    return

    if role == "🎤 Speaker / Host":
        host_view(client)
    else:
        audience_view(client)


if __name__ == "__main__":
    main()
