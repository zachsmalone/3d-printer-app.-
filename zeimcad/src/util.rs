//! Utility functions: 4x4 matrix helpers and the banded-matrix solver.
//!
//! Translated from src/util.cpp and src/dsc.h, Copyright 2008-2013 Jonathan Westhues,
//! GPL-3.0-or-later.

pub const MAX_UNKNOWNS: usize = 16;
pub const RIGHT_OF_DIAG: usize = 1;
pub const LEFT_OF_DIAG: usize = 2;

/// A 4x4 matrix stored column-major, like the original `double mat[16]`
/// written by `MakeMatrix`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Mat4([f64; 16]);

impl Mat4 {
    /// Translated from `MakeMatrix` in util.cpp: takes the 16 elements in row-major
    /// (a11..a44) order and stores them column-major.
    #[allow(clippy::too_many_arguments)]
    pub fn from_rows(
        a11: f64, a12: f64, a13: f64, a14: f64,
        a21: f64, a22: f64, a23: f64, a24: f64,
        a31: f64, a32: f64, a33: f64, a34: f64,
        a41: f64, a42: f64, a43: f64, a44: f64,
    ) -> Mat4 {
        Mat4([
            a11, a21, a31, a41,
            a12, a22, a32, a42,
            a13, a23, a33, a43,
            a14, a24, a34, a44,
        ])
    }

    /// Translated from `MultMatrix` in util.cpp.
    pub fn multiply(a: Mat4, b: Mat4) -> Mat4 {
        let mut r = Mat4([0.0; 16]);
        for i in 0..4 {
            for j in 0..4 {
                let mut s = 0.0;
                for k in 0..4 {
                    s += a.0[k * 4 + j] * b.0[i * 4 + k];
                }
                r.0[i * 4 + j] = s;
            }
        }
        r
    }
}

/// A mostly banded matrix, solved without pivoting (translated from `BandedMatrix`
/// in dsc.h and its `Solve()` in util.cpp).
#[derive(Debug, Clone)]
pub struct BandedMatrix {
    pub a: Vec<Vec<f64>>,   // A[i][j]
    pub b: Vec<f64>,       // B[i]
    pub x: Vec<f64>,       // X[i]
    pub n: usize,
}

impl BandedMatrix {
    pub fn new(n: usize) -> BandedMatrix {
        BandedMatrix {
            a: vec![vec![0.0; MAX_UNKNOWNS]; n],
            b: vec![0.0; n],
            x: vec![0.0; n],
            n,
        }
    }

    /// Reduce the matrix to upper triangular form, then back-substitute.
    /// Translated from `BandedMatrix::Solve()` in util.cpp.
    pub fn solve(&mut self) {
        let n = self.n as i64;

        // Reduce the matrix to upper triangular form.
        for i in 0..n {
            let mut ip = i + 1;
            while ip < n && ip <= i + LEFT_OF_DIAG as i64 {
                let temp = self.a[ip as usize][i as usize] / self.a[i as usize][i as usize];

                let mut jp = i;
                while jp < (n - 2) && jp <= i + RIGHT_OF_DIAG as i64 {
                    self.a[ip as usize][jp as usize] -= temp * self.a[i as usize][jp as usize];
                    jp += 1;
                }
                self.a[ip as usize][(n - 2) as usize] -= temp * self.a[i as usize][(n - 2) as usize];
                self.a[ip as usize][(n - 1) as usize] -= temp * self.a[i as usize][(n - 1) as usize];

                self.b[ip as usize] -= temp * self.b[i as usize];
                ip += 1;
            }
        }

        // And back-substitute.
        for i in (0..n).rev() {
            let mut temp = self.b[i as usize];

            if i < n - 1 {
                temp -= self.x[(n - 1) as usize] * self.a[i as usize][(n - 1) as usize];
            }
            if i < n - 2 {
                temp -= self.x[(n - 2) as usize] * self.a[i as usize][(n - 2) as usize];
            }

            let mut j = std::cmp::min(n - 3, i + RIGHT_OF_DIAG as i64);
            while j > i {
                temp -= self.x[j as usize] * self.a[i as usize][j as usize];
                j -= 1;
            }
            self.x[i as usize] = temp / self.a[i as usize][i as usize];
        }
    }
}
