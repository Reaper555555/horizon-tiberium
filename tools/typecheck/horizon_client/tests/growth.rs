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
        .find(|(p, _)| *p == pos.as_slice())
        .map(|(_, name)| (*name).to_string())
}

fn crystals() -> Vec<[i32; 3]> {
    let blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
    blocks
        .iter()
        .filter(|(_, name)| **name == "tiberium:crystal")
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
        blocks.insert([0, 0, 0], "minecraft:stone"); // земля
        blocks.insert([0, 4, 0], "tiberium:crystal"); // кристалл в воздухе
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
        blocks.insert([0, 0, 0], "minecraft:dirt");
        blocks.insert([0, 1, 0], "tiberium:crystal");
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
        blocks.insert([0, 0, 0], "minecraft:dirt");
        blocks.insert([0, 1, 0], "tiberium:crystal");
        for dx in -4..=4 {
            for dz in -4..=4 {
                blocks.insert([dx, 0, dz], "minecraft:dirt");
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
                blocks.insert([dx, 0, dz], "minecraft:dirt");
                if (dx + dz) % 2 == 0 && dx.abs() <= 4 && dz.abs() <= 4 {
                    blocks.insert([dx, 1, dz], "tiberium:crystal");
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
            .filter(|(_, n)| **n == "tiberium:column")
            .map(|(p, _)| *p)
            .collect()
    };
    with_timeout(|| run(6000));
    let late: Vec<[i32; 3]> = {
        let blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
        blocks
            .iter()
            .filter(|(_, n)| **n == "tiberium:column")
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
                blocks.insert([dx, 0, dz], "minecraft:dirt");
                if (dx + dz) % 2 == 0 && dx.abs() <= 4 && dz.abs() <= 4 {
                    blocks.insert([dx, 1, dz], "tiberium:crystal");
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
                blocks.insert([dx, 0, dz], "minecraft:dirt");
            }
        }
        blocks.insert([0, 1, 0], "tiberium:crystal");
    }
    with_timeout(|| run(6000));
    let blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
    let crystals: Vec<[i32; 3]> = blocks
        .iter()
        .filter(|(_, name)| **name == "tiberium:crystal")
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
                blocks.insert([dx, 0, dz], "minecraft:dirt");
            }
        }
        // Стена со всех сторон: x = 2 и z = 2.
        for y in 1..=4 {
            for dz in -4..=4 {
                blocks.insert([2, y, dz], "minecraft:stone");
            }
            for dx in -4..=4 {
                blocks.insert([dx, y, 2], "minecraft:stone");
            }
        }
        blocks.insert([0, 1, 0], "tiberium:crystal");
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
                blocks.insert([dx, 0, dz], "minecraft:dirt");
            }
        }
        for dx in -4..=4 {
            for dz in -4..=4 {
                if (dx + dz) % 2 == 0 {
                    blocks.insert([dx, 1, dz], "tiberium:crystal");
                }
            }
        }
    }
    with_timeout(|| run(12000));
    let blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
    let columns: Vec<[i32; 3]> = blocks
        .iter()
        .filter(|(_, name)| **name == "tiberium:column")
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

#[test]
fn верхние_слои_съезжают_по_одной_координате() {
    let _scene = scene();
    clear_world();
    set_player();
    {
        let mut blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
        for dx in -9..=9 {
            for dz in -9..=9 {
                blocks.insert([dx, 0, dz], "minecraft:dirt");
                if (dx + dz) % 2 == 0 && dx.abs() <= 4 && dz.abs() <= 4 {
                    blocks.insert([dx, 1, dz], "tiberium:crystal");
                }
            }
        }
    }
    with_timeout(|| run(20000));
    let blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
    let mut levels: std::collections::BTreeMap<i32, Vec<[i32; 3]>> = Default::default();
    for (pos, name) in blocks.iter() {
        if *name == "tiberium:column" {
            levels.entry(pos[1]).or_default().push(*pos);
        }
    }
    assert!(levels.len() >= 3, "массив вырос меньше чем на три слоя");
    let mut prev: Option<((i32, i32), i32)> = None;
    for (level, cells) in levels.iter() {
        // Площадь сечения — от 5 до 30 клеток.
        assert!(
            (5..=30).contains(&cells.len()),
            "в сечении {} клеток, а должно быть от 5 до 30",
            cells.len()
        );
        let min_x = cells.iter().map(|p| p[0]).min().unwrap();
        let min_z = cells.iter().map(|p| p[2]).min().unwrap();
        if let Some((prev_min, prev_level)) = prev {
            assert_eq!(prev_level + 1, *level, "пропущен слой");
            let dx = min_x - prev_min.0;
            let dz = min_z - prev_min.1;
            // Сдвиг — только по одной координате и не больше клетки.
            assert!(
                (dx == 0 || dz == 0) && dx.abs() <= 1 && dz.abs() <= 1,
                "слой {} съехал сразу по двум координатам: dx={}, dz={}",
                level,
                dx,
                dz
            );
        }
        prev = Some(((min_x, min_z), *level));
    }
}

/// Свойство блока, выставленное модом.
fn prop(pos: [i32; 3], key: &str) -> Option<String> {
    horizon_client::game::FAKE_PROPS
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .get(&pos)
        .and_then(|m| m.get(key))
        .cloned()
}

#[test]
fn снег_считается_почвой_и_поле_по_нему_ползёт() {
    let _scene = scene();
    clear_world();
    set_player();
    {
        let mut blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
        blocks.insert([0, 0, 0], "minecraft:snow");
        blocks.insert([0, 1, 0], "tiberium:crystal");
        for dx in -5..=5 {
            for dz in -5..=5 {
                blocks.insert([dx, 0, dz], "minecraft:snow");
            }
        }
    }
    with_timeout(|| run(3000));
    let spread = crystals().iter().filter(|p| p[1] == 1).count();
    assert!(
        spread >= 5,
        "по снегу поле не расползлось: кристаллов всего {}",
        spread
    );
}

#[test]
fn высушенная_почва_становится_камнем_без_зелёного_блока() {
    let _scene = scene();
    clear_world();
    set_player();
    {
        let mut blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
        blocks.insert([0, 0, 0], "minecraft:grass_block");
        blocks.insert([0, 1, 0], "tiberium:crystal");
        for dx in -3..=3 {
            for dz in -3..=3 {
                blocks.insert([dx, 0, dz], "minecraft:grass_block");
            }
        }
    }
    with_timeout(|| run(4000));
    let blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
    let green = blocks
        .iter()
        .filter(|(_, name)| name.contains("tainted"))
        .count();
    assert_eq!(green, 0, "зелёный блок заражённой почвы остался в мире");
    let stone = blocks
        .iter()
        .filter(|(_, name)| **name == "minecraft:stone")
        .count();
    assert!(stone > 0, "высушенная почва не стала камнем");
}

#[test]
fn кристалл_на_стене_получает_настенную_форму() {
    let _scene = scene();
    clear_world();
    set_player();
    {
        let mut blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
        blocks.insert([0, 1, 0], "minecraft:stone"); // стена
        blocks.insert([1, 1, 0], "tiberium:crystal"); // кристалл вплотную к стене
        blocks.insert([0, 0, 0], "minecraft:dirt"); // земля под стеной
    }
    with_timeout(|| run(600));
    assert_eq!(
        prop([1, 1, 0], "style").as_deref(),
        Some("wall_w"),
        "кристалл у стены не прижался к ней"
    );
    assert_eq!(
        prop([1, 1, 0], "rotation").as_deref(),
        Some("r0"),
        "настенный кристалл должен быть без поворота"
    );
}

#[test]
fn кристаллы_продолжают_расти_далеко_от_игрока() {
    let _scene = scene();
    clear_world();
    set_player();
    {
        let mut blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
        // Поле далеко от игрока: игрок стоит в [0,1,0], кристалл — в [30,1,0].
        for dx in 25..=35 {
            for dz in -3..=3 {
                blocks.insert([dx, 0, dz], "minecraft:dirt");
            }
        }
        blocks.insert([30, 1, 0], "tiberium:crystal");
    }
    with_timeout(|| run(4000));
    // Далёкий кристалл должен вырасти в полную стадию: значит, он не
    // замер после того, как игрок отошёл.
    assert_eq!(
        prop([30, 1, 0], "shift").as_deref(),
        Some("p6"),
        "далёкий кристалл перестал расти"
    );
}

#[test]
fn одиночные_кристаллы_появляются_возле_крупной_структуры() {
    let _scene = scene();
    clear_world();
    set_player();
    {
        let mut blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
        // Земля вокруг — чтобы одиночному кристаллу было где появиться.
        for dx in -60..=60 {
            for dz in -60..=60 {
                blocks.insert([dx, 0, dz], "minecraft:dirt");
            }
        }
        // Плотное поле — из него вырастает крупная структура.
        for dx in -3..=3 {
            for dz in -3..=3 {
                for dy in 1..=2 {
                    blocks.insert([dx, dy, dz], "tiberium:crystal");
                }
            }
        }
    }
    // Одиночные кристаллы появляются раз в минуту и не каждый раз, поэтому
    // проверяем несколько минут подряд.
    let found = std::sync::Arc::new(std::sync::atomic::AtomicUsize::new(0));
    let seen = found.clone();
    with_timeout(move || {
        for _ in 0..6 {
            run(1200);
            let far = crystals()
                .iter()
                .filter(|p| p[0].abs() > 25 || p[2].abs() > 25)
                .count();
            seen.store(far, std::sync::atomic::Ordering::Relaxed);
            if far >= 1 {
                break;
            }
        }
    });
    assert!(
        found.load(std::sync::atomic::Ordering::Relaxed) >= 1,
        "одиночные кристаллы рядом со структурой не появились"
    );
}

#[test]
fn массив_не_висит_над_неровной_землёй() {
    let _scene = scene();
    clear_world();
    set_player();
    {
        let mut blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
        // Поле кристаллов — из него вырастает крупная структура.
        for dx in -3..=3 {
            for dz in -3..=3 {
                blocks.insert([dx, 0, dz], "minecraft:dirt");
                blocks.insert([dx, 1, dz], "tiberium:crystal");
            }
        }
        // Ровная земля вокруг поля.
        for dx in -12..=12 {
            for dz in -12..=12 {
                blocks.insert([dx, 0, dz], "minecraft:dirt");
            }
        }
        // Неровный рельеф: с западной стороны земля на два блока ниже.
        for dx in -6..=-4 {
            for dz in -6..=6 {
                blocks.remove(&[dx, 0, dz]);
                blocks.remove(&[dx, 1, dz]);
                blocks.insert([dx, -2, dz], "minecraft:dirt");
            }
        }
    }
    with_timeout(|| run(3000));
    let blocks = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
    let columns: Vec<[i32; 3]> = blocks
        .iter()
        .filter(|(_, n)| **n == "tiberium:column")
        .map(|(p, _)| *p)
        .collect();
    let base_y = columns.iter().map(|p| p[1]).min().unwrap();
    let mut gaps = 0;
    for pos in columns.iter().filter(|p| p[1] == base_y) {
        // Под нижним блоком массива должна быть земля: массив не должен
        // висеть над рельефом.
        let below = [pos[0], pos[1] - 1, pos[2]];
        let under = blocks
            .iter()
            .find(|(p, _)| *p == below.as_slice())
            .map(|(_, n)| *n)
            .unwrap_or("minecraft:air");
        if under == "minecraft:air" {
            gaps += 1;
        }
    }
    assert_eq!(
        gaps, 0,
        "основание массива повисло над землёй: {} блоков",
        gaps
    );
}
