"""conftest.py — project-root pytest configuration.

Registers custom CLI options used across the RAG test suite.
Place this file at the project root (same level as tests/).
"""


def pytest_addoption(parser):
    parser.addoption(
        "--pdf-test2",
        default="test-2.pdf",
        help="Path to test-2.pdf (seaplane handbook)",
    )
    parser.addoption(
        "--pdf-test3",
        default="test-3.pdf",
        help="Path to test-3.pdf (sUAS study guide)",
    )
    parser.addoption(
        "--db-path",
        default="rag.db",
        help="Path to the SQLite RAG database (default: rag.db)",
    )