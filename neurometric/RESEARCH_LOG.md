# RESEARCH LOG

Dated log of what was investigated, how, and what changed as a result. (All 2026-11-27.)

| Time (UTC) | Activity | Result / decision |
|---|---|---|
| 06:30 | Read founder Playbook B (21 pp) and the startup-opportunities workbook (Direction B rows: NR1/F5, NR2/F5b, experiments U6–U9, B5–B8) | Specification adopted; claims to verify listed in EVIDENCE_LEDGER |
| 06:35 | Launched 7 parallel investigations: regulatory/trials; competitors; instruments/licensing/datasets; funding/collaborators; prospects/neuromodulation; platform/BCI-HID/timing; Concord audit | Reports in docs/research/ (search budget of 200 web searches shared and exhausted; residual items [UNR]) |
| 06:40–06:55 | Designed and implemented canonical events, closed-loop simulator, three virtual-user models, switch scanning, metrics | Unit tests with analytic fixtures (all pass) |
| 06:50 | First calibration: BCI profiles far too degraded (TP 0.4 bps, 36% errors) | Added a click "settle" behaviour to the feedback user, halved profile noise; bci_good now ≈1.2 bps ISO, ≈2.4 bps grid achieved bitrate; mouse ≈4.1 bps |
| 06:52 | Concord audit returned: high quality (874 backend tests pass) but proprietary-labelled; no degradation simulator; no committed recordings | Clean-room NeuroMetric + importer; audit agent generated 3 genuine Concord recordings as fixtures (D-002) |
| 06:55 | Competitor scan: SRAlab DAI (with Neuralink) is the closest substitute; Signant+Ametris, Thermo (Clario+Evidera) at the platform level | Niche narrowed to home-use evidence of digital independence, input-agnostic (MASTER_PLAN) |
| 07:00 | Round-trip test found trajectories omitted the final (selection) sample in simulation | Engine fixed; full experiment run restarted so all results use one code version |
| 07:01 | Real-data check on NLB MC_RTT (DANDI:000129, CC-BY) | 541 reaches; pipeline runs on real behaviour as canonical events (X1) |
| 07:03 | Full simulation study launched (sweeps B, B2–B4, C, C2, D, E, F, F2; I, K, L, M, N, H, P, G) | see EXPERIMENT_REGISTRY.md |
| 07:06 | B_noise finished: most ISO movement metrics monotone; ADL completion 91% ceiling; onset and tracking lag insensitive to noise | Supports using kinematic + bitrate metrics as degradation-sensitive scores, and process metrics (completion) as functional, ceiling-prone outcomes |
