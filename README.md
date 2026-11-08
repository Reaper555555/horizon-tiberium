# Tiberium for Horizon

Mod for Horizon (Minecraft-like, Rust). Inspired by Command & Conquer Tiberium.

**Current version: 0.1.22**

## Install
Copy from the release / install zip:
- `horizon-mods/tiberium.hmod`
- `horizon-native-mods/tiberium-0.1.22.hnmod`

Then run **Native Build** in Horizon.

## Growth (0.1.22)
- **Fields first**: crystals expand sideways, 5 angular stages on a single block.
- **One tower per 64×64 region**, only after ~100 crystals within 100 blocks.
- Strong desiccation: leaves strip, grass dies, soil dries; no green carpet traces.
- Water absorption, infection, bio-suit, sonic pylon/gun.

## Source layout
- `content/` — .hmod assets (blockstates, models, recipes)
- `native/` — .hnmod mixins (`runtime.rs`, hooks)

## License
Prototype / fan work. Tiberium is a trademark of its respective owners.
