from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    session_id: str = Field(alias="sessionId", min_length=1)
    course_id: str = Field(default="ai_intro")
    user_message: str = Field(default="我想学习人工智能导论")

    class Config:
        populate_by_name = True
