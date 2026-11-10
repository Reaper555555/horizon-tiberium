// Хук: общий тик игры. На серверном потоке здесь идут отравление и молнии шторма.
fn tiberium_tick(game: &mut crate::game::Game<'_>) {
    crate::game::tiberium::tick(game);
}
