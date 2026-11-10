#!/usr/bin/env python3
"""Генерирует заглушку игрового контекста для проверки типов нативной части.

Horizon-mixins вставляет исходники хелперов как элементы (items) внутрь
целевой функции. include! так не умеет, поэтому хелперы копируются в тело
функции буквально — ровно то, что делает инструмент.
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))
HELPERS = os.path.abspath(os.path.join(HERE, "..", "..", "native", "mixins", "tiberium"))

# helper -> (целевая функция, параметры цели, аргументы вызова)
TARGETS = [
    ("player_tick.rs", "native_player_tick", "", "self"),
    ("tick.rs", "native_tick", "", "self"),
    ("use_item.rs", "native_use_item",
     "stack: &ItemStack, claimed: &mut bool", "self, stack, claimed"),
    ("use_item_on.rs", "native_use_item_on",
     "stack: &ItemStack, pos: [i32; 3], face: [i32; 3], claimed: &mut bool",
     "self, stack, pos, face, claimed"),
    ("item_picked_up.rs", "native_item_picked_up",
     "player: u128, item: &str, count: u32, canceled: &mut bool",
     "self, player, item, count, canceled"),
    ("on_equip.rs", "native_on_equip", "slot: &str, new: Option<&ItemStack>", "self, slot, new"),
    ("compute_fog_color.rs", "native_compute_fog_color",
     "partial: f32, camera: [f64; 3], fog_type: FogType, rgb: &mut [f32; 3]",
     "self, partial, camera, fog_type, rgb"),
    ("camera_shake.rs", "native_camera_shake", "partial: f32, shake: &mut NativeShake",
     "self, partial, shake"),
    ("block_ignite.rs", "native_block_ignite",
     "dimension: Dimension, player: Option<u128>, pos: BlockPos, cause: &str, cancel: &mut bool",
     "self, dimension, player, pos, cause, cancel"),
]

HEADER = '''//! Заглушка игрового контекста Horizon: те же сигнатуры, что и в игре.
//! Сгенерировано tools/typecheck/gen_stub.py — не править руками.

use std::marker::PhantomData;

use crate::fog::FogType;
use crate::items::ItemStack;
use crate::mod_api::{NativeServerPlayer, NativeShake};
use crate::text::Text;
use horizon_core::position::BlockPos;
use horizon_world::level::Dimension;
use horizon_world::registry::BlockStateId;

pub struct Registry;

impl Registry {
    pub fn default_state(&self, _id: &str) -> Option<BlockStateId> {
        None
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
        None
    }
    pub fn native_server_players(&self) -> Vec<NativeServerPlayer> {
        Vec::new()
    }
    pub fn native_block(&self, _pos: [i32; 3]) -> String {
        String::new()
    }
    pub fn native_block_property(&self, _pos: [i32; 3], _key: &str) -> Option<String> {
        None
    }
    pub fn native_set_block(
        &mut self,
        _dimension: &str,
        _pos: [i32; 3],
        _state: BlockStateId,
        _flags: i32,
    ) -> bool {
        true
    }
    pub fn native_set_block_property_with(
        &mut self,
        _pos: [i32; 3],
        _key: &str,
        _value: &str,
        _flags: i32,
    ) -> bool {
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
'''

FOOTER = '''}

/// Модуль мода: в игре он вставляется в crates/horizon-client/src/game.rs.
pub mod tiberium {
    include!("../../../../native/mixins/tiberium/runtime.rs");
}
'''


def helper_fn_name(text):
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("fn "):
            return line[3:].split("(")[0].strip()
    raise SystemExit("в хелперере нет fn")


def main():
    out = [HEADER]
    for helper, target, params, args in TARGETS:
        path = os.path.join(HELPERS, helper)
        body = open(path, encoding="utf-8").read().rstrip()
        name = helper_fn_name(body)
        out.append(f"""
    pub fn {target}(&mut self{", " + params if params else ""}) {{
{body}
        {name}({args});
    }}
""")
    out.append(FOOTER)
    dest = os.path.join(HERE, "horizon_client", "src", "game.rs")
    with open(dest, "w", encoding="utf-8") as f:
        f.write("".join(out))
    print(f"заглушка обновлена: {dest}")


if __name__ == "__main__":
    main()
