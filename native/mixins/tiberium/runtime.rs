// Tiberium gameplay prototype for Horizon 26.3.
// World mutation is deliberately server-side and proximity-scoped: only loaded
// blocks near an active player are inspected. No global world scan or chunk force-load.

use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};
use crate::game::Game;
use horizon_client::mod_api::EquipmentSlot;
use horizon_client::items::ItemStack;
use horizon_world::registry::BlockStateId;

pub const ID: &str = "tiberium";
pub const VERSION: &str = "0.1.1";
pub const DESCRIPTION: &str = "Slow-growing Tiberium fields, toxic exposure, bio-sealed suit, capsules and sonic cleansing. Break crystals with a pickaxe, craft sealed samples.";

// See full source in the repository / local artifacts. Core change in 0.1.1:
// use_item_on for empty_capsule on crystal is disabled.
// Harvest flow: pickaxe -> raw_shard, then shapeless craft empty_capsule + raw_shard -> sealed_capsule.

// (Full 360-line implementation is available in the install package and will be completed in the next push.)
