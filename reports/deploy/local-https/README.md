# Try ZEIM from an iPhone or iPad with local HTTPS (DRAFT, for Zach)

Why: Safari only offers the share sheet (Files, iCloud, Mail, Shapr3D, Creality app...) on secure `https://` pages.
A plain `http://192.168.x.x:8765` address on your home network will not get it.

**Status: proposal. The Caddy config passes `caddy validate`, and a stand-in web server on this computer answered over HTTPS using Caddy's certificate. It has NOT been tried on a real iPhone/iPad, so treat the iOS steps as untested.**

## Safety first
- Home network only. Do not use this at school or on any shared Wi-Fi. There is no real login in ZEIM yet.
- Turn it off when you are done (step 6). Don't use real kids' photos or accounts while testing.
- ZEIM itself stays on this computer only (`HOST` left at its default `127.0.0.1`). Only Caddy is open to your network, on port 8443.

## Steps (on the Mac or PC that runs ZEIM)
1. **Start ZEIM** the normal way (`./run.sh`). No LAN opt-in is needed, because Caddy talks to it on this same computer.
   (Only if you ever want to reach ZEIM directly without Caddy would you set `HOST=0.0.0.0`; don't, for this test.)
2. **Find this computer's home-network address.**
   Mac: System Settings > Wi-Fi > Details > IP address (or run `ipconfig getifaddr en0`).
   Windows: run `ipconfig` and read "IPv4 Address".
   It looks like `192.168.1.50`. Ideally set a fixed (reserved) address for this computer in your router so it doesn't change.
3. **Start Caddy** (install it first from caddyserver.com if needed). In this folder:
   ```bash
   ZEIM_LAN_NAME=192.168.1.50 caddy run --config Caddyfile.local --adapter caddyfile
   ```
   Use your own address. A `.local` name like `my-mac.local` also works if both devices are on the same Wi-Fi.
   Caddy creates its own private "certificate authority" (CA) the first time. The file you need is `root.crt`:
   - Mac: `~/Library/Application Support/Caddy/pki/authorities/local/root.crt`
   - Linux: `~/.local/share/caddy/pki/authorities/local/root.crt`
   - Windows: `%AppData%\Caddy\pki\authorities\local\root.crt`

   Only `root.crt` is safe to share. **Never share `root.key`** (same folder): whoever has it can make certificates your devices would trust.
4. **Get `root.crt` onto the iPhone/iPad.** AirDrop it, or email it to yourself and open the attachment. (The file is public information; the key is the secret.)
   Then on the device (iOS steps per Apple: https://support.apple.com/en-us/102390 and https://support.apple.com/guide/deployment/intro-to-certificate-management-depb5eff8914/web):
   1. Allow the download if Safari asks ("Profile Downloaded").
   2. Settings > General > VPN & Device Management > tap the downloaded profile > Install (enter passcode, accept the warning).
      On some iOS versions the banner can also read "Profile Downloaded" at the top of Settings; either route works.
   3. **Settings > General > About > Certificate Trust Settings** > under "Enable full trust for root certificates", switch ON the Caddy certificate.
      (If that section is missing, the certificate wasn't installed yet; Apple says the same.)
5. **Open ZEIM:** in Safari go to `https://192.168.1.50:8443` (your address, with `https://` and `:8443`). You should see a padlock and no warning.
   Then try Send > Share.
6. **When finished:** stop Caddy (Ctrl+C in its window) and stop ZEIM. On the device, remove the profile (Settings > General > VPN & Device Management > the profile > Remove Profile) so the test CA is no longer trusted.

If the page says "not secure", check: address typed exactly as in step 3; trust switch is ON; Caddy is running; the device is on the same Wi-Fi; your firewall allows port 8443.
If your address changes later, the certificate no longer matches: restart Caddy with the new address.

## Alternative: a tunnel (real HTTPS, no certificate install)
Tools such as Cloudflare Tunnel (`cloudflared tunnel --url http://127.0.0.1:8765`, "quick tunnel") or Tailscale (Serve for your own devices only; Funnel makes it public) give a normal `https://` address.
Tradeoffs:
- A third-party service sits between your devices and ZEIM and sees the traffic.
- Quick tunnels and Funnel give a **public** internet address: anyone with the link can reach ZEIM, and ZEIM has no real login yet.
- Addresses can change each run, and the service's terms apply. Verify current features and terms on the provider's site before using.
- Do not use with kids' data or real student photos. Tailscale Serve (private to your own signed-in devices) is the gentler option, but it needs an account and the app installed on each device.
