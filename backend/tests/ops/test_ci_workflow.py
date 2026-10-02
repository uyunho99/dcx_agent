from pathlib import Path

import pytest
import yaml


WORKFLOW = Path(__file__).resolve().parents[3] / ".github/workflows/ci.yml"


@pytest.fixture
def workflow():
    # BaseLoader preserves GitHub's `on` key rather than treating it as a bool.
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


def test_triggers(workflow):
    assert workflow["on"]["pull_request"]["branches"] == ["main"]
    assert workflow["on"]["push"]["branches"] == ["main"]


def test_permissions_read_only(workflow):
    assert workflow["permissions"] == {"contents": "read"}
    assert "secrets." not in WORKFLOW.read_text()


def test_backend_job(workflow):
    job = workflow["jobs"]["backend"]
    assert job["runs-on"] == "ubuntu-latest"
    setup = next(s for s in job["steps"] if s.get("uses", "").startswith("actions/setup-python@"))
    assert setup["with"]["python-version"] == "3.12"
    commands = [s["run"] for s in job["steps"] if "run" in s]
    install = next(c for c in commands if "pip install -r backend/requirements.txt -r backend/requirements-dev.txt" in c)
    assert "-c backend/constraints.txt" in install
    assert "python -m pytest backend/tests -q -p no:cacheprovider" in commands


def test_frontend_job(workflow):
    job = workflow["jobs"]["frontend"]
    assert job["runs-on"] == "ubuntu-latest"
    setup = next(s for s in job["steps"] if s.get("uses", "").startswith("actions/setup-node@"))
    assert setup["with"]["node-version"] == "26"
    commands = [s["run"] for s in job["steps"] if "run" in s]
    assert commands == [
        "npm ci --prefix frontend",
        "npm --prefix frontend run lint",
        "npm --prefix frontend test",
        "npm --prefix frontend run build",
    ]


def test_concurrency(workflow):
    assert "github.ref" in workflow["concurrency"]["group"]
    assert workflow["concurrency"]["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"
