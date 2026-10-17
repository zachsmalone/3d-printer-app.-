//! Tests for the translated math core (src/dsc.h + src/util.cpp).
//!
//! Every test asserts behavior that matches the original C++ semantics; naming
//! follows the original so each test can be audited against SolveSpace.

use zeimcad::dsc::{Point2d, Quaternion, Vector, Vector4};
use zeimcad::util::{BandedMatrix, Mat4};

fn assert_close(a: f64, b: f64, tol: f64, what: &str) {
    assert!((a - b).abs() < tol, "{what}: {a} != {b}");
}

#[test]
fn vector_basics() {
    let a = Vector::from(1.0, 2.0, 3.0);
    let b = Vector::from(4.0, 5.0, 6.0);

    assert_eq!(a.plus(b), Vector::from(5.0, 7.0, 9.0));
    assert_eq!(a.minus(b), Vector::from(-3.0, -3.0, -3.0));
    assert_eq!(a.negated(), Vector::from(-1.0, -2.0, -3.0));
    assert_eq!(a.cross(b), Vector::from(-3.0, 6.0, -3.0));
    assert_close(a.dot(b), 32.0, 1e-12, "dot");
    assert_close(a.magnitude(), 14.0f64.sqrt(), 1e-12, "magnitude");
    assert_close(a.mag_squared(), 14.0, 1e-12, "mag_squared");
    assert_eq!(a.scaled_by(2.0), Vector::from(2.0, 4.0, 6.0));
    assert_eq!(a.with_magnitude(2.0 * a.magnitude()), a.scaled_by(2.0));
}

#[test]
fn vector_equals_and_tolerance() {
    let a = Vector::from(1.0, 2.0, 3.0);
    let b = Vector::from(1.0 + 1e-9, 2.0, 3.0);
    assert!(a.equals(b, 1e-6));
    assert!(!a.equals(b, 1e-12));
    assert!(a.equals_exactly(a));
    assert!(!a.equals_exactly(b));
}

#[test]
fn vector_with_magnitude_of_zero_vector() {
    // The original returns the zero vector (after a debug print) rather than dividing by zero.
    let z = Vector::from(0.0, 0.0, 0.0);
    assert_eq!(z.with_magnitude(5.0), Vector::from(0.0, 0.0, 0.0));
}

#[test]
fn vector_normal_pivot_rules() {
    // The XY-plane special case: the normal to (0,0,1) is (1,0,0) (DXF export nicety).
    assert_eq!(Vector::from(0.0, 0.0, 1.0).normal(0), Vector::from(1.0, 0.0, 0.0));
    // x is the smallest component: n = {0, z, -y}
    let n = Vector::from(0.1, 5.0, 7.0).normal(0);
    assert!(Vector::from(0.1, 5.0, 7.0).dot(n).abs() < 1e-9);
    // which == 1 is the cross product, still normal
    let n1 = Vector::from(0.1, 5.0, 7.0).normal(1);
    assert!(Vector::from(0.1, 5.0, 7.0).dot(n1).abs() < 1e-9);
    assert!((n.cross(n1).magnitude() - 1.0).abs() < 1e-9);
}

#[test]
fn vector_rotated_about_matches_quaternion_rotation() {
    // Rotating about an axis must agree with the quaternion generated from the
    // same axis and angle.
    let axis = Vector::from(1.0, 1.0, 1.0);
    let theta = 0.9;
    let p = Vector::from(3.0, -2.0, 5.0);

    let by_matrix = p.rotated_about(axis, theta);
    let by_quat = Quaternion::from_axis_angle(axis, theta).rotate(p);
    assert!(by_matrix.equals(by_quat, 1e-9));
}

#[test]
fn quaternion_identity_and_inverse() {
    let q = Quaternion::from_axis_angle(Vector::from(0.0, 1.0, 0.0), 1.234);
    let p = Vector::from(1.0, 2.0, 3.0);
    assert!(q.rotate(p).equals(p.rotated_about(Vector::from(0.0, 1.0, 0.0), 1.234), 1e-9));
    assert!(q.inverse().rotate(q.rotate(p)).equals(p, 1e-9));
}

#[test]
fn quaternion_from_rows_is_unit_and_orthonormal() {
    let u = Vector::from(1.0, 0.0, 0.0);
    let v = Vector::from(0.0, 1.0, 0.0);
    let q = Quaternion::from_rows(u, v);
    assert!((q.magnitude() - 1.0).abs() < 1e-9);
    assert!(q.rotation_u().equals(u, 1e-9));
    assert!(q.rotation_v().equals(v, 1e-9));
    assert!(q.rotation_n().equals(Vector::from(0.0, 0.0, 1.0), 1e-9));
}

#[test]
fn quaternion_times_and_to_the() {
    let q1 = Quaternion::from_axis_angle(Vector::from(0.0, 0.0, 1.0), 0.6);
    let q2 = Quaternion::from_axis_angle(Vector::from(0.0, 0.0, 1.0), 0.3);
    let both = q1.times(q2);
    let expected = Quaternion::from_axis_angle(Vector::from(0.0, 0.0, 1.0), 0.9);
    for (a, b, what) in [(both.w, expected.w, "w"), (both.vx, expected.vx, "vx"),
                         (both.vy, expected.vy, "vy"), (both.vz, expected.vz, "vz")] {
        assert!((a - b).abs() < 1e-9, "quaternion product {what}: {a} != {b}");
    }

    // ToThe(0.5) of a 0.6-rad rotation is a 0.3-rad rotation.
    let half = q1.to_the(0.5);
    assert!((half.w - q2.w).abs() < 1e-9);
}

#[test]
fn line_intersections() {
    // Crossing lines: not skew, intersection at (5, 0, 0).
    let mut skew = true;
    let mut pa = 0.0;
    let mut pb = 0.0;
    let x = Vector::at_intersection_of_lines(
        Vector::from(0.0, 0.0, 0.0), Vector::from(10.0, 0.0, 0.0),
        Vector::from(5.0, -5.0, 0.0), Vector::from(5.0, 5.0, 0.0),
        &mut skew, &mut pa, &mut pb,
    );
    assert!(!skew);
    assert!(x.equals(Vector::from(5.0, 0.0, 0.0), 1e-9));
    assert_close(pa, 0.5, 1e-9, "parama");

    // Skew lines: reported as skew.
    let x2 = Vector::at_intersection_of_lines(
        Vector::from(0.0, 0.0, 0.0), Vector::from(10.0, 0.0, 0.0),
        Vector::from(5.0, -5.0, 3.0), Vector::from(5.0, 5.0, 3.0),
        &mut skew, &mut pa, &mut pb,
    );
    assert!(skew);
    assert!(x2.equals(Vector::from(5.0, 0.0, 0.0), 1e-9));
}

#[test]
fn plane_and_line_intersection() {
    let mut parallel = true;
    let p = Vector::at_intersection_of_plane_and_line(
        Vector::from(0.0, 0.0, 1.0), 5.0,
        Vector::from(0.0, 0.0, 0.0), Vector::from(0.0, 0.0, 10.0),
        &mut parallel,
    );
    assert!(!parallel);
    assert!(p.equals(Vector::from(0.0, 0.0, 5.0), 1e-9));

    // A line parallel to the plane is reported as parallel.
    Vector::at_intersection_of_plane_and_line(
        Vector::from(0.0, 0.0, 1.0), 5.0,
        Vector::from(0.0, 0.0, 0.0), Vector::from(1.0, 0.0, 0.0),
        &mut parallel,
    );
    assert!(parallel);
}

#[test]
fn intersection_of_two_planes() {
    // The planes z = 5 (n=(0,0,1), d=5) and x = 2 (n=(1,0,0), d=2) intersect in the
    // line x=2, z=5; every point the formula returns must lie on both planes.
    let p = Vector::at_intersection_of_planes(
        Vector::from(0.0, 0.0, 1.0), 5.0,
        Vector::from(1.0, 0.0, 0.0), 2.0,
    );
    assert_close(p.z, 5.0, 1e-9, "on plane 1");
    assert_close(p.x, 2.0, 1e-9, "on plane 2");
    assert_close(p.y, 0.0, 1e-9, "closest point to origin");
}

#[test]
fn point2d_distance_to_line() {
    let p = Point2d::from(5.0, 3.0);
    let p0 = Point2d::from(0.0, 0.0);
    let dp = Point2d::from(10.0, 0.0);
    assert_close(p.distance_to_line(p0, dp, false), 3.0, 1e-9, "infinite line");

    // Beyond the segment: distance to the endpoint p0+dp = (10, 0) when treated as a segment.
    let q = Point2d::from(15.0, 3.0);
    assert_close(q.distance_to_line(p0, dp, true), (5.0f64 * 5.0 + 3.0 * 3.0).sqrt(), 1e-9, "segment endpoint");
    // Signed: above the +x direction line is negative (normal is (0, -1) after WithMagnitude).
    assert_close(q.distance_to_line_signed(p0, dp, false), -3.0, 1e-9, "signed distance");
}

#[test]
fn vector4_blend_and_perspective() {
    let a = Vector4::from(1.0, 0.0, 0.0, 0.0);
    let b = Vector4::from(1.0, 10.0, 10.0, 10.0);
    let mid = Vector4::blend(a, b, 0.5);
    assert_eq!(mid, Vector4::from(1.0, 5.0, 5.0, 5.0));

    let p = Vector4::from(2.0, 4.0, 6.0, 8.0);
    assert_eq!(p.perspective_project(), Vector::from(2.0, 3.0, 4.0));
}

#[test]
fn mat4_multiply_matches_original_ordering() {
    // The original stores column-major and multiplies as in MultMatrix; verify with
    // a known product. A = translation by (1,2,3), B = scale by 2.
    let a = Mat4::from_rows(
        1.0, 0.0, 0.0, 1.0,
        0.0, 1.0, 0.0, 2.0,
        0.0, 0.0, 1.0, 3.0,
        0.0, 0.0, 0.0, 1.0,
    );
    let b = Mat4::from_rows(
        2.0, 0.0, 0.0, 0.0,
        0.0, 2.0, 0.0, 0.0,
        0.0, 0.0, 2.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    );
    let c = Mat4::multiply(a, b);
    // A*B: translation applied after scaling.
    let expected = Mat4::from_rows(
        2.0, 0.0, 0.0, 1.0,
        0.0, 2.0, 0.0, 2.0,
        0.0, 0.0, 2.0, 3.0,
        0.0, 0.0, 0.0, 1.0,
    );
    assert_eq!(c, expected);
}

#[test]
fn banded_matrix_solve() {
    // A 3x3 system that fits the banded structure: A is tridiagonal-with-extras,
    // B the right-hand side; X must satisfy A*X = B on the ORIGINAL matrix
    // (the solver mutates its own copy).
    let a = [
        [4.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        [2.0, 5.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        [0.0, 2.0, 6.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    ];
    let b = [7.0, 16.0, 20.0];

    let mut m = BandedMatrix::new(3);
    for (i, row) in a.iter().enumerate() {
        m.a[i] = row.to_vec();
    }
    m.b = b.to_vec();

    m.solve();

    // Verify the solution against the residual on the original system.
    for i in 0..3 {
        let mut r = -b[i];
        for j in 0..3 {
            r += a[i][j] * m.x[j];
        }
        assert!(r.abs() < 1e-9, "residual too large: {r}");
    }
}

#[test]
fn point2d_angle_wraps_into_0_to_2pi() {
    // Point2d::Angle in the original maps atan2 into [0, 2*pi).
    let a = Point2d::from(-1.0, -1.0).angle();   // atan2 gives -3*pi/4
    assert!((a - 5.0 * std::f64::consts::PI / 4.0).abs() < 1e-9, "angle = {a}");
    let zero = Point2d::from(1.0, 0.0).angle();
    assert!(zero.abs() < 1e-9 || (zero - 2.0 * std::f64::consts::PI).abs() < 1e-9);
}

#[test]
fn point2d_with_magnitude_of_zero_vector() {
    // The original returns {v, 0} for a zero vector (with a debug print), not an error.
    assert_eq!(Point2d::from(0.0, 0.0).with_magnitude(5.0), Point2d::from(5.0, 0.0));
}

#[test]
fn vector4_perspective_project_follows_original_semantics() {
    // Plain division; a zero w produces inf/nan by design (no guard in the original).
    let p = Vector4::from(2.0, 4.0, 6.0, 8.0);
    assert_eq!(p.perspective_project(), Vector::from(2.0, 3.0, 4.0));
    let degenerate = Vector4::from(0.0, 1.0, 2.0, 3.0).perspective_project();
    assert!(degenerate.x.is_infinite());
}
