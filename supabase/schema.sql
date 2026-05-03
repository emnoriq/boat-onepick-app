-- ボートレース三連複1点アプリ Supabase スキーマ

create extension if not exists "uuid-ossp";

-- レーステーブル
create table if not exists races (
  id          uuid primary key default uuid_generate_v4(),
  race_date   date        not null,
  stadium     text        not null,
  race_no     integer     not null,
  close_time  timestamptz not null,
  status      text        not null default 'scheduled',  -- scheduled / final / finished
  created_at  timestamp   not null default now(),
  updated_at  timestamp   not null default now(),
  constraint races_status_check check (status in ('scheduled', 'final', 'finished')),
  constraint races_race_no_check check (race_no between 1 and 12),
  unique (race_date, stadium, race_no)
);

-- 出走表・展示テーブル
create table if not exists entries (
  id                 uuid    primary key default uuid_generate_v4(),
  race_id            uuid    not null references races(id) on delete cascade,
  lane               integer not null,
  racer_name         text    not null,
  racer_class        text,
  national_win_rate  numeric(4,2),
  local_win_rate     numeric(4,2),
  motor_rate         numeric(4,2),
  boat_rate          numeric(4,2),
  avg_st             numeric(5,3),
  exhibition_time    numeric(5,2),
  exhibition_st      numeric(5,3),
  approach_lane      integer,
  entry_score        numeric(5,2),
  constraint entries_lane_check check (lane between 1 and 6),
  unique (race_id, lane)
);

-- 予想テーブル
create table if not exists predictions (
  id          uuid    primary key default uuid_generate_v4(),
  race_id     uuid    not null references races(id) on delete cascade,
  pick        text    not null,         -- 例: "1-2-4"
  confidence  numeric(5,2) not null,
  decision    text    not null,         -- buy / candidate / skip
  reason      text,
  rank_today  integer,
  is_hit      boolean,
  created_at  timestamp not null default now(),
  constraint predictions_decision_check check (decision in ('buy', 'candidate', 'skip')),
  unique (race_id)
);

-- 結果テーブル
create table if not exists results (
  id              uuid    primary key default uuid_generate_v4(),
  race_id         uuid    not null references races(id) on delete cascade,
  trifecta_result text,               -- 例: "2-4-1"
  payout          integer,
  popularity      integer,
  prediction_hit  boolean,
  created_at      timestamp not null default now(),
  unique (race_id)
);

-- updated_at 自動更新トリガー
create or replace function update_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger races_updated_at
  before update on races
  for each row execute function update_updated_at();

-- インデックス
create index idx_races_date       on races(race_date);
create index idx_races_status     on races(status);
create index idx_entries_race_id  on entries(race_id);
create index idx_predictions_race on predictions(race_id);
create index idx_results_race     on results(race_id);

-- Row Level Security (読み取りは全員許可、書き込みはサービスロールのみ)
alter table races       enable row level security;
alter table entries     enable row level security;
alter table predictions enable row level security;
alter table results     enable row level security;

create policy "public read races"       on races       for select using (true);
create policy "public read entries"     on entries     for select using (true);
create policy "public read predictions" on predictions for select using (true);
create policy "public read results"     on results     for select using (true);
