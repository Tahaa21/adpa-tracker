from app.services.fingerprint import compute_fingerprint


def test_fingerprint_is_deterministic():
    fp1 = compute_fingerprint("PASSWORD_NOT_REQUIRED", "corp.local", "svc_backup")
    fp2 = compute_fingerprint("PASSWORD_NOT_REQUIRED", "corp.local", "svc_backup")
    assert fp1 == fp2


def test_fingerprint_is_case_and_whitespace_insensitive():
    fp1 = compute_fingerprint("PASSWORD_NOT_REQUIRED", "Corp.Local", "svc_backup")
    fp2 = compute_fingerprint("password_not_required", " corp.local ", " SVC_BACKUP ")
    assert fp1 == fp2


def test_fingerprint_differs_by_type():
    fp1 = compute_fingerprint("PASSWORD_NOT_REQUIRED", "corp.local", "svc_backup")
    fp2 = compute_fingerprint("WEAK_PASSWORD", "corp.local", "svc_backup")
    assert fp1 != fp2


def test_fingerprint_differs_by_asset():
    fp1 = compute_fingerprint("PASSWORD_NOT_REQUIRED", "corp.local", "svc_backup")
    fp2 = compute_fingerprint("PASSWORD_NOT_REQUIRED", "corp.local", "svc_other")
    assert fp1 != fp2


def test_fingerprint_differs_by_domain():
    fp1 = compute_fingerprint("PASSWORD_NOT_REQUIRED", "corp.local", "svc_backup")
    fp2 = compute_fingerprint("PASSWORD_NOT_REQUIRED", "other.local", "svc_backup")
    assert fp1 != fp2
