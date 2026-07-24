from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

Role = Literal["viewer", "analyst", "admin"]

@dataclass(frozen=True)
class Principal:
    user_id: str
    email: str
    role: Role
    must_change_password: bool
