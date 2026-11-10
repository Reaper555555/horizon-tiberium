// Хук: тряска камеры. Во время ионного шторма землю под ногами подрагивает.
fn tiberium_camera_shake(
    game: &crate::game::Game<'_>,
    partial: f32,
    shake: &mut horizon_client::mod_api::NativeShake,
) {
    crate::game::tiberium::camera_shake(game, partial, shake);
}
