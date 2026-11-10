// Tiberium 0.2.0 — мод тиберия для Horizon 26.3.
//
// Модуль вставляется в crates/horizon-client/src/game.rs как `tiberium`
// и содержит всю игровую логику: рост полей, осушение почвы, шестигранные
// шпили, ионные штормы и токсичность.
//
// Правила:
//   * кристалл растёт преимущественно вширь (расползание по почве) и медленно
//     вверх; каждая стадия делает сечение шире (p0..p6);
//   * почва вокруг высушивается: трава -> земля -> грунт -> камень;
//   * шпиль растёт из связанных шестигранных колонн, каждая пятая к��жка сдвигает
//     его на блок в сторону наклона, верхние слои ждут нижних;
//   * заражение реальное: ванильное отравление, а не надпись;
//   * био-костюм снимает заражение, капсула делает осколок безопасным.

use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};

use crate::game::Game;
use crate::text::Text;
use horizon_client::items::ItemStack;
use horizon_client::mod_api::NativeServerPlayer;
use horizon_world::registry::BlockStateId;

pub const ID: &str = "tiberium";
pub const VERSION: &str = "0.2.0";
pub const DESCRIPTION: &str =
    "Tiberium: crystalline growth that drains the land, contaminates the soil, \
     raises hexagonal spires and calls ion storms.";

const CRYSTAL: &str = "tiberium:crystal";
const COLUMN: &str = "tiberium:column";
const SHARD: &str = "tiberium:raw_shard";
const SEALED: &str = "tiberium:sealed_capsule";
const EMPTY_CAPSULE: &str = "tiberium:empty_capsule";
const DISRUPTOR: &str = "tiberium:sonic_disruptor";
const CHARGE: &str = "tiberium:sonic_charge";

const UPDATE_FLAGS: i32 = 3;

/// Стили кристалла: форма (a/b/c/j) + наклон.
const STYLES: [&str; 20] = [
    "a", "axp", "axn", "azp", "azn", "b", "bxp", "bxn", "bzp", "bzn", "c", "cxp", "cxn", "czp",
    "czn", "j", "jxp", "jxn", "jzp", "jzn",
];
const ROTATIONS: [&str; 4] = ["r0", "r1", "r2", "r3"];
const STAGE_NAMES: [&str; 7] = ["p0", "p1", "p2", "p3", "p4", "p5", "p6"];
const MAX_STAGE: u8 = 6;

/// Био-костюм: слоты head/chest/legs/feet.
const BIO_SLOTS: [&str; 4] = ["head", "chest", "legs", "feet"];

mod cfg {
    /// Радиус, в котором мод вообще работает вокруг игрока.
    pub const SCAN_RADIUS: i32 = 9;
    /// Тиков между проходами роста (раз в секунду).
    pub const GROW_INTERVAL: u64 = 20;
    /// Полный перескан поля раз в 10 секунд.
    pub const RESCAN_INTERVAL: u64 = 200;
    /// Шанс расширения кристалла (1 из N).
    pub const WIDEN_CHANCE: u64 = 6;
    /// Шанс роста вверх (1 из N) — вширь растём чаще.
    pub const GROW_CHANCE: u64 = 12;
    /// Шанс расползания по почве (1 из N).
    pub const SPREAD_CHANCE: u64 = 5;
    /// Шанс роста на стене/потолке (1 из N).
    pub const WALL_CHANCE: u64 = 10;
    /// Максимальная высота маленького кристалла.
    pub const MAX_HEIGHT: u8 = 12;
    /// Сколько кристаллов нужно, чтобы появился шпиль.
    pub const SPIRE_SITES: usize = 14;
    /// Минимальная дистанция между шпилями.
    pub const SPIRE_GAP: i32 = 22;
    /// Тиков между слоями шпиля.
    pub const SPIRE_LAYER_TICKS: u64 = 40;
    /// Порог плотности тиберия для заражения.
    pub const POISON_DENSITY: f32 = 0.06;
    /// Длительность отравления, тики (1 тик = 1/20 с).
    pub const POISON_TICKS: u32 = 60;
}

/// Состояние одного кристалла.
#[derive(Clone)]
struct Site {
    base: [i32; 3],
    style: &'static str,
    rotation: &'static str,
    stage: u8,
    height: u8,
    seed: u64,
}

/// Крупная шестигранная структура.
#[derive(Clone)]
struct Spire {
    base: [i32; 3],
    radius: u8,
    height: u8,
    layer: u8,
    lean: (i32, i32),
}

static SITES: OnceLock<Mutex<Vec<Site>>> = OnceLock::new();
static SPIRES: OnceLock<Mutex<Vec<Spire>>> = OnceLock::new();
static PLAYER_TICKS: OnceLock<Mutex<HashMap<u128, u64>>> = OnceLock::new();
static ARMOR: OnceLock<Mutex<HashMap<u128, [bool; 4]>>> = OnceLock::new();
static PICKED: OnceLock<Mutex<Vec<(u128, u64)>>> = OnceLock::new();
static DENSITY: OnceLock<Mutex<HashMap<(i32, i32), (f32, u64)>>> = OnceLock::new();
static SERVER_TICKS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

fn sites() -> &'static Mutex<Vec<Site>> {
    SITES.get_or_init(|| Mutex::new(Vec::new()))
}
fn spires() -> &'static Mutex<Vec<Spire>> {
    SPIRES.get_or_init(|| Mutex::new(Vec::new()))
}
fn player_ticks() -> &'static Mutex<HashMap<u128, u64>> {
    PLAYER_TICKS.get_or_init(|| Mutex::new(HashMap::new()))
}
fn armor() -> &'static Mutex<HashMap<u128, [bool; 4]>> {
    ARMOR.get_or_init(|| Mutex::new(HashMap::new()))
}
fn picked() -> &'static Mutex<Vec<(u128, u64)>> {
    PICKED.get_or_init(|| Mutex::new(Vec::new()))
}
fn density_cache() -> &'static Mutex<HashMap<(i32, i32), (f32, u64)>> {
    DENSITY.get_or_init(|| Mutex::new(HashMap::new()))
}

// ------------------------------------------------------------------ утилиты ---

/// Детерминированный хеш позиции: одинаковые места ведут себя одинаково.
fn hash3(x: i32, y: i32, z: i32, salt: u64) -> u64 {
    let mut h = salt
        .wrapping_add(0x9E37_79B9_7F4A_7C15)
        .wrapping_add((x as u64).wrapping_mul(0xFF51_AFD7_ED55_8CCD));
    h ^= h.rotate_left(31).wrapping_mul(0xC4CE_B9FE_1A85_EC53);
    h ^= (y as u64).wrapping_mul(0x94D0_49BB_1331_11EB);
    h = h.rotate_left(27).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    h ^= (z as u64).wrapping_mul(0xD6E8_FEB8_6659_FD93);
    h.rotate_left(33)
}

/// Шанс 1/N для события, привязанного к месту и тику.
fn chance(seed: u64, salt: u128, n: u64) -> bool {
    if n == 0 {
        return false;
    }
    let mixed = hash3(0, 0, 0, seed) ^ (salt as u64).rotate_left(17);
    hash3(0, 0, 0, mixed) % n == 0
}

fn is_block(game: &Game<'_>, pos: [i32; 3], id: &str) -> bool {
    game.native_block(pos) == id
}

fn is_air(game: &Game<'_>, pos: [i32; 3]) -> bool {
    is_block(game, pos, "minecraft:air")
}

/// Почва, на которой может расти тиберий.
fn is_soil(game: &Game<'_>, pos: [i32; 3]) -> bool {
    let b = game.native_block(pos);
    matches!(
        b.as_str(),
        "minecraft:grass_block"
            | "minecraft:dirt"
            | "minecraft:coarse_dirt"
            | "minecraft:podzol"
            | "minecraft:rooted_dirt"
            | "minecraft:sand"
            | "minecraft:clay"
    )
}

/// Камень, на котором может расти тиберий.
fn is_solid(game: &Game<'_>, pos: [i32; 3]) -> bool {
    let b = game.native_block(pos);
    !matches!(
        b.as_str(),
        "minecraft:air"
            | "minecraft:water"
            | "minecraft:grass"
            | "minecraft:tall_grass"
            | "minecraft:fern"
            | "minecraft:vine"
            | "minecraft:snow"
    ) && !b.starts_with("tiberium:")
}

/// Состояния блоков реестра.
struct Ids {
    crystal: BlockStateId,
    column: BlockStateId,
    air: BlockStateId,
    dirt: BlockStateId,
    coarse_dirt: BlockStateId,
    stone: BlockStateId,
}

fn ids(game: &Game<'_>) -> Option<Ids> {
    let reg = &game.pack.assets.registry;
    Some(Ids {
        crystal: reg.default_state(CRYSTAL)?,
        column: reg.default_state(COLUMN)?,
        air: reg.default_state("minecraft:air")?,
        dirt: reg.default_state("minecraft:dirt")?,
        coarse_dirt: reg.default_state("minecraft:coarse_dirt")?,
        stone: reg.default_state("minecraft:stone")?,
    })
}

// ---------------------------------------------------------------- блоки -------

/// Ставит свойства блока кристалла.
fn set_props(game: &mut Game<'_>, pos: [i32; 3], segment: &str, style: &str, shift: &str, rot: &str) {
    let _ = game.native_set_block_property_with(pos, "segment", segment, UPDATE_FLAGS);
    let _ = game.native_set_block_property_with(pos, "style", style, UPDATE_FLAGS);
    let _ = game.native_set_block_property_with(pos, "shift", shift, UPDATE_FLAGS);
    let _ = game.native_set_block_property_with(pos, "rotation", rot, UPDATE_FLAGS);
}

/// Ставит свойства сразу после установки блока: дефолтные значения пропускаем.
fn set_props_fresh(game: &mut Game<'_>, pos: [i32; 3], segment: &str, style: &str, shift: &str, rot: &str) {
    if segment != "shaft" {
        let _ = game.native_set_block_property_with(pos, "segment", segment, UPDATE_FLAGS);
    }
    if style != "a" {
        let _ = game.native_set_block_property_with(pos, "style", style, UPDATE_FLAGS);
    }
    if shift != "p0" {
        let _ = game.native_set_block_property_with(pos, "shift", shift, UPDATE_FLAGS);
    }
    if rot != "r0" {
        let _ = game.native_set_block_property_with(pos, "rotation", rot, UPDATE_FLAGS);
    }
}

/// Ставит блок кристалла с нужным видом.
fn place_crystal(
    game: &mut Game<'_>,
    ids: &Ids,
    dimension: &str,
    pos: [i32; 3],
    style: &str,
    rotation: &str,
    stage: u8,
    segment: &str,
) -> bool {
    if !is_air(game, pos) {
        return false;
    }
    if !game.native_set_block(dimension, pos, ids.crystal, UPDATE_FLAGS) {
        return false;
    }
    let shift = STAGE_NAMES[stage.min(MAX_STAGE) as usize];
    set_props_fresh(game, pos, segment, style, shift, rotation);
    true
}

/// Перекрашивает всю колонку кристалла: одна стадия, один стиль, верх — наконечник.
fn restyle(game: &mut Game<'_>, site: &Site) {
    let shift = STAGE_NAMES[site.stage.min(MAX_STAGE) as usize];
    for i in 0..site.height {
        let pos = [
            site.base[0],
            site.base[1] + i as i32,
            site.base[2],
        ];
        let segment = if i + 1 == site.height { "tip" } else { "shaft" };
        set_props(game, pos, segment, site.style, shift, site.rotation);
    }
}

// ------------------------------------------------------------------ рост ------

/// Находит новые кристаллы рядом с игроком и заводит на них «сайты».
fn rescan(game: &Game<'_>, centre: [i32; 3]) {
    let mut list = match sites().lock() {
        Ok(l) => l,
        Err(_) => return,
    };
    let r = cfg::SCAN_RADIUS;
    for dx in -r..=r {
        for dz in -r..=r {
            for dy in -4..=4 {
                let p = [centre[0] + dx, centre[1] + dy, centre[2] + dz];
                if !is_block(game, p, CRYSTAL) {
                    continue;
                }
                let below = [p[0], p[1] - 1, p[2]];
                if is_block(game, below, CRYSTAL) {
                    continue; // не нижний блок колонки
                }
                if list.iter().any(|s| s.base == p) {
                    continue;
                }
                let seed = hash3(p[0], p[1], p[2], 0x71BE);
                let style = STYLES[(seed % STYLES.len() as u64) as usize];
                let rotation = ROTATIONS[((seed >> 8) % ROTATIONS.len() as u64) as usize];
                let stage = match game.native_block_property(p, "shift") {
                    Some(s) if s.starts_with('p') => s[1..].parse::<u8>().unwrap_or(0),
                    _ => 0,
                };
                // Высота колонки: считаем блоки кристалла подряд.
                let mut height = 1u8;
                while height < cfg::MAX_HEIGHT {
                    let up = [p[0], p[1] + height as i32, p[2]];
                    if is_block(game, up, CRYSTAL) {
                        height += 1;
                    } else {
                        break;
                    }
                }
                list.push(Site {
                    base: p,
                    style,
                    rotation,
                    stage,
                    height,
                    seed,
                });
            }
        }
    }
}

/// Один шаг роста кристалла.
fn grow_site(game: &mut Game<'_>, ids: &Ids, site: &mut Site, tick: u64, dimension: &str) {
    let seed = site.seed;

    // 1. Расширение: кристалл толстеет с возрастом.
    if site.stage < MAX_STAGE && chance(seed, (tick ^ 0x11) as u128, cfg::WIDEN_CHANCE) {
        site.stage += 1;
        restyle(game, site);
    }

    // 2. Рост вверх: наконечник тянется выше.
    if site.height < cfg::MAX_HEIGHT {
        let top = [
            site.base[0],
            site.base[1] + site.height as i32,
            site.base[2],
        ];
        if is_air(game, top) && chance(seed, (tick ^ 0x22) as u128, cfg::GROW_CHANCE) {
            if place_crystal(game, ids, dimension, top, site.style, site.rotation, site.stage, "shaft")
            {
                site.height += 1;
                restyle(game, site);
            }
        }
    }

    // 3. Расползание вширь: главный способ тиберия завоевать землю.
    if chance(seed, (tick ^ 0x33) as u128, cfg::SPREAD_CHANCE) {
        spread(game, ids, site, dimension, tick);
    }

    // 4. Рост на стенах и потолке.
    if chance(seed, (tick ^ 0x44) as u128, cfg::WALL_CHANCE) {
        wall_growth(game, ids, site, dimension, tick);
    }

    // 5. Осушение: почва вокруг кристалла высыхает и каменеет.
    if chance(seed, (tick ^ 0x55) as u128, 3) {
        dry_soil(game, ids, site, dimension);
    }
}

/// Новый кристалл на соседней почве.
fn spread(
    game: &mut Game<'_>,
    ids: &Ids,
    site: &Site,
    dimension: &str,
    tick: u64,
) {
    let dirs: [[i32; 3]; 4] = [[1, 0, 0], [-1, 0, 0], [0, 0, 1], [0, 0, -1]];
    let pick = (hash3(site.base[0], site.base[1], site.base[2], tick ^ 0x66) % 4) as usize;
    let d = dirs[pick];
    // Поле идёт по рельефу: почва может оказаться на уровень ниже или выше.
    let step = (hash3(site.base[2], site.base[1], site.base[0], tick ^ 0x99) % 3) as usize;
    let levels = [site.base[1] - 1, site.base[1], site.base[1] + 1];
    for (offset, ground_y) in levels.iter().enumerate() {
        if offset != step && offset != 1 {
            continue;
        }
        let ground = [site.base[0] + d[0], *ground_y, site.base[2] + d[2]];
        let above = [ground[0], ground[1] + 1, ground[2]];
        if !is_soil(game, ground) || !is_air(game, above) {
            continue;
        }
        let seed = hash3(above[0], above[1], above[2], 0x5EED);
        let style = STYLES[(seed % STYLES.len() as u64) as usize];
        let rotation = ROTATIONS[((seed >> 8) % ROTATIONS.len() as u64) as usize];
        if !place_crystal(game, ids, dimension, above, style, rotation, 0, "tip") {
            continue;
        }
        if let Ok(mut list) = sites().lock() {
            if !list.iter().any(|s| s.base == above) {
                list.push(Site {
                    base: above,
                    style,
                    rotation,
                    stage: 0,
                    height: 1,
                    seed,
                });
            }
        }
        return;
    }
}

/// Кристалл на стене или потолке: растёт из боковой грани и всегда повёрнут.
fn wall_growth(
    game: &mut Game<'_>,
    ids: &Ids,
    site: &Site,
    dimension: &str,
    tick: u64,
) {
    // Шесть направлений: четыре в стороны и два по вертикали.
    let dirs: [[i32; 3]; 6] = [
        [1, 0, 0],
        [-1, 0, 0],
        [0, 0, 1],
        [0, 0, -1],
        [0, 1, 0],
        [0, -1, 0],
    ];
    let pick = (hash3(site.base[0], site.base[1], site.base[2], tick ^ 0x77) % 6) as usize;
    let d = dirs[pick];
    let level = site.base[1] + site.height as i32 - 1;
    let spot = [site.base[0] + d[0], level + d[1], site.base[2] + d[2]];
    if !is_air(game, spot) {
        return;
    }
    // Опора: сбоку или сверху должен быть камень, иначе кристалл падает.
    let support = if d[1] == 0 {
        [spot[0] - d[0], spot[1], spot[2] - d[2]]
    } else {
        [spot[0], spot[1] - d[1], spot[2]]
    };
    if !is_solid(game, support) {
        return;
    }
    // Поворот по грани, на которой вырос кристалл: соседние не выглядят одинаково.
    let rotation = match (d[0], d[2]) {
        (1, 0) => "r0",
        (-1, 0) => "r2",
        (0, 1) => "r1",
        (0, -1) => "r3",
        _ => "r0",
    };
    let seed = hash3(spot[0], spot[1], spot[2], 0xBEEF);
    let style = STYLES[(seed % STYLES.len() as u64) as usize];
    if place_crystal(game, ids, dimension, spot, style, rotation, 0, "tip") {
        if let Ok(mut list) = sites().lock() {
            if !list.iter().any(|s| s.base == spot) {
                list.push(Site {
                    base: spot,
                    style,
                    rotation,
                    stage: 0,
                    height: 1,
                    seed,
                });
            }
        }
    }
}

/// Почва вокруг тиберия сохнет: трава -> земля -> грунт -> камень.
fn dry_soil(game: &mut Game<'_>, ids: &Ids, site: &Site, dimension: &str) {
    let dirs: [[i32; 3]; 4] = [[1, 0, 0], [-1, 0, 0], [0, 0, 1], [0, 0, -1]];
    let pick = (hash3(site.base[0], site.base[1], site.base[2], site.seed) % 4) as usize;
    let d = dirs[pick];
    let p = [site.base[0] + d[0], site.base[1] - 1, site.base[2] + d[2]];
    let b = game.native_block(p);
    let next = match b.as_str() {
        "minecraft:grass_block" => Some(ids.dirt),
        "minecraft:dirt" => Some(ids.coarse_dirt),
        "minecraft:coarse_dirt" | "minecraft:podzol" => Some(ids.stone),
        _ => None,
    };
    if let Some(state) = next {
        let _ = game.native_set_block(dimension, p, state, UPDATE_FLAGS);
    }
}

// ---------------------------------------------------------------- шпили -------

/// Клетки шестиугольного диска в плоскости XZ (odd-r offset).
fn hex_cells(radius: u8) -> Vec<(i32, i32)> {
    let r = radius as i32;
    let mut out = Vec::new();
    for row in -r..=r {
        let q_min = -r - row;
        let q_max = r - row;
        for q in q_min..=q_max {
            let x = q + (row - (row & 1)) / 2;
            out.push((x, row));
        }
    }
    out
}

/// Направление грани для клетки на границе шестиугольника.
fn edge_style(dx: i32, dz: i32) -> &'static str {
    // Шесть направлений: E, W, NE, NW, SE, SW.
    let ax = dx as f64;
    let az = dz as f64;
    let dirs: [(&'static str, f64, f64); 6] = [
        ("edge_e", 1.0, 0.0),
        ("edge_w", -1.0, 0.0),
        ("edge_ne", 1.0, -1.0),
        ("edge_nw", -1.0, -1.0),
        ("edge_se", 1.0, 1.0),
        ("edge_sw", -1.0, 1.0),
    ];
    let mut best = "edge_e";
    let mut best_dot = f64::MIN;
    for (name, vx, vz) in dirs {
        let len = (ax * vx + az * vz).sqrt();
        if len < 1e-6 {
            continue;
        }
        let dot = (ax * vx + az * vz) / len;
        if dot > best_dot {
            best_dot = dot;
            best = name;
        }
    }
    best
}

/// Строит очередной слой шпиля.
fn build_spire_layer(game: &mut Game<'_>, ids: &Ids, spire: &Spire, dimension: &str) {
    let cells = hex_cells(spire.radius);
    let layer = spire.layer;
    let top = layer + 1 >= spire.height;
    let steps = (layer as i32) / 5;
    let ox = spire.base[0] + spire.lean.0 * steps;
    let oz = spire.base[2] + spire.lean.1 * steps;
    let oy = spire.base[1] + layer as i32;

    // Множество занятых клеток — по нему определяем границу.
    let occupied: std::collections::HashSet<(i32, i32)> = cells.iter().copied().collect();

    for (cx, cz) in cells.iter() {
        let wx = ox + cx;
        let wz = oz + cz;
        let pos = [wx, oy, wz];
        let style = if top {
            "tip"
        } else {
            let mut edge = false;
            for (dx, dz) in [(1, 0), (-1, 0), (1, -1), (0, -1), (0, 1), (1, 1)] {
                if !occupied.contains(&(cx + dx, cz + dz)) {
                    edge = true;
                    break;
                }
            }
            if edge {
                edge_style(*cx, *cz)
            } else {
                "core"
            }
        };
        if !is_block(game, pos, COLUMN) {
            // Здесь должен быть воздух или почва: сквозь камень шпиль не растёт.
            if !is_air(game, pos) && !is_soil(game, pos) {
                continue;
            }
            if !game.native_set_block(dimension, pos, ids.column, UPDATE_FLAGS) {
                continue;
            }
        }
        let _ = game.native_set_block_property_with(pos, "style", style, UPDATE_FLAGS);
    }
}

/// Пытается поднять новый шпиль рядом с полем тиберия.
fn maybe_spire(game: &mut Game<'_>, ids: &Ids, centre: [i32; 3], dimension: &str) {
    let count = {
        let list = match sites().lock() {
            Ok(l) => l,
            Err(_) => return,
        };
        list.iter()
            .filter(|s| {
                (s.base[0] - centre[0]).abs() <= cfg::SCAN_RADIUS
                    && (s.base[2] - centre[2]).abs() <= cfg::SCAN_RADIUS
            })
            .count()
    };
    if count < cfg::SPIRE_SITES {
        return;
    }
    {
        let list = match spires().lock() {
            Ok(l) => l,
            Err(_) => return,
        };
        // Не строим шпиль рядом с уже существующим.
        for s in list.iter() {
            if (s.base[0] - centre[0]).abs() < cfg::SPIRE_GAP
                && (s.base[2] - centre[2]).abs() < cfg::SPIRE_GAP
            {
                return;
            }
        }
    }
    let seed = hash3(centre[0], centre[1], centre[2], 0x5911E);
    let radius = 3 + (seed % 4) as u8;
    let height = 10 + ((seed >> 4) % 14) as u8;
    let lean = match (seed >> 8) % 4 {
        0 => (1, 0),
        1 => (-1, 0),
        2 => (0, 1),
        _ => (0, -1),
    };
    // Ставим шпиль на поверхность рядом с полем.
    let mut ground = centre[1];
    for dy in 0..12 {
        let p = [centre[0], centre[1] - dy, centre[2]];
        if is_solid(game, p) {
            ground = p[1] + 1;
            break;
        }
    }
    let spire = Spire {
        base: [centre[0], ground, centre[2]],
        radius,
        height,
        layer: 0,
        lean,
    };
    build_spire_layer(game, ids, &spire, dimension);
    let mut spire = spire;
    spire.layer = 1;
    if let Ok(mut list) = spires().lock() {
        list.push(spire);
    }
}

/// Продвигает шпили: каждый слой ждёт полного предыдущего.
fn advance_spires(game: &mut Game<'_>, ids: &Ids, dimension: &str) {
    let mut list = match spires().lock() {
        Ok(l) => l,
        Err(_) => return,
    };
    for spire in list.iter_mut() {
        if spire.layer >= spire.height {
            continue;
        }
        build_spire_layer(game, ids, spire, dimension);
        spire.layer += 1;
    }
    list.retain(|s| s.layer < s.height + 4);
}

// ---------------------------------------------------------------- шторм -------

/// Плотность тиберия рядом с точкой: 0..1.
///
/// Считается редко и кэшируется по чанку: клиент спрашивает туман каждый кадр,
/// и полный обход блоков на кадр был бы недопустимо дорог.
fn density(game: &Game<'_>, pos: [i32; 3], radius: i32) -> f32 {
    let chunk = (pos[0] >> 4, pos[2] >> 4);
    let now = game.native_day_time().max(0) as u64;
    if let Ok(map) = density_cache().lock() {
        if let Some((value, stamp)) = map.get(&chunk) {
            if now.saturating_sub(*stamp) < 20 {
                return *value;
            }
        }
    }
    let mut found = 0u32;
    let mut total = 0u32;
    for dx in -radius..=radius {
        for dz in -radius..=radius {
            for dy in -3..=3 {
                let p = [pos[0] + dx, pos[1] + dy, pos[2] + dz];
                let b = game.native_block(p);
                if b == CRYSTAL || b == COLUMN {
                    found += 1;
                }
                total += 1;
            }
        }
    }
    let value = if total == 0 {
        0.0
    } else {
        found as f32 / total as f32
    };
    if let Ok(mut map) = density_cache().lock() {
        map.insert(chunk, (value, now));
        if map.len() > 256 {
            map.clear();
        }
    }
    value
}

/// Сила ионного шторма в точке: плотность тиберия × пульс времени.
fn storm_at(game: &Game<'_>, pos: [i32; 3]) -> f32 {
    let d = density(game, pos, 8);
    if d < 0.01 {
        return 0.0;
    }
    let time = game.native_day_time().max(0) as f64;
    let phase = (time % 2400.0) / 2400.0;
    let pulse = ((phase * std::f64::consts::TAU).sin() * 0.5 + 0.5) as f32;
    (d * 6.0f32).min(1.0) * pulse
}

// ---------------------------------------------------------- игрок и эффекты ---

/// Полный био-костюм? Тогда заражение не действует.
fn protected(uuid: u128) -> bool {
    match armor().lock() {
        Ok(map) => map
            .get(&uuid)
            .map(|set| set.iter().all(|v| *v))
            .unwrap_or(false),
        Err(_) => false,
    }
}

/// Заражение игрока настоящим отравлением.
fn poison_player(game: &mut Game<'_>, player: &NativeServerPlayer) {
    if protected(player.uuid) {
        return;
    }
    let cmd = format!(
        "effect give {} minecraft:poison {} 0",
        player.name,
        cfg::POISON_TICKS / 20
    );
    let _ = game.native_run_command(&cmd);
}

// ------------------------------------------------------------- главные циклы --

/// Тик игрока: рост полей, осушение, отравление.
pub fn player_tick(game: &mut Game<'_>) {
    if !game.native_on(ID) {
        return;
    }
    let Some(player) = game.native_acting_player() else {
        return;
    };
    if player.game_mode == 3 {
        return; // наблюдатель
    }
    let tick = {
        let mut map = match player_ticks().lock() {
            Ok(m) => m,
            Err(_) => return,
        };
        let c = map.entry(player.uuid).or_insert(0);
        *c = c.saturating_add(1);
        *c
    };
    if tick % cfg::GROW_INTERVAL != 0 {
        return;
    }
    let Some(ids) = ids(game) else {
        return;
    };
    let centre = [
        player.position[0].floor() as i32,
        player.position[1].floor() as i32,
        player.position[2].floor() as i32,
    ];
    let dimension = player.dimension.clone();

    if tick % cfg::RESCAN_INTERVAL == 0 {
        rescan(game, centre);
    }

    // Рост.
    {
        let mut list = match sites().lock() {
            Ok(l) => l,
            Err(_) => return,
        };
        for site in list.iter_mut() {
            if (site.base[0] - centre[0]).abs() > cfg::SCAN_RADIUS
                || (site.base[2] - centre[2]).abs() > cfg::SCAN_RADIUS
            {
                continue;
            }
            grow_site(game, &ids, site, tick, &dimension);
        }
    }

    // Шпили.
    if tick % cfg::SPIRE_LAYER_TICKS == 0 {
        advance_spires(game, &ids, &dimension);
        maybe_spire(game, &ids, centre, &dimension);
    }
}

/// Серверный тик: отравление и молнии шторма.
pub fn tick(game: &mut Game<'_>) {
    if !game.native_on(ID) {
        return;
    }
    if game.native_window() {
        return; // только серверный поток
    }
    let counter = SERVER_TICKS.fetch_add(1, std::sync::atomic::Ordering::Relaxed) + 1;
    if counter % cfg::GROW_INTERVAL != 0 {
        return; // раз в секунду: обход блоков дорог
    }
    let players = game.native_server_players();
    if players.is_empty() {
        return;
    }
    let now = game.native_day_time().max(0) as u64;
    let mut pickups: Vec<(u128, u64)> = match picked().lock() {
        Ok(p) => p.clone(),
        Err(_) => Vec::new(),
    };
    pickups.retain(|(_, t)| now.saturating_sub(*t) < 100);

    for player in players.iter() {
        let centre = [
            player.position[0].floor() as i32,
            player.position[1].floor() as i32,
            player.position[2].floor() as i32,
        ];

        // Осколок в руках заражает: подобрал — получил отравление.
        let picked_now = pickups.iter().any(|(u, _)| *u == player.uuid);
        if picked_now {
            poison_player(game, player);
        }

        // Поле тиберия отравляет само по себе.
        let d = density(game, centre, 6);
        if d > cfg::POISON_DENSITY {
            poison_player(game, player);
        }

        // Ионный шторм: молнии бьют рядом с игроком.
        let storm = storm_at(game, centre);
        if storm > 0.35 && chance(now, player.uuid, 14) {
            let lx = centre[0] + ((hash3(centre[0], centre[1], centre[2], now) % 7) as i32) - 3;
            let lz = centre[2] + ((hash3(centre[2], centre[1], centre[0], now) % 7) as i32) - 3;
            let cmd = format!("summon lightning_bolt {} {} {}", lx, centre[1] + 2, lz);
            let _ = game.native_run_command(&cmd);
        }
    }

    if let Ok(mut p) = picked().lock() {
        *p = pickups;
    }
}

/// Игрок подобрал предмет: осколок без капсулы заражает.
pub fn item_picked_up(game: &mut Game<'_>, player: u128, item: &str, _count: u32, _canceled: &mut bool) {
    if !game.native_on(ID) {
        return;
    }
    if item != SHARD {
        return;
    }
    let now = game.native_day_time().max(0) as u64;
    if let Ok(mut p) = picked().lock() {
        p.retain(|(u, _)| *u != player);
        p.push((player, now));
    }
}

/// Игрок сменил броню: запоминаем био-костюм.
pub fn on_equip(game: &mut Game<'_>, slot: &str, new: Option<&ItemStack>) {
    if !game.native_on(ID) {
        return;
    }
    let Some(player) = game.native_acting_player() else {
        return;
    };
    let item = new.map(|s| s.item.as_ref()).unwrap_or("");
    let is_bio = item.starts_with("tiberium:bio_");
    if !is_bio && !item.is_empty() && !BIO_SLOTS.contains(&slot) {
        return;
    }
    if let Ok(mut map) = armor().lock() {
        let set = map.entry(player.uuid).or_insert([false; 4]);
        for (i, s) in BIO_SLOTS.iter().enumerate() {
            if *s == slot {
                set[i] = is_bio;
            }
        }
    }
}

/// Правый клик предметом в воздухе: вскрытие капсулы, ультразвук.
pub fn use_item(game: &mut Game<'_>, stack: &ItemStack, claimed: &mut bool) {
    if !game.native_on(ID) {
        return;
    }
    let item = stack.item.as_ref();
    match item {
        SEALED => {
            if game.native_take_items(SEALED, 1) == 1 {
                game.native_give_items(SHARD, 1);
                *claimed = true;
            }
        }
        DISRUPTOR => {
            let Some(ids) = ids(game) else {
                return;
            };
            if game.native_take_items(CHARGE, 1) != 1 {
                return;
            }
            let Some(player) = game.native_acting_player() else {
                return;
            };
            let centre = [
                player.position[0].floor() as i32,
                player.position[1].floor() as i32,
                player.position[2].floor() as i32,
            ];
            let mut broken = 0u32;
            for dx in -5..=5 {
                for dy in -5..=5 {
                    for dz in -5..=5 {
                        let p = [centre[0] + dx, centre[1] + dy, centre[2] + dz];
                        if is_block(game, p, CRYSTAL) || is_block(game, p, COLUMN) {
                            let _ = game.native_set_block(&player.dimension, p, ids.air, UPDATE_FLAGS);
                            broken += 1;
                        }
                    }
                }
            }
            let _ = game.native_action_bar(
                player.uuid,
                Text::literal(&format!("§bУльтразвук: срезано {}", broken)),
            );
            *claimed = true;
        }
        _ => {}
    }
}

/// Правый клик по блоку: пустая капсула на кристалле → запечатанная капсула.
pub fn use_item_on(
    game: &mut Game<'_>,
    stack: &ItemStack,
    pos: [i32; 3],
    _face: [i32; 3],
    claimed: &mut bool,
) {
    if !game.native_on(ID) {
        return;
    }
    if stack.item.as_ref() != EMPTY_CAPSULE {
        return;
    }
    if !is_block(game, pos, CRYSTAL) {
        return;
    }
    if game.native_take_items(EMPTY_CAPSULE, 1) == 1 {
        game.native_give_items(SEALED, 1);
        *claimed = true;
    }
}

/// Туман зелёный там, где идёт ионный шторм (клиент).
pub fn compute_fog_color(
    game: &Game<'_>,
    _partial: f32,
    camera: [f64; 3],
    fog_type: horizon_client::fog::FogType,
    rgb: &mut [f32; 3],
) {
    if fog_type != horizon_client::fog::FogType::Atmospheric {
        return;
    }
    let pos = [
        camera[0].floor() as i32,
        camera[1].floor() as i32,
        camera[2].floor() as i32,
    ];
    let storm = storm_at(game, pos);
    if storm <= 0.01 {
        return;
    }
    let k = storm.min(1.0) * 0.75;
    rgb[0] = rgb[0] * (1.0 - k) + 0.12 * k;
    rgb[1] = rgb[1] * (1.0 - k) + 0.42 * k;
    rgb[2] = rgb[2] * (1.0 - k) + 0.18 * k;
}

/// Лёгкая тряска камеры во время шторма (клиент).
pub fn camera_shake(game: &Game<'_>, partial: f32, shake: &mut horizon_client::mod_api::NativeShake) {
    let pos = [
        shake.offset[0].floor() as i32,
        shake.offset[1].floor() as i32,
        shake.offset[2].floor() as i32,
    ];
    let _ = partial;
    let storm = storm_at(game, pos);
    if storm <= 0.05 {
        return;
    }
    let t = game.native_day_time() as f32 * 0.37;
    let amp = storm * 0.6;
    shake.pitch += t.sin() * amp;
    shake.yaw += t.cos() * amp * 0.7;
    shake.roll += t.sin() * 0.5 * amp;
}

/// Молния не должна поджигать землю в зоне тиберия.
pub fn block_ignite(
    game: &Game<'_>,
    _dimension: horizon_world::level::Dimension,
    _player: Option<u128>,
    pos: horizon_core::position::BlockPos,
    _cause: &str,
    cancel: &mut bool,
) {
    if !game.native_on(ID) {
        return;
    }
    let at = [pos.x, pos.y, pos.z];
    if storm_at(game, at) > 0.15 {
        *cancel = true;
    }
}
