from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    full_name: str | None = None


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    full_name: str | None = None

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str
