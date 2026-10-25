@ BOSS patch 01 — send HPP (SpotPass DataStore) requests to our own server over HTTP
@
@ Target: BOSS system module 0004013000003402, TMD version 14337 (system 11.17.0).
@   Verify the input with: tools/build_patch.py --check <dumped .dec.code>
@
@ Background
@   Swapnote does not talk to the network itself. To send or receive a friend note it
@   registers a BOSS (SpotPass) task of type "DataStore upload/download"; the BOSS
@   system module then makes NEX DataStore calls over "HPP" (NEX RMC messages in HTTP
@   POST bodies). BOSS builds the HPP address in BuildHppUrl() at 0x0010f00c:
@
@       scheme + "hpp-" + "%08x"(game server ID) + "-" + <env, e.g. "l1"> + "."
@              + host + "/hpp/"
@
@   with scheme  = obj->use_https ? u"https://" (0x0010f0f8) : u"http://" (0x0010f10c)
@        host    = "n.app.nintendowifi.net" (char string at 0x00147e59, 23 bytes with NUL,
@                  reached through the pointer table at 0x0014b214 + 8)
@   For Swapnote (game server ID 0x00051600) that is
@       https://hpp-00051600-l1.n.app.nintendowifi.net/hpp/
@   Nintendo shut that server down, and its certificate chain is Nintendo-only.
@
@   The HPP authentication (pid / token / signature headers, built at 0x00128f8c..)
@   uses only the console's local friend ID and password (frd:u command 0x10,
@   GetMyPassword) — no Nintendo login server is contacted, so nothing else needs
@   redirecting.
@
@ What this patch does (only HPP requests are affected; ordinary SpotPass downloads,
@ policy lists, eShop, friends, etc. use other code paths and are unchanged)
@   1. Always choose the "http://" branch in BuildHppUrl(), so no TLS certificate
@      checks need to be weakened anywhere on the console.
@   2. Replace the host suffix "n.app.nintendowifi.net" with the server name given to
@      the builder (--server), so Swapnote's requests go to
@          http://hpp-00051600-l1.<server>/hpp/
@      <server> must be at most 22 characters (the original string's length).
@
@ Privacy note: over plain HTTP the HPP headers (friend ID, a token derived from the
@ console's friend password, request signatures) and the notes themselves are not
@ encrypted in transit.

.thumb

@ 1. Scheme selection. Original code (Thumb), for auditors:
@     0x0010f084  ldrb r0, [r4]        @ r4 = obj + 0x20 (use_https flag)
@     0x0010f086  cmp  r0, #0
@     0x0010f088  beq  0x0010f08e      @ 01 d0   flag clear -> u"http://"
@     0x0010f08a  adr  r1, 0x0010f0f8  @         u"https://"
@     0x0010f08c  b    0x0010f090
@     0x0010f08e  adr  r1, 0x0010f10c  @         u"http://"
@ The conditional branch becomes unconditional (01 d0 -> 01 e0).
.org 0x0010f088
    b 0x0010f08e        @ always take the u"http://" branch

@ 2. Host suffix. Original bytes: "n.app.nintendowifi.net\0" (23 bytes, 0x00147e59-0x00147e6f);
@ the next string, "cfg:u", starts at 0x00147e70 and is left untouched.
.org 0x00147e59
    .server 23          @ our server name, NUL-padded to the original 23 bytes
