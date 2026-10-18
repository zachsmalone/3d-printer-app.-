//! ZEIMCad binary entry point.
//!
//! Today: a self-checking CLI that exercises the translated core and reports
//! status. It grows with every translated SolveSpace subsystem until it is the
//! full application.

use zeimcad::dsc::{Quaternion, Vector};
use zeimcad::VERSION;

fn self_check() -> Result<(), String> {
    // Quaternion round trip: rotating by an axis-angle quaternion and its inverse
    // must return the original point.
    let axis = Vector::from(1.0, 2.0, 3.0);
    let p = Vector::from(4.0, 5.0, 6.0);
    let q = Quaternion::from_axis_angle(axis, 0.7);
    let rotated = q.rotate(p);
    let restored = q.inverse().rotate(rotated);
    if !restored.equals(p, 1e-9) {
        return Err(format!("quaternion round trip failed: {restored:?}"));
    }

    // Rotation rows must be orthonormal.
    for (u, v) in [(q.rotation_u(), q.rotation_v()), (q.rotation_v(), q.rotation_n())] {
        if (u.dot(v) as f64).abs() > 1e-9 {
            return Err("rotation rows not orthogonal".into());
        }
        if ((u.magnitude() - 1.0) as f64).abs() > 1e-9 {
            return Err("rotation row not unit length".into());
        }
    }

    // Line intersection: two lines that genuinely cross must report non-skew.
    let mut skew = false;
    let mut pa = 0.0;
    let mut pb = 0.0;
    let x = Vector::at_intersection_of_lines(
        Vector::from(0.0, 0.0, 0.0), Vector::from(10.0, 0.0, 0.0),
        Vector::from(5.0, -5.0, 0.0), Vector::from(5.0, 5.0, 0.0),
        &mut skew, &mut pa, &mut pb,
    );
    if skew || !x.equals(Vector::from(5.0, 0.0, 0.0), 1e-9) {
        return Err(format!("line intersection self-check failed: {x:?} skew={skew}"));
    }

    Ok(())
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let cmd = args.get(1).map(|s| s.as_str()).unwrap_or("");

    match cmd {
        "--version" | "-V" => {
            println!("ZEIMCad {VERSION} (SolveSpace translation)");
        }
        "--self-check" => match self_check() {
            Ok(()) => println!("self-check: OK"),
            Err(e) => {
                eprintln!("self-check FAILED: {e}");
                std::process::exit(1);
            }
        },
        _ => {
            println!("ZEIMCad {VERSION} - a Rust translation of SolveSpace");
            println!("Usage: zeimcad --version | --self-check");
        }
    }
}
