"""Entry point for TeacherFlow - generate personalized teacher feedback.

Usage:
    python main.py --student-id ivan123
    python -m teacherflow --student-id ivan123
"""

from teacherflow._cli import main


if __name__ == "__main__":
    main()
