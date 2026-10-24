# rad-android inherits the principle

| | |
|---|---|
| **Kind** | repo-edit |
| **Repo** | quaternionmedia/rad-android — **existence unverified** |
| **State** | stub |
| **Depends on** | rad is a unification engine — the foundational principle |
| **Graduates to** | nothing here; the platform-plans record already owns the spec |
| **Verified** | Not reachable from the drafting session (no `gh` CLI; org API refuses). `rad/adr/DRAFT-rad-platform-plans.md` §2 read in full — it specifies the module in detail already. |

## What
The Android work is already specified: a library module `:radialmenu`,
app-agnostic, with `core/` a line-for-line Kotlin port of the same state machine
(JUnit parsing `vectors.json` checked in as a test resource, a CI grep lint
banning `import android.`/`import androidx.` from `core/`) and `compose/` doing
`drawArc` per wedge. qmetronome is the first host, `minSdk 33`.

The only addition this plan makes: the module carries the unification principle
in its own README, and qmetronome's adoption performs the §4 census like any
other host.

## Why now
Not yet. The platform-plans record sequences web first, Android second, and
nothing here changes that ordering. This stub exists so the principle is not
discovered late by the Kotlin port.

## Seam
qmetronome already owns the MIDI clock ground (`MidiClockSender`,
`UsbMidiConnector`, elevated `TimingDispatcher` scopes), so the clock seam is
the host's, not the menu's — which is the same shape as apothecary's state
layer being the host's. Two hosts, one pattern, worth noting in the integration
standard.

## Open questions
- Existence. Same check, same rule: unknown is not absent, and no stub repository.
- Whether the census clause is even meaningful for a host whose surface is a
  phone screen with few controls to begin with. Possibly the interesting number
  there is IPA, not idiom count.
