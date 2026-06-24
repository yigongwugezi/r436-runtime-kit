from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    session_id: str = Field(default="")
    course_id: str = Field(default="ai_intro")
    user_message: str = Field(default="我想学习人工智能导论")
