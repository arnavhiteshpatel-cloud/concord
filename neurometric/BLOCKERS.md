# BLOCKERS

Items that need resources this session does not have. Each has the unblocking action and owner.

| ID | Blocker | Why it blocks | Unblocking action | Owner |
|---|---|---|---|---|
| X-1 | No human participants / IRB | Reliability, validity, responsiveness in humans cannot be measured | Recruit a faculty PI (e.g., Yuan Yang, JNERL) → OPRS submission using docs/irb drafts | Founder |
| X-2 | No implanted-BCI or AT hardware | Adapters tested in browser with synthetic input only | Buy/borrow switch interface, eye tracker, head pointer (docs/founder/EQUIPMENT.md) | Founder |
| X-3 | Instrument licences (Zarit, PROMIS/Neuro-QoL, QUEST, PIADS, COPM, ALSAQ…) | Cannot reproduce copyrighted items | Send licensing inquiry pack (docs/research/instruments.md) | Founder |
| X-4 | Concord code is "Proprietary (internal preview)"; UIUC IP status unknown | Code reuse and any open release | Landuyt IP Clinic + OTM disclosure before incorporation/publication | Founder |
| X-5 | Web-search budget exhausted during research | Some claims [UNR]/[PK] (state neural-data laws CA/MT/CT, IEEE P2731/P2794 status, some funder pages) | Re-verify listed items manually | Founder / next session |
| X-6 | Dryad API 403 via proxy for one dataset; braininitiative.nih.gov blocked by allow-list | Dataset/RFA verification | Manual download / browser check | Founder |
| X-7 | Windows/macOS/Android/iOS hardware | Telemetry adapters only specified as contracts; not run | Platform spike on real devices (Exp U9 / B8) | Founder |
| X-8 | Sponsor data / device metadata | Measurement chain cannot be estimated | Data use agreement with a sponsor or academic program | Founder |
| X-9 | Formal Part 11 / CSV qualification, counsel opinion on device status | Cannot claim compliance or non-device status | Quality consultant (months 6–12), regulatory counsel / 513(g) if needed | Founder |
| X-10 | Repository separation | Brief asked for a separate repo; session can push only to concord | `git subtree split -P neurometric` → new repo (DECISIONS D-001) | Founder |
