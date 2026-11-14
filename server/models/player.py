from pydantic import BaseModel, ConfigDict
from .enums import Role


class Player(BaseModel):
    model_config = ConfigDict(validate_assignment=True)  # Allow mutation for alive status

    id: int
    name: str
    role: Role
    alive: bool = True

    # since pydantic model, do mode.model_dump() for dict rep of model
