//! Encode and inspect Open Resin Alliance LUMEN v1 files.
//!
//! The container, run-end encoding and validation come from the unmodified
//! `lumen-format` crate (MIT OR Apache-2.0). This binary only fills `HEAD` /
//! `META` from a JSON job and feeds it raw layer masks on stdin.

use std::env;
use std::fs;
use std::io::{self, Read, Write};
use std::path::PathBuf;
use std::process::ExitCode;
use std::time::{SystemTime, UNIX_EPOCH};

use lumen::chunks::head::Head;
use lumen::chunks::preview::PreviewRole;
use lumen::json::{AntiAliasing, Material, Meta, Printer, Profile, Slicer, Timing};
use lumen::reader::LumenFile;
use lumen::validate::Level;
use lumen::writer::Encoder;
use serde::Deserialize;
use sha2::{Digest, Sha256};

const MAX_PIXELS: u64 = 12_000_000;

#[derive(Debug, Deserialize)]
struct Job {
    width: u32,
    height: u32,
    layer_count: u32,
    build_width_um: u32,
    build_depth_um: u32,
    build_height_um: u32,
    layer_height_um: u32,
    normal_exposure_ms: u32,
    bottom_exposure_ms: u32,
    bottom_layer_count: u32,
    transition_layer_count: u32,
    lift_slow_distance_um: u32,
    lift_slow_speed_um_min: u32,
    retract_fast_distance_um: u32,
    retract_fast_speed_um_min: u32,
    printer_name: String,
    manufacturer: String,
    pixel_size_um: Option<u32>,
    aa_enabled: bool,
    aa_level: u32,
    material_name: String,
    material_density_g_ml: Option<f64>,
    estimated_print_time_sec: u32,
    estimated_resin_volume_ml: f64,
    preview_png: Option<String>,
    profile_note: String,
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(err) => {
            eprintln!("zeim-lumen: {err}");
            ExitCode::from(1)
        }
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let cmd = args.next().ok_or_else(|| usage())?;
    match cmd.as_str() {
        "encode" => encode(args.collect()),
        "inspect" => inspect(args.collect()),
        "ctb" | "goo" | "lys" | "lyt" | "photon" | "zip" | "pwmx" | "pws" => {
            Err(format!(
                "refusing .{cmd}: zeim-lumen writes LUMEN (.lumen) only, not a .{cmd} printer file and not a zip"
            ))
        }
        other => Err(format!("unknown command {other}. {}", usage())),
    }
}

fn usage() -> String {
    "usage: zeim-lumen encode --job JOB.json --out FILE.lumen  |  zeim-lumen inspect FILE.lumen".to_string()
}

fn flag(args: &[String], name: &str) -> Result<String, String> {
    let mut i = 0;
    while i < args.len() {
        if args[i] == name {
            return args.get(i + 1).cloned().ok_or_else(|| format!("missing value for {name}"));
        }
        i += 1;
    }
    Err(format!("missing {name}"))
}

fn encode(args: Vec<String>) -> Result<(), String> {
    let job_path = flag(&args, "--job")?;
    let out_path = flag(&args, "--out")?;
    let job: Job = serde_json::from_str(&fs::read_to_string(&job_path).map_err(|e| e.to_string())?)
        .map_err(|e| format!("job JSON: {e}"))?;
    if job.layer_count == 0 || job.width == 0 || job.height == 0 {
        return Err("layer count and plate size must be greater than zero".into());
    }
    let pixels = job.width as u64 * job.height as u64;
    if pixels > MAX_PIXELS {
        return Err(format!(
            "plate is {pixels} pixels; the limit is {MAX_PIXELS}. This is not written as another format."
        ));
    }
    let created = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|e| e.to_string())?
        .as_secs();
    let head = Head {
        head_version: 1,
        encoder_name: "ZEIM TorchC0".to_string(),
        created_unix_sec: created,
        display_width_px: job.width,
        display_height_px: job.height,
        build_width_um: job.build_width_um,
        build_depth_um: job.build_depth_um,
        build_height_um: job.build_height_um,
        layer_height_um: job.layer_height_um,
        total_layers: job.layer_count,
    };
    let timing = Timing {
        layer_height_um: Some(job.layer_height_um),
        normal_exposure_ms: Some(job.normal_exposure_ms),
        bottom_exposure_ms: Some(job.bottom_exposure_ms),
        bottom_layer_count: Some(job.bottom_layer_count),
        transition_layer_count: Some(job.transition_layer_count),
        lift_slow_distance_um: Some(job.lift_slow_distance_um),
        lift_slow_speed_um_min: Some(job.lift_slow_speed_um_min),
        lift_fast_distance_um: Some(0),
        lift_fast_speed_um_min: Some(job.lift_slow_speed_um_min),
        retract_fast_distance_um: Some(job.retract_fast_distance_um),
        retract_fast_speed_um_min: Some(job.retract_fast_speed_um_min),
        retract_slow_distance_um: Some(0),
        retract_slow_speed_um_min: Some(job.retract_fast_speed_um_min),
        ..Timing::default()
    };
    let meta = Meta {
        meta_version: Some(1),
        timing: timing.clone(),
        materials: Some(vec![Material {
            name: job.material_name.clone(),
            brand: None,
            family: None,
            density_g_ml: job.material_density_g_ml,
            color_rgba: None,
            bottle_price: None,
            bottle_capacity_ml: None,
            extra: Default::default(),
        }]),
        printer: Some(Printer {
            name: Some(job.printer_name.clone()),
            manufacturer: Some(job.manufacturer.clone()),
            display_width_px: Some(job.width),
            display_height_px: Some(job.height),
            pixel_size_um: job.pixel_size_um,
            build_width_um: Some(job.build_width_um),
            build_depth_um: Some(job.build_depth_um),
            build_height_um: Some(job.build_height_um),
            ..Printer::default()
        }),
        anti_aliasing: Some(AntiAliasing {
            enabled: Some(job.aa_enabled),
            level: Some(job.aa_level),
            mode: Some("coverage".to_string()),
            ..AntiAliasing::default()
        }),
        estimated_print_time_sec: Some(job.estimated_print_time_sec),
        estimated_resin_volume_ml: Some(job.estimated_resin_volume_ml),
        slicer: Some(Slicer {
            name: Some("ZEIM TorchC0".to_string()),
            version: Some(env!("CARGO_PKG_VERSION").to_string()),
            url: Some("https://github.com/Open-Resin-Alliance/LumenFormat".to_string()),
            ..Slicer::default()
        }),
        ..Meta::default()
    };
    let mut encoder = Encoder::new(head, meta);
    encoder.set_tag_probe(true);
    encoder.set_dictionary(true);
    encoder.set_layer_hashes(true);
    encoder.set_worker_threads(1);
    encoder.set_zstd_level(3);
    encoder.set_profile(Profile {
        profile_name: format!("{} {}", job.manufacturer, job.printer_name),
        profile_version: "1".to_string(),
        profile_type: Some("combined".to_string()),
        description: Some(job.profile_note),
        settings: timing,
        ..Profile::default()
    });
    if let Some(path) = job.preview_png.as_deref() {
        if !path.is_empty() {
            let png = fs::read(path).map_err(|e| format!("preview: {e}"))?;
            encoder.add_preview(PreviewRole::Small, png);
        }
    }
    let mut stdin = io::stdin().lock();
    let mut mask = vec![0u8; pixels as usize];
    for index in 0..job.layer_count {
        stdin
            .read_exact(&mut mask)
            .map_err(|e| format!("layer {index} mask: {e}"))?;
        encoder
            .push_layer(&mask)
            .map_err(|e| format!("layer {index}: {e}"))?;
        let _ = writeln!(io::stderr(), "progress {} {}", index + 1, job.layer_count);
    }
    let bytes = encoder.finish().map_err(|e| e.to_string())?;
    if bytes.len() < 8 || &bytes[..4] != b"LUMN" || &bytes[bytes.len() - 8..bytes.len() - 4] != b"LEND" {
        return Err("encoder did not produce a LUMN…LEND file".into());
    }
    fs::write(&out_path, &bytes).map_err(|e| e.to_string())?;
    let _ = writeln!(
        io::stderr(),
        "wrote {} bytes {}",
        bytes.len(),
        PathBuf::from(&out_path).display()
    );
    Ok(())
}

fn inspect(args: Vec<String>) -> Result<(), String> {
    let path = args.first().cloned().ok_or_else(|| usage())?;
    let bytes = fs::read(&path).map_err(|e| e.to_string())?;
    if bytes.len() < 8 || &bytes[..4] != b"LUMN" {
        return Err("not a LUMEN file (missing LUMN)".into());
    }
    if &bytes[bytes.len() - 8..bytes.len() - 4] != b"LEND" {
        return Err("not a LUMEN file (missing LEND trailer)".into());
    }
    let file = LumenFile::open(&bytes, Level::Strict).map_err(|e| format!("strict open: {e}"))?;
    let head = file.head();
    let meta = file.meta();
    let n = file.layer_count();
    let mut lit = Vec::with_capacity(n as usize);
    let mut solid = Vec::with_capacity(n as usize);
    let mut sha = Vec::with_capacity(n as usize);
    for index in 0..n {
        let layer = file.layer(index).map_err(|e| format!("layer {index}: {e}"))?;
        let pixels = &layer.pixels;
        lit.push(pixels.iter().filter(|p| **p > 0).count());
        solid.push(pixels.iter().filter(|p| **p == 255).count());
        let mut hasher = Sha256::new();
        hasher.update(pixels);
        sha.push(hex_encode(&hasher.finalize()));
    }
    let timing = &meta.timing;
    let report = serde_json::json!({
        "magic": "LUMN",
        "trailer": "LEND",
        "strict": true,
        "encrypted": file.header().encrypted(),
        "width": head.display_width_px,
        "height": head.display_height_px,
        "build_width_um": head.build_width_um,
        "build_depth_um": head.build_depth_um,
        "build_height_um": head.build_height_um,
        "layer_height_um": head.layer_height_um,
        "layers": n,
        "encoder_name": head.encoder_name,
        "normal_exposure_ms": timing.normal_exposure_ms,
        "bottom_exposure_ms": timing.bottom_exposure_ms,
        "bottom_layer_count": timing.bottom_layer_count,
        "transition_layer_count": timing.transition_layer_count,
        "lift_slow_distance_um": timing.lift_slow_distance_um,
        "lift_slow_speed_um_min": timing.lift_slow_speed_um_min,
        "retract_fast_distance_um": timing.retract_fast_distance_um,
        "retract_fast_speed_um_min": timing.retract_fast_speed_um_min,
        "anti_aliasing": meta.anti_aliasing,
        "printer": meta.printer,
        "slicer": meta.slicer,
        "preview_count": file.previews().len(),
        "preview_png": file.previews().first().map(|p| p.png.len()).unwrap_or(0),
        "lit": lit,
        "solid": solid,
        "sha256": sha,
        "bytes": bytes.len(),
    });
    println!("{}", serde_json::to_string(&report).map_err(|e| e.to_string())?);
    Ok(())
}

fn hex_encode(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        out.push(HEX[(b >> 4) as usize] as char);
        out.push(HEX[(b & 0x0f) as usize] as char);
    }
    out
}
