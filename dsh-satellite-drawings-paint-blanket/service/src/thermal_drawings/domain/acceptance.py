"""Editable technical candidates never imply manufacturing acceptance."""
def usable(value):
    if not value or any(c['status']=='fail' for c in value.get('checks',[])):return False
    return value.get('status')=='passed' or (value.get('status')=='needs_review' and value.get('candidate_editable') is True)

def aggregate(checks):
    return 'failed' if any(c['status']=='fail' for c in checks) else 'needs_review' if any(c['status'] not in ('pass','not_applicable') for c in checks) else 'passed'
