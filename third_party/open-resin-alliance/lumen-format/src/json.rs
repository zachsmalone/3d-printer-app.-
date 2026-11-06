//! Typed models for the JSON chunks: `META` (with its `sectors` entries),
//! `PROF` and `LROV`.
//!
//! META, a `META.sectors` entry, a `PROF` profile's `settings` block and an
//! `LROV` payload all draw on the same field namespace, so they share [`Timing`].
//! Unknown JSON keys are preserved in `Timing::extra` rather than dropped, which
//! is what lets this crate re-emit a chunk it did not fully understand
//! ([`spec/16-versioning.md`] section 10.2).
//!
//! Durations are whole milliseconds, lengths are integer micrometers and speeds
//! are integer micrometers per minute, so all three are modelled as integers and
//! nothing below one millisecond is expressible. Floating-point JSON syntax is
//! accepted for every field the specification calls an ordinary number, which is
//! what a temperature, an energy, a percentage or a density is.

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

/// The ten fields META must carry ([`spec/17-validation.md`] section 11.2).
pub const REQUIRED_META_FIELDS: [&str; 10] = [
    "meta_version",
    "normal_exposure_ms",
    "bottom_exposure_ms",
    "bottom_layer_count",
    "transition_layer_count",
    "layer_height_um",
    "lift_slow_distance_um",
    "lift_slow_speed_um_min",
    "retract_fast_distance_um",
    "retract_fast_speed_um_min",
];

/// The timing, motion, PWM and temperature namespace shared by META, a
/// `META.sectors` entry, `PROF.settings` and an `LROV` payload.
///
/// Every field is optional: META requires some of them, a sector entry or an
/// `LROV` payload supplies only what it changes, and a `PROF` supplies all of
/// them. A `bottom_*` field that is absent equals its normal counterpart
/// ([`spec/14-layer-timing.md`] section 8).
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Timing {
    /// Default layer thickness in micrometers.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub layer_height_um: Option<u32>,
    /// Exposure time for normal layers, in milliseconds.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub normal_exposure_ms: Option<u32>,
    /// Exposure time for bottom layers, in milliseconds.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub bottom_exposure_ms: Option<u32>,
    /// How many layers the bottom range holds.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub bottom_layer_count: Option<u32>,
    /// How many layers interpolate between bottom and normal.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub transition_layer_count: Option<u32>,

    /// Lift, slow segment: the peel. Distance of that one segment.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub lift_slow_distance_um: Option<u32>,
    /// Lift, slow segment speed.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub lift_slow_speed_um_min: Option<u32>,
    /// Lift, fast segment: the remainder. `0` makes the lift single-stage.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub lift_fast_distance_um: Option<u32>,
    /// Lift, fast segment speed.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub lift_fast_speed_um_min: Option<u32>,
    /// Retract, fast segment: most of the return. Distance of that one segment.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub retract_fast_distance_um: Option<u32>,
    /// Retract, fast segment speed.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub retract_fast_speed_um_min: Option<u32>,
    /// Retract, slow segment: the final approach. `0` makes the retract single-stage.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub retract_slow_distance_um: Option<u32>,
    /// Retract, slow segment speed.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub retract_slow_speed_um_min: Option<u32>,

    /// Bottom-layer lift, slow segment distance.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub bottom_lift_slow_distance_um: Option<u32>,
    /// Bottom-layer lift, slow segment speed.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub bottom_lift_slow_speed_um_min: Option<u32>,
    /// Bottom-layer lift, fast segment distance.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub bottom_lift_fast_distance_um: Option<u32>,
    /// Bottom-layer lift, fast segment speed.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub bottom_lift_fast_speed_um_min: Option<u32>,
    /// Bottom-layer retract, fast segment distance.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub bottom_retract_fast_distance_um: Option<u32>,
    /// Bottom-layer retract, fast segment speed.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub bottom_retract_fast_speed_um_min: Option<u32>,
    /// Bottom-layer retract, slow segment distance.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub bottom_retract_slow_distance_um: Option<u32>,
    /// Bottom-layer retract, slow segment speed.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub bottom_retract_slow_speed_um_min: Option<u32>,

    /// Pause before curing, in milliseconds.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub wait_time_before_cure_ms: Option<u32>,
    /// Pause after curing, in milliseconds.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub wait_time_after_cure_ms: Option<u32>,
    /// Pause after the lift, in milliseconds.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub wait_time_after_lift_ms: Option<u32>,
    /// Bottom-layer pause before curing, in milliseconds.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub bottom_wait_time_before_cure_ms: Option<u32>,
    /// Bottom-layer pause after curing, in milliseconds.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub bottom_wait_time_after_cure_ms: Option<u32>,
    /// Bottom-layer pause after the lift, in milliseconds.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub bottom_wait_time_after_lift_ms: Option<u32>,

    /// Light PWM for normal layers, `0`-`255`.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub light_pwm: Option<u32>,
    /// Light PWM for bottom layers, `0`-`255`.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub bottom_light_pwm: Option<u32>,

    /// Chamber target temperature in Celsius.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub chamber_temperature_c: Option<f64>,
    /// Vat target temperature in Celsius.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub vat_temperature_c: Option<f64>,

    /// Experimental resin working curve.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub cure_curve: Option<CureCurve>,

    /// Unknown keys, preserved verbatim.
    ///
    /// In a META payload the schema's own `extra` object also lands here, under
    /// the key `"extra"`; see [`Timing::vendor_extra`].
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}

impl Timing {
    /// The META or PROF `extra` object, if the payload carried one.
    pub fn vendor_extra(&self) -> Option<&Value> {
        self.extra.get("extra")
    }

    /// Every field name this namespace defines, in schema order.
    pub fn field_names() -> &'static [&'static str] {
        &[
            "layer_height_um",
            "normal_exposure_ms",
            "bottom_exposure_ms",
            "bottom_layer_count",
            "transition_layer_count",
            "lift_slow_distance_um",
            "lift_slow_speed_um_min",
            "lift_fast_distance_um",
            "lift_fast_speed_um_min",
            "retract_fast_distance_um",
            "retract_fast_speed_um_min",
            "retract_slow_distance_um",
            "retract_slow_speed_um_min",
            "bottom_lift_slow_distance_um",
            "bottom_lift_slow_speed_um_min",
            "bottom_lift_fast_distance_um",
            "bottom_lift_fast_speed_um_min",
            "bottom_retract_fast_distance_um",
            "bottom_retract_fast_speed_um_min",
            "bottom_retract_slow_distance_um",
            "bottom_retract_slow_speed_um_min",
            "wait_time_before_cure_ms",
            "wait_time_after_cure_ms",
            "wait_time_after_lift_ms",
            "bottom_wait_time_before_cure_ms",
            "bottom_wait_time_after_cure_ms",
            "bottom_wait_time_after_lift_ms",
            "light_pwm",
            "bottom_light_pwm",
            "chamber_temperature_c",
            "vat_temperature_c",
            "cure_curve",
        ]
    }

    /// Whether every field in `names` is present in the raw payload.
    ///
    /// `self` alone cannot answer this: a field that was absent and a field that
    /// was explicitly `null` deserialize alike, so presence must be read from
    /// the raw JSON object.
    pub fn missing_from(object: &Map<String, Value>, names: &[&str]) -> Vec<String> {
        names
            .iter()
            .filter(|name| !object.contains_key(**name))
            .map(|name| (*name).to_string())
            .collect()
    }
}

/// The experimental resin working curve: Beer-Lambert parameters.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct CureCurve {
    /// Penetration depth in micrometers.
    pub dp_um: f64,
    /// Critical exposure in mJ/cm^2.
    pub ec_mj_cm2: f64,
    /// Base energy in mJ/cm^2.
    pub e0_mj_cm2: f64,
}

/// One entry of the material library.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Material {
    /// Material name. Required and non-empty when the array is present.
    #[serde(default)]
    pub name: String,
    /// Brand, e.g. `DragonFruit`.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub brand: Option<String>,
    /// Family, e.g. `standard`.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub family: Option<String>,
    /// Density in grams per millilitre.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub density_g_ml: Option<f64>,
    /// Display color.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub color_rgba: Option<[u8; 4]>,
    /// Bottle price, vendor metadata.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub bottle_price: Option<f64>,
    /// Bottle capacity in millilitres, vendor metadata.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub bottle_capacity_ml: Option<f64>,
    /// Unknown keys, preserved verbatim.
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}

/// Printer identity, as carried by META and `PROF.compatible_printers`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Printer {
    /// Printer or model name.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub name: Option<String>,
    /// Manufacturer.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub manufacturer: Option<String>,
    /// Firmware version.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub firmware_version: Option<String>,
    /// Serial number.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub serial: Option<String>,
    /// Display width in pixels.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub display_width_px: Option<u32>,
    /// Display height in pixels.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub display_height_px: Option<u32>,
    /// Pixel pitch in micrometers.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub pixel_size_um: Option<u32>,
    /// Build plate X dimension in micrometers.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub build_width_um: Option<u32>,
    /// Build plate Y dimension in micrometers.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub build_depth_um: Option<u32>,
    /// Build plate Z dimension in micrometers.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub build_height_um: Option<u32>,
    /// Panel bit depth.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub bit_depth: Option<u32>,
    /// Unknown keys, preserved verbatim.
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}

/// A printer a profile is known to fit, as a model pattern plus display hints.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct CompatiblePrinter {
    /// Manufacturer.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub manufacturer: Option<String>,
    /// Glob-like model pattern, e.g. `Ares 12K*`.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub model_pattern: Option<String>,
    /// Display width in pixels.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub display_width_px: Option<u32>,
    /// Display height in pixels.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub display_height_px: Option<u32>,
    /// Pixel pitch in micrometers.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub pixel_size_um: Option<u32>,
    /// Unknown keys, preserved verbatim.
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}

/// Anti-aliasing settings, informational to a printer.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct AntiAliasing {
    /// Whether AA was applied.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub enabled: Option<bool>,
    /// AA level.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub level: Option<u32>,
    /// AA mode, e.g. `blur`.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub mode: Option<String>,
    /// Floor applied to AA alpha, in percent.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub minimum_alpha_percent: Option<f64>,
    /// Blur brush radius in pixels.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub blur_brush_radius_px: Option<u32>,
    /// Blur brush kernel.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub blur_brush_kernel: Option<String>,
    /// Blur brush X sigma.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub blur_brush_sigma_x: Option<f64>,
    /// Blur brush Y sigma.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub blur_brush_sigma_y: Option<f64>,
    /// Z-blend look-back span.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub z_blend_look_back: Option<u32>,
    /// Z-blend fade distance in pixels.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub z_blend_fade_px: Option<u32>,
    /// Whether dithering was applied.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub dither_enabled: Option<bool>,
    /// Unknown keys, preserved verbatim.
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}

/// Per-axis scale compensation in percent.
#[derive(Debug, Clone, Copy, Default, PartialEq, Serialize, Deserialize)]
pub struct ScaleCompensation {
    /// X axis.
    #[serde(default)]
    pub x: f64,
    /// Y axis.
    #[serde(default)]
    pub y: f64,
    /// Z axis.
    #[serde(default)]
    pub z: f64,
}

/// Slicer attribution.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Slicer {
    /// Slicer name.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub name: Option<String>,
    /// Slicer version.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub version: Option<String>,
    /// Slicer URL.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub url: Option<String>,
    /// Unknown keys, preserved verbatim.
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}

/// The `META` chunk: the resolved parameters for this print job.
///
/// Timing fields are flattened in, exactly as they sit at the top level of the
/// JSON object; see [`Timing`].
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Meta {
    /// Schema version of the META payload.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub meta_version: Option<u32>,
    /// Timing, motion, PWM and temperature fields.
    #[serde(flatten)]
    pub timing: Timing,
    /// Authoritative material library for this print.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub materials: Option<Vec<Material>>,
    /// One entry per non-zero sector this print uses, each carrying that
    /// sector's identity and the base timing fields it changes.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub sectors: Option<Vec<Sector>>,
    /// Printer identity.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub printer: Option<Printer>,
    /// Anti-aliasing settings, informational.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub anti_aliasing: Option<AntiAliasing>,
    /// Per-axis scale compensation.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub scale_compensation_pct: Option<ScaleCompensation>,
    /// Estimated print time in whole seconds, informational.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub estimated_print_time_sec: Option<u32>,
    /// Estimated resin volume in millilitres, informational.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub estimated_resin_volume_ml: Option<f64>,
    /// Slicer attribution.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub slicer: Option<Slicer>,
}

impl Meta {
    /// The META `extra` object, if the payload carried one.
    pub fn extra(&self) -> Option<&Value> {
        self.timing.vendor_extra()
    }
}

/// The `PROF` chunk: a named, versioned, reusable print profile.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Profile {
    /// Profile name. Required and non-empty.
    #[serde(default)]
    pub profile_name: String,
    /// Profile version. Required and non-empty.
    #[serde(default)]
    pub profile_version: String,
    /// One of `material`, `printer`, `combined`. Required.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub profile_type: Option<String>,
    /// Unique identifier for deduplication.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub profile_uuid: Option<String>,
    /// Attribution.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub author: Option<String>,
    /// Creation timestamp.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub created_unix_sec: Option<u64>,
    /// Free-form description.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub description: Option<String>,
    /// Printer compatibility hints.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub compatible_printers: Option<Vec<CompatiblePrinter>>,
    /// Printer definition, for a `printer` or `combined` profile.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub printer: Option<Printer>,
    /// The profile's settings, in META's field names. Required.
    #[serde(default)]
    pub settings: Timing,
    /// Anti-aliasing preferences.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub anti_aliasing: Option<AntiAliasing>,
    /// Material library, same schema and indexing as `META.materials`.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub materials: Option<Vec<Material>>,
    /// Per-axis scale compensation.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub scale_compensation_pct: Option<ScaleCompensation>,
    /// Vendor metadata.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub extra: Option<Value>,
}

/// A `META.sectors` entry: one non-zero sector's identity and base timing.
///
/// The entry carries only what differs from META's own values: every timing
/// field it leaves out is inherited from META's, field by field, and a sector
/// with no entry at all - sector 0, the primary one, always - resolves from META
/// alone ([`spec/14-layer-timing.md`] section 8). A sector carries no material
/// until its entry names one.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Sector {
    /// Sector identifier. `0` is reserved for the implicit primary sector, so an
    /// entry carries `>= 1`.
    #[serde(default)]
    pub sector_id: u32,
    /// Display name.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub name: Option<String>,
    /// Index into `META.materials`. Absent means no material.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub material_index: Option<u32>,
    /// Display hint overriding the material's color for this sector.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub color_rgba: Option<[u8; 4]>,
    /// Base timing for this sector; absent fields inherit from META.
    #[serde(flatten)]
    pub timing: Timing,
}
