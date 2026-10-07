from pydantic import BaseModel


class CreateOrder(BaseModel):
    customer_id: int
    quantity: int
    note: str | None = None
