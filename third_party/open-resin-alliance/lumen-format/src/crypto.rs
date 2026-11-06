//! Authenticated encryption: the `AUTH` chunk, the AEAD units, Argon2id
//! password wrapping and X25519 machine binding ([`spec/15-encryption.md`]).
//!
//! This module owns every cryptographic parameter the specification fixes. Two
//! things are deliberately *not* here: the corpus' fixed nonces and salts (a
//! real encoder draws them from the OS CSPRNG), and the per-chunk framing, which
//! belongs to whoever knows the chunk type and unit index.

use crate::check::Check;
use crate::container::ChunkType;
use crate::error::{Error, Result};
use crate::io::{Reader, Writer};

use aes_gcm::aead::generic_array::GenericArray;
use aes_gcm::aead::{Aead, KeyInit, Payload};
use aes_gcm::Aes256Gcm;
use aes_kw::KekAes256;
use argon2::{Algorithm, Argon2, Params, Version};
use chacha20poly1305::ChaCha20Poly1305;
use hkdf::Hkdf;
use rand::rngs::OsRng;
use rand::RngCore;
use sha2::{Digest, Sha256};
use x25519_dalek::{PublicKey, StaticSecret};

/// `auth_version` this specification defines.
const AUTH_VERSION: u32 = 1;
/// Fixed `AUTH` header: cipher id, version, mode and the two section lengths.
const AUTH_HEADER_LEN: usize = 20;

/// `cipher_id` for AES-256-GCM.
pub const CIPHER_A256: [u8; 4] = *b"A256";
/// `cipher_id` for ChaCha20-Poly1305.
pub const CIPHER_C20P: [u8; 4] = *b"C20P";

/// `AUTH.mode` bit 0: a password section is present.
pub const MODE_PASSWORD: u32 = 1;
/// `AUTH.mode` bit 1: a machine-binding section is present.
pub const MODE_MACHINE: u32 = 1 << 1;

/// Fixed size of the password section.
pub const PASSWORD_SECTION_LEN: usize = 65;
/// Fixed size of one machine recipient entry.
pub const RECIPIENT_ENTRY_LEN: usize = 104;
/// Per-unit AEAD framing: 12-byte nonce, 16-byte tag.
pub const UNIT_OVERHEAD: usize = 28;

/// Recommended Argon2id ceilings from section 11.4.
pub const ARGON2_MAX_ITERATIONS: u32 = 10;
/// Recommended Argon2id memory ceiling in KiB.
pub const ARGON2_MAX_MEMORY_KIB: u32 = 4_194_304;
/// Recommended Argon2id lane ceiling.
pub const ARGON2_MAX_PARALLELISM: u32 = 16;

/// The HKDF `info` prefix for machine binding, including its NUL.
pub const MACHINE_BINDING_LABEL: &[u8] = b"LUMEN machine-binding v1\0";

/// The two AEAD ciphers the specification defines.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Cipher {
    /// AES-256-GCM, 12-byte nonce and 16-byte tag.
    Aes256Gcm,
    /// ChaCha20-Poly1305, 12-byte nonce and 16-byte tag.
    ChaCha20Poly1305,
}

impl Cipher {
    /// The four-byte AUTH identifier.
    pub fn id(self) -> [u8; 4] {
        match self {
            Cipher::Aes256Gcm => CIPHER_A256,
            Cipher::ChaCha20Poly1305 => CIPHER_C20P,
        }
    }

    /// Parse an AUTH identifier.
    pub fn from_id(id: [u8; 4]) -> Result<Cipher> {
        match id {
            CIPHER_A256 => Ok(Cipher::Aes256Gcm),
            CIPHER_C20P => Ok(Cipher::ChaCha20Poly1305),
            _ => Err(Error::new(
                Check::AuthCipherKnown,
                format!("unknown cipher_id {}", ChunkType(id).tag()),
            )),
        }
    }

    /// Nonce length in bytes.
    pub const fn nonce_len(self) -> usize {
        12
    }

    /// Tag length in bytes.
    pub const fn tag_len(self) -> usize {
        16
    }
}

/// A 256-bit session key, one per file.
#[derive(Clone, Copy, PartialEq, Eq)]
pub struct SessionKey([u8; 32]);

impl SessionKey {
    /// Wrap raw bytes.
    pub fn from_bytes(bytes: [u8; 32]) -> SessionKey {
        SessionKey(bytes)
    }

    /// The raw bytes.
    pub fn as_bytes(&self) -> &[u8; 32] {
        &self.0
    }

    /// Draw a fresh session key from the OS CSPRNG.
    pub fn generate() -> SessionKey {
        let mut bytes = [0u8; 32];
        let mut rng = OsRng;
        rng.fill_bytes(&mut bytes);
        SessionKey(bytes)
    }

    /// Derive the file's session key for `chunk_type` from a password.
    ///
    /// Convenience over [`unwrap_password`] plus [`parse_auth`].
    pub fn from_password(auth: &Auth, password: &str) -> Result<SessionKey> {
        unwrap_password(auth, password)
    }
}

impl core::fmt::Debug for SessionKey {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        f.write_str("SessionKey(<redacted>)")
    }
}

/// The fixed 65-byte password section.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PasswordSection {
    /// Argon2id salt.
    pub salt: [u8; 16],
    /// Argon2id time cost.
    pub iterations: u32,
    /// Argon2id memory cost in KiB.
    pub memory_kib: u32,
    /// Argon2id lanes.
    pub parallelism: u8,
    /// The session key wrapped with the derived KEK.
    pub wrapped_key: [u8; 40],
}

/// One machine recipient entry.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RecipientEntry {
    /// SHA-256 fingerprint of the recipient's public key.
    pub machine_fp: [u8; 32],
    /// The sender's ephemeral X25519 public key.
    pub ephemeral_pk: [u8; 32],
    /// The session key wrapped with the ECDH-derived KEK.
    pub wrapped_key: [u8; 40],
}

/// The `AUTH` chunk.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Auth {
    /// The recognized cipher.
    pub cipher: Cipher,
    /// Layout version.
    pub auth_version: u32,
    /// Bitfield: bit 0 password, bit 1 machine binding.
    pub mode: u32,
    /// The password section, when `mode` bit 0 is set.
    pub password: Option<PasswordSection>,
    /// The recipient entries, when `mode` bit 1 is set.
    pub recipients: Vec<RecipientEntry>,
}

impl Auth {
    /// The raw `cipher_id` bytes, as they appear on disk.
    pub fn cipher_id(&self) -> [u8; 4] {
        self.cipher.id()
    }

    /// Whether a password section is declared.
    pub fn has_password(&self) -> bool {
        self.mode & MODE_PASSWORD != 0
    }

    /// Whether a machine-binding section is declared.
    pub fn has_machine(&self) -> bool {
        self.mode & MODE_MACHINE != 0
    }
}

/// Parse an `AUTH` payload.
///
/// A non-empty `mode` with no matching section length is rejected here; the
/// Argon2id budget is checked by [`check_argon2_budget`], which a reader must
/// call before deriving anything.
pub fn parse_auth(payload: &[u8]) -> Result<Auth> {
    if payload.len() < AUTH_HEADER_LEN {
        return Err(Error::new(
            Check::AuthFrame,
            format!(
                "AUTH payload is {} bytes, shorter than the {AUTH_HEADER_LEN}-byte header",
                payload.len()
            ),
        ));
    }

    let mut r = Reader::checked(payload, Check::AuthFrame);
    let cipher = Cipher::from_id(r.array::<4>()?)?;
    let auth_version = r.u32()?;
    if auth_version != AUTH_VERSION {
        return Err(Error::new(
            Check::AuthVersion,
            format!("unsupported AUTH.auth_version {auth_version}, expected {AUTH_VERSION}"),
        ));
    }
    let mode = r.u32()?;
    let password_section_len = u64::from(r.u32()?);
    let machine_section_len = u64::from(r.u32()?);

    // Both declared lengths are attacker-controlled, so the bound is computed
    // before either is used as an offset or a capacity.
    if AUTH_HEADER_LEN as u64 + password_section_len + machine_section_len > payload.len() as u64 {
        return Err(Error::new(
            Check::AuthFrame,
            format!(
                "AUTH declares {password_section_len} password and {machine_section_len} machine bytes but carries only {} bytes after the header",
                payload.len() - AUTH_HEADER_LEN
            ),
        ));
    }
    if mode == 0 {
        return Err(Error::new(
            Check::CryptModeEmpty,
            "AUTH.mode is 0: neither a password nor a machine binding is declared",
        ));
    }

    let password = if mode & MODE_PASSWORD != 0 {
        if password_section_len < PASSWORD_SECTION_LEN as u64 {
            return Err(Error::new(
                Check::CryptPasswordSectionLen,
                format!(
                    "AUTH declares a {password_section_len}-byte password section, shorter than the {PASSWORD_SECTION_LEN}-byte fixed section"
                ),
            ));
        }
        let section = r.bytes(password_section_len as usize)?;
        Some(read_password_section(section)?)
    } else {
        None
    };

    let recipients = if mode & MODE_MACHINE != 0 {
        if machine_section_len < RECIPIENT_ENTRY_LEN as u64
            || machine_section_len % RECIPIENT_ENTRY_LEN as u64 != 0
        {
            return Err(Error::new(
                Check::CryptMachineSectionLen,
                format!(
                    "AUTH declares a {machine_section_len}-byte machine section, which is not a positive multiple of the {RECIPIENT_ENTRY_LEN}-byte entry size"
                ),
            ));
        }
        let section = r.bytes(machine_section_len as usize)?;
        let mut recipients = Vec::with_capacity(section.len() / RECIPIENT_ENTRY_LEN);
        for entry in section.chunks_exact(RECIPIENT_ENTRY_LEN) {
            recipients.push(read_recipient_entry(entry)?);
        }
        recipients
    } else {
        Vec::new()
    };

    Ok(Auth {
        cipher,
        auth_version,
        mode,
        password,
        recipients,
    })
}

/// Serialize an `AUTH` payload.
pub fn encode_auth(auth: &Auth) -> Vec<u8> {
    let password_section_len = if auth.password.is_some() {
        PASSWORD_SECTION_LEN
    } else {
        0
    };
    let machine_section_len = auth.recipients.len().saturating_mul(RECIPIENT_ENTRY_LEN);
    let capacity = AUTH_HEADER_LEN
        .saturating_add(password_section_len)
        .saturating_add(machine_section_len);

    let mut w = Writer::with_capacity(capacity);
    w.bytes(&auth.cipher.id());
    w.u32(auth.auth_version);
    w.u32(auth.mode);
    w.u32(password_section_len.min(u32::MAX as usize) as u32);
    w.u32(machine_section_len.min(u32::MAX as usize) as u32);
    if let Some(section) = auth.password {
        w.bytes(&section.salt);
        w.u32(section.iterations);
        w.u32(section.memory_kib);
        w.u8(section.parallelism);
        w.bytes(&section.wrapped_key);
    }
    for entry in &auth.recipients {
        w.bytes(&entry.machine_fp);
        w.bytes(&entry.ephemeral_pk);
        w.bytes(&entry.wrapped_key);
    }
    w.into_vec()
}

/// Reject Argon2id parameters past the recommended ceilings.
pub fn check_argon2_budget(section: &PasswordSection) -> Result<()> {
    if section.iterations > ARGON2_MAX_ITERATIONS {
        return Err(Error::new(
            Check::CryptArgon2Budget,
            format!(
                "AUTH declares {} Argon2id iterations, above the ceiling of {ARGON2_MAX_ITERATIONS}",
                section.iterations
            ),
        ));
    }
    if section.memory_kib > ARGON2_MAX_MEMORY_KIB {
        return Err(Error::new(
            Check::CryptArgon2Budget,
            format!(
                "AUTH declares {} KiB of Argon2id memory, above the ceiling of {ARGON2_MAX_MEMORY_KIB}",
                section.memory_kib
            ),
        ));
    }
    if u32::from(section.parallelism) > ARGON2_MAX_PARALLELISM {
        return Err(Error::new(
            Check::CryptArgon2Budget,
            format!(
                "AUTH declares {} Argon2id lanes, above the ceiling of {ARGON2_MAX_PARALLELISM}",
                section.parallelism
            ),
        ));
    }
    Ok(())
}

/// The associated data binding a unit to its identity: `chunk_type || 0x00 || unit_index`.
///
/// `unit_index` is the slot the unit occupies within its chunk type: `0` for a
/// chunk that is one unit, and the chunk's directory index for a `LAYR` frame,
/// which is one unit per chunk and would otherwise be swappable between two
/// `LAYR` chunks (`crypt.unit_index_binding`, section 9.3). The caller supplies
/// it; [`crate::chunkio`] is where the choice is made.
pub fn associated_data(chunk_type: ChunkType, unit_index: u32) -> [u8; 9] {
    let mut aad = [0u8; 9];
    aad[..4].copy_from_slice(&chunk_type.0);
    aad[4] = 0;
    aad[5..].copy_from_slice(&unit_index.to_le_bytes());
    aad
}

/// Seal one unit: random nonce, ciphertext, tag.
///
/// The nonce is drawn from the OS CSPRNG and must never repeat for a key.
pub fn seal(
    cipher: Cipher,
    key: &SessionKey,
    chunk_type: ChunkType,
    unit_index: u32,
    plaintext: &[u8],
) -> Result<Vec<u8>> {
    let mut nonce = [0u8; 12];
    let mut rng = OsRng;
    rng.fill_bytes(&mut nonce);

    let aad = associated_data(chunk_type, unit_index);
    let body = aead_encrypt(cipher, key.as_bytes(), &nonce, plaintext, &aad)?;

    let mut out = Vec::with_capacity(nonce.len() + body.len());
    out.extend_from_slice(&nonce);
    out.extend_from_slice(&body);
    Ok(out)
}

/// Open one sealed unit, verifying its tag before returning the plaintext.
pub fn open(
    cipher: Cipher,
    key: &SessionKey,
    chunk_type: ChunkType,
    unit_index: u32,
    sealed: &[u8],
) -> Result<Vec<u8>> {
    if sealed.len() < UNIT_OVERHEAD {
        return Err(Error::new(
            Check::CryptTagVerify,
            format!(
                "sealed unit is {} bytes, shorter than the {UNIT_OVERHEAD}-byte nonce and tag framing",
                sealed.len()
            ),
        ));
    }

    // The guard above makes this split total for both ciphers, whose nonces are
    // 12 bytes.
    let (nonce, body) = sealed.split_at(cipher.nonce_len());
    let aad = associated_data(chunk_type, unit_index);
    aead_decrypt(cipher, key.as_bytes(), nonce, body, &aad)
}

/// Compute a machine fingerprint: the SHA-256 of the X25519 public key.
pub fn machine_fingerprint(public_key: &[u8; 32]) -> [u8; 32] {
    let digest = Sha256::digest(public_key);
    let mut out = [0u8; 32];
    out.copy_from_slice(&digest);
    out
}

/// Recover the session key from the password section.
pub fn unwrap_password(auth: &Auth, password: &str) -> Result<SessionKey> {
    let Some(section) = auth.password.as_ref() else {
        return Err(Error::new(
            Check::CryptNoKey,
            "AUTH carries no password section",
        ));
    };
    check_argon2_budget(section)?;
    let kek = password_kek(
        password,
        &section.salt,
        section.iterations,
        section.memory_kib,
        section.parallelism,
    )?;
    Ok(SessionKey::from_bytes(aes_kw_unwrap(
        &kek,
        &section.wrapped_key,
    )?))
}

/// Recover the session key from the recipient entry matching `private_key`.
///
/// Entries that do not match are skipped; a matching entry whose X25519 result
/// is the all-zero value is rejected rather than unwrapped.
pub fn unwrap_machine(auth: &Auth, private_key: &[u8; 32]) -> Result<SessionKey> {
    let secret = StaticSecret::from(*private_key);
    let fingerprint = machine_fingerprint(PublicKey::from(&secret).as_bytes());

    let mut matched = false;
    for entry in &auth.recipients {
        if entry.machine_fp != fingerprint {
            continue;
        }
        matched = true;

        let shared = secret.diffie_hellman(&PublicKey::from(entry.ephemeral_pk));
        let ss = shared.as_bytes();
        if ss.iter().all(|byte| *byte == 0) {
            // The low-order-point result: reject this entry and keep looking,
            // because another entry may still hold the session key.
            continue;
        }

        // A matching entry that fails to unwrap is a hard error: the fingerprint
        // says this key was meant for us, so the file does not bind to it.
        let kek = machine_kek(ss, &entry.ephemeral_pk, &entry.machine_fp)?;
        return Ok(SessionKey::from_bytes(aes_kw_unwrap(
            &kek,
            &entry.wrapped_key,
        )?));
    }

    if matched {
        Err(Error::new(
            Check::CryptLowOrderPoint,
            "every recipient entry matching this machine key yields the all-zero X25519 shared secret",
        ))
    } else {
        Err(Error::new(
            Check::CryptNoKey,
            "no recipient entry carries the fingerprint of this machine key",
        ))
    }
}

/// Wrap `session` for a password, deriving the KEK with Argon2id.
pub fn wrap_password(
    session: &SessionKey,
    password: &str,
    iterations: u32,
    memory_kib: u32,
    parallelism: u8,
) -> Result<PasswordSection> {
    let mut salt = [0u8; 16];
    let mut rng = OsRng;
    rng.fill_bytes(&mut salt);

    let kek = password_kek(password, &salt, iterations, memory_kib, parallelism)?;
    Ok(PasswordSection {
        salt,
        iterations,
        memory_kib,
        parallelism,
        wrapped_key: aes_kw_wrap(&kek, session.as_bytes())?,
    })
}

/// Wrap `session` for one recipient public key.
pub fn wrap_machine(session: &SessionKey, recipient_public: &[u8; 32]) -> Result<RecipientEntry> {
    let mut ephemeral = [0u8; 32];
    let mut rng = OsRng;
    rng.fill_bytes(&mut ephemeral);

    let secret = StaticSecret::from(ephemeral);
    let ephemeral_public = PublicKey::from(&secret);
    let shared = secret.diffie_hellman(&PublicKey::from(*recipient_public));

    let fingerprint = machine_fingerprint(recipient_public);
    let kek = machine_kek(shared.as_bytes(), ephemeral_public.as_bytes(), &fingerprint)?;
    Ok(RecipientEntry {
        machine_fp: fingerprint,
        ephemeral_pk: *ephemeral_public.as_bytes(),
        wrapped_key: aes_kw_wrap(&kek, session.as_bytes())?,
    })
}

/// Read the fixed password section from the start of `section`.
///
/// The caller has already checked that `section` is at least
/// [`PASSWORD_SECTION_LEN`] bytes, so any surplus is ignored.
fn read_password_section(section: &[u8]) -> Result<PasswordSection> {
    let mut r = Reader::checked(section, Check::CryptPasswordSectionLen);
    Ok(PasswordSection {
        salt: r.array::<16>()?,
        iterations: r.u32()?,
        memory_kib: r.u32()?,
        parallelism: r.u8()?,
        wrapped_key: r.array::<40>()?,
    })
}

/// Read one fixed [`RECIPIENT_ENTRY_LEN`]-byte machine recipient entry.
fn read_recipient_entry(entry: &[u8]) -> Result<RecipientEntry> {
    let mut r = Reader::checked(entry, Check::CryptRecipientEntry);
    Ok(RecipientEntry {
        machine_fp: r.array::<32>()?,
        ephemeral_pk: r.array::<32>()?,
        wrapped_key: r.array::<40>()?,
    })
}

/// Derive the 32-byte AES-256-KW key that wraps a session key under `password`.
fn password_kek(
    password: &str,
    salt: &[u8; 16],
    iterations: u32,
    memory_kib: u32,
    parallelism: u8,
) -> Result<[u8; 32]> {
    let params =
        Params::new(memory_kib, iterations, u32::from(parallelism), Some(32)).map_err(|e| {
            Error::new(
                Check::CryptArgon2Budget,
                format!("unsupported Argon2id parameters: {e}"),
            )
        })?;
    let argon2 = Argon2::new(Algorithm::Argon2id, Version::V0x13, params);

    let mut kek = [0u8; 32];
    argon2
        .hash_password_into(password.as_bytes(), salt, &mut kek)
        .map_err(|e| {
            Error::new(
                Check::CryptArgon2Budget,
                format!("Argon2id derivation failed: {e}"),
            )
        })?;
    Ok(kek)
}

/// Derive the 32-byte AES-256-KW key that binds machine `machine_fp` to the
/// ephemeral key `ephemeral_pk` through the shared secret `ss`.
fn machine_kek(ss: &[u8; 32], ephemeral_pk: &[u8; 32], machine_fp: &[u8; 32]) -> Result<[u8; 32]> {
    let mut info = [0u8; MACHINE_BINDING_LABEL.len() + 64];
    info[..MACHINE_BINDING_LABEL.len()].copy_from_slice(MACHINE_BINDING_LABEL);
    info[MACHINE_BINDING_LABEL.len()..MACHINE_BINDING_LABEL.len() + 32]
        .copy_from_slice(ephemeral_pk);
    info[MACHINE_BINDING_LABEL.len() + 32..].copy_from_slice(machine_fp);

    let hkdf = Hkdf::<Sha256>::new(Some(machine_fp.as_slice()), ss);
    let mut kek = [0u8; 32];
    hkdf.expand(&info, &mut kek).map_err(|_| {
        Error::new(
            Check::CryptKeyUnwrap,
            "HKDF-SHA-256 expand failed for the machine-binding KEK",
        )
    })?;
    Ok(kek)
}

/// AES-256-KW wrap (RFC 3394) of a 32-byte session key.
fn aes_kw_wrap(kek: &[u8; 32], key: &[u8; 32]) -> Result<[u8; 40]> {
    let mut wrapped = [0u8; 40];
    KekAes256::from(*kek).wrap(key, &mut wrapped).map_err(|e| {
        Error::new(
            Check::CryptKeyUnwrap,
            format!("AES-256-KW wrap failed: {e}"),
        )
    })?;
    Ok(wrapped)
}

/// AES-256-KW unwrap (RFC 3394) of a 40-byte wrapped session key.
fn aes_kw_unwrap(kek: &[u8; 32], wrapped: &[u8; 40]) -> Result<[u8; 32]> {
    let mut key = [0u8; 32];
    KekAes256::from(*kek)
        .unwrap(wrapped, &mut key)
        .map_err(|e| {
            Error::new(
                Check::CryptKeyUnwrap,
                format!("AES-256-KW unwrap failed: {e}"),
            )
        })?;
    Ok(key)
}

/// AEAD-seal `msg` under `key`, returning `ciphertext || tag`.
fn aead_encrypt(
    cipher: Cipher,
    key: &[u8; 32],
    nonce: &[u8; 12],
    msg: &[u8],
    aad: &[u8],
) -> Result<Vec<u8>> {
    let payload = Payload { msg, aad };
    let nonce = GenericArray::from_slice(nonce);
    let sealed = match cipher {
        Cipher::Aes256Gcm => Aes256Gcm::new(GenericArray::from_slice(key)).encrypt(nonce, payload),
        Cipher::ChaCha20Poly1305 => {
            ChaCha20Poly1305::new(GenericArray::from_slice(key)).encrypt(nonce, payload)
        }
    };
    sealed.map_err(|_| {
        Error::new(
            Check::CryptTagVerify,
            format!("{cipher:?} encryption failed"),
        )
    })
}

/// AEAD-open `msg` under `key`, verifying the tag before returning the plaintext.
fn aead_decrypt(
    cipher: Cipher,
    key: &[u8; 32],
    nonce: &[u8],
    msg: &[u8],
    aad: &[u8],
) -> Result<Vec<u8>> {
    let payload = Payload { msg, aad };
    let nonce = GenericArray::from_slice(nonce);
    let opened = match cipher {
        Cipher::Aes256Gcm => Aes256Gcm::new(GenericArray::from_slice(key)).decrypt(nonce, payload),
        Cipher::ChaCha20Poly1305 => {
            ChaCha20Poly1305::new(GenericArray::from_slice(key)).decrypt(nonce, payload)
        }
    };
    opened.map_err(|_| {
        Error::new(
            Check::CryptTagVerify,
            format!("{cipher:?} AEAD tag did not verify"),
        )
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Argon2id parameters small enough to keep the suite fast.
    const TINY: (u32, u32, u8) = (1, 8, 1);
    const PASSWORD: &str = "lumen-crypto-test";

    fn session_key(byte: u8) -> SessionKey {
        SessionKey::from_bytes([byte; 32])
    }

    /// A deterministic X25519 keypair: `(private, public)`.
    fn keypair(seed: u8) -> ([u8; 32], [u8; 32]) {
        let secret = StaticSecret::from([seed; 32]);
        let public = PublicKey::from(&secret);
        ([seed; 32], *public.as_bytes())
    }

    fn machine_auth(recipients: Vec<RecipientEntry>) -> Auth {
        Auth {
            cipher: Cipher::Aes256Gcm,
            auth_version: AUTH_VERSION,
            mode: MODE_MACHINE,
            password: None,
            recipients,
        }
    }

    /// A hand-built `AUTH` payload, for the frames `encode_auth` cannot produce.
    fn raw_auth(
        cipher_id: [u8; 4],
        version: u32,
        mode: u32,
        password: &[u8],
        machine: &[u8],
    ) -> Vec<u8> {
        let mut w = Writer::new();
        w.bytes(&cipher_id);
        w.u32(version);
        w.u32(mode);
        w.u32(password.len() as u32);
        w.u32(machine.len() as u32);
        w.bytes(password);
        w.bytes(machine);
        w.into_vec()
    }

    /// An entry carrying `fingerprint` whose ephemeral key is the low-order
    /// point, wrapping `wrapped_session`: X25519 against it is all zeros, so a
    /// reader that does not reject it recovers the wrong session key.
    fn low_order_entry(fingerprint: &[u8; 32], wrapped_session: &SessionKey) -> RecipientEntry {
        let zero = [0u8; 32];
        let kek = machine_kek(&zero, &zero, fingerprint).unwrap();
        RecipientEntry {
            machine_fp: *fingerprint,
            ephemeral_pk: zero,
            wrapped_key: aes_kw_wrap(&kek, wrapped_session.as_bytes()).unwrap(),
        }
    }

    #[test]
    fn generated_session_keys_are_random() {
        let a = SessionKey::generate();
        let b = SessionKey::generate();
        assert_eq!(a.as_bytes().len(), 32);
        assert_ne!(a, b);
        assert_ne!(a.as_bytes(), &[0u8; 32]);
    }

    #[test]
    fn associated_data_binds_chunk_type_and_unit_index() {
        let aad = associated_data(ChunkType::LAYR, 0x0102_0304);
        assert_eq!(&aad[..4], b"LAYR");
        assert_eq!(aad[4], 0);
        assert_eq!(&aad[5..], &[0x04, 0x03, 0x02, 0x01]);
    }

    #[test]
    fn seal_open_round_trip_both_ciphers() {
        let key = session_key(0x11);
        let plaintext = b"LUMEN sealed unit payload";
        for cipher in [Cipher::Aes256Gcm, Cipher::ChaCha20Poly1305] {
            let sealed = seal(cipher, &key, ChunkType::META, 0, plaintext).unwrap();
            assert_eq!(sealed.len(), plaintext.len() + UNIT_OVERHEAD);
            assert_eq!(
                open(cipher, &key, ChunkType::META, 0, &sealed).unwrap(),
                plaintext.to_vec()
            );

            // An empty payload is still a legal unit: nonce and tag only.
            let empty = seal(cipher, &key, ChunkType::META, 0, b"").unwrap();
            assert_eq!(empty.len(), UNIT_OVERHEAD);
            assert!(open(cipher, &key, ChunkType::META, 0, &empty)
                .unwrap()
                .is_empty());

            // Every unit gets a fresh nonce.
            let again = seal(cipher, &key, ChunkType::META, 0, plaintext).unwrap();
            assert_ne!(&sealed[..12], &again[..12]);
        }
    }

    #[test]
    fn open_rejects_tampered_or_misbound_units() {
        let key = session_key(0x22);
        let other_key = session_key(0x23);
        for cipher in [Cipher::Aes256Gcm, Cipher::ChaCha20Poly1305] {
            let sealed = seal(cipher, &key, ChunkType::LAYR, 3, b"block payload").unwrap();

            let mut flipped_ciphertext = sealed.clone();
            flipped_ciphertext[12] ^= 0x01;
            assert_eq!(
                open(cipher, &key, ChunkType::LAYR, 3, &flipped_ciphertext)
                    .unwrap_err()
                    .check(),
                Check::CryptTagVerify
            );

            let mut flipped_tag = sealed.clone();
            let last = flipped_tag.len() - 1;
            flipped_tag[last] ^= 0x80;
            assert_eq!(
                open(cipher, &key, ChunkType::LAYR, 3, &flipped_tag)
                    .unwrap_err()
                    .check(),
                Check::CryptTagVerify
            );

            // Frames too short to hold a nonce and a tag are rejected outright.
            assert_eq!(
                open(
                    cipher,
                    &key,
                    ChunkType::LAYR,
                    3,
                    &sealed[..UNIT_OVERHEAD - 1]
                )
                .unwrap_err()
                .check(),
                Check::CryptTagVerify
            );
            assert_eq!(
                open(cipher, &key, ChunkType::LAYR, 3, &sealed[..12])
                    .unwrap_err()
                    .check(),
                Check::CryptTagVerify
            );

            // The AAD binds the unit to its chunk type and index.
            assert_eq!(
                open(cipher, &key, ChunkType::LAYR, 4, &sealed)
                    .unwrap_err()
                    .check(),
                Check::CryptTagVerify
            );
            assert_eq!(
                open(cipher, &key, ChunkType::META, 3, &sealed)
                    .unwrap_err()
                    .check(),
                Check::CryptTagVerify
            );

            // A different session key cannot open it.
            assert_eq!(
                open(cipher, &other_key, ChunkType::LAYR, 3, &sealed)
                    .unwrap_err()
                    .check(),
                Check::CryptTagVerify
            );
        }
    }

    #[test]
    fn password_round_trip_recovers_the_session_key() {
        let session = session_key(0x2a);
        let (iterations, memory_kib, parallelism) = TINY;
        let section =
            wrap_password(&session, PASSWORD, iterations, memory_kib, parallelism).unwrap();
        assert_eq!(section.iterations, 1);
        assert_eq!(section.memory_kib, 8);
        assert_eq!(section.parallelism, 1);
        assert_ne!(section.salt, [0u8; 16]);
        assert_eq!(check_argon2_budget(&section), Ok(()));

        let auth = Auth {
            cipher: Cipher::Aes256Gcm,
            auth_version: AUTH_VERSION,
            mode: MODE_PASSWORD,
            password: Some(section),
            recipients: Vec::new(),
        };
        assert_eq!(
            unwrap_password(&auth, PASSWORD).unwrap().as_bytes(),
            session.as_bytes()
        );
        assert_eq!(
            SessionKey::from_password(&auth, PASSWORD)
                .unwrap()
                .as_bytes(),
            session.as_bytes()
        );

        // The salt is fresh per wrap, so two sections never match.
        let again = wrap_password(&session, PASSWORD, iterations, memory_kib, parallelism).unwrap();
        assert_ne!(again.salt, section.salt);

        // A wrong password derives a KEK whose unwrap fails the RFC 3394 check.
        assert_eq!(
            unwrap_password(&auth, "lumen-crypto-tes")
                .unwrap_err()
                .check(),
            Check::CryptKeyUnwrap
        );

        // A machine-only AUTH carries no password section at all.
        assert_eq!(
            unwrap_password(&machine_auth(Vec::new()), PASSWORD)
                .unwrap_err()
                .check(),
            Check::CryptNoKey
        );
    }

    #[test]
    fn argon2_budget_rejects_cost_above_the_ceiling() {
        let base = PasswordSection {
            salt: [0x5a; 16],
            iterations: 1,
            memory_kib: 8,
            parallelism: 1,
            wrapped_key: [0; 40],
        };
        assert_eq!(check_argon2_budget(&base), Ok(()));

        let at_ceiling = PasswordSection {
            iterations: ARGON2_MAX_ITERATIONS,
            memory_kib: ARGON2_MAX_MEMORY_KIB,
            parallelism: ARGON2_MAX_PARALLELISM as u8,
            ..base
        };
        assert_eq!(check_argon2_budget(&at_ceiling), Ok(()));

        let too_many_iterations = PasswordSection {
            iterations: 99,
            ..base
        };
        assert_eq!(
            check_argon2_budget(&too_many_iterations)
                .unwrap_err()
                .check(),
            Check::CryptArgon2Budget
        );

        let too_much_memory = PasswordSection {
            memory_kib: ARGON2_MAX_MEMORY_KIB + 1,
            ..base
        };
        assert_eq!(
            check_argon2_budget(&too_much_memory).unwrap_err().check(),
            Check::CryptArgon2Budget
        );

        let too_many_lanes = PasswordSection {
            parallelism: (ARGON2_MAX_PARALLELISM + 1) as u8,
            ..base
        };
        assert_eq!(
            check_argon2_budget(&too_many_lanes).unwrap_err().check(),
            Check::CryptArgon2Budget
        );
    }

    #[test]
    fn auth_round_trips_both_modes() {
        let session = session_key(0x5c);
        let (recipient_private, recipient_public) = keypair(0x21);
        let password = wrap_password(&session, PASSWORD, 1, 8, 1).unwrap();
        let entry = wrap_machine(&session, &recipient_public).unwrap();
        let auth = Auth {
            cipher: Cipher::ChaCha20Poly1305,
            auth_version: AUTH_VERSION,
            mode: MODE_PASSWORD | MODE_MACHINE,
            password: Some(password),
            recipients: vec![entry],
        };

        let encoded = encode_auth(&auth);
        assert_eq!(&encoded[..4], b"C20P");
        assert_eq!(
            u32::from_le_bytes(encoded[4..8].try_into().unwrap()),
            AUTH_VERSION
        );
        assert_eq!(
            u32::from_le_bytes(encoded[8..12].try_into().unwrap()),
            MODE_PASSWORD | MODE_MACHINE
        );
        assert_eq!(
            u32::from_le_bytes(encoded[12..16].try_into().unwrap()),
            PASSWORD_SECTION_LEN as u32
        );
        assert_eq!(
            u32::from_le_bytes(encoded[16..20].try_into().unwrap()),
            RECIPIENT_ENTRY_LEN as u32
        );
        assert_eq!(
            encoded.len(),
            AUTH_HEADER_LEN + PASSWORD_SECTION_LEN + RECIPIENT_ENTRY_LEN
        );
        assert_eq!(
            &encoded[AUTH_HEADER_LEN..AUTH_HEADER_LEN + 16],
            &password.salt
        );
        assert_eq!(
            &encoded[AUTH_HEADER_LEN + 25..AUTH_HEADER_LEN + 65],
            &password.wrapped_key
        );
        assert_eq!(
            encoded[AUTH_HEADER_LEN + PASSWORD_SECTION_LEN + 64..],
            entry.wrapped_key
        );

        let parsed = parse_auth(&encoded).unwrap();
        assert_eq!(parsed, auth);
        assert_eq!(parsed.password.unwrap().wrapped_key, password.wrapped_key);
        assert_eq!(parsed.recipients, vec![entry]);
        assert_eq!(
            unwrap_password(&parsed, PASSWORD).unwrap().as_bytes(),
            session.as_bytes()
        );
        assert_eq!(
            unwrap_machine(&parsed, &recipient_private)
                .unwrap()
                .as_bytes(),
            session.as_bytes()
        );
    }

    #[test]
    fn auth_round_trips_single_mode_layouts() {
        let session = session_key(0x60);

        let password = wrap_password(&session, PASSWORD, 1, 8, 1).unwrap();
        let password_only = Auth {
            cipher: Cipher::Aes256Gcm,
            auth_version: AUTH_VERSION,
            mode: MODE_PASSWORD,
            password: Some(password),
            recipients: Vec::new(),
        };
        let encoded = encode_auth(&password_only);
        assert_eq!(encoded.len(), AUTH_HEADER_LEN + PASSWORD_SECTION_LEN);
        assert_eq!(parse_auth(&encoded).unwrap(), password_only);

        let first = wrap_machine(&session, &keypair(0x31).1).unwrap();
        let second = wrap_machine(&session, &keypair(0x32).1).unwrap();
        let machine_only = machine_auth(vec![first, second]);
        let encoded = encode_auth(&machine_only);
        assert_eq!(encoded.len(), AUTH_HEADER_LEN + 2 * RECIPIENT_ENTRY_LEN);
        assert_eq!(parse_auth(&encoded).unwrap(), machine_only);
    }

    #[test]
    fn parse_auth_ignores_surplus_password_section_bytes() {
        let session = session_key(0x77);
        let section = wrap_password(&session, PASSWORD, 1, 8, 1).unwrap();
        let auth = Auth {
            cipher: Cipher::Aes256Gcm,
            auth_version: AUTH_VERSION,
            mode: MODE_PASSWORD,
            password: Some(section),
            recipients: Vec::new(),
        };

        let encoded = encode_auth(&auth);
        let mut padded = encoded[AUTH_HEADER_LEN..].to_vec();
        padded.extend_from_slice(&[0u8; 5]);

        let payload = raw_auth(CIPHER_A256, AUTH_VERSION, MODE_PASSWORD, &padded, &[]);
        assert_eq!(
            u32::from_le_bytes(payload[12..16].try_into().unwrap()),
            (PASSWORD_SECTION_LEN + 5) as u32
        );

        let parsed = parse_auth(&payload).unwrap();
        assert_eq!(parsed.password, Some(section));
        assert_eq!(
            unwrap_password(&parsed, PASSWORD).unwrap().as_bytes(),
            session.as_bytes()
        );
    }

    #[test]
    fn parse_auth_rejects_malformed_frames() {
        let password = [0u8; PASSWORD_SECTION_LEN];

        // Shorter than the fixed header.
        assert_eq!(
            parse_auth(&[0u8; AUTH_HEADER_LEN - 1]).unwrap_err().check(),
            Check::AuthFrame
        );
        assert_eq!(parse_auth(&[]).unwrap_err().check(), Check::AuthFrame);

        // Declared sections that do not fit in the payload.
        let mut overrun = raw_auth(CIPHER_A256, AUTH_VERSION, MODE_MACHINE, &[], &[]);
        overrun[16..20].copy_from_slice(&(RECIPIENT_ENTRY_LEN as u32).to_le_bytes());
        assert_eq!(parse_auth(&overrun).unwrap_err().check(), Check::AuthFrame);

        // An unrecognized cipher or layout version.
        assert_eq!(
            parse_auth(&raw_auth(
                *b"XXXX",
                AUTH_VERSION,
                MODE_PASSWORD,
                &password,
                &[]
            ))
            .unwrap_err()
            .check(),
            Check::AuthCipherKnown
        );
        assert_eq!(
            parse_auth(&raw_auth(CIPHER_A256, 2, MODE_PASSWORD, &password, &[]))
                .unwrap_err()
                .check(),
            Check::AuthVersion
        );

        // Neither mode declared.
        assert_eq!(
            parse_auth(&raw_auth(CIPHER_A256, AUTH_VERSION, 0, &[], &[]))
                .unwrap_err()
                .check(),
            Check::CryptModeEmpty
        );

        // A password section one byte short of the fixed size.
        assert_eq!(
            parse_auth(&raw_auth(
                CIPHER_A256,
                AUTH_VERSION,
                MODE_PASSWORD,
                &password[..PASSWORD_SECTION_LEN - 1],
                &[]
            ))
            .unwrap_err()
            .check(),
            Check::CryptPasswordSectionLen
        );

        // A machine section with no complete recipient entry.
        assert_eq!(
            parse_auth(&raw_auth(CIPHER_C20P, AUTH_VERSION, MODE_MACHINE, &[], &[]))
                .unwrap_err()
                .check(),
            Check::CryptMachineSectionLen
        );
        assert_eq!(
            parse_auth(&raw_auth(
                CIPHER_C20P,
                AUTH_VERSION,
                MODE_MACHINE,
                &[],
                &[0u8; RECIPIENT_ENTRY_LEN + 1]
            ))
            .unwrap_err()
            .check(),
            Check::CryptMachineSectionLen
        );
    }

    #[test]
    fn machine_round_trip_recovers_the_session_key() {
        let session = session_key(0x33);
        let (private, public) = keypair(0x07);
        let entry = wrap_machine(&session, &public).unwrap();
        assert_eq!(entry.machine_fp, machine_fingerprint(&public));
        assert_ne!(entry.ephemeral_pk, [0u8; 32]);

        assert_eq!(
            unwrap_machine(&machine_auth(vec![entry]), &private)
                .unwrap()
                .as_bytes(),
            session.as_bytes()
        );

        // Each wrap uses a fresh ephemeral keypair.
        let other = wrap_machine(&session, &public).unwrap();
        assert_eq!(other.machine_fp, entry.machine_fp);
        assert_ne!(other.ephemeral_pk, entry.ephemeral_pk);
        assert_ne!(other.wrapped_key, entry.wrapped_key);
    }

    #[test]
    fn machine_unwrap_skips_recipients_for_other_machines() {
        let session = session_key(0x44);
        let (stranger_private, stranger_public) = keypair(0x08);
        let (our_private, our_public) = keypair(0x09);
        let auth = machine_auth(vec![
            wrap_machine(&session, &stranger_public).unwrap(),
            wrap_machine(&session, &our_public).unwrap(),
        ]);

        // The matching entry sits after one that is not ours.
        assert_eq!(
            unwrap_machine(&auth, &our_private).unwrap().as_bytes(),
            session.as_bytes()
        );
        // The stranger still recovers it from their own entry.
        assert_eq!(
            unwrap_machine(&auth, &stranger_private).unwrap().as_bytes(),
            session.as_bytes()
        );

        // A machine key in no entry at all is CryptNoKey.
        let (absent_private, _) = keypair(0x0a);
        assert_eq!(
            unwrap_machine(&auth, &absent_private).unwrap_err().check(),
            Check::CryptNoKey
        );
        assert_eq!(
            unwrap_machine(&machine_auth(Vec::new()), &our_private)
                .unwrap_err()
                .check(),
            Check::CryptNoKey
        );
    }

    #[test]
    fn machine_unwrap_skips_low_order_entry_and_keeps_searching() {
        let session = session_key(0x55);
        let decoy_session = session_key(0x56);
        let (our_private, our_public) = keypair(0x0b);
        let fingerprint = machine_fingerprint(&our_public);

        let decoy = low_order_entry(&fingerprint, &decoy_session);
        // The decoy is coherent: a reader that unwraps without checking the
        // shared secret recovers the wrong session key from it.
        let zero = [0u8; 32];
        let decoy_kek = machine_kek(&zero, &zero, &fingerprint).unwrap();
        assert_eq!(
            aes_kw_unwrap(&decoy_kek, &decoy.wrapped_key).unwrap(),
            *decoy_session.as_bytes()
        );

        let auth = machine_auth(vec![decoy, wrap_machine(&session, &our_public).unwrap()]);
        let recovered = unwrap_machine(&auth, &our_private).unwrap();
        assert_eq!(recovered.as_bytes(), session.as_bytes());
        assert_ne!(recovered.as_bytes(), decoy_session.as_bytes());
    }

    #[test]
    fn machine_unwrap_reports_low_order_when_every_match_is_rejected() {
        let decoy_session = session_key(0x56);
        let (our_private, our_public) = keypair(0x0b);
        let fingerprint = machine_fingerprint(&our_public);

        let auth = machine_auth(vec![low_order_entry(&fingerprint, &decoy_session)]);
        assert_eq!(
            unwrap_machine(&auth, &our_private).unwrap_err().check(),
            Check::CryptLowOrderPoint
        );
    }

    #[test]
    fn machine_unwrap_rejects_a_matching_entry_that_does_not_unwrap() {
        let session = session_key(0x66);
        let (our_private, our_public) = keypair(0x0c);
        let mut entry = wrap_machine(&session, &our_public).unwrap();
        entry.wrapped_key[0] ^= 0x01;

        assert_eq!(
            unwrap_machine(&machine_auth(vec![entry]), &our_private)
                .unwrap_err()
                .check(),
            Check::CryptKeyUnwrap
        );
    }
}
