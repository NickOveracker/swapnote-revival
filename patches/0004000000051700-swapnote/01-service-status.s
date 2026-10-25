@ SPDX-License-Identifier: GPL-3.0-or-later
@ Patch 01 — report the SpotPass service as available (removes the 2013 kill switch)
@
@ Background
@   Swapnote keeps a "SpotPass service ended" flag (settings flag 0x3f) in its save.
@   Everything SpotPass-related, including the "Send via SpotPass" button, is only
@   offered when flag 9 (SpotPass on) is set and flag 0x3f is clear.
@
@   The flag is driven by one function, ServiceStatus() at 0x001d874c. It asks the
@   console's BOSS (SpotPass) service for the status of Swapnote's distribution-
@   settings task "JFR_LS2" and returns:
@       2 = service terminated (BOSS status 0)  -> game sets flag 0x3f and disables SpotPass
@       1 = service running    (BOSS status 1)  -> game clears flag 0x3f again
@       0 = unknown / anything else             -> no change
@   Since Nintendo's 2013 shutdown the BOSS status is "terminated", so the game keeps
@   SpotPass switched off.
@
@   Callers (all only compare the result against 1 or 2):
@     0x00194794  startup: if flag clear and status==2 -> set flag, save, clean up tasks
@                          if flag set   and status==1 -> clear flag, save, continue
@     0x00232430  before a send: status==2 -> show "service has ended" dialog
@
@ What this patch does
@   Replaces the first two instructions of ServiceStatus() so it immediately returns 1.
@   The game's own recovery path then clears flag 0x3f on the next launch (only that one
@   settings byte changes; letters, friends and other save data are untouched) and it is
@   never set again. The BOSS status query is no longer made.
@
@ Original code at this address (for auditors; verify by disassembling your own
@ decompressed code.bin at this address, e.g. with Ghidra or capstone, base 0x100000):
@     0x001d874c  push {r4, lr}          @ function prologue
@     0x001d8750  bl   <get BOSS helper>
@     ...         (query task status, map 0->2, 1->1, else->0, return)
@ The rest of the function becomes unreachable; it is left in place.

.org 0x001d874c
    mov r0, #1          @ return 1 = "service running"
    bx  lr
