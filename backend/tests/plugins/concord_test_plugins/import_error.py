"""A plugin module that raises while being imported."""

raise ImportError("this test plugin depends on a library that is not installed")
