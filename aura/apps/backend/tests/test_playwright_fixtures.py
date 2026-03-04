from tools.web_playwright import handle_web_action, parse_search_html, parse_flights_html
from aura.steps import Step


def test_search_fixture_parses():
    step = Step(id='1', name='Search web', action_type='WEB_READ', args={'target':'search'})
    out = handle_web_action(step)
    assert out['ok'] and len(out['key_points']) == 5


def test_gmail_fixture_parses():
    step = Step(id='1', name='Gmail', action_type='WEB_READ', args={'target':'gmail_unread'})
    out = handle_web_action(step)
    assert out['unread_count'] == 2


def test_pipeline_parser_integration():
    html = '<ul><li><a href="https://x.com">Title</a><p>Snippet</p></li></ul>'
    out = parse_search_html(html)
    assert out['items'][0]['url'] == 'https://x.com'


def test_flight_schema_consistent():
    out = parse_flights_html('<div data-airline="A" data-price="120" data-link="u"></div>')
    assert set(out['flights'][0].keys()) == {'airline', 'price', 'link', 'time'}
