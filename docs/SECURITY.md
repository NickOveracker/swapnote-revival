# Security and privacy

## The main limitation: plain HTTP

The 3DS's SSL module only trusts Nintendo's certificate authorities, so a patched console
cannot verify a TLS certificate from your server. The SpotPass patch therefore switches
Swapnote's traffic to **plain HTTP**. Anyone who can see that traffic can read:

- the notes themselves (drawings, photos, sound);
- each console's friend PID;
- a login token derived from the console's friend-account password;
- request signatures.

The recommended setup limits where that traffic travels:

| Hop | Protection |
|---|---|
| 3DS → server or relay | Your home Wi-Fi (WPA2/WPA3) only |
| Relay → server | Tailscale (WireGuard, end-to-end encrypted) |
| Server | No ports open to the internet; only `allowed_networks` may connect |

**Do not** expose the server with a router port forward or put it on a public VPS, unless
you accept that notes cross the internet unencrypted.

## What the server does to limit risk

- **Allowlists.**
  - Only consoles whose friend PID is in `allowed_pids` can send or receive.
  - Notes addressed to anyone else are refused.
  - Only clients in `allowed_networks` can connect at all.
- **No note logging.**
  - Raw requests are only stored if you turn on `debug.log_requests`.
  - Normal logs contain friend PIDs and method names, not contents.
  - Proxied destinations are only logged in verbose mode.
- **Retention.**
  - Note data is deleted `delivered_grace_hours` after every recipient has fetched it.
  - It is deleted after `max_age_days` in any case.
  - Unfinished uploads are deleted after 6 hours.
  - Only IDs and timestamps are kept, so the consoles' notification numbering stays
    consistent.
- **Unguessable URLs.** Upload and download URLs carry a random 128-bit secret, checked
  in constant time.
- **Proxy restrictions.**
  - The server passes through only hosts in `allow_hosts`, so it is not an open proxy.
  - Optional Basic authentication.
- **Request limits.** Bodies over ~4 MB are refused.
- **Least privilege.** The systemd unit runs as a dedicated user, can only write its
  data directory, and is sandboxed (`ProtectSystem=strict` etc.).

## Remaining weaknesses

- **Console identity is trusted, not verified.**
  - Requests are signed with Swapnote's public access key (anyone can compute that) and
    with a key derived from the console's friend-account password, which the server does
    not know.
  - So a device that can reach the server could claim to be an allowed console and fetch
    notes addressed to it.
  - The network allowlist, Tailscale ACLs and the relay password are what prevent that.
    Keep them tight.
- **Proxy credentials over Wi-Fi.** The 3DS sends its proxy password in Basic
  authentication over your Wi-Fi, so treat it as a light barrier, not a strong secret.
- **Notes at rest.** Notes are stored unencrypted in the data directory until deleted.
  Put the data directory on an encrypted disk if that matters to you.

## Tailscale ACL suggestion

Tag relay Pis (e.g. `tag:swapnote-relay`) and allow them to reach only the server's port:

```json
{
  "acls": [
    { "action": "accept", "src": ["tag:swapnote-relay"], "dst": ["swapnote-server:8080"] }
  ]
}
```

Here `swapnote-server` is a host alias or tag for your server. Adjust to your existing
policy.
