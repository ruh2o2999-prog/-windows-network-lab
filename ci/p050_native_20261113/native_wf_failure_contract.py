#!/usr/bin/env python3
# Pure read-only diagnostic adapter; no paths/status text are emitted.
import re
_CODE = re.compile(r'(?<![A-Za-z0-9])WF-([0-9]{4})(?![0-9])')
_CATEGORIES = {
    2401: 'OFFICE_GATE_WPS_ONLY', 2402: 'OFFICE_GATE_MISSING',
    2501: 'STAGING_TEMP_PATH', 2502: 'STAGING_CREATE',
    2503: 'PAYLOAD_UNPACK_OR_INTEGRITY', 2504: 'ICON_INTEGRITY',
    2901: 'PRODUCT_POLICY_GATE', 3020: 'OFFICE_TRUST_LOCATION',
    3060: 'OLD_DIRECTORY_BACKUP_LOCK',
}
def error_code(status):
    if not isinstance(status,str):return None
    m=_CODE.search(status)
    return int(m.group(1)) if m else None
def failure_token(status):
    code=error_code(status)
    return ('%04d'%code) if code is not None else 'UNKNOWN'
def sanitized_failure(status):
    code=error_code(status)
    return {
        'native_error_code':code,
        'native_error_source':'installer_status_control_205' if code is not None else 'NOT_READABLE_FROM_STATUS_205',
        'failure_category':_CATEGORIES.get(code,'PRODUCT_OR_ENV_UNDETERMINED'),
        'failure_cause_confirmed':False,
        'raw_error_text_collected':False,
        'real_office_macro_claim':False,
    }
