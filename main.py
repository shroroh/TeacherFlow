"""Entry point kept at project root for backward compatibility.
Delegates to the package implementation in :mod:`teacherflow.main`.
"""

from teacherflow.main import main


if __name__ == "__main__":
    main()
