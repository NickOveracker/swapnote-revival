@ SPDX-License-Identifier: GPL-3.0-or-later
@ Patch 02 — make the "receive friend notes" SpotPass task run without a run limit
@
@ Background
@   Swapnote registers its receive task JFR_DFR (task index 0) with values from its task
@   table (defaults at 0x002e2410, 0x2c bytes per task: name, run count, interval in
@   minutes, priority). For JFR_DFR that is 2500 runs, every 60 minutes. Each run uses
@   one count; Swapnote only refills it (FUN_001bdbe4) during an in-app sync once it has
@   dropped to half, so a console whose owner does not open Swapnote for ~52+ days would
@   eventually stop receiving notes.
@   BOSS defines a run count of 0 as "persistent": the task never runs out
@   (3dbrew, BOSS Services, PropertyID 0x4 "Count").
@
@   All task code reads the count through TaskCount(settings, index) at 0x001de204:
@       0x001de204  cmp   r1, #7
@       0x001de208  movhi r1, #7           @ clamp index to 0..7
@       0x001de20c  add   r2, r1, r1, lsl #1
@       ...                                @ r0 = settings[index].count (+0x1a50 + index*0x2c)
@       0x001de224  bx    lr
@   Users of the value for index 0: registration (FUN_0017a140), the startup re-sync
@   (FUN_001791f0, which lowers a registered task's count to this value), and the refill
@   check (FUN_001bdbe4, which only refills when the remaining count is <= value/2, so it
@   does nothing for 0).
@
@ What this patch does
@   TaskCount() returns 0 for task index 0 (JFR_DFR); every other task (sending, the
@   discontinued Nintendo channels) keeps its normal count. New registrations of the
@   receive task are persistent, and the startup re-sync switches an existing one to 0.
@
@   The extra instructions live in the unused zero-filled space after the end of .text
@   (0x002e1174..0x002e2000, inside the last executable page; nothing references it).

@ Entry: jump to the extended version of TaskCount(). Original instruction here:
@   0x001de204  cmp r1, #7   (re-executed in the cave below)
.org 0x001de204
    b 0x002e1180

.org 0x002e1180
    cmp   r1, #0            @ task index 0 = JFR_DFR (receive friend notes)?
    moveq r0, #0            @   count 0 = persistent (no run limit)
    bxeq  lr
    cmp   r1, #7            @ original first two instructions of TaskCount()
    movhi r1, #7
    b     0x001de20c        @ continue with the original code
