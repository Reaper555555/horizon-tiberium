//! Регрессионные тесты нативной части мода.
//!
//! Главный тест ловит зависание сервера: рост поля зовёт `spread()` и
//! `wall_growth()`, а они берут тот же мьютекс, что и список сайтов. Если
//! замок держать во время роста, мьютекс std::sync::Mutex не переиспользуется
//! и поток встаёт навсегда — игра зависает, мир не выгружается.
//!
//! Тест гоняет тики в отдельном потоке с тайм-аутом: зависание поймается
//! как падение по таймауту, а не как «игра не отвечает».

use std::sync::mpsc;
use std::time::Duration;

use horizon_client::game::{FAKE_BLOCKS, FAKE_PLAYER};
use horizon_client::mod_api::NativeServerPlayer;

/// Прогоняет тики игрока: пересканирование поля, рост, шпили.
fn run_ticks(times: u64) {
    let mut game = horizon_client::game::Game::new();
    for _ in 0..times {
        horizon_client::game::tiberium::player_tick(&mut game);
    }
}

#[test]
fn рост_поля_не_вешает_поток() {
    // Кристалл на земле: рост, расползание и осушение почвы должны отработать.
    {
        let mut blocks = FAKE_BLOCKS.lock().unwrap();
        blocks.push(([0, 0, 0], "tiberium:crystal"));
        blocks.push(([0, -1, 0], "minecraft:dirt"));
        blocks.push(([1, -1, 0], "minecraft:dirt"));
        blocks.push(([0, 0, 1], "minecraft:dirt"));
    }
    {
        let mut player = FAKE_PLAYER.lock().unwrap();
        *player = Some(NativeServerPlayer {
            uuid: 42,
            name: "Tester".to_string(),
            dimension: "minecraft:overworld".to_string(),
            position: [0.5, 0.0, 0.5],
            game_mode: 0,
            health: 20.0,
        });
    }

    let (tx, rx) = mpsc::channel();
    let handle = std::thread::spawn(move || {
        // 1200 тиков: хватает, чтобы перескан прошёл несколько раз
        // (каждые 200 тиков) и расползание сработало (шанс 1 из 5 за проход).
        run_ticks(1200);
        let _ = tx.send(());
    });

    let result = rx.recv_timeout(Duration::from_secs(20));
    assert!(
        result.is_ok(),
        "тик игрока завис: мьютекс сайтов, видимо, держится во время роста"
    );
    let _ = handle.join();
}

#[test]
fn серверный_тик_не_вешает_поток() {
    let (tx, rx) = mpsc::channel();
    let handle = std::thread::spawn(move || {
        let mut game = horizon_client::game::Game::new();
        for _ in 0..120 {
            horizon_client::game::tiberium::tick(&mut game);
        }
        let _ = tx.send(());
    });

    let result = rx.recv_timeout(Duration::from_secs(20));
    assert!(result.is_ok(), "серверный тик завис");
    let _ = handle.join();
}
