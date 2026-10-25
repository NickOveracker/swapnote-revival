@ SPDX-License-Identifier: GPL-3.0-or-later
@ Patch 03 — L / R buttons change the ink colour while writing a note
@
@ Background
@   Each page of a note has one ink colour (0 black, 1 red, 2 blue, 3 green, 4 purple,
@   5 orange), stored as a byte per page in the letter object: letter+0x21c+page
@   (letter = editor+0x2158, current page = editor+0x2154). The renderer draws every
@   stroke of a page in that colour; on save each pen point gets the page colour in
@   bits 27-29 and the header (0x40 bits 13-15) gets page 0's colour.
@
@   The editor's main state handler (0x00239d68, editor state 6 = drawing) already
@   lets the +Control Pad change it (there is no touch-screen control for it):
@       0x0023a154  ldr r0, [r0, #8]      @ pad "newly pressed" bits (pad object 0x0039d20c)
@       0x0023a158  tst r0, #0x20         @ Left  -> previous colour (5 after 0)
@       ...
@       0x0023a1ac  ldr r0, [r0, #8]
@       0x0023a1b0  tst r0, #0x10         @ Right -> next colour (0 after 5)
@   Both paths call 0x0023cb18, which redraws the page in the new colour and calls
@   0x001ce788; that function already tints the ink gauge (panes P_Ink and InkHead of
@   MakeLetter_Down) with the current colour.
@   The block is only reached while the stylus is not touching the screen and the
@   editor accepts input. L (0x200) and R (0x100) are not tested anywhere in the editor.
@
@ What this patch does
@   Widens the two button masks so that L also selects the previous colour and R the
@   next one (the +Control Pad keeps working). Nothing else changes.

.org 0x0023a158
    tst r0, #0x220          @ was: tst r0, #0x20   (Left)  -> Left or L
.org 0x0023a1b0
    tst r0, #0x110          @ was: tst r0, #0x10   (Right) -> Right or R

