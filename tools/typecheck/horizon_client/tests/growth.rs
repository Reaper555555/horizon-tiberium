//! Регрессионные тесты на поведение мода, а не только на отсутствие зависания.
//!
//! Здесь проверяются правила роста, которые видно в игре:
//!   * кристалл, висящий в воздухе, падает на землю;
//!   * кристалл не растёт выше двух блоков;
//!   * поле расползается вширь;
//!   * крупная структура растёт поблочно из существующего кристалла.

use std::sync::mpsc;
use std::time::Duration;

use horizon_client::game::{FAKE_BLOCKS, FAKE_PLAYER, Game};
use horizon_client::mod_api::NativeServerPlayer;

/// Сценарии делят один фальшивый мир и состояние мода, поэтому идут
/// строго по очереди.
static SCENE: std::sync::Mutex<()> = std::sync::Mutex::new(());

fn scene() -> std::sync::MutexGuard<'static, ()> {
    SCENE.lock().unwrap_or_else(|e| e.into_inner())
}

fn clear_world() {
    horizon_client::game::tiberium::reset_state();
    let mut blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
    blocks.clear();
}

fn set_player() {
    let mut player = FAKE_PLAYER.lock().unwrap_or_else(|e| e.into_inner());
    *player = Some(NativeServerPlayer {
        uuid: 7,
        name: "Tester".to_string(),
        dimension: "minecraft:overworld".to_string(),
        position: [0.5, 1.0, 0.5],
        game_mode: 0,
        health: 20.0,
    });
}

fn block_at(pos: [i32; 3]) -> Option<String> {
    let blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
    blocks
        .iter()
        .find(|(p, _)| *p == pos)
        .map(|(_, name)| (*name).to_string())
}

fn crystals() -> Vec<[i32; 3]> {
    let blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
    blocks
        .iter()
        .filter(|(_, name)| *name == "tiberium:crystal")
        .map(|(p, _)| *p)
        .collect()
}

fn run(times: u64) {
    let mut game = Game::new();
    for _ in 0..times {
        horizon_client::game::tiberium::player_tick(&mut game);
    }
}

/// Гоняет сценарий в отдельном потоке с таймаутом: зависание будет
/// поймано как падение, а не как «игра не отвечает».
fn with_timeout<F: FnOnce() + Send + 'static>(f: F) {
    let (tx, rx) = mpsc::channel();
    let handle = std::thread::spawn(move || {
        f();
        let _ = tx.send(());
    });
    assert!(
        rx.recv_timeout(Duration::from_secs(30)).is_ok(),
        "сценарий завис"
    );
    let _ = handle.join();
}

#[test]
fn кристалл_в_воздухе_падает() {
    let _scene = scene();
    clear_world();
    set_player();
    {
        let mut blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
        blocks.push(([0, 0, 0], "minecraft:stone")); // земля
        blocks.push(([0, 4, 0], "tiberium:crystal")); // кристалл в воздухе
    }
    with_timeout(|| run(4000));
    assert_ne!(
        block_at([0, 4, 0]),
        Some("tiberium:crystal".to_string()),
        "кристалл остался висеть в воздухе"
    );
    assert_eq!(
        block_at([0, 1, 0]),
        Some("tiberium:crystal".to_string()),
        "кристалл должен упасть на землю"
    );
}

#[test]
fn кристалл_не_растёт_выше_двух_блоков() {
    let _scene = scene();
    clear_world();
    set_player();
    {
        let mut blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
        blocks.push(([0, 0, 0], "minecraft:dirt"));
        blocks.push(([0, 1, 0], "tiberium:crystal"));
    }
    with_timeout(|| run(4000));
    let heights: Vec<i32> = crystals()
        .iter()
        .filter(|p| p[0] == 0 && p[2] == 0)
        .map(|p| p[1])
        .collect();
    assert!(
        heights.len() <= 2,
        "над кристаллом выросло блоков: {:?}",
        heights
    );
    assert!(
        heights.iter().all(|h| *h <= 2),
        "кристалл вырос выше двух блоков: {:?}",
        heights
    );
}

#[test]
fn поле_расползается_вширь() {
    let _scene = scene();
    clear_world();
    set_player();
    {
        let mut blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
        blocks.push(([0, 0, 0], "minecraft:dirt"));
        blocks.push(([0, 1, 0], "tiberium:crystal"));
        for dx in -4..=4 {
            for dz in -4..=4 {
                blocks.push(([dx, 0, dz], "minecraft:dirt"));
            }
        }
    }
    with_timeout(|| run(3000));
    let spread = crystals()
        .iter()
        .filter(|p| p[1] == 1)
        .count();
    assert!(
        spread >= 5,
        "поле не расползлось: кристаллов всего {}",
        spread
    );
}

#[test]
fn крупная_структура_растёт_из_кристалла_и_не_сразу() {
    let _scene = scene();
    clear_world();
    set_player();
    {
        let mut blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
        // Поле: плотная сетка кристаллов на земле.
        // Земля шире поля кристаллов: массивы выходят за его пределы.
        for dx in -9..=9 {
            for dz in -9..=9 {
                blocks.push(([dx, 0, dz], "minecraft:dirt"));
                if (dx + dz) % 2 == 0 && dx.abs() <= 4 && dz.abs() <= 4 {
                    blocks.push(([dx, 1, dz], "tiberium:crystal"));
                }
            }
        }
    }
    // Заметный отрезок времени: структура не должна появиться целиком сразу.
    with_timeout(|| run(200));
    let early: Vec<[i32; 3]> = {
        let blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
        blocks
            .iter()
            .filter(|(_, n)| *n == "tiberium:column")
            .map(|(p, _)| *p)
            .collect()
    };
    with_timeout(|| run(6000));
    let late: Vec<[i32; 3]> = {
        let blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
        blocks
            .iter()
            .filter(|(_, n)| *n == "tiberium:column")
            .map(|(p, _)| *p)
            .collect()
    };
    assert!(
        late.len() > early.len(),
        "структура не выросла: было {}, стало {}",
        early.len(),
        late.len()
    );
    assert!(
        early.len() < late.len() / 2,
        "структура появилась вся сразу: {} из {}",
        early.len(),
        late.len()
    );
    // Каждый блок структуры стоит над кристаллом или над другим блоком
    // структуры: из воздуха она не берётся.
    let blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
    let has = |pos: [i32; 3], name: &str| {
        blocks
            .iter()
            .any(|(p, n)| *p == pos && *n == name)
    };
    let is_column = |pos: [i32; 3]| has(pos, "tiberium:column");
    for pos in late.iter() {
        let under = [pos[0], pos[1] - 1, pos[2]];
        let on_ground = ["minecraft:dirt", "minecraft:coarse_dirt", "tiberium:tainted_soil"]
            .iter()
            .any(|n| has(under, n));
        // Верхние слои массива смещаются, поэтому блок может опираться и на
        // соседний блок массива — но не висеть совсем без опоры.
        let beside = [[1, 0, 0], [-1, 0, 0], [0, 0, 1], [0, 0, -1]]
            .iter()
            .any(|d| is_column([pos[0] + d[0], pos[1], pos[2] + d[2]]));
        assert!(
            on_ground
                || has(under, "tiberium:crystal")
                || has(under, "tiberium:column")
                || beside,
            "блок структуры {:?} висит в воздухе",
            pos
        );
    }
}

#[test]
fn массив_не_сужается_вверх_и_слои_заполняются_целиком() {
    let _scene = scene();
    clear_world();
    set_player();
    {
        let mut blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
        for dx in -9..=9 {
            for dz in -9..=9 {
                blocks.push(([dx, 0, dz], "minecraft:dirt"));
                if (dx + dz) % 2 == 0 && dx.abs() <= 4 && dz.abs() <= 4 {
                    blocks.push(([dx, 1, dz], "tiberium:crystal"));
                }
            }
        }
    }
    with_timeout(|| run(20000));
    let blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
    let mut by_level: std::collections::BTreeMap<i32, usize> = Default::default();
    for (pos, name) in blocks.iter() {
        if *name == "tiberium:column" {
            *by_level.entry(pos[1]).or_insert(0) += 1;
        }
    }
    assert!(
        by_level.len() >= 3,
        "массив вырос меньше чем на три слоя: {:?}",
        by_level
    );
    let levels: Vec<(i32, usize)> = by_level.into_iter().collect();
    let base = levels[0].1;
    // Нижние слои заполнены целиком, верхний — ещё нет.
    for (level, count) in levels.iter() {
        assert!(
            *count <= base,
            "слой {} шире основания: {} против {}",
            level,
            count,
            base
        );
    }
    for (level, count) in levels.iter().take(levels.len() - 1) {
        assert_eq!(
            *count, base,
            "слой {} заполнен не целиком: {} из {}",
            level, count, base
        );
    }
}

#[test]
fn кристалл_не_растёт_вторым_блоком() {
    let _scene = scene();
    clear_world();
    set_player();
    {
        let mut blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
        for dx in -6..=6 {
            for dz in -6..=6 {
                blocks.push(([dx, 0, dz], "minecraft:dirt"));
            }
        }
        blocks.push(([0, 1, 0], "tiberium:crystal"));
    }
    with_timeout(|| run(6000));
    let blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
    let crystals: Vec<[i32; 3]> = blocks
        .iter()
        .filter(|(_, name)| *name == "tiberium:crystal")
        .map(|(p, _)| *p)
        .collect();
    assert!(!crystals.is_empty(), "кристаллов не осталось");
    for pos in crystals.iter() {
        let above = [pos[0], pos[1] + 1, pos[2]];
        let stacked = blocks
            .iter()
            .any(|(p, name)| *p == above && *name == "tiberium:crystal");
        assert!(
            !stacked,
            "на кристалле {:?} вырос второй блок {:?}",
            pos,
            above
        );
    }
}

#[test]
fn кристалл_прижимается_к_стене() {
    let _scene = scene();
    clear_world();
    set_player();
    {
        let mut blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
        for dx in -6..=6 {
            for dz in -6..=6 {
                blocks.push(([dx, 0, dz], "minecraft:dirt"));
            }
        }
        // Стена со всех сторон: x = 2 и z = 2.
        for y in 1..=4 {
            for dz in -4..=4 {
                blocks.push(([2, y, dz], "minecraft:stone"));
            }
            for dx in -4..=4 {
                blocks.push(([dx, y, 2], "minecraft:stone"));
            }
        }
        blocks.push(([0, 1, 0], "tiberium:crystal"));
    }
    with_timeout(|| run(4000));
    let blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
    let crystal = |p: [i32; 3]| {
        blocks
            .iter()
            .any(|(pos, name)| *pos == p && *name == "tiberium:crystal")
    };
    let stone = |p: [i32; 3]| {
        blocks
            .iter()
            .any(|(pos, name)| *pos == p && *name == "minecraft:stone")
    };
    // Хотя бы один кристалл должен вырасти вплотную к стене.
    let mut attached = 0;
    for dx in -4..=4 {
        for dy in 1..=4 {
            for dz in -4..=4 {
                let p = [dx, dy, dz];
                if !crystal(p) {
                    continue;
                }
                let near_wall = [[1, 0, 0], [-1, 0, 0], [0, 0, 1], [0, 0, -1], [0, 1, 0]]
                    .iter()
                    .any(|d| stone([p[0] + d[0], p[1] + d[1], p[2] + d[2]]));
                if near_wall {
                    attached += 1;
                }
            }
        }
    }
    assert!(
        attached > 0,
        "кристалл так и не прижался к стене: стена есть, а настенных кристаллов нет"
    );
}

#[test]
fn массив_стоит_на_земле_а_не_висит_в_воздухе() {
    let _scene = scene();
    clear_world();
    set_player();
    {
        let mut blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
        // Земля с ямой: под частью поля пусто.
        for dx in -9..=9 {
            for dz in -9..=9 {
                if dx == 0 && dz == 0 {
                    continue;
                }
                blocks.push(([dx, 0, dz], "minecraft:dirt"));
            }
        }
        for dx in -4..=4 {
            for dz in -4..=4 {
                if (dx + dz) % 2 == 0 {
                    blocks.push(([dx, 1, dz], "tiberium:crystal"));
                }
            }
        }
    }
    with_timeout(|| run(12000));
    let blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
    let columns: Vec<[i32; 3]> = blocks
        .iter()
        .filter(|(_, name)| *name == "tiberium:column")
        .map(|(p, _)| *p)
        .collect();
    assert!(!columns.is_empty(), "массив не вырос");
    // Ни один блок массива не должен стоять ниже уровня земли.
    for pos in columns.iter() {
        assert!(
            pos[1] >= 1,
            "блок массива {:?} ушёл под землю",
            pos
        );
    }
}
