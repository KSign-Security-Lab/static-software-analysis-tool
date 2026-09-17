from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ActionProfile:
    action_name: str
    protocol_version: str = "ocpp1.6"
    component_type: str = "charge_point"
    message_direction: str = "CSMS_TO_CHARGE_POINT"
    sensitive_fields: List[str] = field(default_factory=list)
    handler_patterns: List[str] = field(default_factory=list)
    action_symbols: List[str] = field(default_factory=list)
    numeric_ids: List[int] = field(default_factory=list)


@dataclass
class FieldProfile:
    action_name: str
    field_name: str
    semantic_type: str
    trust_level: str = "remote_ocpp_input"
    dangerous_sink_domain: List[str] = field(default_factory=list)
    expected_checks: List[str] = field(default_factory=list)
    related_cwe: List[str] = field(default_factory=list)
    validation_requirement: List[str] = field(default_factory=list)
    field_source_aliases: List[str] = field(default_factory=list)


@dataclass
class ExpectedCheckProfile:
    check_id: str
    check_type: str
    description: str = ""
    negative_sink_domains: List[str] = field(default_factory=list)
    expected_before_sink: bool = True
    related_cwe: List[str] = field(default_factory=list)


@dataclass
class SinkDomainProfile:
    sink_domain: str
    description: str
    apis: List[str]
    related_cwe: List[str] = field(default_factory=list)
    severity: str = "HIGH"
    dangerous_arg_indexes: List[int] = field(default_factory=list)


@dataclass
class RootCause:
    root_cause_id: str
    description: str
    related_missing_checks: List[str] = field(default_factory=list)
    related_sink_domains: List[str] = field(default_factory=list)
    related_cwe: List[str] = field(default_factory=list)


@dataclass
class CheckPattern:
    check_type: str
    default_strength: str = "WEAK"
    operators: List[str] = field(default_factory=list)
    call_names: List[str] = field(default_factory=list)
    operand_identifiers: List[str] = field(default_factory=list)
    operand_literal_prefixes: List[str] = field(default_factory=list)
    standalone_operators: List[str] = field(default_factory=list)
    matched_expected_check: Optional[str] = None


DEFAULT_CHECK_PATTERNS: List[CheckPattern] = [
    CheckPattern(
        check_type="NULL_CHECK",
        default_strength="WEAK",
        operators=["<operator>.equals", "<operator>.notEquals"],
        operand_identifiers=["NULL", "nullptr"],
        standalone_operators=["<operator>.logicalNot"],
        matched_expected_check=None,
    ),
    CheckPattern(
        check_type="URL_SCHEME_CHECK",
        default_strength="STRONG",
        call_names=[
            "strncmp",
            "strncasecmp",
            "startswith",
            "starts_with",
            "validateurlscheme",
            "isallowedscheme",
        ],
        operators=["<operator>.equals", "<operator>.notEquals"],
        operand_literal_prefixes=["http"],
        matched_expected_check="URL_SCHEME_VALIDATION",
    ),
    CheckPattern(
        check_type="HOST_ALLOWLIST_CHECK",
        default_strength="STRONG",
        call_names=["isallowedhost", "in_allowlist", "host_allowed", "check_host"],
        matched_expected_check="HOST_ALLOWLIST",
    ),
    CheckPattern(
        check_type="SIGNATURE_VERIFICATION",
        default_strength="STRONG",
        call_names=[
            "verify_signature",
            "verifysignature",
            "check_signature",
            "pgp_verify",
            "rsa_verify",
        ],
        matched_expected_check="SIGNATURE_VERIFICATION",
    ),
    CheckPattern(
        check_type="LENGTH_CHECK",
        default_strength="WEAK",
        call_names=["strlen", "strnlen"],
        matched_expected_check=None,
    ),
    CheckPattern(
        check_type="AUTHORIZATION_CHECK",
        default_strength="STRONG",
        call_names=["is_authorized", "check_permission", "has_permission", "authorize"],
        matched_expected_check="OPERATOR_PERMISSION_CHECK",
    ),
    CheckPattern(
        check_type="SCHEMA_VALIDATION",
        default_strength="STRONG",
        call_names=["json_schema_validate", "validate_data_transfer_payload"],
        matched_expected_check="DT_DATA_SCHEMA_VALIDATION",
    ),
    CheckPattern(
        check_type="LENGTH_LIMIT",
        default_strength="STRONG",
        call_names=["strlen_bound", "bounded_parser", "max_length_check", "strnlen"],
        matched_expected_check="DT_DATA_LENGTH_LIMIT",
    ),
    CheckPattern(
        check_type="SQL_PARAMETERIZATION",
        default_strength="STRONG",
        call_names=["sqlite3_prepare_v2", "sqlite3_bind_text", "parameterized_query"],
        matched_expected_check="SQL_PARAMETERIZATION",
    ),
    CheckPattern(
        check_type="LENGTH_BOUND_CHECK",
        default_strength="STRONG",
        operators=[
            "<operator>.lessThan",
            "<operator>.lessEqualsThan",
            "<operator>.greaterThan",
            "<operator>.greaterEqualsThan",
        ],
        matched_expected_check="SCP_PROFILE_LENGTH_BOUND",
    ),
]


class KnowledgeBase:
    def __init__(
        self,
        actions: List[ActionProfile],
        fields: List[FieldProfile],
        expected_checks: List[ExpectedCheckProfile],
        sink_domains: List[SinkDomainProfile],
        root_causes: List[RootCause],
        check_patterns: List[CheckPattern],
    ):
        self.actions = {a.action_name: a for a in actions}
        self._fields = {(f.action_name, f.field_name): f for f in fields}
        self.expected_checks = {c.check_id: c for c in expected_checks}
        self.sink_domains = {s.sink_domain: s for s in sink_domains}
        self.root_causes = root_causes
        self.check_patterns = check_patterns

        self._sink_api_index: Dict[str, SinkDomainProfile] = {}
        for prof in sink_domains:
            for api in prof.apis:
                self._sink_api_index[api.lower()] = prof

    def field_profile(self, action: str, field_name: str) -> Optional[FieldProfile]:
        return self._fields.get((action, field_name))

    def fields_for_action(self, action: str) -> List[FieldProfile]:
        return [f for (a, _), f in self._fields.items() if a == action]

    def all_actions(self) -> List[str]:
        return list(self.actions.keys())

    def sink_apis(self) -> List[str]:
        return list(self._sink_api_index.keys())

    def sink_for_api(self, api: str) -> Optional[SinkDomainProfile]:
        return self._sink_api_index.get((api or "").lower())

    def expected_check(self, check_id: str) -> Optional[ExpectedCheckProfile]:
        return self.expected_checks.get(check_id)

    def negative_sink_domains_for(self, check_id: str) -> List[str]:
        prof = self.expected_checks.get(check_id)
        return prof.negative_sink_domains if prof else []

    def root_cause_for(self, sink_domain: str, missing: List[str]) -> List[str]:
        out: List[str] = []
        missing_set = set(missing)
        for rc in self.root_causes:
            if sink_domain in rc.related_sink_domains or (missing_set & set(rc.related_missing_checks)):
                out.append(rc.root_cause_id)
        return out


def default_knowledge_base() -> KnowledgeBase:
    actions = [
        ActionProfile(
            action_name="UpdateFirmware",
            protocol_version="ocpp1.6",
            component_type="charge_point",
            message_direction="CSMS_TO_CHARGE_POINT",
            sensitive_fields=["location"],
            handler_patterns=[
                "handle_update_firmware",
                "on_update_firmware",
                "process_update_firmware",
            ],
        ),
        ActionProfile(
            action_name="DataTransfer",
            protocol_version="ocpp1.6",
            component_type="charge_point",
            message_direction="CSMS_TO_CHARGE_POINT",
            sensitive_fields=["data"],
            handler_patterns=[
                "handle_data_transfer",
                "on_data_transfer",
                "process_data_transfer",
            ],
        ),
        ActionProfile(
            action_name="SetChargingProfile",
            protocol_version="ocpp1.6",
            component_type="charge_point",
            message_direction="CSMS_TO_CHARGE_POINT",
            sensitive_fields=["chargingSchedule"],
            handler_patterns=[
                "handle_set_charging_profile",
                "on_set_charging_profile",
                "process_set_charging_profile",
                "set_charging_profile",
            ],
            action_symbols=["MSG_SET_PROFILE", "ACTION_SET_CHARGING_PROFILE"],
            numeric_ids=[41],
        ),
        ActionProfile(
            action_name="RemoteStartTransaction",
            protocol_version="ocpp1.6",
            component_type="charge_point",
            message_direction="CSMS_TO_CHARGE_POINT",
            sensitive_fields=["idTag"],
            action_symbols=["ACTION_REMOTE_START"],
            numeric_ids=[15],
        ),
    ]

    fields = [
        FieldProfile(
            action_name="UpdateFirmware",
            field_name="location",
            semantic_type="firmware_download_url",
            trust_level="remote_ocpp_input",
            dangerous_sink_domain=["COMMAND_EXECUTION", "UNSAFE_FIRMWARE_DOWNLOAD"],
            expected_checks=[
                "URL_SCHEME_VALIDATION",
                "HOST_ALLOWLIST",
                "SIGNATURE_VERIFICATION",
                "SAFE_DOWNLOAD_API_NO_SHELL",
            ],
            related_cwe=["CWE-78", "CWE-494", "CWE-345", "CWE-20"],
            validation_requirement=[
                "must be https",
                "host must be allow-listed",
                "firmware signature must be verified before install",
                "download must not go through a shell",
            ],
            field_source_aliases=["location", "firmware_url", "firmwareLocation"],
        ),
        FieldProfile(
            action_name="DataTransfer",
            field_name="data",
            semantic_type="vendor_controlled_payload",
            trust_level="remote_ocpp_input",
            dangerous_sink_domain=["database_query_execution"],
            expected_checks=[
                "DT_DATA_SCHEMA_VALIDATION",
                "DT_DATA_LENGTH_LIMIT",
                "SQL_PARAMETERIZATION",
            ],
            related_cwe=["CWE-89", "CWE-20"],
            validation_requirement=[
                "validate the vendor payload against the expected schema",
                "reject payloads over the max length",
                "use parameterized queries instead of string concatenation",
            ],
            field_source_aliases=["data"],
        ),
        FieldProfile(
            action_name="SetChargingProfile",
            field_name="csChargingProfiles.chargingSchedule",
            semantic_type="charging_schedule_payload",
            trust_level="remote_ocpp_input",
            dangerous_sink_domain=["MEMORY_UNSAFE_OPERATION"],
            expected_checks=[
                "SCP_CHARGING_SCHEDULE_NOT_NULL",
                "SCP_PROFILE_LENGTH_BOUND",
            ],
            related_cwe=["CWE-120", "CWE-787", "CWE-20"],
            validation_requirement=[
                "the charging schedule pointer must be non-null before use",
                "the copied length must be bounded by the destination capacity",
            ],
            field_source_aliases=["schedule"],
        ),
        FieldProfile(
            action_name="SetChargingProfile",
            field_name="csChargingProfiles.chargingSchedule.length",
            semantic_type="profile_copy_length",
            trust_level="remote_ocpp_input",
            dangerous_sink_domain=["MEMORY_UNSAFE_OPERATION"],
            expected_checks=[
                "SCP_PROFILE_LENGTH_BOUND",
            ],
            related_cwe=["CWE-120", "CWE-787", "CWE-20"],
            validation_requirement=[
                "the length must be checked against PROFILE_BUFFER_SIZE before the copy",
            ],
            field_source_aliases=["schedule_length", "chargingScheduleLength"],
        ),
        FieldProfile(
            action_name="RemoteStartTransaction",
            field_name="idTag",
            semantic_type="remote_authorization_id",
            trust_level="remote_ocpp_input",
            dangerous_sink_domain=["COMMAND_EXECUTION"],
            expected_checks=[
                "RS_IDTAG_INPUT_VALIDATION",
                "RS_NO_SHELL_EXECUTION",
            ],
            related_cwe=["CWE-78", "CWE-20"],
            validation_requirement=[
                "validate idTag against the expected identifier format/allowlist",
                "authorization must not be performed by building/executing a shell command",
            ],
            field_source_aliases=["idTag"],
        ),
    ]

    expected_checks = [
        ExpectedCheckProfile(
            check_id="URL_SCHEME_VALIDATION",
            check_type="INPUT_VALIDATION",
            description="Firmware URL scheme is validated (e.g. https only).",
            expected_before_sink=True,
            related_cwe=["CWE-20"],
        ),
        ExpectedCheckProfile(
            check_id="HOST_ALLOWLIST",
            check_type="POLICY_VALIDATION",
            description="Firmware host is checked against an allow-list.",
            related_cwe=["CWE-20"],
        ),
        ExpectedCheckProfile(
            check_id="SIGNATURE_VERIFICATION",
            check_type="INTEGRITY_VERIFICATION",
            description="Downloaded firmware signature is verified before use.",
            related_cwe=["CWE-345", "CWE-494"],
        ),
        ExpectedCheckProfile(
            check_id="SAFE_DOWNLOAD_API_NO_SHELL",
            check_type="SAFE_API_USAGE",
            description="Firmware download must not be performed through a shell.",
            negative_sink_domains=["COMMAND_EXECUTION"],
            related_cwe=["CWE-78"],
        ),
        ExpectedCheckProfile(
            check_id="DT_DATA_SCHEMA_VALIDATION",
            check_type="INPUT_VALIDATION",
            description="Validate the vendor payload against the expected message schema before use.",
            related_cwe=["CWE-20"],
        ),
        ExpectedCheckProfile(
            check_id="DT_DATA_LENGTH_LIMIT",
            check_type="INPUT_VALIDATION",
            description="Reject payloads that exceed the implementation-defined maximum length.",
            related_cwe=["CWE-20", "CWE-1284"],
        ),
        ExpectedCheckProfile(
            check_id="SQL_PARAMETERIZATION",
            check_type="SAFE_API_USAGE",
            description="Use a prepared statement / bound parameter instead of concatenating payload into SQL.",
            negative_sink_domains=["database_query_execution"],
            related_cwe=["CWE-89"],
        ),
        ExpectedCheckProfile(
            check_id="SCP_CHARGING_SCHEDULE_NOT_NULL",
            check_type="INPUT_VALIDATION",
            description="The charging-schedule pointer is checked non-null before it is dereferenced/copied.",
            related_cwe=["CWE-476", "CWE-20"],
        ),
        ExpectedCheckProfile(
            check_id="SCP_PROFILE_LENGTH_BOUND",
            check_type="INPUT_VALIDATION",
            description="The copy length is bounded (e.g. length < PROFILE_BUFFER_SIZE) before memcpy.",
            related_cwe=["CWE-120", "CWE-787", "CWE-20"],
        ),
        ExpectedCheckProfile(
            check_id="RS_IDTAG_INPUT_VALIDATION",
            check_type="INPUT_VALIDATION",
            description="idTag is validated against an expected identifier format/allowlist before use.",
            related_cwe=["CWE-20"],
        ),
        ExpectedCheckProfile(
            check_id="RS_NO_SHELL_EXECUTION",
            check_type="SAFE_API_USAGE",
            description="Authorization must not be performed by constructing and executing a shell command.",
            negative_sink_domains=["COMMAND_EXECUTION"],
            related_cwe=["CWE-78"],
        ),
    ]

    sink_domains = [
        SinkDomainProfile(
            sink_domain="COMMAND_EXECUTION",
            description="Executes an OS command / shell.",
            apis=["system", "popen", "execl", "execlp", "execle", "execv", "execvp", "execvpe"],
            related_cwe=["CWE-78"],
            severity="HIGH",
        ),
        SinkDomainProfile(
            sink_domain="MEMORY_UNSAFE_OPERATION",
            description="Unbounded memory/string write.",
            apis=["strcpy", "strcat", "sprintf", "gets", "memcpy", "vsprintf"],
            related_cwe=["CWE-120", "CWE-787"],
            severity="MEDIUM_HIGH",
        ),
        SinkDomainProfile(
            sink_domain="FILE_WRITE",
            description="Writes to a file path.",
            apis=["fopen", "open", "fwrite", "write"],
            related_cwe=["CWE-22"],
            severity="MEDIUM",
        ),
        SinkDomainProfile(
            sink_domain="database_query_execution",
            description="Executes a database query.",
            apis=["sqlite3_exec", "mysql_query", "pqexec"],
            related_cwe=["CWE-89"],
            severity="HIGH",
            dangerous_arg_indexes=[1],
        ),
    ]

    root_causes = [
        RootCause(
            root_cause_id="untrusted_ocpp_field_to_dangerous_sink",
            description="An untrusted OCPP payload field reaches a dangerous sink without adequate validation.",
            related_missing_checks=[
                "URL_SCHEME_VALIDATION",
                "HOST_ALLOWLIST",
                "SAFE_DOWNLOAD_API_NO_SHELL",
            ],
            related_sink_domains=["COMMAND_EXECUTION", "UNSAFE_FIRMWARE_DOWNLOAD"],
            related_cwe=["CWE-78", "CWE-20"],
        ),
        RootCause(
            root_cause_id="missing_firmware_integrity_verification",
            description="Firmware is installed without verifying its signature/integrity.",
            related_missing_checks=["SIGNATURE_VERIFICATION"],
            related_sink_domains=["UNSAFE_FIRMWARE_DOWNLOAD", "FIRMWARE_INSTALL"],
            related_cwe=["CWE-345", "CWE-494"],
        ),
        RootCause(
            root_cause_id="untrusted_payload_to_sql_injection",
            description="A vendor-controlled payload is concatenated into a database query without parameterization.",
            related_missing_checks=["SQL_PARAMETERIZATION", "DT_DATA_SCHEMA_VALIDATION"],
            related_sink_domains=["database_query_execution"],
            related_cwe=["CWE-89"],
        ),
        RootCause(
            root_cause_id="remote_length_to_unbounded_profile_copy",
            description="A remote-controlled charging-profile payload/length is copied into a fixed-size buffer without a bounds check.",
            related_missing_checks=["SCP_PROFILE_LENGTH_BOUND", "SCP_CHARGING_SCHEDULE_NOT_NULL"],
            related_sink_domains=["MEMORY_UNSAFE_OPERATION"],
            related_cwe=["CWE-120", "CWE-787"],
        ),
        RootCause(
            root_cause_id="remote_id_to_command_injection",
            description="A remote-controlled authorization id reaches a shell command-execution sink without validation.",
            related_missing_checks=["RS_IDTAG_INPUT_VALIDATION", "RS_NO_SHELL_EXECUTION"],
            related_sink_domains=["COMMAND_EXECUTION"],
            related_cwe=["CWE-78", "CWE-20"],
        ),
    ]

    return KnowledgeBase(
        actions=actions,
        fields=fields,
        expected_checks=expected_checks,
        sink_domains=sink_domains,
        root_causes=root_causes,
        check_patterns=list(DEFAULT_CHECK_PATTERNS),
    )
