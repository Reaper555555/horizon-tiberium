// Хук: игрок подобрал предмет. Осколок без капсулы заражает.
fn tiberium_item_picked_up(
    game: &mut crate::game::Game<'_>,
    player: u128,
    item: &str,
    count: u32,
    canceled: &mut bool,
) {
    crate::game::tiberium::item_picked_up(game, player, item, count, canceled);
}
