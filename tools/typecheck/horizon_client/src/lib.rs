//! Заглушка API Horizon: сигнатуры взяты один в один из исходников
//! horizon-rust/horizon на коммите 66f3981. Нужна, чтобы проверить типы
//! нативной части мода без сборки всей игры.

extern crate self as horizon_client;

pub mod mod_api {
    #[derive(Clone, Debug)]
    pub struct NativeServerPlayer {
        pub uuid: u128,
        pub name: String,
        pub dimension: String,
        pub position: [f64; 3],
        pub game_mode: i32,
        pub health: f32,
    }

    #[derive(Clone, Copy, Debug, Default)]
    pub struct NativeShake {
        pub pitch: f32,
        pub yaw: f32,
        pub roll: f32,
        pub offset: [f32; 3],
    }
}

pub mod items {
    use std::sync::Arc;

    #[derive(Clone, Debug, PartialEq)]
    pub struct ItemStack {
        pub item: Arc<str>,
        pub count: u32,
        pub damage: u32,
        pub extra: Option<Box<u8>>,
    }
}

pub mod text {
    #[derive(Clone, Debug)]
    pub struct Text(pub String);
    impl Text {
        pub fn literal(s: &str) -> Self {
            Text(s.to_string())
        }
    }
}

pub mod fog {
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum FogType {
        Atmospheric,
        Water,
        Lava,
        PowderSnow,
    }
}

pub mod game;
