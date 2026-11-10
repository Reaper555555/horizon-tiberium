// Хук: огонь собирается появиться. Молнии шторма не поджигают землю.
fn tiberium_block_ignite(
    game: &crate::game::GameLevel<'_>,
    dimension: horizon_world::level::Dimension,
    player: Option<u128>,
    pos: horizon_core::position::BlockPos,
    cause: &str,
    cancel: &mut bool,
) {
    crate::game::tiberium::block_ignite(game, dimension, player, pos, cause, cancel);
}
