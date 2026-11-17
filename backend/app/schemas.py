from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    created_at: datetime


class StudentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=255)


class SubjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    name: str
    description: str | None = None
    topic_count: int = 0


class TopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_id: int | None = None
    source: str
    name: str
    description: str | None = None
    difficulty: float


class TopicCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    difficulty: float = Field(default=0.5, ge=0.0, le=1.0)
    # Subject key, name or id. Defaults to Computer Science for compatibility
    # with the original single-subject API.
    subject: str | int = "computer-science"


class StudyRecordCreate(BaseModel):
    student_id: int
    topic_id: int
    duration_minutes: int = Field(ge=1, le=1440)
    studied_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=1000)


class StudyRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    topic_id: int
    duration_minutes: int
    studied_at: datetime
    notes: str | None = None


class QuizResultCreate(BaseModel):
    student_id: int
    topic_id: int
    correct_answers: int = Field(ge=0)
    total_questions: int = Field(ge=1, le=200)
    attempted_at: datetime | None = None

    @model_validator(mode="after")
    def validate_score(self) -> "QuizResultCreate":
        if self.correct_answers > self.total_questions:
            raise ValueError("correct_answers cannot exceed total_questions")
        return self


class QuizAttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    topic_id: int
    correct_answers: int
    total_questions: int
    score: float
    attempted_at: datetime


class QuizResultOut(BaseModel):
    attempt: QuizAttemptOut
    mastery: float


class MasteryOut(BaseModel):
    topic_id: int
    topic_name: str
    subject_id: int | None = None
    difficulty: float
    mastery: float
    attempts: int
    last_attempt_at: datetime | None = None


class ProgressOut(BaseModel):
    student: StudentOut
    subject_id: int | None = None
    overall_mastery: float
    total_study_minutes: int
    total_attempts: int
    topics: list[MasteryOut]


class MasteryHistoryPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    topic_id: int
    mastery: float
    source: str
    created_at: datetime


class RecommendationOut(BaseModel):
    topic_id: int
    topic_name: str
    subject_id: int | None = None
    score: float
    mastery: float
    reason: str
    contributions: dict[str, float]


class StudyPlanOut(BaseModel):
    plan: str
    source: Literal["llm", "fallback"]
    generated_at: datetime


class FlashcardCreate(BaseModel):
    student_id: int
    topic_id: int
    question: str = Field(min_length=3, max_length=2000)
    answer: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def normalise_text(self) -> "FlashcardCreate":
        self.question = self.question.strip()
        self.answer = self.answer.strip()
        if len(self.question) < 3:
            raise ValueError("question must contain at least 3 non-space characters")
        if not self.answer:
            raise ValueError("answer cannot be blank")
        return self


class FlashcardGenerateRequest(BaseModel):
    topic_id: int
    count: int = Field(default=5, ge=1, le=10)


class FlashcardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    topic_id: int
    question: str
    answer: str
    source: str
    created_at: datetime


class FlashcardBatchOut(BaseModel):
    flashcards: list[FlashcardOut]
    source: Literal["llm", "fallback"]
