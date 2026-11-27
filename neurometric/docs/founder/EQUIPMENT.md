# Equipment for Stage 1–2 validation and demos

What physical devices to buy or borrow, why, and what not to buy yet. Prepared 2026-11-27.

Labels follow [`../research/CONVENTIONS.md`](../research/CONVENTIONS.md). **Prices are [HYP/PK]** (rough
ranges from prior knowledge, not quotes) unless marked **[V]**, which means the price was read from the
vendor's own page on 2026-11-27. Prices change; get quotes before buying, and ask about academic or
loan programmes first.

This list serves the studies in [`../../CLINICAL_VALIDATION_PLAN.md`](../../CLINICAL_VALIDATION_PLAN.md):
- **Stage 1:** able-bodied adults, standard mouse, full battery
  ([`../clinical/stage1_protocol.md`](../clinical/stage1_protocol.md) §6).
- **Stage 2:** able-bodied adults using four modalities — mouse, camera head pointer with dwell, consumer eye
  tracker via the OS pointer, single-switch scanning through a USB switch interface
  ([`../clinical/stage2_protocol.md`](../clinical/stage2_protocol.md) §7).
It also unblocks `BLOCKERS.md` X-2 (no AT hardware) and X-7 (no real Windows/Android devices for the
telemetry spike).

---

## 1. Shopping list at a glance

| # | Item | Needed for | Buy or borrow | Rough cost |
|---|---|---|---|---|
| 1 | Windows 11 laptop + external 24" 1080p 60 Hz monitor + wired 125 Hz USB mouse | Stage 1–2 study station; Windows Eye Control; Tier 1 telemetry spike | Buy (dedicated, managed account) | Laptop $600–1,000; monitor $120–200; mouse $15–30 [HYP/PK] |
| 2 | USB switch interface + 2 switches | Stage 2 modality D; switch-scanning tasks; 2-switch step scanning | Buy one interface; borrow extra switches | Interface $150–300; switches $50–100 each [HYP/PK] |
| 3 | Consumer eye tracker on Microsoft's Windows Eye Control supported list | Stage 2 modality C | Buy one consumer unit; borrow a clinical AT tracker for demos | $200–300 consumer [HYP/PK]; clinical AT trackers several thousand [PK] |
| 4 | 1080p USB webcam + free head-pointer software | Stage 2 modality B | Buy webcam | $40–80 [HYP/PK]; software free |
| 5 | Joystick: generic USB gamepad/joystick; borrow a mouth joystick | Gamepad API path; AT demos | Buy gamepad; borrow mouth joystick | $20–60 [HYP/PK]; mouth joystick ~$1,000+ [PK] |
| 6 | Android tablet (mid-range, recent Android) | Android Switch Access, UsageStatsManager telemetry spike, tablet battery testing | Buy | $150–350 [HYP/PK] |
| 7 | Photodiode/phototransistor + USB-HID microcontroller latency bench | Bench timing validation required by `browser_timing.md` §5 before any study | Build | $40–120 in parts [HYP/PK]; see §8 |
| 8 | Optional: iPad | iPadOS Switch Control, Eye Tracking, Head Tracking; Apple BCI HID path | Borrow first | $350+ [HYP/PK] |
| 9 | Optional: OpenBCI Ganglion | SSVEP demo only | Defer | $624.99 [V] |

A realistic Stage 1–2 kit (items 1–7) is roughly **$1,400–2,500** if you buy everything new and borrow the
expensive clinical AT [HYP]. Stage 1 alone needs only item 1 and item 7.

---

## 2. Windows laptop (study station and telemetry spike)

Specification (from `stage1_protocol.md` §6): Windows 11, ≥ 8 GB RAM, dedicated to the study, managed
account; Chrome pinned at the IRB-submitted version; external 24" 1920 × 1080 60 Hz monitor with fixed
brightness; wired USB optical mouse, 125 Hz polling, default pointer speed, "enhance pointer precision" off.

Why Windows first:
- **Windows Eye Control** turns a supported eye tracker into an OS pointer, so the browser battery sees
  ordinary pointer events and never touches gaze data ([V] Microsoft support page in
  [`bci_hid_and_input_standards.md`](../research/bci_hid_and_input_standards.md) §3).
- It is the platform where consented Tier 1 activity telemetry (`GetLastInputInfo`, Raw Input device-class
  counts, no key values) is technically feasible
  ([`platform_matrix.md`](../research/platform_matrix.md) §1). The spike must include NeuroMetric's own consent
  screen, visible indicator and kill switch, because Windows does not prompt for these APIs.

Practical notes:
- Keep a second, ordinary user account for development; the study account stays clean.
- Record the display's actual refresh rate; the in-session self-check estimates it too.
- A 120 Hz+ panel is nice for development, but the study protocol fixes 60 Hz.

## 3. USB switch interface and two switches

Purpose: Stage 2 modality D (single-switch row/column scanning), and testing 2-switch step scanning, which
WCAG 2.2.1 timing adjustments and real AT users need
([`bci_hid_and_input_standards.md`](../research/bci_hid_and_input_standards.md) §3).

What to get:
- **A USB HID switch interface with at least two 3.5 mm jacks**, configurable to send keys (e.g. Space and
  Enter) and ideally to act as iOS/Android Switch Control switches. AbleNet Hitch-type and Blue2-type
  interfaces are common examples [PK, vendor pages not reachable this session].
- **Two switches**: the protocol specifies a round button switch, 2.5–3 inch (65–75 mm) with a 3.5 mm jack
  (`stage2_protocol.md` §7). Different colours help in 2-switch tasks.
- **Mounting**: a clamp or non-slip base. Switch position matters more than the switch.

Also consider an **Xbox Adaptive Controller** [PK, ~$100]: it has many 3.5 mm switch jacks and appears as a
gamepad, which exercises the Gamepad API path. Do not substitute it for the protocol's HID switch interface.

Do not use a DIY microcontroller "switch" with participants. It is fine on the bench (§8) but not as study
equipment.

## 4. Eye trackers (and the gaze-data rule)

| Option | Use | Cost | Notes |
|---|---|---|---|
| Consumer screen-mounted tracker **on Microsoft's Eye Control supported list** | Stage 2 modality C | $200–300 [HYP/PK] | Microsoft's page lists Tobii Eye Tracker 4C, EyeX, Tobii Dynavox PCEye Plus, EyeMobile Mini/Plus among supported devices ([V], `bci_hid_and_input_standards.md` §3). Confirm the model you buy is on the current list; newer consumer models' Eye Control support is [UNR]. |
| Clinical AT tracker (e.g. Tobii Dynavox PCEye 5, used in the SRAlab DAI study) | Demos with AT users; credibility with clinicians | Several thousand dollars [PK] | **Borrow** from an AT lending programme, a clinical partner or a vendor trial programme. |
| iPadOS/iOS built-in Eye Tracking | Tablet demos | Free with a supported iPad | All data stays on device; apps see only activations ([V], `bci_hid_and_input_standards.md` §3). |
| WebGazer.js (webcam) | None as an outcome or primary input | Free | Mean angular error about 10–14° in a 2026 evaluation; not suitable ([V]/[RF], same file). |
| Research tracker with analytical licence (e.g. Tobii Pro class) | Only if a future study must store gaze | Thousands [PK] | Not needed for Stage 1–2. |

**Licensing and privacy caveats** (from [`platform_matrix.md`](../research/platform_matrix.md) §3 and
[`bci_hid_and_input_standards.md`](../research/bci_hid_and_input_standards.md) §3, all [V]):
- The USB HID usage tables for eye trackers say hosts "must not ... store gaze point data", including
  aggregates.
- Tobii Pro SDK: analytical use on consumer trackers needs a **special licence key**; medical use needs a
  **special licence**. Tobii's Eye Tracking Data Transparency Policy applies to any solution that stores or
  transfers Tobii eye-tracking data.
- Consumer gaming SDKs have long been understood to allow interactive use only [PK].

**Rule for NeuroMetric:** the eye tracker drives the **OS pointer**; the battery records pointer and dwell
events, eye-tracker model, calibration-quality result if the OS exposes it, and dwell settings — **never gaze
coordinates**. Write this into the protocol and consent form.

## 5. Head pointers

Hardware: a 1080p USB webcam at 30–60 fps on a fixed monitor mount (`stage2_protocol.md` §7).

Free software options:
- **Camera Mouse** (free Windows webcam head mouse) [PK; the project site did not respond on 2026-11-27].
- **Enable Viacam** (free, open source) [PK].
- **Apple Head Pointer** on macOS ([V] https://support.apple.com/guide/mac-help/use-head-pointer-mh41557/mac).
- **iOS/iPadOS Head Tracking** (announced May 2025) ([V], `bci_hid_and_input_standards.md` §3).

Selection criteria for the study (`stage2_protocol.md`): runs locally with **no cloud video upload**, version
pinned, dwell click available. Record its settings (gain, smoothing, dwell time) with each session.

## 6. Joysticks, mouth joysticks and sip-and-puff

- **Generic USB joystick or gamepad** [HYP/PK $20–60]: tests the Gamepad API path (pads hidden until a
  "gamepad user gesture"; poll in rAF and store `Gamepad.timestamp`; [V] W3C spec via
  `browser_timing.md` §2).
- **Mouth joystick** (e.g. Jouse+, used in the SRAlab DAI study [V]): borrow; do not buy for Stage 1–2.
  Note that `jouse.com` currently resolves to a parked "domain details" page ([V] 2026-11-27), so find the
  current manufacturer or distributor before contacting anyone.
- **Sip-and-puff**: borrow. It reaches the computer as a switch or a mouse emulator; test it through the
  switch interface path.

Where to borrow [PK — confirm programmes and eligibility]: state AT Act programmes (in Illinois, the Illinois
Assistive Technology Program runs device loans), clinical partners' AT labs, vendor trial/loan programmes, and
UIUC's disability resources office.

## 7. Android tablet

Purpose ([`platform_matrix.md`](../research/platform_matrix.md) §1–2):
- Test the battery in Chrome on a tablet, with **Android Switch Access** driving it.
- Run the Tier 1 telemetry spike: `UsageStatsManager` foreground time (user grants Usage Access) and
  `AccessibilityManager` booleans for enabled AT. **Do not** use an AccessibilityService for telemetry (Play
  policy; [V]).
Choose a recent mid-range model; very cheap tablets drop frames, which pollutes timing data.

## 8. Latency bench: photodiode + microcontroller

Required before any study configuration is used: `browser_timing.md` §1 says not to claim millisecond
accuracy in the browser and to report absolute timing only with a **device-class lag/precision band from
NeuroMetric's own bench** ([RF] citing Bridges et al. 2020 and Anwyl-Irvine et al. 2021). The Stage 1 protocol
names a "Black Box Toolkit-class" rig; a DIY rig is acceptable for development and must itself be checked
(below).

### Parts [HYP/PK unless marked]
| Part | Example | Cost |
|---|---|---|
| Microcontroller with **native USB HID** (can act as a keyboard/mouse/gamepad) | Teensy 4.1, Arduino Leonardo/Micro, Raspberry Pi Pico | $5–35 [PK] |
| Fast light sensor | **Phototransistor** (e.g. Adafruit #2831, $0.95 [V] adafruit.com) or a photodiode with a transimpedance amplifier | $1–15 |
| **Not** a CdS photoresistor | (e.g. Adafruit #161, $0.95 [V]) — CdS cells respond in tens of milliseconds [PK], too slow for timing | — |
| Optocoupler or small relay + 3.5 mm mono plug | To "press" a real switch through the commercial switch interface | $5–15 |
| Small solenoid + MOSFET driver + flyback diode + supply | To press real keyboard keys / mouse buttons / touch (with conductive tip) | $15–30 |
| Light-blocking enclosure or foam + suction/clip mount for the sensor | Stops room light reaching the sensor | $5–10 |
| Optional: logic analyzer or USB oscilloscope | To check the rig's own timing | $15–500 [PK] |

### What to measure (protocol in `browser_timing.md` §5)
1. **Input → page timestamp:** the MCU sends a HID key report (or closes the switch-interface jack, or fires
   the solenoid) and records its own microsecond clock. The page logs `event.timeStamp`. The page also flips a
   small screen patch from black to white on the event, and the phototransistor detects the flip. That gives
   input-to-photon latency per trial.
2. **Stimulus → photon:** the page shows a stimulus in a rAF callback and logs the rAF timestamp; the sensor
   gives the true onset. That gives display lag and frame quantisation.
3. Repeat **≥ 1,000 trials per configuration** (browser × OS × input device class) and report mean lag, SD,
   p5/p50/p95, and dropped frames.

### Checking the rig itself
- Set the MCU's USB polling interval to 1 ms where the board allows it [PK], and confirm with a logic analyzer
  or scope that the sensor edge is sharp (sub-millisecond rise).
- Measure the rig against a known-latency reference (e.g. a scope reading sensor and actuator together) and
  record its own error budget. Store a `validation_profile_id` per configuration, as specified in
  `browser_timing.md` §6.

## 9. What NOT to buy yet

| Do not buy | Why |
|---|---|
| **An EEG headset for the evidence product** | See §10. |
| A Black Box Toolkit-class commercial timing rig | Expensive [PK]. Build and validate the DIY rig first; buy or borrow a commercial rig only if a sponsor or reviewer requires it. |
| Clinical AT eye trackers, mouth joysticks, sip-and-puff | Borrow. Stage 2 uses able-bodied adults and consumer/emulated AT on purpose. |
| Research eye trackers with analytical licences | NeuroMetric stores no gaze. |
| EMG wristbands or clinical EMG | They reach apps as keys/pointer (e.g. Meta Neural Band; [V] `bci_hid_and_input_standards.md` §1.7). Nothing new to measure at L3. |
| VR/AR headsets | Not in the Stage 1–4 plan. |
| A second laptop "for speed" | Protocol consistency matters more: one pinned configuration. |
| Anything implant-related | NeuroMetric is downstream of sponsors' devices. |

## 10. Why there is no EEG headset in the evidence kit

1. **Wrong level.** NeuroMetric measures L3–L5 above the operating system
   ([`KNOWLEDGE_BASE.md`](KNOWLEDGE_BASE.md) §0). An EEG headset is an L1–L2 device. Building with one invites
   the question "so you are an EEG BCI company?", which is the wrong story for a neutral measurement company.
2. **It would mostly demonstrate EEG's limits.** Consumer EEG BCIs need set-up and training, and a share of
   users cannot reach useful control (BCI inefficiency; Vidaurre & Blankertz, [V-DOI]
   10.1007/s10548-009-0121-6). A demo would show that, not NeuroMetric's value.
3. **Privacy and legal burden.** Raw EEG is "neural data" under laws such as Colorado HB24-1058 ([V] in
   [`regulatory_landscape.md`](../research/regulatory_landscape.md) §8.1). Logging interaction events keeps
   NeuroMetric further from those definitions; storing raw EEG would bring them in.
4. **Comparator studies already exist.** If a partner study needs an EEG comparator arm (as SRAlab's uses an
   EMOTIV EPOC X; [V] `clinical_trials.md` §1), use the partner's device and protocol.
5. **Real BCIs come from sponsors.** The product's BCI evidence will come through sponsors' devices (via OS
   input or sponsor exports), not from NeuroMetric hardware.

### Optional: OpenBCI only for an SSVEP demo
If an investor or recruiting demo needs "a brain signal moving the battery", the cheapest honest option is
an SSVEP selector:
- **OpenBCI Ganglion** (4-channel), **$624.99** [V] (shop.openbci.com, 2026-11-27). The 8-channel **Cyton** is
  **$1,249.00** [V] — not needed for SSVEP over occipital sites [PK].
- Decode the attended target locally and emit **key events** into the battery. The demo then shows the real
  point: the battery treats an EEG selector like any other switch, and reports its selection time and false
  activations.
- **Do not store raw EEG**; keep it on the demo machine and discard it.
- **Safety:** flickering stimuli can trigger seizures in people with photosensitive epilepsy. Screen demo users
  for a history of seizures or photosensitivity, keep flicker areas small and sessions short, and never run a
  flicker demo for an unscreened audience [PK]. This is not a study device; any human-subjects use needs IRB
  review.
