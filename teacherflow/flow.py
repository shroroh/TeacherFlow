from pocketflow import Flow

from teacherflow.nodes import (
    AssessStudentLevel,
    PrioritizeSubjects,
    KnowledgeToDiscover,
    OralQuestionGenerator,
    SimulateOralAnswers,
    OralAssessment,
    FinalTeacherConclusion,
)

def create_teacher_flow():
    """Creates and returns the Teacher AI Agent flow."""

    assess_student = AssessStudentLevel(max_retries=3, wait=10)
    prioritize_subjects = PrioritizeSubjects(max_retries=3, wait=10)
    knowledge_to_discover = KnowledgeToDiscover(max_retries=3, wait=10)
    oral_q_gen = OralQuestionGenerator(max_retries=2, wait=2)
    oral_answers = SimulateOralAnswers(max_retries=2, wait=2)
    oral_assess = OralAssessment(max_retries=2, wait=2)
    final_conclusion = FinalTeacherConclusion()

    # Connect nodes
    assess_student >> prioritize_subjects
    prioritize_subjects >> knowledge_to_discover
    knowledge_to_discover >> oral_q_gen
    oral_q_gen >> oral_answers
    oral_answers >> oral_assess
    oral_assess >> final_conclusion
    

    # Create flow
    teacher_flow = Flow(start=assess_student)

    return teacher_flow
