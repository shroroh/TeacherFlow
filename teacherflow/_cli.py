import dotenv
import os
from pathlib import Path
import argparse
from teacherflow.db import Database
from teacherflow.flow import create_teacher_flow

# Load variables from `.var` (project-specific) if it exists, then fallback to default `.env`.
var_path = Path(".var")
if var_path.exists():
    dotenv.load_dotenv(dotenv_path=str(var_path), override=False)
# Also load default .env (won't override existing variables)
dotenv.load_dotenv(override=False)


def main():
    parser = argparse.ArgumentParser(
        description="Generate personalized teacher feedback for a student."
    )

    parser.add_argument(
        "--student-id",
        required=True,
        help="Student ID in the database (e.g. student_001)"
    )

    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable LLM response caching (default: enabled)"
    )

    parser.add_argument(
        "--max-subjects",
        type=int,
        default=10,
        help="Maximum number of subjects to assess"
    )

    parser.add_argument(
        "--max-topics",
        type=int,
        default=10,
        help="Maximum number of learning topics to generate"
    )

    parser.add_argument(
        "--course",
        type=str,
        help="University course/year (e.g. '2' or '1st'). Optional"
    )
    parser.add_argument(
        "--major",
        type=str,
        help="Study field / major of the student. Optional"
    )
    parser.add_argument(
        "--no-oral",
        action="store_true",
        help="Disable generation of oral Q&A and assessment"
    )

    args = parser.parse_args()

    # Load student data
    db = Database()
    student_data = db.get(args.student_id)

    if not student_data:
        raise ValueError(f"Student '{args.student_id}' not found in database")

    # allow command-line overrides
    if args.course:
        student_data["Course"] = args.course
    if args.major:
        student_data["Major"] = args.major

    # Shared state for PocketFlow
    shared = {
        "student_data": student_data,
        "use_cache": not args.no_cache,
        "max_subjects": args.max_subjects,
        "max_topics": args.max_topics,
        "no_oral": args.no_oral,
    }

    print(f"🎓 Generating teacher feedback for: {student_data.get('Full Name')}")
    print(f"LLM caching: {'Disabled' if args.no_cache else 'Enabled'}")

    # Create and run flow
    teacher_flow = create_teacher_flow()
    teacher_flow.run(shared)

    # Output result
    print("\n" + "=" * 60)
    print(shared["teacher_conclusion"])
    print("=" * 60)


if __name__ == "__main__":
    main()
