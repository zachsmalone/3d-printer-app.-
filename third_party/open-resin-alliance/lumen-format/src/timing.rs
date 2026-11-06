//! The per-layer settings pipeline ([`spec/14-layer-timing.md`] section 8).
//!
//! Base values come from `META`, a `META.sectors` entry overrides them per
//! sector, the bottom and transition ranges blend bottom-prefixed values into
//! normal ones, and the `(layer, sector)`'s own `LROV` payload - at most one, so
//! there is nothing to fold in order - replaces what it carries.

use crate::check::Check;
use crate::error::{Error, Result};
use crate::json::{CureCurve, Meta, Sector, Timing, REQUIRED_META_FIELDS};

/// Light PWM when META carries none (`spec/05-meta.md` section 4.2).
const DEFAULT_LIGHT_PWM: u32 = 255;

/// The concrete timing of one `(layer, sector)` pair.
#[derive(Debug, Clone, PartialEq)]
pub struct Resolved {
    /// Layer thickness in micrometers.
    pub layer_height_um: u32,
    /// Exposure time for this layer, in milliseconds.
    pub exposure_ms: u32,
    /// Lift, slow segment distance.
    pub lift_slow_distance_um: u32,
    /// Lift, slow segment speed.
    pub lift_slow_speed_um_min: u32,
    /// Lift, fast segment distance.
    pub lift_fast_distance_um: u32,
    /// Lift, fast segment speed.
    pub lift_fast_speed_um_min: u32,
    /// Retract, fast segment distance.
    pub retract_fast_distance_um: u32,
    /// Retract, fast segment speed.
    pub retract_fast_speed_um_min: u32,
    /// Retract, slow segment distance.
    pub retract_slow_distance_um: u32,
    /// Retract, slow segment speed.
    pub retract_slow_speed_um_min: u32,
    /// Pause before curing, in milliseconds.
    pub wait_time_before_cure_ms: u32,
    /// Pause after curing, in milliseconds.
    pub wait_time_after_cure_ms: u32,
    /// Pause after the lift, in milliseconds.
    pub wait_time_after_lift_ms: u32,
    /// Light PWM for this layer.
    pub light_pwm: u32,
    /// Chamber target temperature, if any.
    pub chamber_temperature_c: Option<f64>,
    /// Vat target temperature, if any.
    pub vat_temperature_c: Option<f64>,
    /// The resin working curve, if any.
    pub cure_curve: Option<CureCurve>,
    /// Whether this layer is in the bottom range.
    pub is_bottom: bool,
    /// Whether this layer is in the interpolated transition range.
    pub is_transition: bool,
}

/// [`field_pair`] for a field named in both its normal and its `bottom_` form.
macro_rules! pair {
    ($meta:expr, $sector:expr, $normal:ident, $bottom:ident, $default:expr) => {
        field_pair($meta, $sector, |t| t.$normal, |t| t.$bottom, $default)
    };
}

/// Resolve one layer's timing.
///
/// `sector` is the `META.sectors` entry for `sector_id`, when the print defines
/// one; sector 0 has none by construction. `overrides` is that `(layer,
/// sector)`'s `LROV` payload, when it has one.
pub fn resolve(
    meta: &Meta,
    sector: Option<&Sector>,
    overrides: Option<&Timing>,
    layer: u32,
    sector_id: u32,
) -> Result<Resolved> {
    // The pipeline needs a concrete value for every required META field except
    // the schema version, which `validate` owns and a resolved layer never
    // depends on. Presence can only be read from the parsed `Option`s here.
    let missing: Vec<&str> = REQUIRED_META_FIELDS
        .iter()
        .copied()
        .filter(|name| *name != "meta_version")
        .filter(|name| !meta_carries(meta, name))
        .collect();
    if !missing.is_empty() {
        return Err(Error::new(
            Check::MetaRequiredFields,
            format!("META is missing {}", missing.join(", ")),
        ));
    }

    let timing = &meta.timing;
    // A `META.sectors` entry describes a non-zero sector, so it only speaks
    // for one; sector 0 has none by construction.
    let sect = match sector_id {
        0 => None,
        _ => sector.map(|definition| &definition.timing),
    };

    // Base values: META, with every field the sector definition carries
    // replacing the META value for that sector.
    let layer_height_um = merged(timing, sect, |t| t.layer_height_um).unwrap_or_default();
    let bottom_layer_count = merged(timing, sect, |t| t.bottom_layer_count).unwrap_or_default();
    let transition_layer_count =
        merged(timing, sect, |t| t.transition_layer_count).unwrap_or_default();
    let light_pwm = merged(timing, sect, |t| t.light_pwm).unwrap_or(DEFAULT_LIGHT_PWM);
    let bottom_light_pwm = merged(timing, sect, |t| t.bottom_light_pwm).unwrap_or(light_pwm);

    // The values the bottom and transition ranges blend, each as a (normal,
    // bottom) pair. An absent optional field resolves to `0`, which the spec
    // renders as a segment that is not performed, or no pause at all.
    let exposure = pair!(timing, sect, normal_exposure_ms, bottom_exposure_ms, 0);
    let lift_slow_distance = pair!(
        timing,
        sect,
        lift_slow_distance_um,
        bottom_lift_slow_distance_um,
        0
    );
    let lift_slow_speed = pair!(
        timing,
        sect,
        lift_slow_speed_um_min,
        bottom_lift_slow_speed_um_min,
        0
    );
    let lift_fast_distance = pair!(
        timing,
        sect,
        lift_fast_distance_um,
        bottom_lift_fast_distance_um,
        0
    );
    let lift_fast_speed = pair!(
        timing,
        sect,
        lift_fast_speed_um_min,
        bottom_lift_fast_speed_um_min,
        0
    );
    let retract_fast_distance = pair!(
        timing,
        sect,
        retract_fast_distance_um,
        bottom_retract_fast_distance_um,
        0
    );
    let retract_fast_speed = pair!(
        timing,
        sect,
        retract_fast_speed_um_min,
        bottom_retract_fast_speed_um_min,
        0
    );
    let retract_slow_distance = pair!(
        timing,
        sect,
        retract_slow_distance_um,
        bottom_retract_slow_distance_um,
        0
    );
    let retract_slow_speed = pair!(
        timing,
        sect,
        retract_slow_speed_um_min,
        bottom_retract_slow_speed_um_min,
        0
    );
    let wait_before_cure = pair!(
        timing,
        sect,
        wait_time_before_cure_ms,
        bottom_wait_time_before_cure_ms,
        0
    );
    let wait_after_cure = pair!(
        timing,
        sect,
        wait_time_after_cure_ms,
        bottom_wait_time_after_cure_ms,
        0
    );
    let wait_after_lift = pair!(
        timing,
        sect,
        wait_time_after_lift_ms,
        bottom_wait_time_after_lift_ms,
        0
    );

    // `u64` keeps `bottom + transition` from wrapping on a malformed META.
    let bottom = u64::from(bottom_layer_count);
    let transition = u64::from(transition_layer_count);
    let index = u64::from(layer);
    let stage = if index < bottom {
        Stage::Bottom
    } else if index < bottom + transition {
        // One step into the range is the first blend step, so `k` runs
        // `1..=transition_layer_count` and the first fully-normal layer,
        // `bottom + transition`, is the `k == N` case the formula collapses to
        // the normal value. Both counts are `u32`s widened before the `+ 1`, so
        // even `transition = u32::MAX` cannot overflow.
        Stage::Transition {
            k: index - bottom + 1,
            n: transition + 1,
        }
    } else {
        Stage::Normal
    };

    let mut resolved = Resolved {
        layer_height_um,
        exposure_ms: blend_u32(exposure, stage),
        lift_slow_distance_um: blend_u32(lift_slow_distance, stage),
        lift_slow_speed_um_min: blend_u32(lift_slow_speed, stage),
        lift_fast_distance_um: blend_u32(lift_fast_distance, stage),
        lift_fast_speed_um_min: blend_u32(lift_fast_speed, stage),
        retract_fast_distance_um: blend_u32(retract_fast_distance, stage),
        retract_fast_speed_um_min: blend_u32(retract_fast_speed, stage),
        retract_slow_distance_um: blend_u32(retract_slow_distance, stage),
        retract_slow_speed_um_min: blend_u32(retract_slow_speed, stage),
        wait_time_before_cure_ms: blend_u32(wait_before_cure, stage),
        wait_time_after_cure_ms: blend_u32(wait_after_cure, stage),
        wait_time_after_lift_ms: blend_u32(wait_after_lift, stage),
        // PWM is categorical: it switches at the first non-bottom layer instead
        // of interpolating.
        light_pwm: match stage {
            Stage::Bottom => bottom_light_pwm,
            _ => light_pwm,
        },
        chamber_temperature_c: merged(timing, sect, |t| t.chamber_temperature_c),
        vat_temperature_c: merged(timing, sect, |t| t.vat_temperature_c),
        cure_curve: merged(timing, sect, |t| t.cure_curve),
        is_bottom: matches!(stage, Stage::Bottom),
        is_transition: matches!(stage, Stage::Transition { .. }),
    };

    // A (layer, sector) has one override set or none, so this is a single
    // replacement rather than a fold: a field the payload leaves out keeps what
    // the pipeline resolved for it.
    if let Some(overrides) = overrides {
        fold_entry(&mut resolved, overrides);
    }

    Ok(resolved)
}

/// Which range a layer falls in.
#[derive(Clone, Copy)]
enum Stage {
    /// Below `bottom_layer_count`: bottom-prefixed values, verbatim.
    Bottom,
    /// At or beyond `bottom_layer_count + transition_layer_count`: normal values.
    Normal,
    /// Inside the transition range: the `k`th of `n` blend steps.
    Transition { k: u64, n: u64 },
}

/// One field's two forms, with an absent bottom form already folded onto the
/// normal one, which is what makes its interpolation a no-op.
#[derive(Clone, Copy)]
struct Blend<T> {
    /// The normal-layer value.
    normal: T,
    /// The bottom-layer value.
    bottom: T,
}

impl<T: Copy> Blend<T> {
    /// Pair `normal` with `bottom`, defaulting an absent `normal` to `default`
    /// and an absent `bottom` to the resolved normal value.
    fn new(normal: Option<T>, bottom: Option<T>, default: T) -> Self {
        let normal = normal.unwrap_or(default);
        Blend {
            normal,
            bottom: bottom.unwrap_or(normal),
        }
    }
}

/// A META field with the sector override applied.
///
/// `sector` is the definition's timing namespace, or `None` for sector 0.
fn merged<T: Copy>(
    meta: &Timing,
    sector: Option<&Timing>,
    get: impl Fn(&Timing) -> Option<T>,
) -> Option<T> {
    sector.and_then(&get).or_else(|| get(meta))
}

/// One field's `(normal, bottom)` pair, each with the sector override applied.
fn field_pair<T: Copy>(
    meta: &Timing,
    sector: Option<&Timing>,
    normal: impl Fn(&Timing) -> Option<T>,
    bottom: impl Fn(&Timing) -> Option<T>,
    default: T,
) -> Blend<T> {
    Blend::new(
        merged(meta, sector, normal),
        merged(meta, sector, bottom),
        default,
    )
}

/// Whether META carries a value for `name`, one of the fields the pipeline
/// needs ([`REQUIRED_META_FIELDS`] without `meta_version`).
///
/// [`resolve`] only receives the parsed struct, so unlike `validate`, which
/// reads the raw JSON object, it has nothing but the `Option`s to go on.
fn meta_carries(meta: &Meta, name: &str) -> bool {
    let timing = &meta.timing;
    match name {
        "normal_exposure_ms" => timing.normal_exposure_ms.is_some(),
        "bottom_exposure_ms" => timing.bottom_exposure_ms.is_some(),
        "bottom_layer_count" => timing.bottom_layer_count.is_some(),
        "transition_layer_count" => timing.transition_layer_count.is_some(),
        "layer_height_um" => timing.layer_height_um.is_some(),
        "lift_slow_distance_um" => timing.lift_slow_distance_um.is_some(),
        "lift_slow_speed_um_min" => timing.lift_slow_speed_um_min.is_some(),
        "retract_fast_distance_um" => timing.retract_fast_distance_um.is_some(),
        "retract_fast_speed_um_min" => timing.retract_fast_speed_um_min.is_some(),
        _ => false,
    }
}

/// An integer field at `stage`: verbatim at either end, blended in between.
///
/// The blend is the specification's exact integer form (§8), with `N = n` and
/// `k` the step:
///
/// ```text
/// value = round((bottom * (N - k) + normal * k) / N)
/// ```
///
/// `round` is half away from zero, which for the non-negative values here is
/// half **up**: a remainder of exactly half a unit rounds to the larger value.
/// The numerator is computed in `u128` and the doubling the tie needs is folded
/// into it, so no pair of `u32` values and no layer count a malformed META can
/// carry can overflow the intermediate or truncate the result: the value is a
/// convex combination of the two ends, so it lies between them and fits the
/// `u32` it came from.
fn blend_u32(field: Blend<u32>, stage: Stage) -> u32 {
    match stage {
        Stage::Bottom => field.bottom,
        Stage::Normal => field.normal,
        Stage::Transition { k, n } => {
            let bottom = u128::from(field.bottom);
            let normal = u128::from(field.normal);
            let numerator = bottom * (n - k) as u128 + normal * k as u128;
            // `floor(numerator / n + 1/2)`, written so that the half-unit is
            // exact: `(2 * numerator + n) / (2 * n)`. `n` is
            // `transition_layer_count + 1`, so it is never zero, and `k < n`
            // inside the range.
            ((2 * numerator + n as u128) / (2 * n as u128)) as u32
        }
    }
}

/// Replace the fields one `(layer, sector)`'s `LROV` payload carries.
///
/// The payload replaces only the fields it names, so an absent field keeps the
/// value the pipeline resolved for it. When it names a field in both its normal
/// and its `bottom_` form, the normal one wins: an `LROV` payload overrides the
/// layer's single resolved value, not the two ends of a blend.
fn fold_entry(resolved: &mut Resolved, over: &Timing) {
    if let Some(value) = over.layer_height_um {
        resolved.layer_height_um = value;
    }
    if let Some(value) = over.normal_exposure_ms.or(over.bottom_exposure_ms) {
        resolved.exposure_ms = value;
    }
    if let Some(value) = over
        .lift_slow_distance_um
        .or(over.bottom_lift_slow_distance_um)
    {
        resolved.lift_slow_distance_um = value;
    }
    if let Some(value) = over
        .lift_slow_speed_um_min
        .or(over.bottom_lift_slow_speed_um_min)
    {
        resolved.lift_slow_speed_um_min = value;
    }
    if let Some(value) = over
        .lift_fast_distance_um
        .or(over.bottom_lift_fast_distance_um)
    {
        resolved.lift_fast_distance_um = value;
    }
    if let Some(value) = over
        .lift_fast_speed_um_min
        .or(over.bottom_lift_fast_speed_um_min)
    {
        resolved.lift_fast_speed_um_min = value;
    }
    if let Some(value) = over
        .retract_fast_distance_um
        .or(over.bottom_retract_fast_distance_um)
    {
        resolved.retract_fast_distance_um = value;
    }
    if let Some(value) = over
        .retract_fast_speed_um_min
        .or(over.bottom_retract_fast_speed_um_min)
    {
        resolved.retract_fast_speed_um_min = value;
    }
    if let Some(value) = over
        .retract_slow_distance_um
        .or(over.bottom_retract_slow_distance_um)
    {
        resolved.retract_slow_distance_um = value;
    }
    if let Some(value) = over
        .retract_slow_speed_um_min
        .or(over.bottom_retract_slow_speed_um_min)
    {
        resolved.retract_slow_speed_um_min = value;
    }
    if let Some(value) = over
        .wait_time_before_cure_ms
        .or(over.bottom_wait_time_before_cure_ms)
    {
        resolved.wait_time_before_cure_ms = value;
    }
    if let Some(value) = over
        .wait_time_after_cure_ms
        .or(over.bottom_wait_time_after_cure_ms)
    {
        resolved.wait_time_after_cure_ms = value;
    }
    if let Some(value) = over
        .wait_time_after_lift_ms
        .or(over.bottom_wait_time_after_lift_ms)
    {
        resolved.wait_time_after_lift_ms = value;
    }
    if let Some(value) = over.light_pwm.or(over.bottom_light_pwm) {
        resolved.light_pwm = value;
    }
    if let Some(value) = over.chamber_temperature_c {
        resolved.chamber_temperature_c = Some(value);
    }
    if let Some(value) = over.vat_temperature_c {
        resolved.vat_temperature_c = Some(value);
    }
    if let Some(value) = over.cure_curve {
        resolved.cure_curve = Some(value);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// META with every required field, the optional four-segment motion, and the
    /// bottom counts the acceptance case names.
    fn meta() -> Meta {
        Meta {
            meta_version: Some(1),
            timing: Timing {
                layer_height_um: Some(50),
                normal_exposure_ms: Some(2500),
                bottom_exposure_ms: Some(30000),
                bottom_layer_count: Some(4),
                transition_layer_count: Some(8),
                lift_slow_distance_um: Some(5000),
                lift_slow_speed_um_min: Some(65000),
                lift_fast_distance_um: Some(3000),
                lift_fast_speed_um_min: Some(180000),
                retract_fast_distance_um: Some(5000),
                retract_fast_speed_um_min: Some(150000),
                retract_slow_distance_um: Some(3000),
                retract_slow_speed_um_min: Some(180000),
                wait_time_before_cure_ms: Some(1000),
                wait_time_after_cure_ms: Some(0),
                wait_time_after_lift_ms: Some(500),
                light_pwm: Some(255),
                ..Timing::default()
            },
            ..Meta::default()
        }
    }

    /// Sector 0's resolution, which is what most cases look at.
    fn at(meta: &Meta, layer: u32) -> Resolved {
        resolve(meta, None, None, layer, 0).unwrap()
    }

    #[test]
    fn exposure_blends_bottom_transition_and_normal() {
        let meta = meta();

        assert_eq!(at(&meta, 0).exposure_ms, 30000);
        assert_eq!(at(&meta, 3).exposure_ms, 30000);
        // Layer 4 is `k = 1` of `N = 9`:
        // (30000 * 8 + 2500 * 1) / 9 = 26944.44.. -> 26944.
        assert_eq!(at(&meta, 4).exposure_ms, 26944);
        // Layer 11 is `k = 8`: (30000 * 1 + 2500 * 8) / 9 = 5555.55.. -> 5556.
        assert_eq!(at(&meta, 11).exposure_ms, 5556);
        assert_eq!(at(&meta, 12).exposure_ms, 2500);

        assert_eq!(
            (at(&meta, 0).is_bottom, at(&meta, 0).is_transition),
            (true, false)
        );
        assert_eq!(
            (at(&meta, 3).is_bottom, at(&meta, 3).is_transition),
            (true, false)
        );
        assert_eq!(
            (at(&meta, 4).is_bottom, at(&meta, 4).is_transition),
            (false, true)
        );
        assert_eq!(
            (at(&meta, 11).is_bottom, at(&meta, 11).is_transition),
            (false, true)
        );
        assert_eq!(
            (at(&meta, 12).is_bottom, at(&meta, 12).is_transition),
            (false, false)
        );
        assert_eq!(
            (at(&meta, 400).is_bottom, at(&meta, 400).is_transition),
            (false, false)
        );
    }

    #[test]
    fn wait_times_interpolate_between_their_two_forms() {
        let mut meta = meta();
        meta.timing.bottom_wait_time_before_cure_ms = Some(10000);

        assert_eq!(at(&meta, 0).wait_time_before_cure_ms, 10000);
        // `k = 1` of `N = 9`: (10000 * 8 + 1000 * 1) / 9 = 9000 exactly.
        assert_eq!(at(&meta, 4).wait_time_before_cure_ms, 9000);
        assert_eq!(at(&meta, 12).wait_time_before_cure_ms, 1000);
        // A wait with no bottom form holds its normal value throughout.
        assert_eq!(at(&meta, 0).wait_time_after_lift_ms, 500);
        assert_eq!(at(&meta, 5).wait_time_after_lift_ms, 500);
    }

    #[test]
    fn absent_bottom_form_inherits_its_normal_value() {
        let meta = meta();
        // No `bottom_lift_fast_distance_um` in META, so a bottom layer lifts the
        // same as a normal one.
        assert_eq!(at(&meta, 0).lift_fast_distance_um, 3000);
        assert_eq!(at(&meta, 6).lift_fast_distance_um, 3000);
        assert_eq!(at(&meta, 40).lift_fast_distance_um, 3000);

        // An optional segment that is absent altogether is not performed.
        let mut without = meta.clone();
        without.timing.lift_fast_distance_um = None;
        assert_eq!(at(&without, 40).lift_fast_distance_um, 0);
    }

    #[test]
    fn interpolation_rounds_half_away_from_zero() {
        let mut meta = meta();
        meta.timing.bottom_lift_slow_distance_um = Some(6000);

        assert_eq!(at(&meta, 0).lift_slow_distance_um, 6000);
        // `k = 1` of `N = 9`: (6000 * 8 + 5000 * 1) / 9 = 5888.88.. -> 5889.
        assert_eq!(at(&meta, 4).lift_slow_distance_um, 5889);
        assert_eq!(at(&meta, 12).lift_slow_distance_um, 5000);

        // A one-layer transition makes `N = 2`, so an odd sum lands exactly on
        // the half: `(bottom + normal) / 2`. Truncation would take the smaller
        // value every time; the rule takes the larger, half away from zero.
        let mut half = meta.clone();
        half.timing.bottom_layer_count = Some(1);
        half.timing.transition_layer_count = Some(1);
        half.timing.lift_slow_distance_um = Some(5000);
        half.timing.bottom_lift_slow_distance_um = Some(5001);
        half.timing.normal_exposure_ms = Some(2500);
        half.timing.bottom_exposure_ms = Some(2501);
        half.timing.wait_time_after_lift_ms = Some(100);
        half.timing.bottom_wait_time_after_lift_ms = Some(101);

        assert_eq!(at(&half, 1).lift_slow_distance_um, 5001);
        assert_eq!(at(&half, 1).exposure_ms, 2501);
        assert_eq!(at(&half, 1).wait_time_after_lift_ms, 101);
        // Either end is verbatim: layer 0 is a bottom layer, layer 2 normal.
        assert_eq!(at(&half, 0).exposure_ms, 2501);
        assert_eq!(at(&half, 2).exposure_ms, 2500);

        // The widest layer counts a malformed META can carry: `N` is 2^32 and
        // the weighted sum reaches close to 2^64. That is the case the
        // intermediate width exists for, so it is pinned: an implementation
        // computing this in `u32` would wrap `bottom + transition` to zero and
        // one computing the sum too narrowly would truncate. The value is a
        // convex combination rounded to nearest, `u32::MAX / 2^32`.
        let mut extreme = meta.clone();
        extreme.timing.bottom_layer_count = Some(0);
        extreme.timing.transition_layer_count = Some(u32::MAX);
        extreme.timing.normal_exposure_ms = Some(0);
        extreme.timing.bottom_exposure_ms = Some(u32::MAX);

        assert_eq!(at(&extreme, u32::MAX - 1).exposure_ms, 1);
        assert!(at(&extreme, u32::MAX - 1).is_transition);
        assert_eq!(at(&extreme, u32::MAX).exposure_ms, 0);
    }

    #[test]
    fn light_pwm_switches_at_the_bottom_boundary_without_interpolating() {
        let mut meta = meta();
        meta.timing.bottom_light_pwm = Some(200);

        assert_eq!(at(&meta, 3).light_pwm, 200);
        // The first non-bottom layer, even a transition one, takes the normal
        // value: the boundary is `bottom_layer_count`, not the end of blending.
        assert_eq!(at(&meta, 4).light_pwm, 255);

        // An absent bottom PWM falls back to the normal one.
        let mut no_bottom_pwm = meta.clone();
        no_bottom_pwm.timing.bottom_light_pwm = None;
        no_bottom_pwm.timing.light_pwm = Some(180);
        assert_eq!(at(&no_bottom_pwm, 0).light_pwm, 180);
        assert_eq!(at(&no_bottom_pwm, 4).light_pwm, 180);

        // An absent normal PWM is the spec's default of 255.
        let mut no_pwm = meta.clone();
        no_pwm.timing.light_pwm = None;
        no_pwm.timing.bottom_light_pwm = None;
        assert_eq!(at(&no_pwm, 0).light_pwm, 255);
        assert_eq!(at(&no_pwm, 40).light_pwm, 255);
    }

    #[test]
    fn a_sector_entry_overrides_its_own_sector_only() {
        let meta = meta();
        let sector = Sector {
            sector_id: 1,
            timing: Timing {
                normal_exposure_ms: Some(3000),
                bottom_exposure_ms: Some(35000),
                ..Timing::default()
            },
            ..Sector::default()
        };

        // Sector 0 keeps META even when an entry is offered.
        assert_eq!(
            resolve(&meta, Some(&sector), None, 0, 0)
                .unwrap()
                .exposure_ms,
            30000
        );
        assert_eq!(
            resolve(&meta, Some(&sector), None, 12, 0)
                .unwrap()
                .exposure_ms,
            2500
        );

        // Sector 1 blends the entry's own pair.
        assert_eq!(
            resolve(&meta, Some(&sector), None, 0, 1)
                .unwrap()
                .exposure_ms,
            35000
        );
        assert_eq!(
            resolve(&meta, Some(&sector), None, 12, 1)
                .unwrap()
                .exposure_ms,
            3000
        );

        // A field the entry leaves out still comes from META...
        assert_eq!(
            resolve(&meta, Some(&sector), None, 12, 1)
                .unwrap()
                .lift_slow_distance_um,
            5000
        );
        // ...for a sector with no entry at all, as well.
        assert_eq!(resolve(&meta, None, None, 12, 1).unwrap().exposure_ms, 2500);

        // The entry's own layer counts move the ranges for its sector.
        let sector = Sector {
            sector_id: 1,
            timing: Timing {
                bottom_layer_count: Some(6),
                transition_layer_count: Some(0),
                ..Timing::default()
            },
            ..Sector::default()
        };
        assert!(resolve(&meta, Some(&sector), None, 5, 1).unwrap().is_bottom);
        assert!(
            resolve(&meta, Some(&sector), None, 5, 0)
                .unwrap()
                .is_transition
        );
    }

    #[test]
    fn temperatures_and_cure_curve_come_from_meta_or_a_sector_entry_unblended() {
        let mut meta = meta();
        meta.timing.chamber_temperature_c = Some(30.0);
        meta.timing.cure_curve = Some(CureCurve {
            dp_um: 120.0,
            ec_mj_cm2: 7.5,
            e0_mj_cm2: 3.0,
        });

        let resolved = at(&meta, 0);
        assert_eq!(resolved.chamber_temperature_c, Some(30.0));
        assert_eq!(resolved.vat_temperature_c, None);
        assert_eq!(
            resolved.cure_curve,
            Some(CureCurve {
                dp_um: 120.0,
                ec_mj_cm2: 7.5,
                e0_mj_cm2: 3.0,
            })
        );

        let sector = Sector {
            sector_id: 1,
            timing: Timing {
                chamber_temperature_c: Some(40.0),
                ..Timing::default()
            },
            ..Sector::default()
        };
        let for_sector_1 = resolve(&meta, Some(&sector), None, 0, 1).unwrap();
        assert_eq!(for_sector_1.chamber_temperature_c, Some(40.0));
        assert_eq!(for_sector_1.vat_temperature_c, None);
        assert_eq!(for_sector_1.cure_curve.unwrap().dp_um, 120.0);
        assert_eq!(at(&meta, 0).chamber_temperature_c, Some(30.0));
    }

    #[test]
    fn an_lrov_payload_replaces_only_the_fields_it_carries() {
        let meta = meta();
        let overrides = Timing {
            normal_exposure_ms: Some(9000),
            lift_slow_distance_um: Some(7000),
            ..Timing::default()
        };

        let resolved = resolve(&meta, None, Some(&overrides), 12, 0).unwrap();
        assert_eq!(resolved.exposure_ms, 9000);
        assert_eq!(resolved.lift_slow_distance_um, 7000);
        // A field the payload leaves out keeps the blended value.
        assert_eq!(resolved.lift_slow_speed_um_min, 65_000);

        // The payload is applied to the (layer, sector) the caller passes it
        // for; which one that is comes from the table entry that points at it,
        // not from anything inside the payload, so a point with no payload
        // resolves from the pipeline alone.
        assert_eq!(resolve(&meta, None, None, 16, 0).unwrap().exposure_ms, 2500);
        assert_eq!(resolve(&meta, None, None, 12, 1).unwrap().exposure_ms, 2500);
    }

    #[test]
    fn an_lrov_payload_overrides_pwm_and_optional_motion() {
        let meta = meta();
        let overrides = Timing {
            normal_exposure_ms: Some(9000),
            light_pwm: Some(120),
            bottom_light_pwm: Some(130),
            lift_fast_distance_um: Some(2500),
            chamber_temperature_c: Some(35.0),
            ..Timing::default()
        };

        let resolved = resolve(&meta, None, Some(&overrides), 1, 0).unwrap();
        assert_eq!(resolved.light_pwm, 120);
        assert_eq!(resolved.lift_fast_distance_um, 2500);
        assert_eq!(resolved.chamber_temperature_c, Some(35.0));
        // The payload names the resolved value, not the blend's two ends.
        assert_eq!(
            resolve(&meta, None, Some(&overrides), 0, 0)
                .unwrap()
                .light_pwm,
            120
        );
        assert_eq!(resolve(&meta, None, None, 0, 0).unwrap().light_pwm, 255);
    }

    #[test]
    fn missing_required_meta_field_is_reported() {
        let mut meta = meta();
        meta.timing.bottom_exposure_ms = None;
        meta.timing.lift_slow_speed_um_min = None;

        let err = resolve(&meta, None, None, 0, 0).unwrap_err();
        assert_eq!(err.check(), Check::MetaRequiredFields);
        let detail = err.detail();
        assert!(detail.contains("bottom_exposure_ms"), "{detail}");
        assert!(detail.contains("lift_slow_speed_um_min"), "{detail}");
        assert!(!detail.contains("normal_exposure_ms"), "{detail}");

        // The schema version is `validate`'s business, not the pipeline's.
        let mut no_version = meta.clone();
        no_version.meta_version = None;
        no_version.timing.bottom_exposure_ms = Some(30000);
        no_version.timing.lift_slow_speed_um_min = Some(65000);
        assert!(resolve(&no_version, None, None, 0, 0).is_ok());
    }
}
