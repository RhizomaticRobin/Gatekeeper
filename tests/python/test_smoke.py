def test_pytest_works():
    assert True


def test_conftest_fixtures(sample_plan):
    assert "metadata" in sample_plan
    assert "phases" in sample_plan
