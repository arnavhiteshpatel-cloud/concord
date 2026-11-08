# Neural-to-communication: recorded intracortical data selecting words on the board

Milestone 5, P0. The decoding science (decoders, labels, held-out metrics, controls) is in
[CURSOR_CLICK.md](CURSOR_CLICK.md); this page is about the **whole chain** and the reproducible
test that drives it in a browser.

## 1. What this shows, and what it does not

**Shows:** genuine human intracortical recordings (participant T15, Singer-Clark et al., Dryad
doi:10.5061/dryad.prr4xgxzq, CC0), replayed through the unchanged BrainOS runtime, produce
word selections on the participant communication board, through exactly the path a live
system would use:

```
recorded block (t15:*, Offline Replay)
  -> features.binned threshold crossings + features.vector spike band power (same bin times)
  -> pipeline: decoder(s)           [historical passthrough | BrainOS Kalman + click]
  -> command router (operator-enabled; pointer: velocity x gain, y inverted; click rule)
  -> operator authorization of the board app (default deny)
  -> SDK CommandGuard + control.state -> board: integrate pointer, click selects the tile
```

The board's own record of what it selected equals, bin for bin and tile for tile, an
independent offline computation of the same chain (`brainos.evaluation.board_e2e`).

**Does not show:** that anyone can communicate with BrainOS. The person recorded was steering
the original research system's cursor in a target task; nobody saw BrainOS's cursor. Text
composed from replayed data is labelled on the board "demonstration — not the participant's
message". No closed-loop use, no live acquisition, one participant, one day.

## 2. Three modes, never confused

| Mode | Decoder | Provenance on every command | Shown on the board |
| --- | --- | --- | --- |
| Historical replay | the original online decoders' recorded outputs (velocity, click) | `decoded_intent`, `model_origin: historical`, `replayed: true` | "historical decoder replay (original research system)" |
| BrainOS inference | BrainOS Kalman (cursor) + logistic click decoder, fitted on calibration blocks 0-2 only | `model_origin: brainos`, `replayed: true` (input was a recording) | "decoded by t15-kalman-… (BrainOS)" + "recorded data replay" |
| Live device | the same pipeline on a live source (LSL, Open Ephys, a plugin) | `model_origin: brainos` or `external` | as above, without "replay" |

The live mode is exercised only with software publishers and synthetic or prerecorded data
(e2e steps M3-x, M5-C-x; docs/VALIDATION_LEVELS.md). No live neural source has been connected.

Guards on this chain (tested in `backend/tests/test_cursorclick_chain.py`): a BrainOS model is
refused on any block it was trained on (block-level leakage unit); a decoder declaring +y up is
refused for a +y-down pointer unless the operator sets `invert_y`; behavioral labels (recorded
cursor/target positions) never reach the router.

## 3. Reproducible test (`make e2e-communication`)

```bash
make dataset-t15
```
```bash
make e2e-communication
```

`dataset-t15` downloads day 468 blocks 0-3 (~90 MiB; Dryad needs an API token, see
`python -m brainos.datasets.dryad --help`). `e2e-communication` builds the console, then
`e2e/communication.cjs`:

1. `python -m brainos.evaluation.board_e2e prepare`: links the four blocks into a fresh data
   directory and fits the BrainOS Kalman + click models on blocks 0-2 with the settings
   `run_cursorclick` selected (docs/CURSOR_CLICK.md).
2. Starts a server, opens the board (`board.html?layout=grid&n=N&method=cursor_click`: an N×N
   word grid laid over the task's target grid; the mouse is never used).
3. For each run: connects grid block 3 paused, starts the chain, enables the router, authorizes
   the board, replays one full pass (180 s) at 8×, reads `window.__brainosBoard`.
4. `board_e2e compare`: predicts the board's selections offline and compares; scores them
   against the cued targets. Writes `reports/communication_e2e.json`.

Runs: historical on the 14 × 14 board (the task's own grid); BrainOS on 14 × 14, 7 × 7 and
2 × 2 (coarser boards group whole task cells).

## 4. Results (grid block 3, one run of `make e2e-communication`, 2026-11-08)

| Chain | Board | Board selections | Same tile as the offline prediction | On the cued word | Chance |
| --- | --- | ---: | ---: | ---: | ---: |
| Historical (original decoders) | 14 × 14 | 70 | 70 / 70 (cursor difference 0) | 39 / 70 = 56 % | 0.5 % |
| BrainOS Kalman + click | 14 × 14 | 72 | 72 / 72 (cursor difference 0) | 0 / 72 = 0 % | 0.5 % |
| BrainOS Kalman + click | 7 × 7 | 72 | 72 / 72 | 2 / 72 = 3 % | 2 % |
| BrainOS Kalman + click | 2 × 2 | 72 | 72 / 72 | 32 / 72 = 44 % | 25 % |

How to read it:

- **The software chain is exact.** Every selection the board made is the one the offline model
  of runtime + router + board predicts, at the same bin, on the same tile.
- **Open-loop replay limits what any decoder can do here.** Integrated over a whole block, a
  replayed velocity stream drifts away from where the participant actually was; even the
  original decoder's own outputs select the cued word in 56 % of trials on this block (the
  session itself: 93 %). Across all nine grid blocks the board-integration figures are 65 % for
  the original outputs and 1 % / 4 % / 44 % for BrainOS on 14 × 14 / 7 × 7 / 2 × 2
  (docs/CURSOR_CLICK.md).
- **BrainOS on the 2 × 2 board** is above chance (44 % vs 25 %), but its selections are biased by
  cursor drift: 51 of 72 chose the top-left word, which was cued only 17 times; always choosing
  it would score 24 %. With the cursor restarted at the recorded position each trial (analysis
  only), BrainOS reaches 15 % / 35 % / 84 % on 14 × 14 / 7 × 7 / 2 × 2 (docs/CURSOR_CLICK.md):
  the decoders carry real intention information; open-loop integration loses most of it.
- **Answer to "can the board select words from independently decoded recordings?"** Yes, the
  path works end to end with BrainOS's own decoders and is labelled correctly; reliably, no:
  on recorded data replayed open loop, word choice is near chance except on a 4-word board.
  Whether a person could communicate with BrainOS's decoders can only be measured closed loop,
  under an approved research protocol.
