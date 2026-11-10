//! Заглушка игрового контекста Horizon: те же сигнатуры, что и в игре.
//! Сгенерировано tools/typecheck/gen_stub.py — не править руками.

use std::marker::PhantomData;

use crate::fog::FogType;
use crate::items::ItemStack;
use crate::mod_api::{NativeServerPlayer, NativeShake};
use crate::text::Text;
use horizon_core::position::BlockPos;
use horizon_world::level::Dimension;
use horizon_world::registry::BlockStateId;

/// Фальшивый мир для регрессионных тестов: блоки и игрок.
pub static FAKE_BLOCKS: std::sync::LazyLock<
    std::sync::Mutex<std::collections::HashMap<[i32; 3], &'static str>>,
> = std::sync::LazyLock::new(|| {
    std::sync::Mutex::new(std::collections::HashMap::new())
});
pub static FAKE_PLAYER: std::sync::Mutex<Option<NativeServerPlayer>> =
    std::sync::Mutex::new(None);
/// Свойства блоков: что мод выставил (стиль, стадия, поворот).
pub static FAKE_PROPS: std::sync::LazyLock<
    std::sync::Mutex<std::collections::HashMap<[i32; 3], std::collections::HashMap<String, String>>>,
> = std::sync::LazyLock::new(|| {
    std::sync::Mutex::new(std::collections::HashMap::new())
});

pub struct Registry;

impl Registry {
    pub fn default_state(&self, id: &str) -> Option<BlockStateId> {
        // Разные id для разных блоков: тесту нужно отличать кристалл
        // от воздуха и от земли.
        let n = if id.starts_with("tiberium:crystal") {
            1
        } else if id == "minecraft:air" {
            2
        } else if id == "minecraft:dirt" {
            3
        } else if id.starts_with("tiberium:column") {
            4
        } else if id == "minecraft:coarse_dirt" {
            7
        } else {
            5
        };
        Some(BlockStateId(n))
    }
}

pub struct Assets {
    pub registry: Registry,
}

pub struct Pack {
    pub assets: Assets,
}

pub struct Game<'a> {
    pub pack: Pack,
    _marker: PhantomData<&'a ()>,
}

impl<'a> Game<'a> {
    pub fn new() -> Self {
        Game {
            pack: Pack {
                assets: Assets { registry: Registry },
            },
            _marker: PhantomData,
        }
    }

    pub fn native_on(&self, _mod_id: &str) -> bool {
        true
    }
    pub fn native_window(&self) -> bool {
        false
    }
    pub fn native_acting_player(&self) -> Option<NativeServerPlayer> {
        FAKE_PLAYER
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .clone()
    }
    pub fn native_server_players(&self) -> Vec<NativeServerPlayer> {
        Vec::new()
    }
    pub fn native_block(&self, pos: [i32; 3]) -> String {
        {
            let map = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
            if let Some(name) = map.get(&pos) {
                return (*name).to_string();
            }
        }
        // Пустое место — это воздух, как в игре.
        String::from("minecraft:air")
    }
    pub fn native_block_property(&self, pos: [i32; 3], key: &str) -> Option<String> {
        let props = FAKE_PROPS.lock().unwrap_or_else(|e| e.into_inner());
        props.get(&pos).and_then(|m| m.get(key)).cloned()
    }
    pub fn native_set_block(
        &mut self,
        _dimension: &str,
        pos: [i32; 3],
        state: BlockStateId,
        _flags: i32,
    ) -> bool {
        // Фальшивый мир помнит, что поставили: тесты смотрят на результат.
        {
            let mut map = FAKE_BLOCKS.lock().unwrap_or_else(|e| e.into_inner());
            if state.0 == 2 {
                map.insert(pos, "minecraft:air");
            } else if state.0 == 1 {
                map.insert(pos, "tiberium:crystal");
            } else if state.0 == 3 {
                map.insert(pos, "minecraft:dirt");
            } else if state.0 == 4 {
                map.insert(pos, "tiberium:column");
            } else if state.0 == 7 {
                map.insert(pos, "minecraft:coarse_dirt");
            } else {
                map.insert(pos, "minecraft:stone");
            }
        }
        true
    }
    pub fn native_set_block_property_with(
        &mut self,
        pos: [i32; 3],
        key: &str,
        value: &str,
        _flags: i32,
    ) -> bool {
        let mut props = FAKE_PROPS.lock().unwrap_or_else(|e| e.into_inner());
        props
            .entry(pos)
            .or_default()
            .insert(key.to_string(), value.to_string());
        true
    }
    pub fn native_run_command(&mut self, _line: &str) -> bool {
        true
    }
    pub fn native_action_bar(&mut self, _uuid: u128, _line: Text) -> bool {
        true
    }
    pub fn native_take_items(&mut self, _item: &str, _count: u32) -> u32 {
        0
    }
    pub fn native_give_items(&mut self, _item: &str, _count: u32) -> u32 {
        0
    }
    pub fn native_day_time(&self) -> i64 {
        0
    }

    // --- целевые функции хуков ---

    pub fn player_tick(&mut self) {
        let game: &mut crate::game::Game<'_> = &mut *self;
// Хук: конец серверного тика игрока. Здесь крутится рост полей тиберия.
fn tiberium_player_tick(game: &mut crate::game::Game<'_>) {
    crate::game::tiberium::player_tick(game);
}
        tiberium_player_tick(game);
    }

    pub fn tick(&mut self) {
        let game: &mut crate::game::Game<'_> = &mut *self;
// Хук: общий тик игры. На серверном потоке здесь идут отравление и молнии шторма.
fn tiberium_tick(game: &mut crate::game::Game<'_>) {
    crate::game::tiberium::tick(game);
}
        tiberium_tick(game);
    }

    pub fn use_item(&mut self, stack: &ItemStack, claimed: &mut bool) {
        let game: &mut crate::game::Game<'_> = &mut *self;
        let stack: &horizon_client::items::ItemStack = stack;
        let claimed: &mut bool = claimed;
// Хук: игрок использует предмет в воздухе (правый клик).
fn tiberium_use_item(
    game: &mut crate::game::Game<'_>,
    stack: &horizon_client::items::ItemStack,
    claimed: &mut bool,
) {
    crate::game::tiberium::use_item(game, stack, claimed);
}
        tiberium_use_item(game, stack, claimed);
    }

    pub fn use_item_on(&mut self, stack: &ItemStack, pos: [i32; 3], face: [i32; 3], claimed: &mut bool) {
        let game: &mut crate::game::Game<'_> = &mut *self;
        let stack: &horizon_client::items::ItemStack = stack;
        let pos: [i32; 3] = pos;
        let face: [i32; 3] = face;
        let claimed: &mut bool = claimed;
// Хук: игрок использует предмет по блоку (правый клик по кристаллу).
fn tiberium_use_item_on(
    game: &mut crate::game::Game<'_>,
    stack: &horizon_client::items::ItemStack,
    pos: [i32; 3],
    face: [i32; 3],
    claimed: &mut bool,
) {
    crate::game::tiberium::use_item_on(game, stack, pos, face, claimed);
}
        tiberium_use_item_on(game, stack, pos, face, claimed);
    }

    pub fn item_picked_up(&mut self, player: u128, item: &str, count: u32, canceled: &mut bool) {
        let game: &mut crate::game::Game<'_> = &mut *self;
        let player: u128 = player;
        let item: &str = item;
        let count: u32 = count;
        let canceled: &mut bool = canceled;
// Хук: игрок подобрал предмет. Осколок без капсулы заражает.
fn tiberium_item_picked_up(
    game: &mut crate::game::Game<'_>,
    player: u128,
    item: &str,
    count: u32,
    canceled: &mut bool,
) {
    crate::game::tiberium::item_picked_up(game, player, item, count, canceled);
}
        tiberium_item_picked_up(game, player, item, count, canceled);
    }

    pub fn on_equip(&mut self, slot: &str, new: Option<&ItemStack>) {
        let game: &mut crate::game::Game<'_> = &mut *self;
        let slot: &str = slot;
        let new: Option<&horizon_client::items::ItemStack> = new;
// Хук: игрок сменил броню. Отслеживаем био-костюм.
fn tiberium_on_equip(
    game: &mut crate::game::Game<'_>,
    slot: &str,
    new: Option<&horizon_client::items::ItemStack>,
) {
    crate::game::tiberium::on_equip(game, slot, new);
}
        tiberium_on_equip(game, slot, new);
    }

    pub fn compute_fog_color(&self, partial: f32, camera: [f64; 3], fog_type: FogType, rgb: &mut [f32; 3]) {
        let game: &crate::game::Game<'_> = self;
        let partial: f32 = partial;
        let camera: [f64; 3] = camera;
        let fog_type: horizon_client::fog::FogType = fog_type;
        let rgb: &mut [f32; 3] = rgb;
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
        tiberium_compute_fog_color(game, partial, camera, fog_type, rgb);
    }

    pub fn camera_shake(&self, partial: f32, shake: &mut NativeShake) {
        let game: &crate::game::Game<'_> = self;
        let partial: f32 = partial;
        let shake: &mut horizon_client::mod_api::NativeShake = shake;
// Хук: тряска камеры. Во время ионного шторма землю под ногами подрагивает.
fn tiberium_camera_shake(
    game: &crate::game::Game<'_>,
    partial: f32,
    shake: &mut horizon_client::mod_api::NativeShake,
) {
    crate::game::tiberium::camera_shake(game, partial, shake);
}
        tiberium_camera_shake(game, partial, shake);
    }
}

/// Уровень: в Horizon хук block_ignite вешается на GameLevel, а не на Game.
pub struct GameLevel<'a> {
    _marker: PhantomData<&'a ()>,
}

impl<'a> GameLevel<'a> {

    pub fn block_ignite(&self, dimension: Dimension, player: Option<u128>, pos: BlockPos, cause: &str, cancel: &mut bool) {
        let game: &crate::game::GameLevel<'_> = self;
        let dimension: horizon_world::level::Dimension = dimension;
        let player: Option<u128> = player;
        let pos: horizon_core::position::BlockPos = pos;
        let cause: &str = cause;
        let cancel: &mut bool = cancel;
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
        tiberium_block_ignite(game, dimension, player, pos, cause, cancel);
    }
}

/// Модуль мода: в игре он вставляется в crates/horizon-client/src/game.rs.
pub mod tiberium {
    include!("../../../../native/mixins/tiberium/runtime.rs");
}
