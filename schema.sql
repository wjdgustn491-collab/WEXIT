create extension if not exists pgcrypto;
create extension if not exists vector;

create table if not exists public.stores (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    name_en text,
    name_vi text,
    hours text,
    hours_en text,
    hours_vi text,
    description text,
    description_en text,
    description_vi text,
    recommendation_keywords jsonb not null default '[]'::jsonb,
    menu_categories jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.menus (
    id uuid primary key default gen_random_uuid(),
    store_id uuid not null references public.stores(id) on delete cascade,
    name jsonb not null,
    price numeric not null check (price >= 0),
    currency text not null,
    description jsonb not null,
    category text not null default '',
    tags jsonb not null default '[]'::jsonb,
    image_data text,
    image_url text,
    is_sold_out boolean not null default false,
    embedding vector(1536),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.tables (
    id uuid primary key default gen_random_uuid(),
    store_id uuid not null references public.stores(id) on delete cascade,
    table_code text not null,
    x numeric not null check (x between 0 and 100),
    y numeric not null check (y between 0 and 100),
    status text not null check (
        status in ('available', 'soon', 'reserved', 'occupied')
    ),
    view_name text not null default '',
    tag text not null default '',
    capacity integer not null default 4 check (capacity between 1 and 50),
    table_image text,
    view_image text,
    sort_order integer not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (store_id, table_code)
);

create table if not exists public.orders (
    id uuid primary key default gen_random_uuid(),
    store_id uuid not null references public.stores(id) on delete cascade,
    table_id text not null,
    menu_id uuid not null references public.menus(id) on delete restrict,
    menu_name text not null,
    quantity integer not null check (quantity >= 1),
    total_price numeric not null check (total_price >= 0),
    currency text not null,
    status text not null default 'pending' check (
        status in ('pending', 'completed', 'cancelled')
    ),
    customer_session_id text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.reservations (
    id uuid primary key default gen_random_uuid(),
    store_id uuid not null references public.stores(id) on delete cascade,
    table_id text not null,
    status text not null check (
        status in ('reserved', 'waiting', 'accepted', 'cancelled')
    ),
    customer_session_id text not null,
    party_size integer not null default 1 check (party_size between 1 and 4),
    estimated_wait_minutes integer not null default 0 check (
        estimated_wait_minutes between 0 and 1440
    ),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.reviews (
    id uuid primary key default gen_random_uuid(),
    store_id uuid not null references public.stores(id) on delete cascade,
    rating numeric(2, 1) not null check (
        rating between 0.5 and 5 and mod(rating * 2, 1) = 0
    ),
    review_text text not null check (char_length(review_text) between 1 and 500),
    image_data text,
    reply text,
    customer_session_id text not null,
    created_at timestamptz not null default now()
);

-- Keep this file safe to re-run against databases created by an earlier release.
alter table public.stores add column if not exists name_en text;
alter table public.stores add column if not exists name_vi text;
alter table public.stores add column if not exists hours_en text;
alter table public.stores add column if not exists hours_vi text;
alter table public.stores add column if not exists description_en text;
alter table public.stores add column if not exists description_vi text;
alter table public.stores add column if not exists menu_categories jsonb not null default '[]'::jsonb;
alter table public.menus add column if not exists category text not null default '';
alter table public.tables add column if not exists table_image text;
alter table public.tables add column if not exists view_image text;
alter table public.reviews add column if not exists reply text;
alter table public.reviews drop constraint if exists reviews_review_text_check;
alter table public.reviews add constraint reviews_review_text_check check (
    char_length(review_text) between 1 and 500
) not valid;
alter table public.reviews drop constraint if exists reviews_rating_check;
alter table public.reviews alter column rating type numeric(2, 1)
    using rating::numeric;
alter table public.reviews add constraint reviews_rating_check check (
    rating between 0.5 and 5 and mod(rating * 2, 1) = 0
);
alter table public.reservations alter column party_size set default 1;
alter table public.reservations add column if not exists estimated_wait_minutes
    integer not null default 0;
alter table public.reservations drop constraint if exists reservations_estimated_wait_minutes_check;
alter table public.reservations add constraint reservations_estimated_wait_minutes_check check (
    estimated_wait_minutes between 0 and 1440
);
update public.reservations
set party_size = greatest(1, least(4, party_size))
where party_size not between 1 and 4;
alter table public.reservations drop constraint if exists reservations_party_size_check;
alter table public.reservations add constraint reservations_party_size_check check (
    party_size between 1 and 4
);
update public.reservations reservation
set status = 'cancelled'
where reservation.status in ('reserved', 'waiting', 'accepted')
  and exists (
      select 1
      from public.tables table_item
      where table_item.store_id = reservation.store_id
        and table_item.table_code = reservation.table_id
        and table_item.status = 'available'
  );

create index if not exists menus_store_id_idx
    on public.menus(store_id);
create index if not exists tables_store_sort_idx
    on public.tables(store_id, sort_order);
create index if not exists orders_store_created_idx
    on public.orders(store_id, created_at desc);
create index if not exists orders_customer_session_idx
    on public.orders(store_id, customer_session_id, created_at desc);
create index if not exists reservations_store_created_idx
    on public.reservations(store_id, created_at desc);
create index if not exists reservations_customer_session_idx
    on public.reservations(store_id, customer_session_id, created_at desc);
create index if not exists reservations_waiting_idx
    on public.reservations(store_id, status)
    where status = 'waiting';
create index if not exists reviews_store_created_idx
    on public.reviews(store_id, created_at desc);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists stores_set_updated_at on public.stores;
create trigger stores_set_updated_at
before update on public.stores
for each row execute function public.set_updated_at();

drop trigger if exists menus_set_updated_at on public.menus;
create trigger menus_set_updated_at
before update on public.menus
for each row execute function public.set_updated_at();

drop trigger if exists tables_set_updated_at on public.tables;
create trigger tables_set_updated_at
before update on public.tables
for each row execute function public.set_updated_at();

drop trigger if exists orders_set_updated_at on public.orders;
create trigger orders_set_updated_at
before update on public.orders
for each row execute function public.set_updated_at();

drop trigger if exists reservations_set_updated_at on public.reservations;
create trigger reservations_set_updated_at
before update on public.reservations
for each row execute function public.set_updated_at();

create or replace function public.replace_store_tables(
    p_store_id uuid,
    p_tables jsonb
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    if jsonb_typeof(p_tables) <> 'array' then
        raise exception 'p_tables must be a JSON array';
    end if;

    if exists (
        select 1
        from jsonb_array_elements(p_tables) item
        group by upper(trim(item->>'table_code'))
        having count(*) > 1
    ) then
        raise exception 'duplicate table_code';
    end if;

    -- Treat an explicit admin change back to available as releasing the table.
    update public.reservations reservation
    set status = 'cancelled'
    where reservation.store_id = p_store_id
      and reservation.status in ('reserved', 'waiting', 'accepted')
      and exists (
          select 1
          from public.tables current_table
          join jsonb_array_elements(p_tables) item
            on upper(trim(item->>'table_code')) = current_table.table_code
          where current_table.store_id = p_store_id
            and current_table.table_code = reservation.table_id
            and item->>'status' = 'available'
      );

    delete from public.tables
    where store_id = p_store_id
      and table_code not in (
          select upper(trim(item->>'table_code'))
          from jsonb_array_elements(p_tables) item
      );

    insert into public.tables (
        store_id,
        table_code,
        x,
        y,
        status,
        view_name,
        tag,
        capacity,
        table_image,
        view_image,
        sort_order
    )
    select
        p_store_id,
        upper(trim(item->>'table_code')),
        (item->>'x')::numeric,
        (item->>'y')::numeric,
        item->>'status',
        coalesce(item->>'view_name', ''),
        coalesce(item->>'tag', ''),
        coalesce((item->>'capacity')::integer, 4),
        nullif(item->>'table_image', ''),
        nullif(item->>'view_image', ''),
        coalesce((item->>'sort_order')::integer, 0)
    from jsonb_array_elements(p_tables) item
    on conflict (store_id, table_code)
    do update set
        x = excluded.x,
        y = excluded.y,
        status = excluded.status,
        view_name = excluded.view_name,
        tag = excluded.tag,
        capacity = excluded.capacity,
        table_image = excluded.table_image,
        view_image = excluded.view_image,
        sort_order = excluded.sort_order,
        updated_at = now();
end;
$$;

create or replace function public.create_reservation_and_table(
    p_store_id uuid,
    p_table_code text,
    p_customer_session_id text,
    p_party_size integer
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_table public.tables%rowtype;
    v_reservation public.reservations%rowtype;
    v_status text;
begin
    select *
    into v_table
    from public.tables
    where store_id = p_store_id
      and table_code = upper(trim(p_table_code))
    for update;

    if not found then
        raise exception 'table not found';
    end if;

    if p_party_size < 1 or p_party_size > least(4, v_table.capacity) then
        raise exception 'invalid party size';
    end if;

    if v_table.status = 'available' then
        -- The table status is the source of truth. If an administrator released
        -- the table, retire stale booking rows before creating the new booking.
        update public.reservations
        set status = 'cancelled'
        where store_id = p_store_id
          and table_id = v_table.table_code
          and status in ('reserved', 'waiting', 'accepted');
        v_status := 'reserved';
    else
        v_status := 'waiting';
    end if;

    if v_status = 'waiting' then
        select *
        into v_reservation
        from public.reservations
        where store_id = p_store_id
          and table_id = v_table.table_code
          and customer_session_id = p_customer_session_id
          and status in ('reserved', 'waiting', 'accepted')
        order by created_at desc
        limit 1;

        if found then
            return to_jsonb(v_reservation);
        end if;
    end if;

    insert into public.reservations (
        store_id, table_id, status, customer_session_id, party_size
    ) values (
        p_store_id,
        v_table.table_code,
        v_status,
        p_customer_session_id,
        p_party_size
    ) returning * into v_reservation;

    if v_status = 'reserved' then
        update public.tables
        set status = 'reserved'
        where id = v_table.id;
    end if;

    return to_jsonb(v_reservation);
end;
$$;

create or replace function public.update_reservation_and_table(
    p_store_id uuid,
    p_reservation_id uuid,
    p_status text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_reservation public.reservations%rowtype;
begin
    if p_status not in ('accepted', 'cancelled') then
        raise exception 'invalid reservation status';
    end if;

    select *
    into v_reservation
    from public.reservations
    where id = p_reservation_id
      and store_id = p_store_id
    for update;

    if not found then
        raise exception 'reservation not found';
    end if;

    update public.reservations
    set status = p_status
    where id = p_reservation_id
    returning * into v_reservation;

    if p_status = 'accepted' then
        update public.tables
        set status = 'reserved'
        where store_id = p_store_id
          and table_code = v_reservation.table_id;
    elsif not exists (
        select 1
        from public.reservations
        where store_id = p_store_id
          and table_id = v_reservation.table_id
          and status in ('reserved', 'waiting', 'accepted')
    ) then
        update public.tables
        set status = 'available'
        where store_id = p_store_id
          and table_code = v_reservation.table_id;
    end if;

    return to_jsonb(v_reservation);
end;
$$;

create or replace function public.clear_store_reservations(
    p_store_id uuid
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
    v_deleted_count integer := 0;
    v_table_codes text[];
begin
    with deleted as (
        delete from public.reservations
        where store_id = p_store_id
        returning table_id
    )
    select count(*)::integer, array_agg(distinct table_id)
    into v_deleted_count, v_table_codes
    from deleted;

    if v_table_codes is not null then
        update public.tables
        set status = 'available'
        where store_id = p_store_id
          and status = 'reserved'
          and table_code = any(v_table_codes);
    end if;

    return v_deleted_count;
end;
$$;

alter table public.stores enable row level security;
alter table public.menus enable row level security;
alter table public.tables enable row level security;
alter table public.orders enable row level security;
alter table public.reservations enable row level security;
alter table public.reviews enable row level security;

-- No browser-facing policies are created. The Python API uses the server-only
-- Supabase service role key and is the sole data access layer for this release.
