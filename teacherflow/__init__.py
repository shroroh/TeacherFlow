"""Top-level package for TeacherFlow.

Exports commonly used classes so users can import directly from
``teacherflow`` instead of submodules.
"""

from .db import Database
from .flow import create_teacher_flow
from .nodes import (
    AssessStudentLevel,
    PrioritizeSubjects,
    KnowledgeToDiscover,
    FinalTeacherConclusion,
)

__all__ = [
    "Database",
    "create_teacher_flow",
    "AssessStudentLevel",
    "PrioritizeSubjects",
    "KnowledgeToDiscover",
    "FinalTeacherConclusion",
]
