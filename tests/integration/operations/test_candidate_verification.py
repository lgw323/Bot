import io
import zipfile

import pytest

from .test_production_tools import tool


@pytest.mark.parametrize("name", ["../escape.py", ".env", "src/actual.db", "data/private.txt"])
def test_candidate_source_archive_rejects_out_of_scope_files(name):
    verifier = tool("production/verify_candidate.py")
    with zipfile.ZipFile(io.BytesIO(), "w") as archive:
        archive.comment = b"a" * 40
        archive.writestr(name, "synthetic")
        with pytest.raises(ValueError):
            verifier.safe_archive(archive, "a" * 40)


def test_candidate_source_archive_requires_exact_revision():
    verifier = tool("production/verify_candidate.py")
    with zipfile.ZipFile(io.BytesIO(), "w") as archive:
        archive.comment = b"a" * 40
        archive.writestr("src/discordbot/synthetic.py", "synthetic")
        verifier.safe_archive(archive, "a" * 40)
        with pytest.raises(ValueError):
            verifier.safe_archive(archive, "b" * 40)
