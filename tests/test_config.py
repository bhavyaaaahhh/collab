from collab.config import load_config


def test_defaults_when_missing(tmp_path):
    c = load_config(tmp_path / "nope.json")
    assert c.port == 4747
    assert c.budget.max_messages == 80


def test_overrides(tmp_path):
    p = tmp_path / "c.json"
    p.write_text('{"port": 5000, "budget": {"max_minutes": 5}}')
    c = load_config(p)
    assert c.port == 5000
    assert c.budget.max_minutes == 5
    assert c.budget.max_messages == 80
