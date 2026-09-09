from pydantic import BaseModel, ConfigDict


class UserContext(BaseModel):
    user_id: str = "demo-user"
    display_name: str = "演示用户"


class AnswerRequest(BaseModel):
    question_id: str
    selected_department_id: str


class ImportOption(BaseModel):
    department_code: str
    department_name: str


class ImportQuestion(BaseModel):
    source_case_id: str
    case_origin: str | None = None
    question_type: str
    level: int | None = None
    case_content: str
    correct_department_code: str
    correct_department_name: str
    wrong_options: list[ImportOption]
    explanation: str
    reference_basis: str
    reference_basis_title: str | None = None
    reference_basis_source: str | None = None
    reference_basis_excerpt: str | None = None
    reference_basis_locator: str | None = None
    reference_basis_reason: str | None = None
    difficulty_score: int | None = None
    difficulty_dimension_1: int | None = None
    difficulty_dimension_1_reason: str | None = None
    difficulty_dimension_2: int | None = None
    difficulty_dimension_2_reason: str | None = None
    difficulty_dimension_3: int | None = None
    difficulty_dimension_3_reason: str | None = None
    difficulty_dimension_4: int | None = None
    difficulty_dimension_4_reason: str | None = None
    difficulty_dimension_5: int | None = None
    difficulty_dimension_5_reason: str | None = None
    review_status: str = "pending"
    review_note: str | None = None
    reference_basis_status: str = "needs_review"
    enabled: bool = True
    final_selection: bool = False


class ImportPayload(BaseModel):
    questions: list[ImportQuestion]
    replace: bool = False
