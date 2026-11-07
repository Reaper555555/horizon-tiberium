# Packages

Ready-to-install archive:

**`tiberium-0.1.1-install.zip`**

Contents (drop into the root of your Horizon instance):

```
horizon-mods/tiberium.hmod
horizon-native-mods/tiberium-0.1.1.hnmod
```

## Where to get it

1. From the Grok conversation artifacts (file `tiberium-0.1.1-install.zip`).
2. Or rebuild from source:

```bash
# Content mod
cd content && zip -r ../packages/tiberium-0.1.1.hmod .

# Native mod
cd native && zip -r ../packages/tiberium-0.1.1.hnmod .

# Install zip
mkdir -p /tmp/inst/horizon-mods /tmp/inst/horizon-native-mods
cp packages/tiberium-0.1.1.hmod /tmp/inst/horizon-mods/tiberium.hmod
cp packages/tiberium-0.1.1.hnmod /tmp/inst/horizon-native-mods/
cd /tmp/inst && zip -r tiberium-0.1.1-install.zip .
```

Then unpack the install zip into the game folder (next to `options.txt`).
