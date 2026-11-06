//! The named conformance checks.
//!
//! Every check carries the `<group>.<rule>` name the specification's conformance
//! corpus uses in `expected_failure` ([`test-vectors/README.md`]), so a failure
//! reported by this crate can be compared verbatim against the corpus. Names are
//! stable: see `spec/17-validation.md` section 11, which groups them.

/// A named conformance check, mirroring the corpus convention `<group>.<rule>`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
#[non_exhaustive]
pub enum Check {
    // -- group: trailer (section 3.3) --------------------------------------
    /// `LEND` magic is absent from the last 8 bytes.
    TrailerMagic,
    /// Trailer CRC-32C does not match `bytes[0 .. file_len-8]`.
    TrailerCrc32c,

    // -- group: header (section 3.1) ---------------------------------------
    /// `LUMN` magic is absent at offset 0.
    HeaderMagic,
    /// `header.version` is not recognized.
    HeaderVersion,
    /// `header.dir_offset` is outside the file, or the directory does not fit.
    HeaderDirOffset,
    /// `header.flags` sets a reserved bit (0, 2 or 4).
    HeaderFlagsReserved,
    /// `header.total_uncompressed_size` is non-zero and wrong.
    HeaderTotalUncompressedSize,

    // -- group: dir (section 3.2) ------------------------------------------
    /// A chunk descriptor could not be read.
    DirDescriptor,
    /// Two chunks overlap.
    DirOverlap,
    /// A chunk's stored extent lies outside the file, or inside the directory.
    DirChunkExtent,
    /// The first chunk is not `HEAD`.
    DirHeadFirst,

    // -- group: presence (section 3, section 4) ----------------------------
    /// A required chunk is missing.
    PresenceHead,
    /// `META` is missing.
    PresenceMeta,
    /// `LTBL` is missing.
    PresenceLtbl,
    /// `LAYR` is missing.
    PresenceLayr,
    /// The `ENCRYPTED` flag is set but `AUTH` is absent, or vice versa.
    PresenceAuth,
    /// Exactly one `ZDIC` is required (or forbidden) by the `LAYR` frames.
    PresenceZdic,

    // -- group: head (section 4.1) ------------------------------------------
    /// `head_version` is not recognized.
    HeadVersion,
    /// `encoder_name_len` exceeds 256, or the chunk is not exactly the fixed
    /// fields plus the name.
    HeadFrame,
    /// `total_layers == 0`, or disagrees with `LTBL.layer_count`.
    HeadTotalLayers,
    /// `layer_height_um == 0`.
    HeadLayerHeight,
    /// A build dimension is zero.
    HeadBuildDims,
    /// `display_width_px * display_height_px == 0`.
    HeadDisplayPixels,
    /// `MULTI_SECTOR` is set without a layer carrying more than one sector, or
    /// clear while one does.
    HeadMultiSectorFlag,

    // -- group: auth (section 4.4) -----------------------------------------
    /// `auth_version` is not recognized.
    AuthVersion,
    /// `cipher_id` is not `A256` or `C20P`.
    AuthCipherKnown,
    /// The AUTH payload is too short for its declared sections.
    AuthFrame,

    // -- group: meta (section 4.2) -----------------------------------------
    /// The META payload is not a JSON object.
    MetaJson,
    /// `meta_version` is absent or unrecognized.
    MetaVersion,
    /// A required META field is absent.
    MetaRequiredFields,
    /// A META duration is not an integer number of milliseconds.
    MetaTimeInteger,
    /// An exposure time is not `> 0`.
    MetaExposure,
    /// `layer_height_um` is not `> 0`.
    MetaLayerHeight,
    /// `materials`, when present, is not a non-empty array of named entries.
    MetaMaterialsShape,
    /// `sectors`, when present, is not an array of objects with unique ids >= 1.
    MetaSectorsShape,
    /// A sector's `material_index` addresses no non-empty `materials` array.
    MetaSectorMaterialIndex,
    /// A cure curve has a non-positive `dp_um`/`ec_mj_cm2` or a negative `e0_mj_cm2`.
    MetaCureCurve,
    /// A temperature is outside `[0.0, 120.0]`.
    MetaTemperatureRange,
    /// A `light_pwm` or `bottom_light_pwm` is outside `0..=255`, in any payload
    /// that carries one (section 4.2).
    PwmRange,

    // -- group: prof (section 4.3) -----------------------------------------
    /// `profile_type` is not one of `material`, `printer`, `combined`.
    ProfProfileType,
    /// `profile_name` or `profile_version` is empty.
    ProfProfileIdentity,
    /// A profile duration is not an integer number of milliseconds.
    ProfSettingsTimeInteger,
    /// A profile exposure time is not `> 0`.
    ProfSettingsExposure,
    /// A profile `layer_height_um` is not `> 0`.
    ProfSettingsLayerHeight,
    /// A profile cure curve is out of range.
    ProfCureCurve,
    /// `profile_uuid` is not a well-formed UUID string.
    ProfProfileUuid,
    /// Profile materials are malformed.
    ProfMaterialsShape,

    // -- group: lrov (section 4.5) -----------------------------------------
    /// The payload is not a JSON object.
    LrovJson,
    /// An overridden duration is not an integer number of milliseconds.
    LrovTimeInteger,
    /// An `LROV` chunk is referenced by no entry. Several entries naming one
    /// chunk is how an override set covers a range of pairs, and is legal.
    LrovOrphan,

    // -- group: prev (section 4.6) -----------------------------------------
    /// A reserved flag bit is set, or the role is outside 0-3.
    PrevFlags,
    /// The payload does not begin with the PNG signature (strict mode).
    PrevPngSignature,

    // -- group: voxl (section 4.11) ----------------------------------------
    /// The payload is neither VOXL V2 nor a VOXL V1 document (strict mode).
    VoxlSignature,

    // -- group: extd (section 4.12) ----------------------------------------
    /// The payload is shorter than the 8-byte frame.
    ExtdFrame,
    /// `ext_type` is not four ASCII characters.
    ExtdExtType,
    /// A reserved flag bit is set.
    ExtdFlags,
    /// An unimplemented extension carries `critical = 1`.
    ExtdCritical,

    // -- group: ltbl (section 4.7) -----------------------------------------
    /// `table_version` is not recognized.
    LtblVersion,
    /// `layer_count` disagrees with `HEAD.total_layers`.
    LtblLayerCount,
    /// `entry_size < 28`, or the entries do not fit the chunk.
    LtblEntrySize,
    /// The entries do not account for every layer, or `entry_count` disagrees
    /// with the sum of `1 + additional_sector_count` over each layer's first
    /// entry, or a non-first entry carries a non-zero count.
    LtblEntryCount,
    /// A read or a table entry names a layer the table does not describe.
    LtblLayerIndexRange,
    /// Sector ids do not ascend within a layer.
    LtblSectorIdsAscending,
    /// The same sector id appears twice on one layer.
    LtblSectorIdUnique,
    /// A layer's first entry is not sector 0's.
    LtblFirstEntryIsSectorZero,
    /// `first_layr` is not the directory index of a `LAYR` chunk.
    LtblFirstLayrInRange,
    /// An `LROV` chunk no entry names carries a payload no named chunk carries.
    LtblFirstLrovNull,
    /// `first_lrov` is neither `0` nor the directory index of an `LROV` chunk.
    LtblFirstLrovInRange,
    /// `data_offset + data_size` exceeds the `LAYR` chunk's decompressed output.
    LtblOffsetWithinChunk,
    /// Two slices of one `LAYR` chunk overlap.
    LtblSlicesDisjoint,

    // -- group: layr (section 4.9) ----------------------------------------
    /// `layr_version` is not recognized.
    LayrVersion,
    /// A frame carries no content size, so a reader cannot size its output.
    LayrContentSizePresent,
    /// A frame did not decompress to the size it declares.
    LayrFrameDecompressedSize,
    /// A frame's declared output exceeds what its stored size may expand to.
    FrameAllocationBound,
    /// A frame's dictionary ID disagrees with `ZDIC`.
    LayrDictIdMatch,
    /// A frame reports no dictionary while the file carries `ZDIC`.
    LayrDictIdAbsent,

    // -- group: zdic (section 4.8) -----------------------------------------
    /// `zdic_version` is not recognized.
    ZdicVersion,
    /// `dict_size` exceeds `ZDIC_DICTSIZE_MAX`, or the bytes are missing.
    ZdicDictSize,
    /// `dict_id` disagrees with the `LAYR` frames.
    ZdicDictIdMatch,
    /// More than one non-null `ZDIC` chunk is present.
    ZdicSingle,

    // -- group: lhas (section 4.10) ----------------------------------------
    /// The payload is too short for its header and hashes.
    LhasFrame,
    /// `hash_algorithm` is not `0x01` (SHA-256).
    LhasHashAlgorithm,
    /// `layer_count` disagrees with `HEAD.total_layers`.
    LhasLayerCount,
    /// The recomputed Merkle root differs from the stored one.
    LhasRootRecompute,
    /// A layer's recomputed leaf hash differs from the stored one (strict mode).
    LhasLeafMatch,

    // -- group: ree (section 5) --------------------------------------------
    /// A layer carries an encoding tag other than `0x00`-`0x03`.
    ReeTag,
    /// A varint is overlong, truncated, or longer than 10 bytes.
    ReeVarint,
    /// The four plane lengths of a varint array describe planes that are not
    /// prefix-closed, or that hold more bytes than the array's varints use
    /// (strict); or a value needs more than four planes to encode.
    ReePlanes,
    /// A binary REE `first_value` is neither `0x00` nor `0xFF`.
    ReeFirstValue,
    /// The non-canonical `run_count == 0` form (strict mode).
    ReeNoRunCountZero,
    /// A stored run length is zero, or the lengths do not sum to `total_pixels` (strict).
    ReeRunLengths,
    /// Adjacent grayscale runs carry the same value, or a run is empty (strict).
    ReeGrayscaleRuns,
    /// An all-`0x00`/`0xFF` layer is stored as grayscale REE (strict).
    ReeGrayscaleAllBinary,
    /// An all-`0x00`/`0xFF` layer is stored as split REE, with no anti-aliasing
    /// to overlay (strict).
    ReeSplitAllBinary,
    /// The split binary component does not threshold at `v >= 128` (strict).
    ReeSplitThreshold,
    /// Split overlay positions are not strictly increasing, or out of range.
    ReeSplitPositions,
    /// Attached-form escapes are not strictly increasing, fall outside the layer,
    /// or do not sit strictly inside the core run they belong to.
    ReeAttachPositions,
    /// `aa_pixel_count` disagrees with the pixels the attachment bits and escapes
    /// describe.
    ReeAttachCount,
    /// An attachment bit addresses a run that does not exist, or a run of one
    /// pixel claims both of its ends, or padding bits past the last run are set
    /// (strict).
    ReeAttachBits,
    /// An attached-form overlay value is `0x00`/`0xFF`, or does not threshold to
    /// the core run it sits in (strict).
    ReeAttachThreshold,
    /// The decoded stream does not end exactly at `total_pixels`.
    ReeEndPositions,
    /// Bytes follow the end of a layer's REE stream.
    ReeNoTrailingBytes,
    /// A layer's `data_size` does not match its decoded stream.
    ReeDataSize,

    // -- group: sector (section 7) -----------------------------------------
    /// Sector masks of one layer overlap (strict mode).
    SectorPartition,

    // -- group: crypt (section 9) ------------------------------------------
    /// `AUTH.mode` has no bit set.
    CryptModeEmpty,
    /// The password section is shorter than its fixed 65 bytes.
    CryptPasswordSectionLen,
    /// The machine section holds no complete recipient entry.
    CryptMachineSectionLen,
    /// Argon2id parameters exceed the reader's budget.
    CryptArgon2Budget,
    /// A chunk's encrypted flag disagrees with the file's `ENCRYPTED` flag.
    CryptChunkFlags,
    /// An AEAD tag did not verify.
    CryptTagVerify,
    /// A `LAYR` frame's associated data did not bind it to its directory index.
    CryptUnitIndexBinding,
    /// A wrapped session key did not unwrap.
    CryptKeyUnwrap,
    /// A machine recipient entry is malformed.
    CryptRecipientEntry,
    /// An X25519 exchange produced the all-zero shared secret.
    CryptLowOrderPoint,
    /// No key could be recovered: wrong password, or no matching recipient.
    CryptNoKey,
}

impl Check {
    /// The `<group>.<rule>` name, verbatim as the conformance corpus spells it.
    pub fn name(self) -> &'static str {
        use Check::*;
        match self {
            TrailerMagic => "trailer.magic",
            TrailerCrc32c => "trailer.crc32c",
            HeaderMagic => "header.magic",
            HeaderVersion => "header.version",
            HeaderDirOffset => "header.dir_offset",
            HeaderFlagsReserved => "header.flags_reserved",
            HeaderTotalUncompressedSize => "header.total_uncompressed_size",
            DirDescriptor => "dir.descriptor",
            DirOverlap => "dir.overlap",
            DirChunkExtent => "dir.chunk_extent",
            DirHeadFirst => "dir.head_first",
            PresenceHead => "presence.head",
            PresenceMeta => "presence.meta",
            PresenceLtbl => "presence.ltbl",
            PresenceLayr => "presence.layr",
            PresenceAuth => "presence.auth",
            PresenceZdic => "presence.zdic",
            HeadVersion => "head.version",
            HeadFrame => "head.frame",
            HeadTotalLayers => "head.total_layers",
            HeadLayerHeight => "head.layer_height",
            HeadBuildDims => "head.build_dims",
            HeadDisplayPixels => "head.display_pixels",
            HeadMultiSectorFlag => "head.multi_sector_flag",
            AuthVersion => "auth.version",
            AuthCipherKnown => "auth.cipher_known",
            AuthFrame => "auth.frame",
            MetaJson => "meta.json",
            MetaVersion => "meta.version",
            MetaRequiredFields => "meta.required_fields",
            MetaTimeInteger => "meta.time_integer",
            MetaExposure => "meta.exposure",
            MetaLayerHeight => "meta.layer_height",
            MetaMaterialsShape => "meta.materials_shape",
            MetaSectorsShape => "meta.sectors_shape",
            MetaSectorMaterialIndex => "meta.sector_material_index",
            MetaCureCurve => "meta.cure_curve",
            MetaTemperatureRange => "meta.temperature_range",
            PwmRange => "pwm.range",
            ProfProfileType => "prof.profile_type",
            ProfProfileIdentity => "prof.profile_identity",
            ProfSettingsTimeInteger => "prof.settings_time_integer",
            ProfSettingsExposure => "prof.settings_exposure",
            ProfSettingsLayerHeight => "prof.settings_layer_height",
            ProfCureCurve => "prof.cure_curve",
            ProfProfileUuid => "prof.profile_uuid",
            ProfMaterialsShape => "prof.materials_shape",
            LrovJson => "lrov.json",
            LrovTimeInteger => "lrov.time_integer",
            LrovOrphan => "lrov.orphan",
            PrevFlags => "prev.flags",
            PrevPngSignature => "prev.png_signature",
            VoxlSignature => "voxl.signature",
            ExtdFrame => "extd.frame",
            ExtdExtType => "extd.ext_type",
            ExtdFlags => "extd.flags",
            ExtdCritical => "extd.critical",
            LtblVersion => "ltbl.version",
            LtblLayerCount => "ltbl.layer_count",
            LtblEntrySize => "ltbl.entry_size",
            LtblEntryCount => "ltbl.entry_count",
            LtblLayerIndexRange => "ltbl.layer_index_range",
            LtblSectorIdsAscending => "ltbl.sector_ids_ascending",
            LtblSectorIdUnique => "ltbl.sector_id_unique",
            LtblFirstEntryIsSectorZero => "ltbl.first_entry_is_sector_zero",
            LtblFirstLayrInRange => "ltbl.first_layr_in_range",
            LtblFirstLrovNull => "ltbl.first_lrov_null",
            LtblFirstLrovInRange => "ltbl.first_lrov_in_range",
            LtblOffsetWithinChunk => "ltbl.offset_within_chunk",
            LtblSlicesDisjoint => "ltbl.slices_disjoint",
            LayrVersion => "layr.version",
            LayrContentSizePresent => "layr.content_size_present",
            LayrFrameDecompressedSize => "layr.frame_decompressed_size",
            FrameAllocationBound => "frame.allocation_bound",
            LayrDictIdMatch => "layr.dict_id_match",
            LayrDictIdAbsent => "layr.dict_id_absent",
            ZdicVersion => "zdic.version",
            ZdicDictSize => "zdic.dict_size",
            ZdicDictIdMatch => "zdic.dict_id_match",
            ZdicSingle => "zdic.single",
            LhasFrame => "lhas.frame",
            LhasHashAlgorithm => "lhas.hash_algorithm",
            LhasLayerCount => "lhas.layer_count",
            LhasRootRecompute => "lhas.root_recompute",
            LhasLeafMatch => "lhas.leaf_match",
            ReeTag => "ree.tag",
            ReeVarint => "ree.varint",
            ReePlanes => "ree.planes",
            ReeFirstValue => "ree.first_value",
            ReeNoRunCountZero => "ree.no_run_count_zero",
            ReeRunLengths => "ree.run_lengths",
            ReeGrayscaleRuns => "ree.grayscale_runs",
            ReeGrayscaleAllBinary => "ree.grayscale_all_binary",
            ReeSplitAllBinary => "ree.split_all_binary",
            ReeSplitThreshold => "ree.split_threshold",
            ReeSplitPositions => "ree.split_positions",
            ReeAttachPositions => "ree.attach_positions",
            ReeAttachCount => "ree.attach_count",
            ReeAttachBits => "ree.attach_bits",
            ReeAttachThreshold => "ree.attach_threshold",
            ReeEndPositions => "ree.end_positions",
            ReeNoTrailingBytes => "ree.no_trailing_bytes",
            ReeDataSize => "ree.data_size",
            SectorPartition => "sector.partition",
            CryptModeEmpty => "crypt.mode_empty",
            CryptPasswordSectionLen => "crypt.password_section_len",
            CryptMachineSectionLen => "crypt.machine_section_len",
            CryptArgon2Budget => "crypt.argon2_budget",
            CryptChunkFlags => "crypt.chunk_flags",
            CryptTagVerify => "crypt.tag_verify",
            CryptUnitIndexBinding => "crypt.unit_index_binding",
            CryptKeyUnwrap => "crypt.key_unwrap",
            CryptRecipientEntry => "crypt.recipient_entry",
            CryptLowOrderPoint => "crypt.low_order_point",
            CryptNoKey => "crypt.no_key",
        }
    }

    /// Whether the specification marks this check strict-mode only ([section 11.5]).
    ///
    /// A loose-mode read must not fail these; a strict validator must.
    pub fn is_strict_only(self) -> bool {
        use Check::*;
        matches!(
            self,
            ReeNoRunCountZero
                | ReePlanes
                | ReeRunLengths
                | ReeGrayscaleRuns
                | ReeGrayscaleAllBinary
                | ReeSplitAllBinary
                | ReeSplitThreshold
                | ReeAttachBits
                | ReeAttachThreshold
                | SectorPartition
                | LhasLeafMatch
                | PrevPngSignature
                | VoxlSignature
        )
    }
}

impl core::fmt::Display for Check {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        f.write_str(self.name())
    }
}
