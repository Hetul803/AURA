from aura.safety import requires_confirmation

def test_sensitive_detection():
    assert requires_confirmation('send email now')
    assert not requires_confirmation('open gmail')
