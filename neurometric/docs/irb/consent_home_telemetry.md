# Consent addendum: home use and telemetry (Stage 5; adaptable for Stage 6 partner modules)

**DRAFT — not submitted — requires faculty PI and IRB review**

This addendum goes with the AT-user consent (`consent_at_user.md`) and the care-partner consent.
It uses the same accessible consent process. Tier 1 telemetry is a **separate opt-in**. A person
may take part in the home battery and the diary with **no** Tier 1 telemetry.

---

## 1. Key information
- For 14 days you would use NeuroMetric at home: three practice-task sessions (days 1, 8, 14),
  and, **only if you choose**, a small program that counts how much you use your computer or
  tablet each day.
- The program **counts**. It does **not read** what you type, see, say or look at.
- You can pause it, or remove it, at any time. We remove it with you at the end.

## 2. What is collected: exact list
| Item | Example | Opt-in needed |
|---|---|---|
| Task timing and scores from the three home sessions | "selected 20 of 24 squares; 3.1 bits/s" | Home study consent |
| Session information | Start and end time, length, pauses, browser and device type, your access settings | Home study consent |
| Daily **active minutes** on the device | "212 minutes active on 3 May" | **Tier 1 box** |
| Daily **counts** of pointer moves, selections, scrolls, switch presses, dwell selections | "1,840 selections" | **Tier 1 box** |
| Daily **number** of characters typed (a count only, never the characters) | "1,120 characters" | **Tier 1 box** |
| Whether an assistive-access mode was on during a session | "switch access: yes" | **Tier 1 box** |
| Minutes per broad app category: communication, web, media, productivity, social, games, health, smart home, accessibility tools, other | "communication: 45 min" | **Separate app-category box** |
| Care partner's daily form | Minutes of help; burden 0–10 | Care-partner consent |
| Your ratings of tiredness and effort | 0–10 | Home study consent |

## 3. What is never collected
- The content of anything you type: letters, words, messages, emails, passwords, searches.
- What is on your screen: screenshots, window titles, documents, photos.
- Web addresses, browsing history, names of apps or websites.
- Audio, microphone, camera, video.
- Where your eyes look (gaze coordinates), even if you use an eye tracker.
- Your location.
- Your contacts or other people's information.

The NeuroMetric server **rejects** any data outside the list in §2. It keeps only a receipt
saying that something was rejected and why (`src/neurometric/study/telemetry.py`). On Android
the program does **not** use accessibility services to watch the screen. On Windows it does not
read keys (`docs/research/platform_matrix.md`).

## 4. How it works
- Windows: a small signed program with a visible icon showing when it is counting.
- Android: an app that uses the "Usage access" permission. You turn it on yourself in
  Settings.
- Counts are added up **on your device** into daily totals, then sent securely to the
  university-hosted study server under your code number.
- Pause: one click or tap, or ask your care partner or the study team.
- Removal: at the end of the study, or whenever you want. We check with you that it is gone.

## 5. Risks
- Feeling watched. We count; we do not read.
- A small risk that the counts could be linked to you if there were a data breach.
- The program could, rarely, slow your device or conflict with your AT software. It is tested
  first, and support is available *[hours]*. Tell us, and we remove it immediately.
- **Do not change your AT settings for the study.**

## 6. Choices
| Choice | Yes | No |
|---|---|---|
| I agree to the three home task sessions and the study forms | ☐ | ☐ |
| **Tier 1:** I agree to install the counting program (daily totals only, as listed) | ☐ | ☐ |
| **App categories:** I agree to share minutes per broad app category (no app names) | ☐ | ☐ |
| If I stop, delete the telemetry already collected (otherwise kept) | ☐ | ☐ |

## 7. Device and computer ownership
If the study lends you a device, it is returned at the end and wiped. If the program runs on
your own device, you may need to be the device's administrator or have the owner's permission
*[IRB to advise; e.g. employer- or school-managed devices are excluded]*.

Signature block as in the main consent (participant; witness where applicable; person obtaining
consent, who is not the student founder).
