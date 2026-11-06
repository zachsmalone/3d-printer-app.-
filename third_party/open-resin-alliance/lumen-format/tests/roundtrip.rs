//! Round trips: encode, then decode, and check the pixels come back.
//!
//! The conformance corpus proves this crate *reads* LUMEN. These tests prove it
//! *writes* LUMEN: a file it produces validates at both levels, and every layer
//! decodes back to the exact bytes that went in - including through the
//! dictionary, through multiple blocks, through the sector framing, and through
//! password encryption.

use lumen::chunks::extd::Extension;
use lumen::chunks::head::Head;
use lumen::chunks::ltbl::LayerTable;
use lumen::chunks::preview::PreviewRole;
use lumen::container::{self, ChunkType};
use lumen::crypto::Cipher;
use lumen::json::{Meta, Sector, Timing};
use lumen::reader::LumenFile;
use lumen::ree::{self, EncodeMode};
use lumen::validate::{self, Level};
use lumen::writer::{Argon2Params, EncodedLayer, Encoder, EncryptOptions, Override};

const WIDTH: u32 = 64;
const HEIGHT: u32 = 48;
const PIXELS: usize = (WIDTH * HEIGHT) as usize;

fn head(layers: u32) -> Head {
    Head {
        head_version: 1,
        encoder_name: "lumen-format tests".to_string(),
        created_unix_sec: 1_750_000_000,
        display_width_px: WIDTH,
        display_height_px: HEIGHT,
        build_width_um: 143_000,
        build_depth_um: 89_000,
        build_height_um: 175_000,
        layer_height_um: 50,
        total_layers: layers,
    }
}

fn meta() -> Meta {
    let mut timing = Timing {
        layer_height_um: Some(50),
        normal_exposure_ms: Some(2500),
        bottom_exposure_ms: Some(30000),
        bottom_layer_count: Some(2),
        transition_layer_count: Some(2),
        lift_slow_distance_um: Some(5000),
        lift_slow_speed_um_min: Some(65_000),
        retract_fast_distance_um: Some(5000),
        retract_fast_speed_um_min: Some(150_000),
        lift_fast_distance_um: Some(3000),
        lift_fast_speed_um_min: Some(180_000),
        retract_slow_distance_um: Some(3000),
        retract_slow_speed_um_min: Some(180_000),
        light_pwm: Some(255),
        ..Timing::default()
    };
    timing.extra.clear();
    Meta {
        meta_version: Some(1),
        timing,
        ..Meta::default()
    }
}

/// A corpus of layer masks that between them exercise every encoding and both
/// degenerate cases.
fn masks() -> Vec<Vec<u8>> {
    let mut out = Vec::new();

    // Empty: stored as the empty-layer form.
    out.push(vec![0u8; PIXELS]);

    // Solid white: one binary run.
    out.push(vec![255u8; PIXELS]);

    // A left/right split: two binary runs.
    let mut split = vec![0u8; PIXELS];
    for (i, pixel) in split.iter_mut().enumerate() {
        if i % (WIDTH as usize) >= 20 {
            *pixel = 255;
        }
    }
    out.push(split);

    // A horizontal gradient: grayscale or split, whichever is smaller.
    let mut gradient = vec![0u8; PIXELS];
    for (i, pixel) in gradient.iter_mut().enumerate() {
        *pixel = ((i % WIDTH as usize) * 255 / (WIDTH as usize - 1)) as u8;
    }
    out.push(gradient);

    // A disc with a soft anti-aliased edge: mostly solid, few AA pixels.
    let mut disc = vec![0u8; PIXELS];
    for y in 0..HEIGHT {
        for x in 0..WIDTH {
            let dx = x as f64 - WIDTH as f64 / 2.0;
            let dy = y as f64 - HEIGHT as f64 / 2.0;
            let distance = (dx * dx + dy * dy).sqrt();
            let radius = HEIGHT as f64 / 2.5;
            let value = if distance <= radius - 1.0 {
                255.0
            } else if distance >= radius + 1.0 {
                0.0
            } else {
                255.0 * (radius + 1.0 - distance) / 2.0
            };
            disc[y as usize * WIDTH as usize + x as usize] = value.round() as u8;
        }
    }
    out.push(disc);

    // A checkerboard: worst case for run-end encoding, and many runs per block.
    let mut checker = vec![0u8; PIXELS];
    for (i, pixel) in checker.iter_mut().enumerate() {
        let x = i % WIDTH as usize;
        let y = i / WIDTH as usize;
        *pixel = if (x + y) % 2 == 0 { 255 } else { 0 };
    }
    out.push(checker);

    out
}

/// Encode the masks and return the file.
fn encode(encrypt: Option<EncryptOptions>, layers_per_chunk: u32) -> Vec<u8> {
    let layer_masks = masks();
    let mut encoder = Encoder::new(head(layer_masks.len() as u32), meta());
    encoder.set_layers_per_chunk(layers_per_chunk);
    encoder.set_zstd_level(6);
    encoder.set_dictionary(true);
    encoder.set_layer_hashes(true);
    encoder.add_preview(PreviewRole::Small, fake_png());
    if let Some(options) = encrypt {
        encoder.set_encryption(options);
    }
    for mask in &layer_masks {
        encoder.push_layer(mask).expect("a pushable layer");
    }
    encoder.finish().expect("a writable file")
}

/// A minimal well-formed PNG: signature, IHDR, and an empty IEND.
fn fake_png() -> Vec<u8> {
    let mut png = vec![0x89, b'P', b'N', b'G', 0x0D, 0x0A, 0x1A, 0x0A];
    let mut ihdr = Vec::new();
    ihdr.extend_from_slice(&13u32.to_be_bytes());
    ihdr.extend_from_slice(b"IHDR");
    ihdr.extend_from_slice(&WIDTH.to_be_bytes());
    ihdr.extend_from_slice(&HEIGHT.to_be_bytes());
    ihdr.extend_from_slice(&[8, 0, 0, 0, 0]);
    ihdr.extend_from_slice(&lumen::container::crc32c(&ihdr[4..]).to_be_bytes());
    png.extend_from_slice(&ihdr);
    png
}

fn assert_layers(file: &LumenFile<'_>) {
    for (index, expected) in masks().iter().enumerate() {
        let decoded = file
            .layer(index as u32)
            .unwrap_or_else(|e| panic!("layer {index} must decode: {e}"));
        assert_eq!(
            decoded.pixels.len(),
            PIXELS,
            "layer {index} must decode to a full mask"
        );
        assert_eq!(
            &decoded.pixels, expected,
            "layer {index} pixels must round trip"
        );
        if expected.iter().all(|p| *p == 0) {
            assert!(
                decoded.is_empty(),
                "layer {index} must use the empty-layer form"
            );
        } else {
            assert!(!decoded.is_empty(), "layer {index} must carry a stream");
        }
    }
}

#[test]
fn plaintext_round_trip_with_a_dictionary_and_multiple_chunks() {
    // Six layers in chunks of two exercises the multi-chunk path and the
    // dictionary; small prints cannot train a dictionary, so the encoder must
    // fall back to plain zstd without failing.
    let bytes = encode(None, 2);
    validate::validate(&bytes, Level::Strict).expect("an authored file must validate strictly");
    let file = LumenFile::open(&bytes, Level::Strict).expect("an authored file must open");
    assert_eq!(file.layer_count(), masks().len() as u32);
    assert_layers(&file);
    file.verify_all()
        .expect("the authored integrity tree must verify");
    assert_eq!(file.previews().len(), 1, "the preview must round trip");

    // META has bottom_layer_count 2 and transition_layer_count 2, so layer 4 is
    // the first fully normal layer and layers 0-1 use the bottom exposure.
    assert_eq!(file.timing_for(0, 0).expect("layer 0").exposure_ms, 30000);
    assert_eq!(file.timing_for(1, 0).expect("layer 1").exposure_ms, 30000);
    assert_eq!(file.timing_for(4, 0).expect("layer 4").exposure_ms, 2500);
    let transition = file.timing_for(2, 0).expect("layer 2");
    assert!(transition.is_transition);
    // `N = 3`, so layer 2 is `k = 1`: (30000 * 2 + 2500) / 3 = 20833.33.. .
    assert_eq!(transition.exposure_ms, 20833, "layer 2 interpolates");
}

#[test]
fn plaintext_round_trip_in_one_chunk() {
    let bytes = encode(None, 64);
    let file = LumenFile::open(&bytes, Level::Strict).expect("an authored file must open");
    assert_eq!(
        file.layr_chunks().len(),
        1,
        "one chunk for six single-sector layers"
    );
    assert_layers(&file);
    file.verify_all()
        .expect("the authored integrity tree must verify");
}

#[test]
fn encoding_is_deterministic() {
    let first = encode(None, 3);
    let second = encode(None, 3);
    assert_eq!(
        first, second,
        "identical input and settings must produce identical bytes"
    );
}

#[test]
fn password_encryption_round_trips() {
    let bytes = encode(
        Some(EncryptOptions {
            cipher: Cipher::Aes256Gcm,
            password: Some("correct horse".to_string()),
            recipients: Vec::new(),
            argon2: Argon2Params {
                iterations: 1,
                memory_kib: 8,
                parallelism: 1,
            },
        }),
        2,
    );

    // Without a key the sealed content cannot be opened, and the flag rules still
    // hold at both levels.
    validate::validate(&bytes, Level::Strict).expect("an encrypted file validates without a key");
    let err = LumenFile::open(&bytes, Level::Loose).expect_err("sealed content needs a key");
    assert_eq!(err.check_name(), "crypt.no_key");

    let file = LumenFile::open_with_password(&bytes, Level::Strict, "correct horse")
        .expect("the right password must open the file");
    assert_layers(&file);
    file.verify_all()
        .expect("the integrity tree must verify through decryption");

    let wrong = LumenFile::open_with_password(&bytes, Level::Loose, "wrong password")
        .expect_err("a wrong password must not open the file");
    assert_eq!(wrong.check_name(), "crypt.key_unwrap");

    // The session key recovered explicitly is the one the content is sealed with.
    let key = file
        .recover_password("correct horse")
        .expect("key recovery");
    let reopened = LumenFile::open_with_key(&bytes, Level::Strict, key).expect("keyed open");
    assert_layers(&reopened);
}

#[test]
fn machine_binding_round_trips() {
    // A fixed recipient keypair: the X25519 private key is opaque to this test,
    // which only needs a public key the encoder can wrap for.
    let private: [u8; 32] = [
        0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F,
        0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E,
        0x1F, 0x20,
    ];
    let public = x25519_dalek::PublicKey::from(&x25519_dalek::StaticSecret::from(private));
    let bytes = encode(
        Some(EncryptOptions {
            cipher: Cipher::ChaCha20Poly1305,
            password: None,
            recipients: vec![public.to_bytes()],
            argon2: Argon2Params::default(),
        }),
        2,
    );

    let file = LumenFile::open_with_machine_key(&bytes, Level::Strict, &private)
        .expect("the recipient key must open the file");
    assert_layers(&file);

    let stranger: [u8; 32] = [0x77; 32];
    let err = LumenFile::open_with_machine_key(&bytes, Level::Loose, &stranger)
        .expect_err("another machine's key must not open the file");
    assert_eq!(err.check_name(), "crypt.no_key");
}

#[test]
fn multi_sector_round_trips_and_reports_its_sectors() {
    let mut encoder = Encoder::new(head(3), meta());
    encoder.set_sectors(vec![Sector {
        sector_id: 1,
        name: Some("supports".to_string()),
        material_index: None,
        color_rgba: Some([0, 255, 0, 128]),
        timing: Timing {
            normal_exposure_ms: Some(3000),
            bottom_exposure_ms: Some(35000),
            ..Timing::default()
        },
    }]);

    // Layer 0: model in sector 0, supports in sector 1, disjoint.
    let mut model = vec![0u8; PIXELS];
    let mut supports = vec![0u8; PIXELS];
    for (i, pixel) in model.iter_mut().enumerate() {
        if i % (WIDTH as usize) < 32 {
            *pixel = 255;
        }
    }
    for (i, pixel) in supports.iter_mut().enumerate() {
        if i % (WIDTH as usize) >= 48 {
            *pixel = 255;
        }
    }
    encoder
        .push_layer_sectors(&[(0, model.clone()), (1, supports.clone())])
        .expect("a pushable multi-sector layer");
    // Layer 1: empty.
    encoder.push_layer_sectors(&[]).expect("an empty layer");
    // Layer 2: sector 1 only, so the layer's first entry carries no data.
    encoder
        .push_layer_sectors(&[(1, supports.clone())])
        .expect("a pushable sector-1-only layer");
    // Layer 2's sector 0 is overridden even though it prints nothing.
    encoder
        .set_overrides(vec![
            Override {
                layer: 2,
                sector_id: 0,
                timing: Timing {
                    normal_exposure_ms: Some(1234),
                    ..Timing::default()
                },
            },
            Override {
                layer: 0,
                sector_id: 1,
                timing: Timing {
                    normal_exposure_ms: Some(4321),
                    ..Timing::default()
                },
            },
        ])
        .expect("one override set per (layer, sector)");

    let bytes = encoder.finish().expect("a writable file");
    validate::validate(&bytes, Level::Strict).expect("a multi-sector file must validate strictly");

    let file = LumenFile::open(&bytes, Level::Strict).expect("a multi-sector file must open");
    assert!(file.multi_sector());
    // Three layers in one group of the default size: the chunk set is the
    // sectors the group actually holds data for, which is sectors 0 and 1.
    assert_eq!(
        file.layr_chunks().len(),
        2,
        "one chunk per (sector, layer group) that holds data"
    );

    // Layer 0 carries both sectors, in ascending order.
    let sectors = file.layer_sectors(0).expect("layer 0 must decode");
    assert_eq!(sectors.len(), 2);
    assert_eq!(sectors[0].sector_id, 0);
    assert_eq!(sectors[1].sector_id, 1);
    assert_eq!(sectors[0].layer.pixels, model);
    assert_eq!(sectors[1].layer.pixels, supports);

    // A layer's first entry is sector 0's, and a single-material reader reads
    // that and nothing else.
    let primary = file.layer(0).expect("layer 0 must decode");
    assert_eq!(primary.pixels, model);
    let sector_one_only = file.layer(2).expect("layer 2 must decode");
    assert!(sector_one_only.is_empty(), "layer 2 prints no sector 0");
    assert_eq!(file.layer_sectors(2).expect("layer 2 must decode").len(), 1);
    assert!(file
        .layer_sectors(1)
        .expect("layer 1 must decode")
        .is_empty());

    // Sector 1 is non-empty, so a sector-0-only reader would drop content.
    assert!(
        !file.is_single_material_complete(),
        "a print with content outside sector 0 is not complete for a single material"
    );
    assert!(
        LumenFile::open(&encode(None, 2), Level::Strict)
            .expect("a single-sector file must open")
            .is_single_material_complete(),
        "a file with no second sector is complete"
    );

    // Per-sector timing resolves, and the sector's entry wins for its sector.
    // Layer 0 is inside the bottom range, so it uses the bottom exposure.
    let sector_0 = file.timing_for(0, 0).expect("sector 0 timing");
    let sector_1 = file.timing_for(0, 1).expect("sector 1 timing");
    assert!(sector_0.is_bottom, "layer 0 is a bottom layer");
    assert_eq!(
        sector_0.exposure_ms, 30000,
        "sector 0 takes META's bottom exposure"
    );
    assert_eq!(
        sector_1.exposure_ms, 4321,
        "layer 0's sector 1 takes its own override"
    );

    // Layer 1 has no override on sector 1, so the sector entry's own bottom
    // exposure shows through there.
    assert_eq!(
        file.timing_for(1, 1).expect("layer 1 sector 1").exposure_ms,
        35000
    );

    // The overrides reach exactly the (layer, sector) that carries them.
    assert_eq!(file.timing_for(2, 0).expect("layer 2").exposure_ms, 1234);
    assert_eq!(
        file.timing_for(1, 0).expect("layer 1").exposure_ms,
        30000,
        "layer 1 carries no override"
    );

    file.verify_all()
        .expect("the integrity tree must verify over concatenated slices");
}

/// Section 7.3's invariant, on the streams themselves.
///
/// Two sectors of one layer must not expose the same pixel, and the rule is
/// about the pixels a slice *exposes* - not the runs it stores and not the reach
/// of its overlay. The streams are pushed as they are encoded, so the case each
/// one makes is exact.
#[test]
fn two_sectors_of_one_layer_must_not_expose_the_same_pixel() {
    /// A white block over `[from, to)` and black everywhere else.
    fn block(from: usize, to: usize) -> Vec<u8> {
        let mut pixels = vec![0u8; PIXELS];
        pixels[from..to].fill(255);
        pixels
    }

    fn binary(pixels: &[u8]) -> Vec<u8> {
        ree::encode_binary(pixels, PIXELS as u32).expect("a binary mask")
    }

    /// One layer holding `sectors`, written out as a file.
    fn file(sectors: Vec<(u32, Vec<u8>)>) -> Vec<u8> {
        let mut encoder = Encoder::new(head(1), meta());
        encoder
            .push_encoded_layer(EncodedLayer::Sectors(sectors))
            .expect("a pushable layer");
        encoder.finish().expect("a writable file")
    }

    // Blocks that meet at pixel 32 expose no pixel in common.
    let adjacent = file(vec![
        (0, binary(&block(0, 32))),
        (1, binary(&block(32, 64))),
    ]);
    validate::validate(&adjacent, Level::Strict).expect("adjacent sectors are disjoint");

    // One pixel in common: the rule fires, and it is a strict one.
    let overlapping = file(vec![
        (0, binary(&block(0, 33))),
        (1, binary(&block(32, 64))),
    ]);
    let err = validate::validate(&overlapping, Level::Strict)
        .expect_err("pixel 32 is exposed by both sectors");
    assert_eq!(err.check_name(), "sector.partition");
    validate::validate(&overlapping, Level::Loose).expect("a loose read does not ask");

    // A grayscale sector exposes the runs that are not black: a second sector
    // may cover its black pixels, which its runs do reach.
    let mut striped = vec![0u8; PIXELS];
    striped[..16].fill(0x40);
    let grayscale = ree::encode_grayscale(&striped, PIXELS as u32).expect("a grayscale mask");
    let over_a_black_run = file(vec![(0, grayscale), (1, binary(&block(16, 32)))]);
    validate::validate(&over_a_black_run, Level::Strict)
        .expect("sector 0 exposes only pixels 0..16");

    // A split sector exposes the pixel its overlay carries, which is inside a
    // black run of its core: a sector that covers that pixel overlaps it.
    let mut edge = vec![0u8; PIXELS];
    edge[..32].fill(255);
    edge[40] = 0x40;
    let split = ree::encode_split(&edge, PIXELS as u32).expect("a split mask");
    let overlay_in_the_dark = file(vec![(0, split.clone()), (1, binary(&block(40, 64)))]);
    let err = validate::validate(&overlay_in_the_dark, Level::Strict)
        .expect_err("pixel 40 is exposed by sector 0's overlay");
    assert_eq!(err.check_name(), "sector.partition");

    // And a pixel a split sector exposes twice - its core's run holds it and its
    // overlay carries it - is still one sector's: it must not read as an overlap
    // with the sector next to it.
    let mut ramp = vec![0u8; PIXELS];
    ramp[..32].fill(255);
    ramp[16] = 0x80;
    let split = ree::encode_split(&ramp, PIXELS as u32).expect("a split mask");
    let twice_in_one_sector = file(vec![(0, split), (1, binary(&block(32, 64)))]);
    validate::validate(&twice_in_one_sector, Level::Strict)
        .expect("one sector exposing a pixel twice is not two sectors exposing it");

    // The two sectors' decoded masks, for the shapes the rule was read off:
    // what the walk says is exposed is what the masks expose.
    let opened = LumenFile::open(&overlay_in_the_dark, Level::Loose).expect("a readable file");
    for sector in opened.layer_sectors(0).expect("layer 0 must decode") {
        let exposed: Vec<usize> = sector
            .layer
            .pixels
            .iter()
            .enumerate()
            .filter(|(_, pixel)| **pixel != 0)
            .map(|(index, _)| index)
            .collect();
        let expected: Vec<usize> = if sector.sector_id == 0 {
            (0..32).chain(std::iter::once(40)).collect()
        } else {
            (40..64).collect()
        };
        assert_eq!(exposed, expected, "sector {}", sector.sector_id);
    }
}

#[test]
fn extensions_and_embedded_scene_round_trip() {
    let mut encoder = Encoder::new(head(1), meta());
    encoder.set_voxl(b"{\"voxl\":1}".to_vec());
    encoder.add_extension(Extension {
        ext_version: 1,
        ext_type: *b"TEST",
        vendor_id: 0x1234,
        critical: false,
        encrypted: false,
        data: vec![1, 2, 3, 4],
    });
    encoder
        .push_layer(&vec![255u8; PIXELS])
        .expect("a pushable layer");
    let bytes = encoder.finish().expect("a writable file");

    validate::validate(&bytes, Level::Strict).expect("the file must validate strictly");
    let file = LumenFile::open(&bytes, Level::Strict).expect("the file must open");
    assert_eq!(
        file.voxl(),
        Some(&b"{\"voxl\":1}"[..]),
        "the scene is opaque"
    );
    let extensions = file.extensions();
    assert_eq!(extensions.len(), 1);
    assert_eq!(extensions[0].tag(), "TEST");
    assert_eq!(extensions[0].vendor_id, 0x1234);
    assert_eq!(extensions[0].data, vec![1, 2, 3, 4]);
}

#[test]
fn the_encoder_refuses_a_malformed_sector_table() {
    // META's own shape rules, enforced where the file is assembled, so the
    // encoder cannot write something its validator would reject.
    let mut encoder = Encoder::new(head(1), meta());
    encoder.set_sectors(vec![Sector {
        sector_id: 0,
        ..Sector::default()
    }]);
    encoder
        .push_layer(&vec![255u8; PIXELS])
        .expect("a pushable layer");
    let error = encoder.finish().expect_err("sector 0 is implicit");
    assert_eq!(error.check_name(), "meta.sectors_shape");

    let mut encoder = Encoder::new(head(1), meta());
    encoder.set_sectors(vec![
        Sector {
            sector_id: 2,
            ..Sector::default()
        },
        Sector {
            sector_id: 2,
            ..Sector::default()
        },
    ]);
    encoder
        .push_layer(&vec![255u8; PIXELS])
        .expect("a pushable layer");
    let error = encoder.finish().expect_err("a sector id is unique");
    assert_eq!(error.check_name(), "meta.sectors_shape");
}

/// A `LAYR` frame is sealed as its own unit, and its associated data binds it to
/// the chunk's directory index.
///
/// This is the whole point of the binding: with every unit bound to slot zero, a
/// ciphertext lifted out of one `LAYR` chunk and dropped into another would
/// authenticate there, and a reader would print one sector's masks for another.
/// Re-sealing one frame under slot zero is the mutation that says so, and a
/// reader holding the key must report the binding rather than the tag.
#[test]
fn a_layer_frame_is_bound_to_its_directory_index() {
    let mut encoder = Encoder::new(head(masks().len() as u32), meta());
    encoder.set_layers_per_chunk(2);
    encoder.set_encryption(EncryptOptions::password("correct horse"));
    for mask in &masks() {
        encoder.push_layer(mask).expect("a pushable layer");
    }
    let key = encoder
        .session_key()
        .expect("an encrypted encoder has a key");
    let bytes = encoder.finish().expect("a writable file");
    validate::validate_with_key(&bytes, Level::Strict, key)
        .expect("the unmodified file is valid with its key");

    let mutated = rebind_first_layer_frame(&bytes, &key);
    let error = validate::validate_with_key(&mutated, Level::Strict, key)
        .expect_err("a frame bound to slot zero must not authenticate");
    assert_eq!(error.check_name(), "crypt.unit_index_binding");

    let refused = LumenFile::open_with_key(&mutated, Level::Strict, key)
        .expect_err("the reader must refuse it too");
    assert_eq!(refused.check_name(), "crypt.unit_index_binding");
}

/// Seal the first `LAYR` chunk's frame under slot zero again, in place, and
/// rebuild the file around it.
fn rebind_first_layer_frame(bytes: &[u8], key: &lumen::crypto::SessionKey) -> Vec<u8> {
    use lumen::container::{self, ChunkType};

    let header = container::FileHeader::parse(bytes).unwrap();
    let directory = container::parse_directory(bytes, &header).unwrap();
    let (index, descriptor) = directory
        .descriptors
        .iter()
        .enumerate()
        .find(|(_, d)| d.chunk_type == ChunkType::LAYR && d.is_encrypted())
        .map(|(index, d)| (index as u32, *d))
        .expect("an encrypted file seals its layer frames");
    let start = descriptor.offset as usize;
    let stored = &bytes[start..start + descriptor.stored_len() as usize];
    let frame = lumen::chunks::layr::frame(stored).unwrap();
    let plain = lumen::crypto::open(Cipher::Aes256Gcm, key, ChunkType::LAYR, index, frame).unwrap();
    let rebound = lumen::crypto::seal(Cipher::Aes256Gcm, key, ChunkType::LAYR, 0, &plain).unwrap();

    let mut mutated = Vec::from(&bytes[..start]);
    mutated.extend_from_slice(&lumen::chunks::layr::to_bytes(&rebound));
    mutated.extend_from_slice(&bytes[start + stored.len()..bytes.len() - 8]);
    let crc = container::crc32c(&mutated);
    mutated.extend_from_slice(&container::TRAILER_MAGIC);
    mutated.extend_from_slice(&crc.to_le_bytes());
    mutated
}

/// One defect introduced into a written file: the check it must fail, and the
/// mutation that introduces it.
type Mutation = (&'static str, fn(&[u8]) -> Vec<u8>);

/// The layer table, and the header flag that summarizes it, must describe the
/// file they are in.
///
/// Three defects, three rules: a `first_layr` that names no `LAYR` chunk, two
/// slices of one chunk that overlap, and an `LROV` chunk no entry points at.
#[test]
fn a_layer_table_that_lies_is_rejected() {
    let mut encoder = Encoder::new(head(4), meta());
    encoder.set_layers_per_chunk(2);
    encoder.set_sectors(vec![Sector {
        sector_id: 1,
        name: Some("supports".to_string()),
        material_index: None,
        color_rgba: None,
        timing: Timing::default(),
    }]);
    let mut primary = vec![0u8; PIXELS];
    let mut supports = vec![0u8; PIXELS];
    for (i, pixel) in primary.iter_mut().enumerate() {
        if i % 4 < 2 {
            *pixel = 255;
        }
    }
    for (i, pixel) in supports.iter_mut().enumerate() {
        if i % 4 >= 2 {
            *pixel = 255;
        }
    }
    encoder
        .push_layer_sectors(&[(0, primary.clone()), (1, supports.clone())])
        .expect("a pushable layer");
    encoder.push_layer(&primary).expect("a pushable layer");
    encoder.push_layer(&primary).expect("a pushable layer");
    encoder.push_layer(&primary).expect("a pushable layer");
    encoder
        .set_overrides(vec![Override {
            layer: 0,
            sector_id: 1,
            timing: Timing {
                normal_exposure_ms: Some(1234),
                ..Timing::default()
            },
        }])
        .expect("one override set per (layer, sector)");
    let bytes = encoder.finish().expect("a writable file");
    validate::validate(&bytes, Level::Strict).expect("the unmodified file is valid");

    let cases: [Mutation; 4] = [
        ("ltbl.first_layr_in_range", mutate_first_layr_to_zero),
        ("ltbl.slices_disjoint", overlap_two_slices),
        ("ltbl.first_lrov_null", drop_the_override_reference),
        ("head.multi_sector_flag", clear_multi_sector),
    ];
    for (expected, mutate) in cases {
        let mutated = mutate(&bytes);
        let error = validate::validate(&mutated, Level::Strict)
            .err()
            .unwrap_or_else(|| panic!("{expected}: the file must be refused"));
        assert_eq!(error.check_name(), expected);
        let refused = LumenFile::open(&mutated, Level::Strict)
            .err()
            .unwrap_or_else(|| panic!("{expected}: the reader must refuse it too"));
        assert_eq!(refused.check_name(), expected);
    }
}

/// Rewrite the table with `edit` applied, and rebuild the file around it.
fn edit_layer_table(bytes: &[u8], edit: impl FnOnce(&mut LayerTable)) -> Vec<u8> {
    let header = container::FileHeader::parse(bytes).unwrap();
    let directory = container::parse_directory(bytes, &header).unwrap();
    let descriptor = directory.find(ChunkType::LTBL).unwrap();
    let start = descriptor.offset as usize;
    let end = start + descriptor.stored_len() as usize;
    let mut table = LayerTable::parse(&bytes[start..end]).unwrap();
    edit(&mut table);
    let mut mutated = Vec::from(&bytes[..start]);
    mutated.extend_from_slice(&table.to_bytes());
    mutated.extend_from_slice(&bytes[end..bytes.len() - 8]);
    let crc = container::crc32c(&mutated);
    mutated.extend_from_slice(&container::TRAILER_MAGIC);
    mutated.extend_from_slice(&crc.to_le_bytes());
    mutated
}

/// Name the primary sector's own chunk as HEAD's index, which no entry may.
fn mutate_first_layr_to_zero(bytes: &[u8]) -> Vec<u8> {
    edit_layer_table(bytes, |table| {
        assert!(!table.entries[0].is_empty());
        table.entries[0].first_layr = 0;
    })
}

/// Give one slice a byte of the next one's, keeping both inside their chunk.
fn overlap_two_slices(bytes: &[u8]) -> Vec<u8> {
    edit_layer_table(bytes, |table| {
        let mut previous: Option<(u32, usize)> = None;
        let mut pair = None;
        for (i, entry) in table.entries.iter().enumerate() {
            if entry.is_empty() {
                continue;
            }
            if let Some((chunk, first)) = previous {
                if chunk == entry.first_layr {
                    pair = Some((first, i));
                    break;
                }
            }
            previous = Some((entry.first_layr, i));
        }
        let (first, second) = pair.expect("a chunk holding two slices");
        assert!(table.entries[first].data_offset < table.entries[second].data_offset);
        table.entries[first].data_size += 1;
    })
}

/// Keep the overrides but stop pointing at them.
///
/// The chunk stays in the file, so what the zeroed entry asserts - that this pair
/// has no overrides - is contradicted by an override set nothing applies, which is
/// `ltbl.first_lrov_null`. The orphan rule would see the same chunk one check
/// later; section 11 orders the two so this one names the defect.
fn drop_the_override_reference(bytes: &[u8]) -> Vec<u8> {
    edit_layer_table(bytes, |table| {
        let entry = table
            .entries
            .iter_mut()
            .find(|entry| entry.first_lrov != 0)
            .expect("the file carries an override");
        entry.first_lrov = 0;
    })
}

/// Clear the `MULTI_SECTOR` flag on a file whose layers carry two sectors.
fn clear_multi_sector(bytes: &[u8]) -> Vec<u8> {
    let mut mutated = Vec::from(bytes);
    let flags = u32::from_le_bytes(mutated[20..24].try_into().unwrap());
    assert_ne!(flags & 0b10, 0);
    mutated[20..24].copy_from_slice(&(flags & !0b10u32).to_le_bytes());
    let crc = container::crc32c(&mutated[..mutated.len() - 8]);
    let end = mutated.len() - 8;
    mutated.truncate(end);
    mutated.extend_from_slice(&container::TRAILER_MAGIC);
    mutated.extend_from_slice(&crc.to_le_bytes());
    mutated
}

/// A file whose layer table claims more bytes for a layer than its stream uses.
///
/// This is the corpus' own invalid-vector style: introduce one defect, recompute
/// the trailer CRC, and assert that the advertised check is the first to fail -
/// at both levels, since padding is not a strict-only defect.
///
/// One byte moves from layer 2's slice to layer 1's: layer 1's stream now has a
/// byte after its end, and the two slices stay disjoint and inside the chunk, so
/// the trailing byte is the only defect and `ree.no_trailing_bytes` is the first
/// check to see it.
#[test]
fn padding_after_a_layer_stream_is_rejected() {
    let bytes = encode_without_hashes();
    validate::validate(&bytes, Level::Strict).expect("the unmodified file is valid");

    let mutated = pad_layer_one(&bytes);
    for level in [Level::Loose, Level::Strict] {
        let error = validate::validate(&mutated, level)
            .err()
            .unwrap_or_else(|| panic!("{level:?}: padding must be rejected"));
        assert_eq!(error.check_name(), "ree.no_trailing_bytes", "{level:?}");
    }

    // The reader refuses it as well: `open` validates first, so a layer whose
    // stored range exceeds its stream is rejected rather than decoded with the
    // surplus bytes quietly ignored.
    let refused = LumenFile::open(&mutated, Level::Loose).expect_err("the reader must refuse it");
    assert_eq!(refused.check_name(), "ree.no_trailing_bytes");
}

/// Encode the masks with the integrity tree omitted, so a mutation to the layer
/// table cannot also trip the leaf hashes.
fn encode_without_hashes() -> Vec<u8> {
    let layer_masks = masks();
    let mut encoder = Encoder::new(head(layer_masks.len() as u32), meta());
    encoder.set_dictionary(false);
    encoder.set_layer_hashes(false);
    for mask in &layer_masks {
        encoder.push_layer(mask).expect("a pushable layer");
    }
    encoder.finish().expect("a writable file")
}

/// Move one byte from layer 2's slice to layer 1's and rebuild the file around
/// it.
fn pad_layer_one(bytes: &[u8]) -> Vec<u8> {
    use lumen::chunks::ltbl::LayerTable;
    use lumen::container::{self, ChunkType};

    let header = container::FileHeader::parse(bytes).unwrap();
    let directory = container::parse_directory(bytes, &header).unwrap();
    let descriptor = directory.find(ChunkType::LTBL).unwrap();
    let start = descriptor.offset as usize;
    let end = start + descriptor.stored_len() as usize;
    let mut table = LayerTable::parse(&bytes[start..end]).unwrap();
    assert!(table.entries[1].data_size > 1, "layer 1 carries a stream");
    table.entries[1].data_size += 1;
    table.entries[2].data_offset += 1;
    table.entries[2].data_size -= 1;

    let mut mutated = Vec::from(&bytes[..start]);
    mutated.extend_from_slice(&table.to_bytes());
    mutated.extend_from_slice(&bytes[end..bytes.len() - 8]);
    let crc = container::crc32c(&mutated);
    mutated.extend_from_slice(&container::TRAILER_MAGIC);
    mutated.extend_from_slice(&crc.to_le_bytes());
    mutated
}

#[test]
fn explicit_encoding_modes_round_trip() {
    for mode in [
        EncodeMode::Auto,
        EncodeMode::Binary,
        EncodeMode::Grayscale,
        EncodeMode::Split,
        EncodeMode::Attached,
    ] {
        let mut selected: Vec<Vec<u8>> = Vec::new();
        for (index, mask) in masks().iter().enumerate() {
            let binary = mask.iter().all(|p| *p == 0 || *p == 255);
            match mode {
                EncodeMode::Binary if !binary => {
                    // Binary REE cannot represent an anti-aliased mask: the
                    // encoder must refuse it rather than re-quantise the pixels.
                    let mut probe = Encoder::new(head(1), meta());
                    let err = probe
                        .push_layer_with_mode(mask, mode)
                        .expect_err("binary REE must reject an anti-aliased mask");
                    assert_eq!(err.check_name(), "ree.first_value", "layer {index}");
                    continue;
                }
                // Section 5.7: a mask whose pixels are all 0x00/0xFF MUST use tag
                // 0x00, and section 11.3 makes a strict validator reject one
                // stored as grayscale or as split. Forcing another tag on such a
                // mask therefore builds a stream no strict reader accepts, which
                // is not a property worth asserting.
                EncodeMode::Grayscale | EncodeMode::Split if binary => continue,
                // Tag 0x03 is the parity-delta binary form when a mask carries no
                // anti-aliasing, so section 5.7 allows it there too.
                _ => {}
            }
            selected.push(mask.clone());
        }
        if mode == EncodeMode::Binary {
            continue;
        }
        assert!(!selected.is_empty(), "each mode has masks to encode");

        let mut encoder = Encoder::new(head(selected.len() as u32), meta());
        for mask in &selected {
            encoder
                .push_layer_with_mode(mask, mode)
                .unwrap_or_else(|e| panic!("a pushable layer in mode {mode:?}: {e}"));
        }
        let bytes = encoder.finish().expect("a writable file");
        validate::validate(&bytes, Level::Strict)
            .unwrap_or_else(|e| panic!("a {} file must validate strictly: {e}", mode_name(mode)));
        let file = LumenFile::open(&bytes, Level::Strict).expect("the file must open");
        for (index, mask) in selected.iter().enumerate() {
            let decoded = file.layer(index as u32).expect("a decodable layer");
            assert_eq!(
                &decoded.pixels,
                mask,
                "layer {index} in mode {}",
                mode_name(mode)
            );
        }
    }
}

fn mode_name(mode: EncodeMode) -> &'static str {
    match mode {
        EncodeMode::Auto => "Auto",
        EncodeMode::Binary => "Binary",
        EncodeMode::Grayscale => "Grayscale",
        EncodeMode::Split => "Split",
        EncodeMode::Attached => "Attached",
    }
}
