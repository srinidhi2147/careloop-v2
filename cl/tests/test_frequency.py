import pytest

from careloop.frequency import times_from_frequency


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1-0-1", ["08:00", "21:00"]),
        ("1-1-1", ["08:00", "14:00", "21:00"]),
        ("0-0-1", ["21:00"]),
        ("0-0-0", []),
        ("OD", ["09:00"]),
        ("bd", ["08:00", "20:00"]),
        (" T D S ", ["08:00", "14:00", "20:00"]),
        ("QID", ["08:00", "12:00", "16:00", "20:00"]),
        ("HS", ["22:00"]),
        ("SOS", []),
        ("PRN", []),
        ("before breakfast", []),
        ("", []),
        (None, []),
    ],
)
def test_times_from_frequency(text, expected):
    assert times_from_frequency(text) == expected


def test_returned_list_is_a_copy():
    first = times_from_frequency("BD")
    first.append("23:00")
    assert times_from_frequency("BD") == ["08:00", "20:00"]
