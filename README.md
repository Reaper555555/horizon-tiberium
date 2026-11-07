# Tiberium for Horizon (Minecraft 26.3 in Rust)

Alpha prototype of Tiberium from Command & Conquer: Tiberium universe.

## Features (0.1.1)

- **Crystals** grow in stages (seed → base → spire → crown), then spread sideways.
- **Soil infection** at different rates (dirt/grass fast, sand medium, stone slow).
- **Toxicity**: periodic damage near Tiberium or while holding raw shards unless wearing full bio-suit.
- **Bio-protection**: full 4-piece set grants complete immunity.
- **Harvest**: break crystals with a pickaxe → `raw_shard`. Craft `empty_capsule` + `raw_shard` → `sealed_capsule` (safe storage/fuel).
- **Sonic tools**: portable disruptor (consumes charges) and stationary pylons that slowly cleanse the area.

## Install

### Ready-to-use (recommended)

1. Download `tiberium-0.1.1-install.zip` from [Releases](https://github.com/Reaper555555/horizon-tiberium/releases) (or the Artifacts of this conversation).
2. Unpack into the **root of your Horizon game instance** (the folder that contains `options.txt` / `horizon-mods` / `horizon-native-mods`).
3. In the launcher: enable the content mod, and for the native mod let the launcher build a custom instance (first build takes time).

Contents of the install zip:

```
horizon-mods/tiberium.hmod
horizon-native-mods/tiberium-0.1.1.hnmod
```

### From source

- **Content mod** (`content/`): put the folder or the built `.hmod` into `horizon-mods/`.
- **Native mod** (`native/`): put the `.hnmod` (or the mixins folder + horizon-native.json) into `horizon-native-mods/` and let the Horizon launcher compile it against the pinned revision.

## Changelog

### 0.1.1
- Collection reworked: crystals must be broken with a pickaxe (drop raw shards).
- New shapeless recipe: empty capsule + raw shard → sealed capsule.
- Removed right-click harvest with empty capsule.

### 0.1.0
- Initial prototype by ChatGPT: growth, infection, toxicity, bio-suit, sonic tools, capsules.

## Licence

MIT (code & data). Textures are simple placeholders.
