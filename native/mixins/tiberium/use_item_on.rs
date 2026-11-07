fn tiberium_use_item_on(
    game: &mut crate::game::Game<'_>,
    stack: &crate::items::ItemStack,
    pos: [i32; 3],
    face: [i32; 3],
    claimed: &mut bool,
) {
    crate::game::tiberium::use_item_on(game, stack, pos, face, claimed);
}
