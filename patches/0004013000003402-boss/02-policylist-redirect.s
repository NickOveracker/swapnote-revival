@ BOSS patch 02 — fetch the SpotPass policy list from our own server
@
@ Target: BOSS system module 0004013000003402, TMD version 14337 (system 11.17.0).
@
@ Background
@   BOSS periodically downloads a "policy list" (plain XML) that decides which SpotPass
@   tasks may run: <DefaultStop> stops every task not listed, and <Priority> entries
@   (TitleId + TaskId + Level, e.g. STOPPED / HIGH) override single tasks.
@   Observed 2026-10-25 through a logging proxy: after the patched console queued three
@   notes, BOSS fetched the policy list from Nintendo and ran other titles' tasks, but
@   never started Swapnote's upload tasks. Nintendo discontinued SpotPass for all 3DS
@   software, so its current policy list stops them.
@
@   The address is built in BuildPolicyListUrl() at 0x00107480 (Thumb):
@       sprintf(url, "%s/%s/policylist/%s/%s?ap=%s", base, env, "3", country, ap)
@       (or the same without "?ap=%s", format at 0x00107534)
@   with  base = "https://nppl.c.app.nintendowifi.net" (char string at 0x001074f0,
@         36 bytes with NUL; its only users are the two `adr` at 0x001074c2/0x001074d6)
@         env  = "p01" for retail consoles
@   giving e.g. https://nppl.c.app.nintendowifi.net/p01/policylist/3/US?ap=...
@
@ What this patch does
@   Replaces the base with "http://<server>", so the console asks our server for
@       http://<server>/p01/policylist/3/<country>...
@   Our server answers with a list that has <DefaultStop>false</DefaultStop>, so
@   Swapnote's tasks are allowed to run again. Like patch 01, plain HTTP avoids any
@   change to the console's certificate checks.
@   Side effect: all SpotPass tasks on the console follow our policy list instead of
@   Nintendo's. Since Nintendo's SpotPass service is discontinued, other titles' tasks
@   only reach dead servers either way.
@
@ Original bytes, for auditors: "https://nppl.c.app.nintendowifi.net\0" at
@ 0x001074f0-0x00107513; the format string "%s/%s/policylist/..." follows at 0x00107514
@ and is left untouched.

.org 0x001074f0
    .server 36 http://  @ "http://" + our server name, NUL-padded to the original 36 bytes
