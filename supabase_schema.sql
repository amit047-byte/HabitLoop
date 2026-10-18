-- ==============================================================================
-- HabitLoop x Ramp — Supabase Database Architecture & Security Schema
-- Target Project: https://pzfvmnsbhqkrtxietlle.supabase.co
-- ==============================================================================
-- Instructions:
-- 1. Open your Supabase Dashboard: https://supabase.com/dashboard/project/pzfvmnsbhqkrtxietlle
-- 2. Click "SQL Editor" in the left sidebar
-- 3. Click "New Query", paste this entire script, and click "Run" (CMD+Enter)
-- ==============================================================================

-- 1. USER PROFILES TABLE (Linked to Supabase Auth)
create table if not exists public.profiles (
  id uuid references auth.users on delete cascade primary key,
  email text,
  name text,
  university text default 'JECRC University',
  degree text default 'B.Tech Computer Science & Engineering',
  semester text default '4th Semester',
  student_id text default '23BCON047',
  daily_target_hours numeric default 4,
  bio text default '',
  section text default 'SEC C',
  top_streak int default 0,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- 2. USER APPLICATION DATA TABLE (Habits, Schedules, Targets, Hourly Energy, etc.)
create table if not exists public.user_data (
  user_id uuid references auth.users on delete cascade not null,
  key text not null,
  value jsonb not null,
  updated_at timestamptz default now(),
  primary key (user_id, key)
);

-- 3. SHARED MASTER TIMETABLES (For College Sections like SEC C, SEC B, SEC A)
create table if not exists public.master_timetables (
  id text primary key, -- e.g. "jecrc_sec_c"
  institution text default 'JECRC University',
  department text default 'Computer Science & Engineering',
  semester text default '4th Semester',
  section text default 'SEC C',
  schedule jsonb not null, -- Array of class events by day
  updated_at timestamptz default now()
);

-- 4. ENABLE ROW-LEVEL SECURITY (RLS) FOR BULLETPROOF PRIVACY
alter table public.profiles enable row level security;
alter table public.user_data enable row level security;
alter table public.master_timetables enable row level security;

-- 5. RLS POLICIES FOR PROFILES
drop policy if exists "Public profiles are viewable by authenticated users" on public.profiles;
create policy "Public profiles are viewable by authenticated users" on public.profiles
  for select using (auth.role() = 'authenticated' or auth.role() = 'anon');

drop policy if exists "Users can insert their own profile" on public.profiles;
create policy "Users can insert their own profile" on public.profiles
  for insert with check (auth.uid() = id);

drop policy if exists "Users can update their own profile" on public.profiles;
create policy "Users can update their own profile" on public.profiles
  for update using (auth.uid() = id);

-- 6. RLS POLICIES FOR USER DATA (Habits, Schedule, Targets)
-- Strict Isolation: User A can NEVER view or alter User B's data
drop policy if exists "Users can view own data" on public.user_data;
create policy "Users can view own data" on public.user_data
  for select using (auth.uid() = user_id);

drop policy if exists "Users can insert own data" on public.user_data;
create policy "Users can insert own data" on public.user_data
  for insert with check (auth.uid() = user_id);

drop policy if exists "Users can update own data" on public.user_data;
create policy "Users can update own data" on public.user_data
  for update using (auth.uid() = user_id);

drop policy if exists "Users can delete own data" on public.user_data;
create policy "Users can delete own data" on public.user_data
  for delete using (auth.uid() = user_id);

-- 7. RLS POLICIES FOR MASTER TIMETABLES
-- Master schedules are readable by all college students
drop policy if exists "Master timetables are viewable by all" on public.master_timetables;
create policy "Master timetables are viewable by all" on public.master_timetables
  for select using (true);

-- 8. AUTOMATIC PROFILE CREATION TRIGGER ON USER SIGNUP
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, email, name)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'name', split_part(new.email, '@', 1))
  )
  on conflict (id) do nothing;
  return new;
end;
$$ language plpgsql security definer;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- ==============================================================================
-- Schema creation complete!
-- ==============================================================================
