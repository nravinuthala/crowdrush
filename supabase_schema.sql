-- Run this in the Supabase SQL editor before launching the Streamlit app.
-- The app expects SUPABASE_URL and SUPABASE_KEY in Streamlit secrets or environment variables.

create extension if not exists "pgcrypto";

create table if not exists public.sessions (
    id uuid primary key default gen_random_uuid(),
    session_name text not null,
    event_code text not null unique check (event_code ~ '^[0-9]{4}$'),
    current_phase text not null default 'pre' check (current_phase in ('pre', 'during', 'post')),
    current_question_index integer not null default 0,
    question_start_time timestamptz
);

create table if not exists public.questions (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null references public.sessions(id) on delete cascade,
    phase text not null check (phase in ('pre', 'during', 'post')),
    question_text text not null,
    options_json jsonb not null default '[]'::jsonb,
    correct_option text,
    points_weight integer not null default 100,
    created_at timestamptz not null default now()
);

create table if not exists public.player_scores (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null references public.sessions(id) on delete cascade,
    player_name text not null,
    total_score integer not null default 0,
    unique (session_id, player_name)
);

create table if not exists public.responses (
    id uuid primary key default gen_random_uuid(),
    question_id uuid not null references public.questions(id) on delete cascade,
    player_name text not null,
    selected_option text not null,
    is_correct boolean not null default false,
    response_time_ms integer not null default 0,
    created_at timestamptz not null default now(),
    unique (question_id, player_name)
);

create index if not exists idx_questions_session_phase on public.questions(session_id, phase);
create index if not exists idx_scores_session_score on public.player_scores(session_id, total_score desc);
create index if not exists idx_responses_question_time on public.responses(question_id, response_time_ms asc);

-- Demo-friendly policies. For production, replace these with authenticated role policies.
alter table public.sessions enable row level security;
alter table public.questions enable row level security;
alter table public.player_scores enable row level security;
alter table public.responses enable row level security;

drop policy if exists "demo read sessions" on public.sessions;
drop policy if exists "demo write sessions" on public.sessions;
drop policy if exists "demo read questions" on public.questions;
drop policy if exists "demo write questions" on public.questions;
drop policy if exists "demo read scores" on public.player_scores;
drop policy if exists "demo write scores" on public.player_scores;
drop policy if exists "demo read responses" on public.responses;
drop policy if exists "demo write responses" on public.responses;

create policy "demo read sessions" on public.sessions for select using (true);
create policy "demo write sessions" on public.sessions for all with check (true);
create policy "demo read questions" on public.questions for select using (true);
create policy "demo write questions" on public.questions for all with check (true);
create policy "demo read scores" on public.player_scores for select using (true);
create policy "demo write scores" on public.player_scores for all with check (true);
create policy "demo read responses" on public.responses for select using (true);
create policy "demo write responses" on public.responses for all with check (true);
