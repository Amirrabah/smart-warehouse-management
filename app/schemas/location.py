from pydantic import BaseModel, ConfigDict, Field, field_validator

LOCATION_CODE_PATTERN = r"^[A-Z]-\d{2}-\d{2}$"


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    description: str | None
    is_active: bool


class LocationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(pattern=LOCATION_CODE_PATTERN)
    description: str | None = Field(default=None, max_length=200)

    @field_validator("code", mode="before")
    @classmethod
    def normalise_code(cls, value):
        return value.strip().upper() if isinstance(value, str) else value


class LocationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    description: str | None = Field(default=None, max_length=200)
    is_active: bool | None = None
