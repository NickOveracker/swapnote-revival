# How it works

These are technical notes for the curious and for auditors. Addresses are virtual
addresses in the decompressed code (base `0x100000`). Each patch source in
[patches/](../patches/) documents the original instructions it replaces.

## 1. Swapnote's kill switch

- **The flag.** Swapnote keeps a "SpotPass service ended" flag (settings flag `0x3f`) in
  its save. It only offers SpotPass, including the "Send via SpotPass" button, when
  SpotPass is on (flag 9) and that flag is clear.
- **What sets it.** On startup it asks the console's BOSS (SpotPass) service for the
  status of its `JFR_LS2` task through `ServiceStatus()` (`0x1d874c`). If Nintendo
  reports the service as terminated, the game sets the flag. Its own recovery path clears
  the flag again when the status reads "running".
- **The patch.** Patch `01-service-status` makes `ServiceStatus()` return "running".

## 2. How notes travel

- **Swapnote doesn't use the network itself.** It registers BOSS tasks, and the BOSS
  system module does the networking:
  - **Sending:** a one-shot task per note (`JFR_U01`–`JFR_U07`), type "DataStore upload".
  - **Receiving:** task `JFR_DFR`, type "DataStore download", repeated every 60 minutes.
- **The protocol.** Both tasks speak NEX **DataStore** (protocol `0x73`) over **HPP**:
  NEX RMC messages carried in HTTP POST bodies.
  - Swapnote's game server ID is `0x00051600` and its access key is `a1a0778a`.
  - BOSS builds the address in `BuildHppUrl()` (BOSS `0x10f00c`):
    `https://hpp-00051600-l1.n.app.nintendowifi.net/hpp/`.
- **Authentication** is computed locally from the console's friend account. BOSS asks the
  Friends module for the account password (frd command `0x10`). No Nintendo login
  server is involved, which is why only BOSS needs patching.

### The message flow (all confirmed on hardware)

**Sender:**
1. `PreparePostObjectV1` (2) → the server returns an upload URL and a form field.
2. The console POSTs the note as multipart form data.
3. `CompletePostObjectV1` (3).

**Recipient** (hourly, or "check for new notes"):
1. `GetNotificationUrl` (13), then a GET of a tiny notification file
   `"<latest notification id>,<pid>,<constant>"`.
2. If the ID changed: `GetNewArrivedNotificationsV1` (14) → `GetSpecificMetaV1` (20).
3. For each note: `PrepareGetObjectV1` (1), then a GET of the note.

**HPP details:**
- **Requests:** `POST /hpp/` with headers `pid`, `version` (`NEX_2_4_1_S25`), `token`,
  `signature1` and `signature2`. The RMC message is the multipart field `file`.
- **Signatures:**
  - `signature1` is HMAC-MD5 over the RMC message, keyed with the hex-decoded access key.
  - `signature2` uses a key derived from the account password.
- **Responses:** they have no protocol byte (unlike PRUDP). There are no structure
  headers (NEX 2.4.1).

## 3. The SpotPass policy list

- **What it is.** BOSS periodically downloads a policy list (XML) from
  `nppl.c.app.nintendowifi.net`. It can stop every task not listed (`DefaultStop`) or set
  per-task priorities.
- **The obstacle.** Since SpotPass was discontinued, Nintendo's list stops Swapnote's
  tasks. Notes stay "saved for delivery" forever.
- **The patch.** BOSS patch `02-policylist-redirect` points the list at your server
  instead. The server answers with `DefaultStop=false` and Swapnote's tasks at HIGH
  priority.

## 4. The BOSS patches

Both target the BOSS module from system update 11.17.0 (TMD v14337):

- **`01-hpp-redirect`:**
  - BuildHppUrl always takes its built-in `http://` branch (`0x10f088`, `beq` → `b`).
  - The host suffix string `n.app.nintendowifi.net` (`0x147e59`, 23 bytes) is replaced
    with your server name.
- **`02-policylist-redirect`:** the base URL `https://nppl.c.app.nintendowifi.net`
  (`0x1074f0`, 36 bytes) becomes `http://<server name>`.

Luma3DS loads system-module patches from `/luma/sysmodules/<TitleID>.ips`. That needs
both "Enable game patching" and "Enable loading external FIRMs and modules".

## 5. Optional extras (Swapnote)

- **`02-persistent-receive-task`.**
  - The receive task normally runs 2500 times. Swapnote refills that count during an
    in-app sync once it drops below half.
  - The patch registers it with a count of 0, which BOSS treats as "persistent", so it
    never runs out even if Swapnote isn't opened for months.
- **`03-ink-colour-lr`.** The editor already cycles each page's ink colour with D-pad
  Left/Right. This adds L/R.
- **`04-unlock-stationery`.**
  - The stationery picker shows 6 designs until a scripted "Nikki" letter unlocks the
    rest (flag `0x22`).
  - The patch makes the four stationery checks see the flag as set. The Nikki letters
    themselves are unaffected.

## 6. Notes on the server side

- **Note format.** A Swapnote note is a `TLRF0300` container behind a 24-byte header with
  three CRC-32 checksums: poly `0x04C11DB7`, MSB-first, initial value `0x04C11DB7`. The
  server stores notes as uploaded and never modifies them.
- **Duplicates.** Swapnote discards an incoming note if bytes `0x18..0x27` of its body (a
  tick-count + content-CRC ID set when the note is first saved) match a note it already
  has.
