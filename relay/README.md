# Relay Pi for friends in other homes

The 3DS can't run Tailscale, but it can use an HTTP proxy. A Raspberry Pi in your
friend's home acts as that proxy and forwards everything through your tailnet to the
server.

- Unencrypted 3DS traffic stays inside your friend's home network. The internet hop is
  encrypted by Tailscale (WireGuard).
- Your server never opens a port to the internet.

```
3DS --(home Wi-Fi, HTTP)--> relay Pi --(Tailscale, encrypted)--> Swapnote server
```

## What you need

- **Raspberry Pi:** a Zero 2 W, 3, 4 or 5, with a microSD card (8 GB+) and a power supply.
  A **wired** connection (Pi 3/4/5, or a USB Ethernet adapter on a Zero) is easiest for
  non-technical friends, because the Pi then needs no Wi-Fi password.
- **Tailscale:** the administrator's account, with the server already on the tailnet.

## Prepare the Pi (administrator, before mailing it)

1. **Flash Raspberry Pi OS Lite (64-bit)** with [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
   In Imager's "OS customisation":
   - set a hostname (e.g. `swapnote-relay`), a user and a password;
   - enable SSH;
   - if the Pi will use Wi-Fi, enter the friend's Wi-Fi name and password. Ask them, or
     let them do this step.
2. **Create a Tailscale auth key** in the Tailscale admin console (Settings → Keys):
   reusable no, pre-approved yes. Consider tagging it (e.g. `tag:swapnote-relay`) and
   restricting that tag in your ACLs to the server's port 8080 only.
3. Boot the Pi on your own network once. Copy this folder to it and run:

   ```sh
   sudo ./setup.sh --server-ip <server's tailscale ip> --authkey tskey-...
   ```

   Add `--relay-user NAME --relay-pass PASS` to require a password from the 3DS. If the
   server's `[proxy]` has a username and password, add `--upstream-user` /
   `--upstream-pass`.
4. Test it with your own 3DS (proxy = the Pi's address, port 8080) before mailing it.

The Pi keeps working on any network. Tailscale reconnects by itself, and the relay accepts
devices from whichever local network it is on (detected at setup; re-run `setup.sh`
after moving it to a different network if your friend's network uses a different address
range than yours did).

> To re-detect the local network automatically, you can also re-run setup over SSH via
> Tailscale (`ssh user@swapnote-relay`) once the Pi is at your friend's home.

## At your friend's home

1. Plug the Pi into the router (or power it on if it uses Wi-Fi) and leave it on.
2. Find the Pi's local address. In the Tailscale admin console, the relay's machine
   page lists its local endpoint. Or look in the router's device list.
3. On the friend's 3DS, set the proxy to that address, port 8080 (see
   [SETUP.md step 5](../docs/SETUP.md#5-point-the-console-at-the-server)).
4. If possible, ask the router to always give the Pi the same address (a "DHCP
   reservation"), so the 3DS setting keeps working.

If the Pi is off, the 3DS cannot go online until it is back, or until the proxy setting
is turned off.
