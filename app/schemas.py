"""Request validation. Structural checks live here; checks that depend on
the questions stored in the database live in repository.create_feedback."""
import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+()\-.\s]{6,30}$")

STATUSES = ("new", "reviewed", "actioned", "archived")
Status = Literal["new", "reviewed", "actioned", "archived"]


class _Model(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


def _blank_to_none(v):
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


class CustomerIn(_Model):
    name: str = Field(min_length=1, max_length=120)
    company: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=254)

    _blanks = field_validator("company", "phone", "email", mode="before")(_blank_to_none)

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        if v is not None and not EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address, like name@example.com.")
        return v

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        if v is not None and (not PHONE_RE.match(v) or len(re.sub(r"\D", "", v)) < 6):
            raise ValueError("Enter a valid phone number.")
        return v


class AnswerIn(_Model):
    question_code: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_]+$")
    # Strict so JSON true/false is rejected instead of becoming a 1/0 rating.
    value: StrictInt | StrictStr | None = None
    detail: str | None = Field(default=None, max_length=200)
    suggestion: str | None = Field(default=None, max_length=2000)

    _blanks = field_validator("value", "detail", "suggestion", mode="before")(_blank_to_none)


class FeedbackIn(_Model):
    customer: CustomerIn
    service_type_id: int | None = Field(default=None, ge=1)
    answers: list[AnswerIn] = Field(default_factory=list, max_length=200)
    other_suggestions: str | None = Field(default=None, max_length=4000)
    # Honeypot: hidden from people, bots tend to fill it.
    website: str | None = Field(default=None, max_length=200)

    _blanks = field_validator("other_suggestions", "website", mode="before")(_blank_to_none)


class LoginIn(_Model):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class PasswordChangeIn(_Model):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator("new_password")
    @classmethod
    def _strength(cls, v):
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password is too long.")
        if v.isdigit() or v.isalpha():
            raise ValueError("Use a mix of letters and numbers.")
        return v


class StatusIn(_Model):
    status: Status


class FeedbackFilters(_Model):
    q: str | None = Field(default=None, max_length=100)
    date_from: date | None = None
    date_to: date | None = None
    service_id: int | None = Field(default=None, ge=1)
    rating_min: int | None = Field(default=None, ge=1, le=5)
    rating_max: int | None = Field(default=None, ge=1, le=5)
    status: Status | None = None

    _blanks = field_validator(
        "q", "date_from", "date_to", "service_id", "rating_min", "rating_max", "status", mode="before"
    )(_blank_to_none)
