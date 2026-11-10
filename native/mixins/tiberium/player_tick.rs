// Хук: конец серверного тика игрока. Здесь крутится рост полей тиберия.
fn tiberium_player_tick(game: &mut crate::game::Game<'_>) {
    crate::game::tiberium::player_tick(game);
}
