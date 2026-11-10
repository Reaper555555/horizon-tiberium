// Хук: финальный цвет тумана. В зоне ионного шторма туман зеленеет.
fn tiberium_compute_fog_color(
    game: &crate::game::Game<'_>,
    partial: f32,
    camera: [f64; 3],
    fog_type: horizon_client::fog::FogType,
    rgb: &mut [f32; 3],
) {
    crate::game::tiberium::compute_fog_color(game, partial, camera, fog_type, rgb);
}
