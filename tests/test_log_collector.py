import pytest

from log_collector import (
    load_state_app, dt_translate_and_format,
    parse_event_xml, load_bookmark,
)


def _read_data(file_name):
    with open(file_name, 'r') as source_file:
        result_data = source_file.read()

    return result_data


def test_load_state_app():
    pass


def test_dt_translate_and_format():
    pass


def test_parse_event_xml():
    pass


def test_load_bookmark():
    pass
