"""Tests for src/index.py."""

from src.index import add, multiply


def test_add():
    assert add(2, 3) == 5


def test_multiply():
    assert multiply(4, 5) == 20


def test_add_negative():
    assert add(-1, 1) == 0
