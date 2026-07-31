insert into public.stores (
    id,
    name,
    name_en,
    name_vi,
    hours,
    hours_en,
    hours_vi,
    description,
    description_en,
    description_vi,
    recommendation_keywords
)
values (
    '11111111-1111-4111-8111-111111111111',
    '라 테라짜 키친',
    'La Terrazza Kitchen',
    'Nhà hàng La Terrazza',
    '평일 11:30 - 22:00',
    'Weekdays 11:30 - 22:00',
    'Các ngày trong tuần 11:30 - 22:00',
    '테라스가 있는 양식 레스토랑',
    'A Western restaurant with a terrace',
    'Nhà hàng món Âu có sân hiên',
    '["#스트레스", "#해장", "#혼밥", "#가성비", "#회식", "#매운맛", "#달콤한", "#국물"]'::jsonb
)
on conflict (id) do update set
    name = excluded.name,
    name_en = excluded.name_en,
    name_vi = excluded.name_vi,
    hours = excluded.hours,
    hours_en = excluded.hours_en,
    hours_vi = excluded.hours_vi,
    description = excluded.description,
    description_en = excluded.description_en,
    description_vi = excluded.description_vi,
    recommendation_keywords = excluded.recommendation_keywords;

-- Remove the retired default menu item while preserving manager-created menus.
delete from public.menus
where id = '22222222-2222-4222-8222-222222222221';

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
    '22222222-2222-4222-8222-222222222222',
    '11111111-1111-4111-8111-111111111111',
    '{"ko":"후라이드 치킨","en":"Fried Chicken","vi":"Gà rán"}'::jsonb,
    18000,
    'KRW',
    '{"ko":"바삭바삭한 황금빛 후라이드 치킨","en":"Crispy golden fried chicken","vi":"Gà rán vàng giòn"}'::jsonb,
    '[{"ko":"#바삭한","en":"#crispy","vi":"#giòn"},{"ko":"#야식","en":"#late-night","vi":"#ăn-khuya"}]'::jsonb,
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
