# Swapnote SpotPass revival

Send and receive **Swapnote** (Nintendo 3DS) friend notes over SpotPass again, using a
small server you run yourself.

Nintendo ended Swapnote's SpotPass service in 2013 and later shut down SpotPass for every
3DS title. This project brings friend-to-friend note exchange back for a group of friends:

- **Console patches:** small patches for Swapnote and the console's SpotPass (BOSS)
  system module, applied at load time by Luma3DS. Nothing is installed or permanently
  changed.
- **Server:** a self-hosted server (Python, standard library only) that stores notes until
  they are delivered.
- **Relay (optional):** a Raspberry Pi relay, so friends in other homes can reach your
  server privately over [Tailscale](https://tailscale.com).

Notes, drawings, photos, sound and stationery all work. Sending happens in the background
like the original. Receiving checks hourly, including in sleep mode, or immediately via
"check for new notes" in Swapnote.

## What you need

| | |
|---|---|
| Console | Any 3DS/2DS family console with **custom firmware (Luma3DS 13.x)** |
| System version | **11.17.0** (the latest; the system-module patch is version-specific) |
| Game | **Swapnote, US version, updated to v3.3.0** |
| Server | An always-on computer (Linux, macOS or a Raspberry Pi) with Python 3.11+ |
| Friends elsewhere | A Raspberry Pi (Zero 2 W or better) per remote home, plus a free Tailscale account |
| To build the patch | Python 3 and `pip install keystone-engine` (any computer) |

Other Swapnote regions (EU, JP) and Swapdoodle are not supported yet.

## How to set it up

Follow **[docs/SETUP.md](docs/SETUP.md)** step by step. In short:

1. Back up your Swapnote save data.
2. Set up the server with a config file and add your consoles to its allowlist.
3. Build the patches with your server's name (`tools/build_patch.py`) and copy them to
   the SD card.
4. Turn on two Luma settings.
5. Point each 3DS's proxy setting at the server (at home) or at a relay Pi (elsewhere).

## Is this legal / safe?

- **No Nintendo code is distributed.** The patches are hand-written ARM assembly
  ([patches/](patches/)) with comments explaining every replaced byte. The builder never
  reads game files: it only assembles these sources. You need your own installed copy of
  Swapnote.
- **Your saves are untouched.** Your existing notes and friend list stay as they are. The
  only save change the game itself makes is clearing its "service has ended" flag. Back up
  anyway (step 1).
- **Privacy: read this.** The 3DS only trusts Nintendo's certificates, so the patched
  console talks to your server over **plain HTTP**. The recommended setup keeps that
  traffic inside your home Wi-Fi and Tailscale's encrypted tunnel, and the server deletes
  notes after delivery. See [docs/SECURITY.md](docs/SECURITY.md).

## Pretendo Network users

This works alongside Pretendo's Nimbus. Build with `--pretendo` and see
[docs/PRETENDO.md](docs/PRETENDO.md).

## How it works

See [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md) for the reverse-engineering details:
- the kill switch;
- how SpotPass carries notes (NEX DataStore over "HPP");
- the policy list;
- the server protocol.

## License

[GPL-3.0-or-later](LICENSE). You may use, share and modify this project. If you
distribute modified versions, they must also be released under the GPL with their source
code.

## Credits

The protocol work relied on public research by:
- the [Pretendo Network](https://github.com/PretendoNetwork) developers (nex-go,
  Swapdoodle HPP research, and a community-shared traffic capture);
- [Kinnay's NintendoClients wiki](https://github.com/kinnay/NintendoClients/wiki);
- [3dbrew](https://www.3dbrew.org).

[Luma3DS](https://github.com/LumaTeam/Luma3DS) applies the patches. No code from these
projects is included here.
