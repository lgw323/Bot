import pytest_asyncio

from characterization.summary_support import harness


@pytest_asyncio.fixture
async def summary():
    fixture = harness()
    try:
        yield fixture
    finally:
        await fixture.service.stop()
