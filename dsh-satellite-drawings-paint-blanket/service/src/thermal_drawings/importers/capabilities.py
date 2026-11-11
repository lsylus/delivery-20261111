"""No native adapter is advertised without a selected, licensed and tested engine."""


def native_capability(manifest, config=None):
    config = config or {}
    format_ = manifest['detected_format']
    code = 'converter_not_configured'
    if format_ not in ('Creo_PART', 'Creo_ASSEMBLY', 'NX_PART'):
        code = 'unsupported_format'
    elif manifest.get('missing_refs'):
        code = 'missing_dependencies'
    elif config.get('license_state') in ('denied', 'expired'):
        code = 'license_unavailable'
    elif config.get('supported_versions') and manifest.get('vendor_version') not in config['supported_versions']:
        code = 'unsupported_version'
    elif config.get('adapter'):
        code = 'adapter_not_validated'
    return dict(vendor=manifest.get('vendor'), vendor_version=manifest.get('vendor_version'),
                format=format_, status='blocked', available=False, tool=None,
                license_state=config.get('license_state', 'unverified'), validated_case_ids=[],
                code=code, reason='No licensed native engine selected and validated for B05; no conversion executed')
