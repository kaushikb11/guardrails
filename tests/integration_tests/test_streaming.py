# 3 tests
# 1. Test streaming with OpenAICallable (mock openai.Completion.create)
# 2. Test streaming with OpenAIChatCallable (mock openai.ChatCompletion.create)
# 3. Test string schema streaming
# Using the LowerCase Validator, and a custom validator to show new streaming behavior
import json
from typing import Any, Callable, Dict, Iterable, List, Optional, Union

import openai
import pytest
import nltk
from pydantic import BaseModel, Field

import guardrails as gd
from guardrails.utils.casting_utils import to_int
from guardrails.utils.openai_utils import OPENAI_VERSION
from guardrails.validator_base import (
    FailResult,
    OnFailAction,
    PassResult,
    ValidationResult,
    Validator,
    register_validator,
)
from guardrails.validators import LowerCase

expected_raw_output = {"statement": "I am DOING well, and I HOPE you aRe too."}
expected_fix_output = {"statement": "i am doing well, and i hope you are too."}
expected_noop_output = {"statement": "I am DOING well, and I HOPE you aRe too."}
expected_filter_refrain_output = {}


@register_validator(name="minsentencelength", data_type=["string", "list"])
class MinSentenceLengthValidator(Validator):
    def __init__(
        self,
        min: Optional[int] = None,
        max: Optional[int] = None,
        on_fail: Optional[Callable] = None,
    ):
        super().__init__(
            on_fail=on_fail,
            min=min,
            max=max,
        )
        self._min = to_int(min)
        self._max = to_int(max)

    def sentence_split(self, value):
        if "." not in value:
            return [value]
        sentences = nltk.sent_tokenize(value)
        if len(sentences) == 0:
            return [value]
        return sentences

    def validate(self, value: Union[str, List], metadata: Dict) -> ValidationResult:
        # return PassResult()
        sentences = self.sentence_split(value)
        print("validating sentence:", sentences)
        for sentence in sentences:
            if len(sentence) < self._min:
                return FailResult(
                    error_message=f"Sentence has length less than {self._min}. "
                    f"Please return a longer output, "
                    f"that is shorter than {self._max} characters.",
                )
            if len(sentence) > self._max:
                return FailResult(
                    error_message=f"Sentence has length greater than {self._max}. "
                    f"Please return a shorter output, "
                    f"that is shorter than {self._max} characters.",
                )
        return PassResult()

    def validate_stream(self, chunk: Any, metadata: Dict, **kwargs) -> ValidationResult:
        return super().validate_stream(chunk, metadata, **kwargs)


class Delta:
    content: str

    def __init__(self, content):
        self.content = content


class Choice:
    text: str
    finish_reason: str
    index: int
    delta: Delta

    def __init__(self, text, delta, finish_reason, index=0):
        self.index = index
        self.delta = delta
        self.text = text
        self.finish_reason = finish_reason


class MockOpenAIV1ChunkResponse:
    choices: list
    model: str

    def __init__(self, choices, model):
        self.choices = choices
        self.model = model


def mock_openai_completion_create(chunks):
    # Returns a generator
    def gen():
        for chunk in chunks:
            if OPENAI_VERSION.startswith("0"):
                yield {
                    "choices": [{"text": chunk, "finish_reason": None}],
                    "model": "OpenAI model name",
                }
            else:
                yield MockOpenAIV1ChunkResponse(
                    choices=[
                        Choice(
                            text=chunk,
                            delta=Delta(content=""),
                            finish_reason=None,
                        )
                    ],
                    model="OpenAI model name",
                )

    return gen()


def mock_openai_chat_completion_create(chunks):
    # Returns a generator
    def gen():
        for chunk in chunks:
            if OPENAI_VERSION.startswith("0"):
                yield {
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": chunk},
                            "finish_reason": None,
                        }
                    ]
                }
            else:
                yield MockOpenAIV1ChunkResponse(
                    choices=[
                        Choice(
                            text="",
                            delta=Delta(content=chunk),
                            finish_reason=None,
                        )
                    ],
                    model="OpenAI model name",
                )

    return gen()


class LowerCaseFix(BaseModel):
    statement: str = Field(
        description="Validates whether the text is in lower case.",
        validators=[LowerCase(on_fail=OnFailAction.FIX)],
    )


class LowerCaseNoop(BaseModel):
    statement: str = Field(
        description="Validates whether the text is in lower case.",
        validators=[LowerCase(on_fail=OnFailAction.NOOP)],
    )


class LowerCaseFilter(BaseModel):
    statement: str = Field(
        description="Validates whether the text is in lower case.",
        validators=[LowerCase(on_fail=OnFailAction.FILTER)],
    )


class LowerCaseRefrain(BaseModel):
    statement: str = Field(
        description="Validates whether the text is in lower case.",
        validators=[LowerCase(on_fail=OnFailAction.REFRAIN)],
    )


expected_minsentence_noop_output = ""


class MinSentenceLengthNoOp(BaseModel):
    statement: str = Field(
        description="Validates whether the text is in lower case.",
        validators=[MinSentenceLengthValidator(on_fail=OnFailAction.NOOP)],
    )


STR_PROMPT = "Say something nice to me."

PROMPT = """
Say something nice to me.

${gr.complete_json_suffix}
"""

JSON_LLM_CHUNKS = [
    '{"statement":',
    ' "I am DOING',
    " well, and I",
    " HOPE you aRe",
    ' too."}',
]


@pytest.mark.parametrize(
    "guard, expected_validated_output",
    [
        (
            gd.Guard.from_pydantic(output_class=LowerCaseNoop, prompt=PROMPT),
            expected_noop_output,
        ),
        (
            gd.Guard.from_pydantic(output_class=LowerCaseFix, prompt=PROMPT),
            expected_fix_output,
        ),
        (
            gd.Guard.from_pydantic(output_class=LowerCaseFilter, prompt=PROMPT),
            expected_filter_refrain_output,
        ),
        (
            gd.Guard.from_pydantic(output_class=LowerCaseRefrain, prompt=PROMPT),
            expected_filter_refrain_output,
        ),
    ],
)
def test_streaming_with_openai_callable(
    mocker,
    guard,
    expected_validated_output,
):
    """Test streaming with OpenAICallable.

    Mocks openai.Completion.create.
    """
    if OPENAI_VERSION.startswith("0"):
        mocker.patch(
            "openai.Completion.create",
            return_value=mock_openai_completion_create(JSON_LLM_CHUNKS),
        )
    else:
        mocker.patch(
            "openai.resources.Completions.create",
            return_value=mock_openai_completion_create(JSON_LLM_CHUNKS),
        )

    method = (
        openai.Completion.create
        if OPENAI_VERSION.startswith("0")
        else openai.completions.create
    )

    method.__name__ = "mock_openai_completion_create"

    generator = guard(
        method,
        engine="text-davinci-003",
        max_tokens=10,
        temperature=0,
        stream=True,
    )

    assert isinstance(generator, Iterable)

    for op in generator:
        actual_output = op

    assert actual_output.raw_llm_output == json.dumps(expected_raw_output)
    assert actual_output.validated_output == expected_validated_output


@pytest.mark.parametrize(
    "guard, expected_validated_output",
    [
        (
            gd.Guard.from_pydantic(output_class=LowerCaseNoop, prompt=PROMPT),
            expected_noop_output,
        ),
        (
            gd.Guard.from_pydantic(output_class=LowerCaseFix, prompt=PROMPT),
            expected_fix_output,
        ),
        (
            gd.Guard.from_pydantic(output_class=LowerCaseFilter, prompt=PROMPT),
            expected_filter_refrain_output,
        ),
        (
            gd.Guard.from_pydantic(output_class=LowerCaseRefrain, prompt=PROMPT),
            expected_filter_refrain_output,
        ),
    ],
)
def test_streaming_with_openai_chat_callable(
    mocker,
    guard,
    expected_validated_output,
):
    """Test streaming with OpenAIChatCallable.

    Mocks openai.ChatCompletion.create.
    """
    if OPENAI_VERSION.startswith("0"):
        mocker.patch(
            "openai.ChatCompletion.create",
            return_value=mock_openai_chat_completion_create(JSON_LLM_CHUNKS),
        )
    else:
        mocker.patch(
            "openai.resources.chat.completions.Completions.create",
            return_value=mock_openai_chat_completion_create(JSON_LLM_CHUNKS),
        )

    method = (
        openai.ChatCompletion.create
        if OPENAI_VERSION.startswith("0")
        else openai.chat.completions.create
    )

    method.__name__ = "mock_openai_chat_completion_create"

    generator = guard(
        method,
        model="gpt-3.5-turbo",
        max_tokens=10,
        temperature=0,
        stream=True,
    )

    assert isinstance(generator, Iterable)

    actual_output = ""
    for op in generator:
        actual_output = op

    assert actual_output.raw_llm_output == json.dumps(expected_raw_output)
    assert actual_output.validated_output == expected_validated_output


STR_LLM_CHUNKS = [
    # 38 characters
    "This sentence is simply just ",
    "too long."
    # 25 characters long
    "This ",
    "sentence ",
    "is 2 ",
    "short."
    # 29 characters long
    "This sentence is just ",
    "right.",
]


@pytest.mark.parametrize(
    "guard, expected_validated_output",
    [
        (
            gd.Guard.from_string(
                # only the middle sentence should pass
                validators=[
                    MinSentenceLengthValidator(26, 30, on_fail=OnFailAction.NOOP)
                ],
                prompt=STR_PROMPT,
            ),
            # For now these should be correct.
            # This will be different pending validation outcome
            # schema changes.
            [True, False, True, True, False, False],
        )
    ],
)
def test_string_schema_streaming_with_openai_chat(
    mocker, guard, expected_validated_output
):
    """Test string schema streaming with OpenAIChatCallable.

    Mocks openai.ChatCompletion.create.
    """
    if OPENAI_VERSION.startswith("0"):
        mocker.patch(
            "openai.ChatCompletion.create",
            return_value=mock_openai_chat_completion_create(STR_LLM_CHUNKS),
        )
    else:
        mocker.patch(
            "openai.resources.chat.completions.Completions.create",
            return_value=mock_openai_chat_completion_create(STR_LLM_CHUNKS),
        )

    method = (
        openai.ChatCompletion.create
        if OPENAI_VERSION.startswith("0")
        else openai.chat.completions.create
    )

    method.__name__ = "mock_openai_chat_completion_create"
    generator = guard(
        method,
        model="gpt-3.5-turbo",
        max_tokens=10,
        temperature=0,
        stream=True,
    )

    assert isinstance(generator, Iterable)

    for op, desired_result in zip(generator, expected_validated_output):
        assert op.validation_passed == desired_result
        print("op", op)
