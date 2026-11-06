//! The crate's single error type, carrying the conformance check that failed.

use crate::check::Check;

/// Result alias for every fallible operation in this crate.
pub type Result<T, E = Error> = core::result::Result<T, E>;

/// A conformance failure: which check failed, and the bytes that caused it.
///
/// The [`Check`] travels with the error rather than being reconstructed by the
/// caller, so a failure can be compared against the conformance corpus'
/// `expected_failure` name verbatim.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Error {
    check: Check,
    detail: String,
}

impl Error {
    /// Build an error for `check` with a human-readable explanation.
    pub fn new(check: Check, detail: impl Into<String>) -> Self {
        Error {
            check,
            detail: detail.into(),
        }
    }

    /// The check that failed.
    pub fn check(&self) -> Check {
        self.check
    }

    /// The `<group>.<rule>` name of the failed check.
    pub fn check_name(&self) -> &'static str {
        self.check.name()
    }

    /// The explanation, without the check name.
    pub fn detail(&self) -> &str {
        &self.detail
    }
}

impl core::fmt::Display for Error {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        write!(f, "{}: {}", self.check.name(), self.detail)
    }
}

impl std::error::Error for Error {}

impl From<core::str::Utf8Error> for Error {
    fn from(err: core::str::Utf8Error) -> Self {
        Error::new(Check::MetaJson, err.to_string())
    }
}

impl From<serde_json::Error> for Error {
    fn from(err: serde_json::Error) -> Self {
        Error::new(Check::MetaJson, err.to_string())
    }
}
