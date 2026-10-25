# Setup guide

This guide sets up one server and connects any number of consoles to it.

- **Server administrator:** whoever runs the server. They follow every step.
- **Friends:** they only need the patched SD card files (steps 3–5), plus a relay if they
  live elsewhere (step 6).

Time needed: about an hour for the administrator, 15 minutes per friend.

---

## 0. Before you start

- **Custom firmware.** Every console needs **Luma3DS 13.x** with boot9strap. If you
  don't have custom firmware yet, follow <https://3ds.hacks.guide> first.
- **System version.** System Settings shows it in the lower-right corner of the top
  screen. It must be **11.17.0** (any region letter). If it is older, run System Update
  (it is safe with current Luma3DS).
- **Swapnote.** It must be the US version, updated to v3.3.0 (the last update).
- **Optional check.** Copy `tools/gm9/check_versions.gm9` to `/gm9/scripts/` on the SD
  card. Run it from GodMode9 (hold START while powering on → HOME → Scripts). It checks
  both versions and changes nothing.

## 1. Back up your Swapnote data

Do this on every console before installing anything.

1. Power off and put the SD card in a computer.
2. Copy the whole **`Nintendo 3DS`** folder from the SD card to the computer. It
   contains Swapnote's save and its extra data (your notes).

To restore, copy it back. If you use JKSM or Checkpoint, a save backup from there also
works.

## 2. Set up the server (administrator)

**Run it on an always-on machine.** Friends' consoles check for notes every hour, so the
server must be reachable whenever they do. A home server, NAS or Raspberry Pi works well.

1. **Get the code** on the server machine:

   ```sh
   git clone <this repository> swapnote-revival
   cd swapnote-revival
   ```

2. **Pick a server name.** It is only used inside your setup and does not need to exist in
   public DNS. The rules:
   - lowercase letters, digits, dots and dashes;
   - **at most 22 characters**;
   - e.g. `swapnote.home.arpa` (18 characters).

   You will use the same name in the config and when building the patches.

3. **Create the config:**

   ```sh
   cp server/server.example.toml server.toml
   ```

   Edit `server.toml`:
   - **`server_name`:** your name from step 2.
   - **`bind`:**
     - `0.0.0.0` if consoles on your home network connect directly;
     - your Tailscale address (`tailscale ip -4`) if only relays connect.
   - **`allowed_networks`:**
     - keep `100.64.0.0/10` (Tailscale);
     - keep your home network's range, e.g. `192.168.1.0/24`;
     - remove what you don't use.
   - **`allowed_pids`:** set it to `[0]` for now, which allows no console. You will add the
     real values in step 7.
   - Leave `[debug]` off.

4. **Try it in a terminal:**

   ```sh
   python3 server/hpp_server.py server.toml
   ```

   Stop it with Ctrl+C. You can also run the self-test: `server/tests/run_tests.sh`.

5. **Install it as a service** (Linux with systemd). The commands are at the top of
   `server/swapnote-server.service`. They create a dedicated `swapnote` user, copy the
   server to `/opt/swapnote` and the config to `/etc/swapnote/server.toml`, and keep notes
   in `/var/lib/swapnote` (only readable by that user). Remember to set
   `data = "/var/lib/swapnote"` in the copied config. Check it with:

   ```sh
   systemctl status swapnote-server
   journalctl -u swapnote-server -f
   ```

6. **Firewall:**
   - If consoles on your LAN connect directly, allow TCP port 8080 from your LAN.
   - **Do not forward any port on your router.** Remote friends come in through
     Tailscale.

## 3. Build the patches

On any computer with Python 3:

```sh
python3 -m venv .venv
.venv/bin/pip install keystone-engine
.venv/bin/python tools/build_patch.py --server swapnote.home.arpa
```

Use your own server name.

**Options:**
- `--pretendo`: for consoles that use Pretendo Network (see [PRETENDO.md](PRETENDO.md)).
- `--without 03-ink-colour-lr` / `--without 04-unlock-stationery`: leave out the optional
  extras:
  - **03:** the L and R buttons change the ink colour while writing (the D-pad already
    does).
  - **04:** all 42 built-in stationery designs are available from the start, instead of
    unlocking over time.

The result is in **`build/sd/`**. It is the same for every console that uses your server,
unless some use `--pretendo`.

## 4. Install the patches on each console

1. Power off and put the SD card in a computer.
2. Copy everything inside `build/sd/` to the root of the SD card. This creates or
   updates:
   - `luma/titles/0004000000051700/code.ips` (Swapnote);
   - `luma/sysmodules/0004013000003402.ips` (SpotPass module).
3. Put the card back. Power on while holding **SELECT** to open the Luma3DS
   configuration and turn on both:
   - **Enable game patching**
   - **Enable loading external FIRMs and modules**

   Press START to save.
4. **Leave nothing else in `luma/sysmodules/`** unless you know what it is. That folder
   is loaded because of the second setting.

To uninstall, delete the two `.ips` files. Swapnote then behaves exactly as before.

## 5. Point the console at the server

**At the server's home**, set the console's proxy to the server itself. Otherwise set it
to the relay Pi (step 6).

On the 3DS:

1. Go to **System Settings → Internet Settings → Connection Settings**.
2. Pick your connection, then **Change Settings → Proxy Settings → Yes → Detailed Setup**.
3. Enter:
   - **Proxy server:** the server's (or relay's) local IP address, e.g. `192.168.1.20`.
   - **Port:** `8080`.
   - **Authentication:** only if you set a username and password in `[proxy]` (or on
     the relay).
4. Save and run the connection test. It should pass.

All of the console's internet traffic now goes through that address. The server passes
through only Nintendo and Pretendo hosts (see `allow_hosts`). The console's web browser
won't load other sites while the proxy is on.

## 6. Friends in other homes: the relay Pi

Each remote home needs a small always-on Raspberry Pi on its Wi-Fi or wired network.
[relay/README.md](../relay/README.md) explains how to prepare the Pi, ideally before
mailing it, so your friend only has to plug it in. After that, do step 5 on their 3DS
using the Pi's address.

## 7. Allow your consoles

The server only serves the friend IDs listed in `allowed_pids`.

1. On each console, open Swapnote and choose to check for new notes.
2. The server log shows:

   ```
   refused console with friend PID 123456789 (not in allowed_pids)
   ```

3. Put every console's number in the config:

   ```toml
   allowed_pids = [123456789, 987654321]
   ```

4. Restart the server (`systemctl restart swapnote-server`).

## 8. First note

1. In Swapnote, turn SpotPass on (Settings) if it isn't already.
2. Write a note, choose **Send via SpotPass**, and pick a friend. Swapnote says the note
   is saved for delivery.
3. Close Swapnote or put the console to sleep. It goes out within a few minutes. The
   server log shows `PreparePostObjectV1` / `CompletePostObjectV1`.
4. On your friend's console, check for new notes in Swapnote, or wait for the hourly
   check.

Both consoles must already be friends (in the 3DS friend list), as on the original
service.

## Troubleshooting

| Symptom | Check |
|---|---|
| Notes stay "saved for delivery" | Luma settings from step 4; the proxy from step 5; the server log; system version 11.17.0 |
| Nothing in the server log at all | The console can't reach the server: wrong proxy address or port, firewall, or the relay is offline |
| "refused console with friend PID" | Add that PID to `allowed_pids` (step 7) |
| "refused client 1.2.3.4" | Add that network to `allowed_networks` |
| Received notes "deleted as duplicates" | Expected only for notes you already have |
| Console can't get online | The server or relay is down. Set the proxy back to "No" to use the internet without it |

Admin tools: `python3 server/admin.py server.toml list` shows stored notes (no
contents), and `... cleanup` applies the retention rules immediately.
