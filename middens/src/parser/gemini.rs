use std::path::Path;
use anyhow::Result;
use crate::session::{Session, SourceTool};
use super::SessionParser;

pub struct GeminiParser;

impl SessionParser for GeminiParser {
    fn source_tool(&self) -> SourceTool { SourceTool::GeminiCli }
    fn can_parse(&self, _path: &Path) -> bool { false }
    fn parse(&self, _path: &Path) -> Result<Vec<Session>> { Ok(vec![]) }
}
