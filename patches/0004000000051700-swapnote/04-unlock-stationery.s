@ Patch 04 — all built-in stationery available from the start
@
@ Background
@   The stationery picker shows only the first 6 stationeries until settings flag 0x22 is
@   set. Swapnote sets that flag when it delivers the scripted "Nikki" letter TL12, which
@   requires a usage score built up over many notes (scheduler 0x0017c9c8). All 42
@   preset stationeries (romfs letterpaper/PRESET_LP_000000..000041) are in the game.
@
@   Flag 0x22 is read with IsFlagSet(settings, 0x22) = bl 0x001dcd60 at six places:
@     0x0017c9c8 (two reads)  Nikki-letter scheduler  -> NOT changed (keeps the letters)
@     0x0024a77c  picker: number of stationeries (6 if flag clear, else 42 + downloaded)
@     0x0024b7e4  picker: scrolling through the full list
@     0x0024b8cc  picker: scrolling through the full list
@     0x001ca15c  saving the stationery of a received note to the collection
@
@ What this patch does
@   At the four stationery sites only, the flag read is replaced by "flag is set"
@   (r0 = 1); every following `cmp r0, #0` then takes the unlocked path. The saved flag
@   itself is not changed, so the Nikki letters still arrive as before and removing
@   this patch restores the original behaviour.

.org 0x0024a77c
    mov r0, #1              @ was: bl 0x001dcd60 (IsFlagSet 0x22) - picker size
.org 0x0024b7e4
    mov r0, #1              @ was: bl 0x001dcd60 (IsFlagSet 0x22) - picker scrolling
.org 0x0024b8cc
    mov r0, #1              @ was: bl 0x001dcd60 (IsFlagSet 0x22) - picker scrolling
.org 0x001ca15c
    mov r0, #1              @ was: bl 0x001dcd60 (IsFlagSet 0x22) - keep received stationery
