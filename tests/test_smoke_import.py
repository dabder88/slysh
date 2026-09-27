def test_package_imports_without_torch():
    import slysh
    assert slysh.__version__ == "0.1.0"
