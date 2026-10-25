# Using this with Pretendo Network

This was worked out by reading Nimbus's source; it has not been tested on a console
running Nimbus.

[Nimbus](https://github.com/PretendoNetwork/Nimbus) patches the act, friends, http,
miiverse, socket and ssl system modules. It does **not** patch BOSS (SpotPass), so its
files don't clash with this project's BOSS patch. It needs the same Luma3DS settings and
system version (11.17.0).

**Build with `--pretendo`.** This leaves out the policy-list redirect:

- **Not needed:** Pretendo serves its own SpotPass policy list, which already lets tasks
  run.
- **Not wanted:** ours would replace it for every title and drop Pretendo's per-task
  settings.

The other patches are needed as usual:

- **Swapnote patches:** these work the same in either mode.
- **SpotPass redirect for Swapnote's notes:** this still points Swapnote's note traffic
  at your server. Pretendo does not host a Swapnote note server. In Pretendo mode,
  Nimbus rewrites Nintendo server names on the fly, but the patched Swapnote address no
  longer contains one, so it reaches your server unchanged.

Things to know:

- **Separate friend accounts.**
  - Pretendo mode uses a separate friend account: different friend PID and friend list.
  - People exchanging notes must be in the **same** mode and be friends there.
  - Put the Pretendo-mode PIDs in `allowed_pids`.
- **Nintendo mode.** If you switch Nimbus back to Nintendo mode, Nintendo's own policy
  list stops Swapnote's SpotPass tasks again, so notes won't send or arrive until you
  switch back. Build without `--pretendo` if you want them to work in both modes.
- **If Pretendo adds Swapnote.** Should Pretendo ever host Swapnote's note server, you
  would only need the Swapnote patches.
