"""Declarative base + id helper shared by every ORM model."""

import uuid

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def new_id() -> str:
    return uuid.uuid4().hex
