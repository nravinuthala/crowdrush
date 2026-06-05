import io
import os
import random
import time
from datetime import datetime, timezone

import pandas as pd
import qrcode
import streamlit as st
from PIL import Image
from streamlit_autorefresh import st_autorefresh
from supabase import Client, create_client


PHASES = ["pre", "during", "post"]
PHASE_LABELS = {
    "pre": "Pre-Session Interaction",
    "during": "During-Session Live Game",
    "post": "Post-Session Feedback",
}


st.set_page_config(
    page_title="CrowdRush Live",
    page_icon="CR",
    layout="wide",
    initial_sidebar_state="expanded",
)

st_autorefresh(interval=2500, key="live_refresh")


def inject_css():
    st.markdown(
        """
        <style>
        :root {
            --ink: #1d140f;
            --muted: #6f5f55;
            --line: #efd7bf;
            --accent: #f26a13;
            --accent-deep: #e83f1f;
            --accent-gold: #ffc400;
            --surface: #fff8ed;
        }
        .stApp { background: linear-gradient(180deg, #fffaf2 0%, #fff0d6 58%, #ffe3bd 100%); color: var(--ink); }
        .stApp, .stApp p, .stApp span, .stApp label, .stApp div { color: var(--ink); }
        section[data-testid="stSidebar"] { background: #1b120e; border-right: 1px solid #3b2118; }
        section[data-testid="stSidebar"] * { color: var(--ink); }
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] span,
        section[data-testid="stSidebar"] div {
            color: #fff8ed;
        }
        section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] * { color: #f2c69f; }
        .hero {
            padding: 26px 28px;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: linear-gradient(135deg, #ffffff 0%, #fff7e5 55%, #ffe0a3 100%);
            box-shadow: 0 10px 28px rgba(180, 78, 20, 0.14);
            margin-bottom: 18px;
        }
        .hero h1 { margin: 0 0 8px 0; font-size: 34px; line-height: 1.05; letter-spacing: 0; }
        .hero p { margin: 0; color: var(--muted); font-size: 16px; }
        .metric-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 12px;
            margin: 14px 0 18px 0;
        }
        .pulse-card {
            border: 1px solid var(--line);
            border-radius: 8px;
            background: #fffdf8;
            padding: 16px;
        }
        .big-code {
            font-size: clamp(34px, 7vw, 68px);
            font-weight: 800;
            letter-spacing: 0;
            color: var(--accent-deep);
            line-height: 1;
        }
        .waiting {
            min-height: 260px;
            display: grid;
            place-items: center;
            border: 1px dashed #f29b4b;
            border-radius: 8px;
            background: repeating-linear-gradient(135deg, #fffdf8, #fffdf8 14px, #fff0d3 14px, #fff0d3 28px);
            text-align: center;
        }
        .waiting h2 { margin-bottom: 6px; }
        .badge {
            display: inline-block;
            padding: 8px 10px;
            border-radius: 8px;
            background: #fff2b8;
            border: 1px solid #f6b716;
            color: #5b3100;
            font-weight: 700;
        }
        .phase-pill {
            display: inline-block;
            padding: 6px 10px;
            border-radius: 999px;
            background: #fff0d4;
            color: #b93817;
            font-weight: 700;
            font-size: 13px;
        }
        div[data-testid="stButton"] > button,
        div[data-testid="stFormSubmitButton"] > button {
            border-radius: 8px;
            border: 1px solid var(--accent-deep);
            background: linear-gradient(90deg, var(--accent-deep) 0%, var(--accent) 58%, #f6a111 100%);
            color: #ffffff;
            font-weight: 700;
            min-height: 42px;
            box-shadow: 0 3px 9px rgba(232, 63, 31, 0.22);
        }
        div[data-testid="stButton"] > button *,
        div[data-testid="stFormSubmitButton"] > button * {
            color: #ffffff;
        }
        div[data-testid="stButton"] > button:hover,
        div[data-testid="stFormSubmitButton"] > button:hover {
            border-color: #bf2f17;
            background: linear-gradient(90deg, #cf3418 0%, #e95a13 58%, #ec920b 100%);
            color: #ffffff;
        }
        div[data-testid="stButton"] > button:focus,
        div[data-testid="stFormSubmitButton"] > button:focus {
            color: #ffffff;
            box-shadow: 0 0 0 3px rgba(242, 106, 19, 0.28);
        }
        div[data-testid="stButton"] > button:disabled,
        div[data-testid="stFormSubmitButton"] > button:disabled {
            border-color: #e6cdb6;
            background: #f3e7db;
            color: #8a786a;
            box-shadow: none;
        }
        div[data-testid="stButton"] > button:disabled *,
        div[data-testid="stFormSubmitButton"] > button:disabled * {
            color: #8a786a;
        }
        div[data-testid="stTextInput"] label,
        div[data-testid="stTextArea"] label,
        div[data-testid="stNumberInput"] label,
        div[data-testid="stSelectbox"] label,
        div[data-testid="stRadio"] label {
            color: var(--ink);
            font-weight: 700;
        }
        div[data-testid="stTextInput"] input,
        div[data-testid="stTextArea"] textarea,
        div[data-baseweb="select"] > div,
        div[data-testid="stNumberInput"] input {
            background: #ffffff;
            border-color: #b8c6d1;
            color: var(--ink);
        }
        div[data-testid="stTextInput"] input::placeholder,
        div[data-testid="stTextArea"] textarea::placeholder {
            color: #9a8373;
        }
        button[role="tab"] {
            color: var(--muted);
            background: transparent;
            border-radius: 8px 8px 0 0;
            font-weight: 700;
        }
        button[role="tab"] *,
        button[role="tab"] p {
            color: var(--muted);
        }
        button[role="tab"]:hover,
        button[role="tab"]:hover *,
        button[role="tab"]:hover p {
            color: var(--accent-deep);
        }
        button[role="tab"][aria-selected="true"],
        button[role="tab"][aria-selected="true"] *,
        button[role="tab"][aria-selected="true"] p {
            color: var(--accent-deep);
        }
        div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
            background: linear-gradient(90deg, var(--accent-deep), var(--accent-gold));
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


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


def qr_image(link: str) -> Image.Image:
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(link)
    qr.make(fit=True)
    return qr.make_image(fill_color="#172033", back_color="white").convert("RGB")


def render_header(title: str, subtitle: str):
    st.markdown(f"<div class='hero'><h1>{title}</h1><p>{subtitle}</p></div>", unsafe_allow_html=True)


def render_session_metrics(session: dict, questions: list[dict]):
    phase = session["current_phase"]
    phase_count = len([q for q in questions if q["phase"] == phase])
    st.markdown(
        f"""
        <div class="metric-row">
            <div class="pulse-card"><div class="phase-pill">{PHASE_LABELS[phase]}</div><h3>{session["session_name"]}</h3></div>
            <div class="pulse-card"><div>Room Code</div><div class="big-code">{session["event_code"]}</div></div>
            <div class="pulse-card"><div>Active Question</div><h2>{int(session.get("current_question_index") or 0) + 1 if phase_count else 0} / {phase_count}</h2></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def host_configuration(client: Client):
    st.subheader("Create or load an event")
    notice = st.session_state.pop("host_event_created_notice", None)
    if notice:
        st.success(notice)
    left, right = st.columns(2)
    with left:
        with st.form("create_session"):
            session_name = st.text_input("Configurable Session Name", value="Product Town Hall Live")
            submitted = st.form_submit_button("Create event", help="Click once and wait for the room code to appear.")
        if submitted and session_name.strip():
            status_box = st.empty()
            status_box.info("Creating your event and reserving a 4-digit room code. This can take a few seconds...")
            with st.spinner("Creating event in Supabase..."):
                started = time.perf_counter()
                session = create_session(client, session_name.strip())
                elapsed = time.perf_counter() - started
            status_box.empty()
            if session:
                st.session_state.host_event_code = session["event_code"]
                st.session_state.host_event_created_notice = (
                    f"Event created with code {session['event_code']} in {elapsed:.1f}s."
                )
                st.rerun()
            else:
                st.error("The event was not created. Please check your Supabase connection and try again.")
        elif submitted:
            st.warning("Enter a session name before creating the event.")
    with right:
        code = st.text_input("Load existing 4-digit event code", value=st.session_state.get("host_event_code", ""))
        if st.button("Load event") and code.strip():
            session = get_session_by_code(client, code.strip())
            if session:
                st.session_state.host_event_code = session["event_code"]
                st.rerun()
            else:
                st.warning("No session found for that code.")


def question_builder(client: Client, session: dict):
    st.subheader("Question timeline builder")
    with st.expander("Add a question, poll, icebreaker, or survey item", expanded=True):
        with st.form("add_question"):
            phase = st.selectbox("Timeline", PHASES, format_func=lambda value: PHASE_LABELS[value])
            question_text = st.text_area("Question text", placeholder="What should we ask the room?")
            options_text = st.text_area(
                "Options, one per line. Leave blank for an open-ended response.",
                placeholder="Option A\nOption B\nOption C",
            )
            options = normalize_options(options_text)
            correct = st.selectbox("Correct option for live game", [""] + options, disabled=(phase != "during" or not options))
            weight = st.number_input("Points weight", min_value=0, max_value=5000, value=100, step=25)
            submitted = st.form_submit_button("Add to timeline")
        if submitted:
            if not question_text.strip():
                st.warning("Add question text first.")
            else:
                add_question(client, session["id"], phase, question_text.strip(), options, correct, int(weight))
                st.success("Added.")
                st.rerun()

    questions = get_questions(client, session["id"])
    for phase in PHASES:
        phase_questions = [q for q in questions if q["phase"] == phase]
        st.markdown(f"**{PHASE_LABELS[phase]}**")
        if not phase_questions:
            st.caption("No questions yet.")
        for idx, q in enumerate(phase_questions, start=1):
            options = q.get("options_json") or []
            option_note = "open response" if not options else ", ".join(options)
            st.write(f"{idx}. {q['question_text']} ({option_note})")


def timeline_controls(client: Client, session: dict):
    questions = get_questions(client, session["id"])
    render_session_metrics(session, questions)

    st.subheader("Master timeline control")
    phase_cols = st.columns(3)
    for col, phase in zip(phase_cols, PHASES):
        with col:
            if st.button(PHASE_LABELS[phase], use_container_width=True, disabled=session["current_phase"] == phase):
                set_phase(client, session, phase)
                st.rerun()

    phase = session["current_phase"]
    phase_questions = [q for q in questions if q["phase"] == phase]
    current_index = int(session.get("current_question_index") or 0)
    if phase_questions:
        current_index = min(current_index, len(phase_questions) - 1)
        active = phase_questions[current_index]
        st.info(f"Live now: {active['question_text']}")
        left, mid, right = st.columns(3)
        with left:
            if st.button("Previous question", disabled=current_index <= 0, use_container_width=True):
                activate_question(client, session, phase, current_index - 1)
                st.rerun()
        with mid:
            if st.button("Open / restart timer", use_container_width=True):
                activate_question(client, session, phase, current_index)
                st.rerun()
        with right:
            if st.button("Next question", disabled=current_index >= len(phase_questions) - 1, use_container_width=True):
                activate_question(client, session, phase, current_index + 1)
                st.rerun()
        if phase == "during":
            frozen = not bool(session.get("question_start_time"))
            label = "Responses frozen" if frozen else "Freeze responses and show leaderboard"
            if st.button(label, disabled=frozen, use_container_width=True):
                freeze_question(client, session)
                st.rerun()
    else:
        st.warning("This phase has no questions yet.")


def host_qr_panel(session: dict):
    st.subheader("QR room access")
    default_url = st.session_state.get("public_app_url", "http://localhost:8501")
    public_url = st.text_input("Your-App-URL", value=default_url, key="public_app_url")
    join_link = f"{public_url.rstrip('/')}/?room={session['event_code']}"
    st.code(join_link)
    st.image(qr_image(join_link), caption="Scan to join instantly", width=230)


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
        st.dataframe(df[["player_name", "selected_option"]].rename(columns={"selected_option": "response"}), use_container_width=True)


def host_analytics(client: Client, session: dict):
    st.subheader("Real-time analytics")
    question = get_active_question(client, session)
    if not question:
        st.caption("No active question selected.")
        return

    responses = get_responses(client, question["id"])
    st.write(f"Submission progress: **{len(responses)}** responses")

    if session["current_phase"] in ("pre", "post"):
        chart_responses(client, question)
        return

    correct = [r for r in responses if r.get("is_correct")]
    fastest = sorted(correct, key=lambda r: int(r.get("response_time_ms") or 999999999))[:1]
    if fastest:
        st.markdown(
            f"<span class='badge'>Fastest Finger: {fastest[0]['player_name']} at {fastest[0]['response_time_ms']} ms</span>",
            unsafe_allow_html=True,
        )
    else:
        st.caption("No correct answers yet.")

    scores = get_scores(client, session["id"], limit=5)
    if scores:
        st.dataframe(
            pd.DataFrame(scores)[["player_name", "total_score"]].rename(
                columns={"player_name": "Player", "total_score": "Score"}
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("Leaderboard will appear after the first scored answer.")


def host_view(client: Client):
    render_header("CrowdRush Live Host", "Run polls, live game rounds, and post-event feedback from one synchronized dashboard.")
    host_configuration(client)
    code = st.session_state.get("host_event_code")
    if not code:
        return
    session = get_session_by_code(client, code)
    if not session:
        st.warning("The selected event code no longer exists.")
        return

    tabs = st.tabs(["Control", "Configure", "Access", "Analytics"])
    with tabs[0]:
        timeline_controls(client, session)
    with tabs[1]:
        question_builder(client, session)
    with tabs[2]:
        host_qr_panel(session)
    with tabs[3]:
        host_analytics(client, session)


def get_query_room() -> str:
    try:
        value = st.query_params.get("room")
    except Exception:
        value = None
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""


def audience_join(client: Client) -> dict | None:
    query_room = get_query_room()
    if query_room and not st.session_state.get("audience_event_code"):
        st.session_state.audience_event_code = query_room

    code = st.session_state.get("audience_event_code", "")
    if not code:
        render_header("Join CrowdRush", "Enter the room code from the screen or scan the host QR code.")
        code = st.text_input("Room code", max_chars=4)
        if st.button("Join room", disabled=len(code.strip()) != 4):
            st.session_state.audience_event_code = code.strip()
            st.rerun()
        return None

    session = get_session_by_code(client, code)
    if not session:
        st.warning("That room code is not active.")
        if st.button("Choose another room"):
            st.session_state.pop("audience_event_code", None)
            st.rerun()
        return None

    player_key = f"player_name_{session['event_code']}"
    if not st.session_state.get(player_key):
        render_header(session["session_name"], f"Room {session['event_code']} is ready. Pick your player name.")
        name = st.text_input("Player Name", max_chars=36)
        if st.button("Enter session", disabled=not name.strip()):
            st.session_state[player_key] = name.strip()
            ensure_player_score(client, session["id"], name.strip())
            st.rerun()
        return None

    st.session_state.player_name = st.session_state[player_key]
    return session


def waiting_graphic(text: str = "Waiting for host..."):
    st.markdown(
        f"""
        <div class="waiting">
            <div>
                <h2>{text}</h2>
                <p>The screen will update automatically when the next moment opens.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def answer_options(question: dict) -> list[str]:
    options = question.get("options_json") or []
    return options if isinstance(options, list) else []


def audience_question(client: Client, session: dict, question: dict, player_name: str):
    st.markdown(f"<div class='phase-pill'>{PHASE_LABELS[session['current_phase']]}</div>", unsafe_allow_html=True)
    st.header(question["question_text"])

    existing = get_existing_response(client, question["id"], player_name)
    if existing:
        if session["current_phase"] == "during":
            if existing["is_correct"]:
                st.success(f"Locked in. Correct in {existing['response_time_ms']} ms.")
            else:
                st.info("Locked in. Waiting for the host to move on.")
        else:
            st.success("Response received.")
        waiting_graphic("Waiting for the next prompt...")
        return

    options = answer_options(question)
    start_ms = parse_epoch_ms(session.get("question_start_time"))
    if options:
        selected = st.radio("Choose one", options, index=None)
        disabled = selected is None
    else:
        selected = st.text_area("Your response")
        disabled = not selected.strip()

    if st.button("Submit", disabled=disabled, use_container_width=True):
        click_ms = now_ms()
        response_time = max(0, click_ms - start_ms) if session["current_phase"] == "during" else 0
        submit_response(client, session, question, player_name, selected.strip() if isinstance(selected, str) else selected, response_time)
        st.rerun()


def audience_view(client: Client):
    session = audience_join(client)
    if not session:
        return

    player_name = st.session_state.player_name
    render_header(session["session_name"], f"{player_name}, you are in room {session['event_code']}.")
    question = get_active_question(client, session)
    if not question:
        waiting_graphic()
        return

    if session["current_phase"] == "during" and not session.get("question_start_time"):
        waiting_graphic("Game round is almost ready...")
        return

    audience_question(client, session, question, player_name)


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

    st.sidebar.title("CrowdRush Live")
    role = st.sidebar.radio("Role", ["Speaker (Host)", "Audience Participant"])
    st.sidebar.caption("Auto-refresh is active every 2.5 seconds for shared live state.")

    if role == "Speaker (Host)":
        host_view(client)
    else:
        audience_view(client)


if __name__ == "__main__":
    main()
