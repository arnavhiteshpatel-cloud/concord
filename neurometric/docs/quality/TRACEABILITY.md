# Traceability matrix (URS -> FS -> tests)

Generated from a checked mapping: every listed test exists in the suite (the generator fails
otherwise). Run the suite: `python -m pytest tests/test_study*.py tests/test_api*.py
tests/test_instruments*.py tests/test_telemetry*.py -q`. Passing tests are OQ evidence only
when executed under the IQ/OQ protocol in VALIDATION_STRATEGY.md.

| URS | FS | Verified by (tests/...) |
|---|---|---|
| URS-01 | FS-01 | `test_study_core.py::test_tenant_isolation`<br>`test_api_e2e.py::test_tenant_isolation_over_http` |
| URS-02 | FS-02 | `test_study_core.py::test_permission_matrix_is_complete_and_least_privilege`<br>`test_study_core.py::test_role_actions_enforced`<br>`test_study_core.py::test_sponsor_gets_aggregate_only_error`<br>`test_study_sessions.py::test_upload_roles`<br>`test_study_exports.py::test_export_permissions` |
| URS-03 | FS-03 | `test_study_core.py::test_site_scoping_for_site_staff`<br>`test_study_core.py::test_participant_sees_only_self_and_care_partner_only_linked` |
| URS-04 | FS-04 | `test_study_core.py::test_password_hashing_scrypt`<br>`test_study_core.py::test_password_policy`<br>`test_study_core.py::test_login_tokens_expire_and_revoke`<br>`test_api_e2e.py::test_auth_required_and_token_expiry`<br>`test_api_e2e.py::test_login_rate_limiting` |
| URS-05 | FS-05 | `test_study_core.py::test_pseudonyms_random_and_not_derived`<br>`test_study_core.py::test_reidentification_encrypted_site_scoped_and_audited`<br>`test_study_core.py::test_reid_requires_key` |
| URS-06 | FS-06 | `test_study_core.py::test_enrollment_state_machine`<br>`test_study_sessions.py::test_upload_stores_compressed_events_with_hash` |
| URS-07 | FS-07 | `test_study_core.py::test_schedule_expansion_with_windows_and_recurrence`<br>`test_study_core.py::test_invalid_schedules_rejected`<br>`test_study_core.py::test_visit_generation_assignments_reminders_and_windows`<br>`test_study_core.py::test_performed_at_in_future_rejected` |
| URS-08 | FS-08 | `test_study_sessions.py::test_device_config_link` |
| URS-09 | FS-09 | `test_study_sessions.py::test_upload_stores_compressed_events_with_hash`<br>`test_study_sessions.py::test_upload_rejections`<br>`test_study_sessions.py::test_a1_known_answers`<br>`test_study_sessions.py::test_a1_misses_and_assistance`<br>`test_study_sessions.py::test_a1_target_geometry_from_stimuli`<br>`test_study_sessions.py::test_a2_throughput_matches_iso_formula`<br>`test_study_sessions.py::test_e1_known_answers`<br>`test_study_sessions.py::test_generic_adl_scoring`<br>`test_study_sessions.py::test_text_outside_copy_typing_needs_free_text_consent` |
| URS-10 | FS-10 | `test_instruments.py::test_definitions_files_valid_and_no_licensed_text`<br>`test_instruments.py::test_invalid_definitions_rejected`<br>`test_instruments.py::test_reverse_scoring_and_proration_nm_cpb`<br>`test_instruments.py::test_nm_session_mean_with_reverse_item`<br>`test_instruments.py::test_response_validation_errors`<br>`test_instruments.py::test_versioning_responses_keep_version`<br>`test_instruments.py::test_service_respondent_types_translations_and_completion`<br>`test_study_core.py::test_visit_generation_assignments_reminders_and_windows` |
| URS-11 | FS-11 | `test_instruments.py::test_catalogue_and_labels`<br>`test_instruments.py::test_sus_known_answers`<br>`test_instruments.py::test_sus_requires_all_items`<br>`test_instruments.py::test_tlx_raw_and_weighted_known_answers`<br>`test_instruments.py::test_tlx_weights_from_pairwise_comparisons`<br>`test_instruments.py::test_tlx_step_and_range_validation`<br>`test_instruments.py::test_licensed_stub_cannot_be_answered_until_loaded` |
| URS-12 | FS-07, FS-12 | `test_study_core.py::test_visit_generation_assignments_reminders_and_windows` |
| URS-13 | FS-13, FS-16 | `test_api_e2e.py::test_end_to_end_workflow`<br>`test_study_audit.py::test_signature_meanings_and_roles` |
| URS-14 | FS-14 | `test_study_audit.py::test_chain_valid_and_entries_complete`<br>`test_study_audit.py::test_audit_is_append_only`<br>`test_study_audit.py::test_tampering_is_detected`<br>`test_study_audit.py::test_truncation_detected_against_external_anchor`<br>`test_study_audit.py::test_sensitive_values_hashed_in_audit` |
| URS-15 | FS-15 | `test_study_core.py::test_updates_require_reason_and_keep_history`<br>`test_study_core.py::test_questionnaire_correction_rescores_and_keeps_version` |
| URS-16 | FS-16 | `test_study_audit.py::test_signature_requires_reauthentication`<br>`test_study_audit.py::test_signature_meanings_and_roles`<br>`test_study_audit.py::test_signature_detects_later_changes` |
| URS-17 | FS-17 | `test_study_core.py::test_timestamps_are_utc_server_clock` |
| URS-18 | FS-18 | `test_study_audit.py::test_backup_restore_roundtrip`<br>`test_study_audit.py::test_backup_verification_detects_corruption`<br>`test_study_audit.py::test_backup_with_tampered_audit_fails_verification`<br>`test_study_audit.py::test_integrity_check_detects_raw_event_tampering`<br>`test_api_demo.py::test_cli_operator_commands` |
| URS-19 | FS-19 | `test_study_consent.py::test_consent_record_scopes_versioned`<br>`test_study_core.py::test_collection_requires_consent_and_enrollment`<br>`test_study_consent.py::test_free_text_rejected_without_consent` |
| URS-20 | FS-20 | `test_study_consent.py::test_full_withdrawal_retain_stops_collection`<br>`test_study_consent.py::test_full_withdrawal_delete_per_protocol`<br>`test_study_consent.py::test_study_default_withdrawal_action`<br>`test_study_consent.py::test_partial_withdrawal_of_telemetry`<br>`test_study_consent.py::test_withdrawal_deletes_free_text` |
| URS-21 | FS-21 | `test_study_consent.py::test_retention_purge` |
| URS-22 | FS-22 | `test_study_consent.py::test_subject_export_and_deletion` |
| URS-23 | FS-23 | `test_study_consent.py::test_sponsor_dashboard_is_aggregate_and_consent_filtered`<br>`test_study_exports.py::test_sponsor_export_manifest_and_contents`<br>`test_study_exports.py::test_full_export_includes_all_site_participants` |
| URS-24 | FS-24 | `test_telemetry.py::test_forbidden_content_rejected_and_never_stored`<br>`test_telemetry.py::test_content_keys_are_labelled_forbidden`<br>`test_telemetry.py::test_consent_and_visible_recording_state`<br>`test_telemetry.py::test_app_categories_require_their_own_scope`<br>`test_telemetry.py::test_participant_mismatch_and_care_partner`<br>`test_telemetry.py::test_local_review_shows_exactly_what_was_sent` |
| URS-25 | FS-25 | `test_telemetry.py::test_duplicates_are_idempotent`<br>`test_telemetry.py::test_out_of_order_batches_accepted_and_flagged`<br>`test_telemetry.py::test_overlapping_periods`<br>`test_telemetry.py::test_clock_skew_and_period_sanity`<br>`test_telemetry.py::test_batch_hash_integrity`<br>`test_telemetry.py::test_experiment_o_stored_aggregates_are_correct` |
| URS-26 | FS-26 | `test_study_exports.py::test_sponsor_export_manifest_and_contents`<br>`test_study_exports.py::test_analysis_dataset_and_sdtm_like_layouts`<br>`test_study_exports.py::test_fhir_questionnaire_response_structure`<br>`test_api_e2e.py::test_end_to_end_workflow` |
| URS-27 | FS-27, FS-23 | `test_study_consent.py::test_small_cells_suppressed`<br>`test_api_demo.py::test_demo_dashboard_via_api`<br>`test_api_e2e.py::test_end_to_end_workflow` |
| URS-28 | FS-28, FS-09 | `test_study_core.py::test_demo_records_cannot_mix_with_real_studies`<br>`test_api_demo.py::test_demo_is_labelled_and_synthetic`<br>`test_api_demo.py::test_demo_data_cannot_enter_real_study` |
| URS-29 | FS-29 | `test_api_e2e.py::test_security_headers_cors_off_and_docs_off`<br>`test_api_e2e.py::test_request_size_limits`<br>`test_api_e2e.py::test_unknown_fields_rejected`<br>`test_api_e2e.py::test_static_web_dist_served` |
| URS-30 | FS-30 | `test_study_core.py::test_database_pragmas_and_migrations`<br>`test_study_core.py::test_changed_applied_migration_is_refused`<br>`test_study_exports.py::test_every_schema_column_is_documented` |

## Tests not mapped to a single URS (supporting / regression)

- `test_telemetry.py::test_valid_payload_passes_validator`

## Coverage summary

- URS items: 30; all have at least one FS and one test.
- Test functions mapped: 102 of 103 collected (parametrised cases counted once).
