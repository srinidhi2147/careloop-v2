import json

import pytest

from careloop.ai import BedrockClient, MockReader, parse_model_output


def payload(*medicines):
    return json.dumps({"medicines": list(medicines)})


GOOD = {"name": "Metformin", "strength": "500 mg", "frequency": "1-0-1", "times": [],
        "instructions": "after food", "confidence": 0.95}


def test_parses_clean_json_and_maps_frequency():
    med = parse_model_output(payload(GOOD))[0]
    assert med.times == ["08:00", "21:00"]
    assert med.needs_review is False


def test_parses_json_wrapped_in_markdown_fences():
    raw = "Here you go:\n```json\n" + payload(GOOD) + "\n```"
    assert parse_model_output(raw)[0].name == "Metformin"


def test_explicit_times_override_frequency():
    med = parse_model_output(payload({**GOOD, "times": ["07:30"]}))[0]
    assert med.times == ["07:30"]


def test_invalid_explicit_times_are_dropped_and_frequency_used():
    med = parse_model_output(payload({**GOOD, "times": ["7am", "25:00"]}))[0]
    assert med.times == ["08:00", "21:00"]


@pytest.mark.parametrize(
    "change",
    [{"confidence": 0.5}, {"name": ""}, {"frequency": "SOS"}, {"confidence": "high"}],
)
def test_uncertain_lines_are_flagged_for_review(change):
    assert parse_model_output(payload({**GOOD, **change}))[0].needs_review is True


def test_confidence_is_clamped_to_zero_one():
    assert parse_model_output(payload({**GOOD, "confidence": 7}))[0].confidence == 1.0


@pytest.mark.parametrize("raw", ["", "no json here", "{broken json", "}{"])
def test_unreadable_output_raises_value_error(raw):
    with pytest.raises(ValueError, match="readable"):
        parse_model_output(raw)


def test_missing_medicines_key_gives_empty_list():
    assert parse_model_output("{}") == []


def test_mock_reader_returns_sample_with_one_flagged_line():
    meds = MockReader().read(b"", "image/png")
    assert [m.name for m in meds] == ["Metformin", "Amlodipine", "Pantoprazole"]
    assert [m.needs_review for m in meds] == [False, False, True]


class FakeBedrock:
    def __init__(self, text="{}", fail=False):
        self.text, self.fail, self.calls = text, fail, []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("throttled")
        return {"output": {"message": {"content": [{"text": self.text}]}}}


def test_bedrock_sends_image_block_and_parses_reply():
    fake = FakeBedrock(payload(GOOD))
    meds = BedrockClient("model-x", client=fake).read(b"\x89PNG", "image/png")
    sent = fake.calls[0]
    assert sent["modelId"] == "model-x"
    assert sent["messages"][0]["content"][0]["image"]["format"] == "png"
    assert sent["inferenceConfig"]["temperature"] == 0
    assert meds[0].name == "Metformin"


def test_bedrock_sends_pdf_as_document_block():
    fake = FakeBedrock(payload(GOOD))
    BedrockClient("m", client=fake).read(b"%PDF", "application/pdf")
    assert fake.calls[0]["messages"][0]["content"][0]["document"]["format"] == "pdf"


def test_bedrock_rejects_unsupported_file_type_without_calling_aws():
    fake = FakeBedrock()
    with pytest.raises(ValueError, match="PNG, JPEG, WEBP or PDF"):
        BedrockClient("m", client=fake).read(b"x", "text/plain")
    assert fake.calls == []


def test_generate_returns_text_and_none_on_failure():
    assert BedrockClient("m", client=FakeBedrock("  hello  ")).generate("hi") == "hello"
    assert BedrockClient("m", client=FakeBedrock(fail=True)).generate("hi") is None
