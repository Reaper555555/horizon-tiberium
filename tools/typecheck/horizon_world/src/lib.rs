//! Заглушка: типы мира, которые использует мод Tiberium.
pub mod registry {
    #[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
    pub struct BlockStateId(pub u32);
}
pub mod level {
    #[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
    pub enum Dimension {
        Overworld,
        Nether,
        End,
    }
}
