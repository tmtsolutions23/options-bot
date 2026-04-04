import json
import os
import pytest
from unittest.mock import patch, MagicMock
from universe import load_seed_universe, get_dynamic_tickers, build_daily_universe


def test_load_seed_universe():
    tickers = load_seed_universe()
    assert isinstance(tickers, list)
    assert len(tickers) > 50
    assert "SOFI" in tickers
    assert "PLTR" in tickers


def test_seed_no_duplicates():
    tickers = load_seed_universe()
    assert len(tickers) == len(set(tickers))


def test_build_daily_universe_includes_seed():
    with patch("universe.get_dynamic_tickers", return_value=["ZZZZ"]):
        result = build_daily_universe()
        seed = load_seed_universe()
        for t in seed:
            assert t in result
        assert "ZZZZ" in result


def test_build_daily_universe_deduplicates():
    seed = load_seed_universe()
    with patch("universe.get_dynamic_tickers", return_value=[seed[0]]):
        result = build_daily_universe()
        assert len(result) == len(set(result))
