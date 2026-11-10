// Хук: игрок сменил броню. Отслеживаем био-костюм.
fn tiberium_on_equip(
    game: &mut crate::game::Game<'_>,
    slot: &str,
    new: Option<&horizon_client::items::ItemStack>,
) {
    crate::game::tiberium::on_equip(game, slot, new);
}
