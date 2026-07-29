insert into public.stores (
    id,
    name,
    hours,
    description,
    recommendation_keywords
)
values (
    '11111111-1111-4111-8111-111111111111',
    '라 테라짜 키친',
    '평일 11:30 - 22:00',
    '테라스가 있는 양식 레스토랑',
    '["#스트레스", "#해장", "#혼밥", "#가성비", "#회식", "#매운맛", "#달콤한", "#국물"]'::jsonb
)
on conflict (id) do update set
    name = excluded.name,
    hours = excluded.hours,
    description = excluded.description,
    recommendation_keywords = excluded.recommendation_keywords;

insert into public.menus (
    id,
    store_id,
    name,
    price,
    currency,
    description,
    tags,
    image_url,
    is_sold_out
)
values
(
    '22222222-2222-4222-8222-222222222221',
    '11111111-1111-4111-8111-111111111111',
    '{"ko":"햄버거 (Hamburger)","en":"햄버거 (Hamburger)","vi":"햄버거 (Hamburger)"}'::jsonb,
    8,
    'USD',
    '{"ko":"육즙 가득한 프리미엄 수제 햄버거","en":"육즙 가득한 프리미엄 수제 햄버거","vi":"육즙 가득한 프리미엄 수제 햄버거"}'::jsonb,
    '[{"ko":"#수제","en":"#수제","vi":"#수제"},{"ko":"#든든한","en":"#든든한","vi":"#든든한"}]'::jsonb,
    'https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=150&q=80',
    false
),
(
    '22222222-2222-4222-8222-222222222222',
    '11111111-1111-4111-8111-111111111111',
    '{"ko":"치킨 (Fried Chicken)","en":"치킨 (Fried Chicken)","vi":"치킨 (Fried Chicken)"}'::jsonb,
    18000,
    'KRW',
    '{"ko":"바삭바삭한 황금빛 후라이드 치킨","en":"바삭바삭한 황금빛 후라이드 치킨","vi":"바삭바삭한 황금빛 후라이드 치킨"}'::jsonb,
    '[{"ko":"#바삭한","en":"#바삭한","vi":"#바삭한"},{"ko":"#야식","en":"#야식","vi":"#야식"}]'::jsonb,
    'https://images.unsplash.com/photo-1564834724105-918b73d1b9e0?w=150&q=80',
    false
)
on conflict (id) do update set
    name = excluded.name,
    price = excluded.price,
    currency = excluded.currency,
    description = excluded.description,
    tags = excluded.tags,
    image_url = excluded.image_url,
    is_sold_out = excluded.is_sold_out;

insert into public.tables (
    store_id,
    table_code,
    x,
    y,
    status,
    view_name,
    tag,
    capacity,
    sort_order
)
values
('11111111-1111-4111-8111-111111111111', 'T1', 12, 35, 'available', '창가', '창가', 4, 1),
('11111111-1111-4111-8111-111111111111', 'T2', 28, 35, 'occupied', '창가', '창가', 4, 2),
('11111111-1111-4111-8111-111111111111', 'T3', 40, 35, 'available', '실내', '', 4, 3),
('11111111-1111-4111-8111-111111111111', 'T4', 55, 45, 'reserved', '실내', '', 4, 4),
('11111111-1111-4111-8111-111111111111', 'T5', 70, 45, 'soon', '실내', '', 4, 5),
('11111111-1111-4111-8111-111111111111', 'T6', 12, 75, 'available', '창가', '창가', 4, 6),
('11111111-1111-4111-8111-111111111111', 'T7', 28, 75, 'occupied', '창가', '창가', 4, 7),
('11111111-1111-4111-8111-111111111111', 'T8', 43, 75, 'available', '실내', '인기', 4, 8),
('11111111-1111-4111-8111-111111111111', 'T9', 70, 75, 'available', '창가', '창가', 4, 9),
('11111111-1111-4111-8111-111111111111', 'T10', 75, 25, 'available', '테라스', '', 4, 10),
('11111111-1111-4111-8111-111111111111', 'T11', 88, 25, 'reserved', '테라스', '', 4, 11),
('11111111-1111-4111-8111-111111111111', 'T12', 78, 55, 'available', '테라스', '인기', 4, 12),
('11111111-1111-4111-8111-111111111111', 'T13', 75, 80, 'soon', '테라스', '', 4, 13),
('11111111-1111-4111-8111-111111111111', 'T14', 88, 80, 'available', '테라스', '', 4, 14)
on conflict (store_id, table_code) do update set
    x = excluded.x,
    y = excluded.y,
    status = excluded.status,
    view_name = excluded.view_name,
    tag = excluded.tag,
    capacity = excluded.capacity,
    sort_order = excluded.sort_order;
