from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TicketCreate(BaseModel):
    subject: str = Field(min_length=3)
    message: str = Field(min_length=3)
    priority: str = "normal"


class TicketReply(BaseModel):
    body: str = Field(min_length=1)


class TicketPatch(BaseModel):
    status: str | None = None
    priority: str | None = None


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    reference: str
    merchant_id: str
    subject: str
    status: str
    priority: str
    last_message_at: datetime
    created_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ticket_id: str
    author_role: str
    author_name: str
    body: str
    created_at: datetime


class TicketDetail(TicketOut):
    messages: list[MessageOut] = []


class AdminTicketOut(TicketOut):
    merchant_name: str


class AdminTicketDetail(AdminTicketOut):
    messages: list[MessageOut] = []
