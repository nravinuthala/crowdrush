-- ============================================================
-- Career Shaper™ CrowdRush  –  Supabase Schema  v4
-- Run this in the Supabase SQL editor before launching the app.
-- ============================================================

create extension if not exists "pgcrypto";

-- Sessions
create table if not exists public.sessions (
    id                    uuid primary key default gen_random_uuid(),
    session_name          text not null,
    event_code            text not null unique check (event_code ~ '^[0-9]{4}$'),
    current_phase         text not null default 'lobby',
    current_question_index integer not null default -1,
    question_start_time   timestamptz,
    game_id               text,
    created_at            timestamptz not null default now()
);

-- Questions
create table if not exists public.questions (
    id             uuid primary key default gen_random_uuid(),
    session_id     uuid not null references public.sessions(id) on delete cascade,
    phase          text not null check (phase in ('pre','during','post')),
    question_text  text not null,
    options_json   jsonb not null default '[]'::jsonb,
    correct_option text,
    points_weight  integer not null default 100,
    created_at     timestamptz not null default now()
);

-- Player scores (correct_count added for grouped results)
create table if not exists public.player_scores (
    id            uuid primary key default gen_random_uuid(),
    session_id    uuid not null references public.sessions(id) on delete cascade,
    player_name   text not null,
    total_score   integer not null default 0,
    correct_count integer not null default 0,
    created_at    timestamptz not null default now(),
    unique (session_id, player_name)
);

-- Responses (unique constraint = safe upsert, no double-submit)
create table if not exists public.responses (
    id               uuid primary key default gen_random_uuid(),
    question_id      uuid not null references public.questions(id) on delete cascade,
    player_name      text not null,
    selected_option  text not null,
    is_correct       boolean not null default false,
    response_time_ms integer not null default 0,
    created_at       timestamptz not null default now(),
    unique (question_id, player_name)
);

-- Indexes
create index if not exists idx_q_session_phase   on public.questions(session_id, phase);
create index if not exists idx_scores_session    on public.player_scores(session_id, total_score desc);
create index if not exists idx_resp_question     on public.responses(question_id, response_time_ms asc);
create index if not exists idx_resp_player       on public.responses(question_id, player_name);

-- RLS (open for demo; restrict per-user for production)
alter table public.sessions      enable row level security;
alter table public.questions     enable row level security;
alter table public.player_scores enable row level security;
alter table public.responses     enable row level security;

do $$ begin
  drop policy if exists "cr_sessions_r"  on public.sessions;
  drop policy if exists "cr_sessions_w"  on public.sessions;
  drop policy if exists "cr_questions_r" on public.questions;
  drop policy if exists "cr_questions_w" on public.questions;
  drop policy if exists "cr_scores_r"    on public.player_scores;
  drop policy if exists "cr_scores_w"    on public.player_scores;
  drop policy if exists "cr_responses_r" on public.responses;
  drop policy if exists "cr_responses_w" on public.responses;
end $$;

create policy "cr_sessions_r"  on public.sessions      for select using (true);
create policy "cr_sessions_w"  on public.sessions      for all    with check (true);
create policy "cr_questions_r" on public.questions     for select using (true);
create policy "cr_questions_w" on public.questions     for all    with check (true);
create policy "cr_scores_r"    on public.player_scores for select using (true);
create policy "cr_scores_w"    on public.player_scores for all    with check (true);
create policy "cr_responses_r" on public.responses     for select using (true);
create policy "cr_responses_w" on public.responses     for all    with check (true);
