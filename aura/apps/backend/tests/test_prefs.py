from aura.prefs import set_pref, should_ask, reset_pref


def test_ask_once_then_stop_asking():
    reset_pref('gmail.browser')
    assert should_ask('gmail.browser')
    set_pref('gmail.browser', 'Default')
    assert not should_ask('gmail.browser')
