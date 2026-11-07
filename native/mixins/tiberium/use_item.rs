fn tiberium_use_item(
    game: &mut crate::game::Game<'_>,
    stack: &crate::items::ItemStack,
    claimed: &mut bool,
) {
    crate::game::tiberium::use_item(game, stack, claimed);
}
