#!/usr/bin/env python3
"""Генерирует заглушку игрового контекста для проверки типов нативной части.

Horizon-mixins вставляет исходники хелперов как элементы (items) внутрь
целевой функции. include! так не умеет, поэтому хелперы копируются в тело
функции буквально — ровно то, что делает инструмент.

Сигнатуры целевых функций взяты из исходников Horizon (crates/horizon-client/
src/game/native_hooks.rs) на коммите 66f3981f, а привязки — из
native/mixins/tiberium/horizon-mixin.toml. Заглушка объявляет привязку ровно
тем типом, который указан в toml, и присваивает ей значение из целевой
функции. Поэтому несовпадение (например, Game вместо GameLevel у хука
block_ignite) ломает сборку стенда, а не сборку игры.
"""

import os
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
MIXINS = os.path.join(ROOT, "native", "mixins", "tiberium")

# Настоящие цели хуков: impl -> ("&mut self" | "&self", "параметры").
# Источник: crates/horizon-client/src/game/native_hooks.rs @ 66f3981f.
TARGETS = {
    "player_tick": ("Game", "&mut self", ""),
    "tick": ("Game", "&mut self", ""),
    "use_item": ("Game", "&mut self", "stack: &ItemStack, claimed: &mut bool"),
    "use_item_on": (
        "Game",
        "&mut self",
        "stack: &ItemStack, pos: [i32; 3], face: [i32; 3], claimed: &mut bool",
    ),
    "item_picked_up": (
        "Game",
        "&mut self",
        "player: u128, item: &str, count: u32, canceled: &mut bool",
    ),
    "on_equip": ("Game", "&mut self", "slot: &str, new: Option<&ItemStack>"),
    "compute_fog_color": (
        "Game",
        "&self",
        "partial: f32, camera: [f64; 3], fog_type: FogType, rgb: &mut [f32; 3]",
    ),
    "camera_shake": ("Game", "&self", "partial: f32, shake: &mut NativeShake"),
    "block_ignite": (
        "GameLevel",
        "&self",
        "dimension: Dimension, player: Option<u128>, pos: BlockPos, "
        "cause: &str, cancel: &mut bool",
    ),
}

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
    with open(os.path.join(MIXINS, "horizon-mixin.toml"), "rb") as f:
        manifest = tomllib.load(f)

    out = [HEADER]
    methods = {"Game": [], "GameLevel": []}
    for injection in manifest.get("injection", []):
        hook = injection.get("hook")
        if hook not in TARGETS:
            raise SystemExit(f"неизвестный хук: {hook}")
        impl, receiver, params = TARGETS[hook]
        helper = injection["helper"]
        body = open(os.path.join(MIXINS, helper), encoding="utf-8").read().rstrip()
        name = helper_fn_name(body)

        # Привязки ровно те, что описаны в toml: тип и значение из целевой функции.
        binds = []
        for binding in injection.get("bindings", []):
            binds.append(f"        let {binding['name']}: {binding['ty']} = {binding['value']};")
        args = ", ".join(b["name"] for b in injection.get("bindings", []))
        sig = f"    pub fn {hook}({receiver}{', ' + params if params else ''}) {{"

        methods[impl].append(f"""
{sig}
{chr(10).join(binds)}
{body}
        {name}({args});
    }}
""")

    out.extend(methods["Game"])
    out.append(
        "}\n\n"
        "/// Уровень: в Horizon хук block_ignite вешается на GameLevel, а не на Game.\n"
        "pub struct GameLevel<'a> {\n    _marker: PhantomData<&'a ()>,\n}\n\n"
        "impl<'a> GameLevel<'a> {\n"
    )
    out.extend(methods["GameLevel"])
    out.append(FOOTER)

    dest = os.path.join(HERE, "horizon_client", "src", "game.rs")
    with open(dest, "w", encoding="utf-8") as f:
        f.write("".join(out))
    print(f"заглушка обновлена: {dest}")


if __name__ == "__main__":
    main()
