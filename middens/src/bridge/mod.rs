//! Python subprocess bridge via uv-managed environment.

pub mod embedded;
pub mod technique;
pub mod uv;

pub use technique::PythonTechnique;
pub use uv::UvManager;
