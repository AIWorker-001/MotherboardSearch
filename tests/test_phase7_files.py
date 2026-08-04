from pathlib import Path


def test_phase7_configuration_and_tools_exist():
    assert Path('config/continual_learning.json').exists()
    assert Path('src/continual_learning.py').exists()
    assert Path('src/compare_models.py').exists()
    assert Path('src/continual_promotion.py').exists()
