//! The JSON chunks: `META`, `PROF` and `LROV`
//! ([`spec/05-meta.md`], [`spec/06-prof.md`], [`spec/08-print-control.md`]).
//!
//! `META` and `PROF` are objects of their own; an `LROV` payload is one
//! `(layer, sector)`'s timing delta, an object in the same field namespace META
//! and a sector entry use.

use crate::check::Check;
use crate::error::{Error, Result};
use crate::json::{Meta, Profile, Timing};
use serde::de::DeserializeOwned;
use serde::Serialize;

/// Deserialize a JSON chunk payload.
///
/// Every JSON chunk reports the same check on a shape failure: the corpus has
/// no per-chunk JSON variant, and a caller that cares about a specific group
/// validates the parsed value afterwards.
fn from_json<T: DeserializeOwned>(payload: &[u8]) -> Result<T> {
    serde_json::from_slice(payload).map_err(|e| {
        Error::new(
            Check::MetaJson,
            format!("the JSON payload is not a valid object: {e}"),
        )
    })
}

/// Serialize a JSON chunk payload.
fn to_json<T: Serialize>(value: &T) -> Result<Vec<u8>> {
    serde_json::to_vec(value).map_err(|e| {
        Error::new(
            Check::MetaJson,
            format!("the JSON payload could not be serialized: {e}"),
        )
    })
}

/// Parse a `META` payload.
pub fn parse_meta(payload: &[u8]) -> Result<Meta> {
    from_json(payload)
}

/// Serialize a `META` payload.
pub fn meta_to_bytes(meta: &Meta) -> Result<Vec<u8>> {
    to_json(meta)
}

/// Parse a `PROF` payload.
pub fn parse_profile(payload: &[u8]) -> Result<Profile> {
    from_json(payload)
}

/// Serialize a `PROF` payload.
pub fn profile_to_bytes(profile: &Profile) -> Result<Vec<u8>> {
    to_json(profile)
}

/// Parse an `LROV` payload: one (layer, sector)'s timing delta.
///
/// Its own group reports the shape failure (`lrov.json`), because an `LROV`
/// payload is not a `META` and a caller needs to know which chunk was wrong.
pub fn parse_lrov(payload: &[u8]) -> Result<Timing> {
    serde_json::from_slice(payload).map_err(|e| {
        Error::new(
            Check::LrovJson,
            format!("the LROV payload is not a JSON object: {e}"),
        )
    })
}

/// Serialize an `LROV` payload.
pub fn lrov_to_bytes(timing: &Timing) -> Result<Vec<u8>> {
    serde_json::to_vec(timing).map_err(|e| {
        Error::new(
            Check::LrovJson,
            format!("the LROV payload could not be serialized: {e}"),
        )
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn meta_round_trips_and_preserves_unknown_keys() {
        let payload = br#"{
            "meta_version": 1,
            "normal_exposure_ms": 2500,
            "bottom_exposure_ms": 30000,
            "layer_height_um": 50,
            "vendor_extension": {"a": 1},
            "sectors": [{"sector_id": 1, "name": "Support", "normal_exposure_ms": 3000}]
        }"#;
        let meta = parse_meta(payload).unwrap();
        assert_eq!(meta.meta_version, Some(1));
        assert_eq!(meta.timing.normal_exposure_ms, Some(2500));
        // An unknown key is preserved rather than rejected or dropped.
        assert_eq!(
            meta.timing.extra.get("vendor_extension"),
            Some(&serde_json::json!({"a": 1}))
        );

        let sectors = meta.sectors.as_deref().expect("a sectors array");
        assert_eq!(sectors[0].sector_id, 1);
        assert_eq!(sectors[0].name.as_deref(), Some("Support"));
        assert_eq!(sectors[0].timing.normal_exposure_ms, Some(3000));

        let bytes = meta_to_bytes(&meta).unwrap();
        assert_eq!(parse_meta(&bytes).unwrap(), meta);
    }

    #[test]
    fn every_json_chunk_reports_its_group_on_bad_input() {
        assert_eq!(
            parse_meta(b"not json").unwrap_err().check(),
            Check::MetaJson
        );
        assert_eq!(parse_profile(b"[").unwrap_err().check(), Check::MetaJson);
        assert_eq!(parse_lrov(b"{}x").unwrap_err().check(), Check::LrovJson);
    }

    #[test]
    fn an_lrov_payload_is_a_flat_timing_object() {
        let timing = parse_lrov(br#"{"normal_exposure_ms": 2000, "light_pwm": 120}"#).unwrap();
        assert_eq!(timing.normal_exposure_ms, Some(2000));
        assert_eq!(timing.light_pwm, Some(120));
        assert_eq!(timing.bottom_layer_count, None);
        assert_eq!(
            parse_lrov(&lrov_to_bytes(&timing).unwrap()).unwrap(),
            timing
        );
    }
}
