"""Drift tests for .github/workflows/ — the gates that run unattended.

Every other check in this repo is something a human or agent chose to run.
These workflows are the only ones that fire on their own, so the conditions
that make them meaningful have to be asserted somewhere that fails loudly.

The first thing asserted is that each gate still *does* something: a `test`
job that installs dependencies and stops would satisfy every other check in
this file, and "present in form, doing nothing" is precisely what #27 was
filed about. The rest are conditions a reader cannot see in the YAML:

* **The test database must be named with a ``_test`` suffix.** ``db_safety``
  matches the suffix, not a substring, and ``get_database_url()`` is the
  chokepoint every connection crosses. A service container named ``notifier``
  fails the whole suite at fixture setup with what reads like a security
  refusal rather than the config typo it is.
* **The migrations job needs its own database.** ``tests/conftest.py`` builds
  schema with ``Base.metadata.create_all``; pointing ``alembic upgrade head``
  at a database pytest has touched fails on "relation already exists".
* **The interpreter must be pinned.** ``[tool.coverage.run] core = "sysmon"``
  falls back silently on CPython < 3.12 and reports ~6 points low against a
  live ``fail_under = 80`` (issue #27).
* **Dependencies must install from the lockfile.** ``coverage`` is pinned
  nowhere in ``pyproject.toml`` but sysmon needs >= 7.10, so an unlocked
  resolve can change what the coverage gate measures.
* **The test job must check out full history and tags.**
  ``actions/checkout`` defaults to ``fetch-depth: 1``, which fetches
  neither. ``test_release_tags.py`` would then find no tag, find no
  ``HEAD~1`` to compare against, and report green — a gate that has
  silently stopped being one (#50).
"""

import re
import shlex
import tomllib
from pathlib import Path

import pytest
import yaml

from tests.ci.test_dependencies import TABLES

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"
STALENESS = WORKFLOWS / "sdk-staleness.yml"
AUDIT = WORKFLOWS / "audit.yml"

# PyYAML resolves a bare `on:` key to the boolean True (the YAML 1.1 "Norway
# problem"). GitHub Actions means the string. Look up both rather than
# quoting the key in the workflow, which would be unidiomatic there.
ON = True


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def triggers(doc: dict) -> dict:
    return doc.get(ON, doc.get("on"))


def steps(job: dict) -> list[dict]:
    return job.get("steps", [])


def run_lines(job: dict) -> str:
    return "\n".join(step.get("run", "") for step in steps(job))


def run_tokens(job: dict) -> list[str]:
    """Every run line split into shell words.

    Token-level, not substring: `"-m" in run_lines(job)` also matches
    `--no-modify-path` and would fail a step about something else entirely
    with a message about marker expressions.
    """
    return [token for step in steps(job) for token in shlex.split(step.get("run", ""))]


def postgres(job: dict) -> dict:
    return job["services"]["postgres"]


def service_env(job: dict) -> dict:
    return postgres(job)["env"]


@pytest.fixture(scope="module")
def ci() -> dict:
    return load(CI)


@pytest.fixture(scope="module")
def staleness() -> dict:
    return load(STALENESS)


@pytest.fixture(scope="module")
def audit() -> dict:
    return load(AUDIT) if AUDIT.is_file() else {}


def test_ci_workflow_exists():
    assert CI.is_file(), "the repo's only automated correctness gate"


def test_ci_fires_on_push_to_main(ci):
    """The trigger that matters: this repo commits straight to main.

    A pull_request-only gate is vacuous here — that is the whole of #27.
    """
    assert "main" in triggers(ci)["push"]["branches"]


def test_ci_also_covers_pull_requests_and_manual_runs(ci):
    on = triggers(ci)
    assert "main" in on["pull_request"]["branches"]
    assert "workflow_dispatch" in on


def test_ci_never_cancels_a_run_on_main(ci):
    """Superseding a PR run is free; superseding main's loses that commit's
    only signal, and on this VM main is what is deployed."""
    concurrency = ci["concurrency"]
    assert "github.event_name == 'pull_request'" in str(concurrency["cancel-in-progress"])
    assert "github.head_ref || github.ref" in concurrency["group"]


def test_ci_takes_read_only_permissions(ci):
    assert ci["permissions"] == {"contents": "read"}


def test_ci_runs_lint_test_and_migrations(ci):
    assert {"lint", "test", "migrations"} <= set(ci["jobs"])


def test_lint_names_its_own_failure(ci):
    """Separate steps, so a red run says whether it was style or format."""
    runs = [step["run"] for step in steps(ci["jobs"]["lint"]) if "ruff" in step.get("run", "")]
    assert "uv run ruff check ." in runs
    assert "uv run ruff format --check ." in runs


def test_test_job_database_carries_the_non_production_suffix(ci):
    """`db_safety` matches the suffix; any other name fails all 240 tests."""
    name = service_env(ci["jobs"]["test"])["POSTGRES_DB"]
    assert name.endswith("_test"), (
        f"{name!r} reads as production to src/core/db_safety.py, which every "
        f"connection path crosses"
    )


def test_test_job_passes_that_database_as_test_database_url(ci):
    job = ci["jobs"]["test"]
    assert service_env(job)["POSTGRES_DB"] in job["env"]["TEST_DATABASE_URL"]


def test_test_job_actually_runs_the_suite(ci):
    """The absence checks below say what the step must not carry. This one
    says the step exists at all.

    Without it the whole file is satisfiable by a `test` job that installs
    dependencies and stops — present in form, doing nothing, which is the
    exact failure #27 was filed about.
    """
    assert "uv run pytest" in run_lines(ci["jobs"]["test"])


def test_test_job_does_not_restate_the_marker_expression(ci):
    """`-m 'not integration'` is already in addopts. A second spelling on the
    command line overrides rather than composes, and can drift."""
    assert "-m" not in run_tokens(ci["jobs"]["test"])


def test_migrations_job_uses_a_database_pytest_never_touches(ci):
    """conftest's create_all would leave tables behind and break upgrade head."""
    test_db = service_env(ci["jobs"]["test"])["POSTGRES_DB"]
    migrations_db = service_env(ci["jobs"]["migrations"])["POSTGRES_DB"]
    assert migrations_db != test_db


def test_migrations_job_builds_from_scratch_and_checks_for_drift(ci):
    """The one gate the suite structurally cannot be: conftest builds schema
    with create_all, so a broken migration chain surfaces only on deploy."""
    runs = run_lines(ci["jobs"]["migrations"])
    assert "alembic upgrade head" in runs
    assert "alembic check" in runs


def test_no_job_carries_the_production_opt_in(ci):
    """alembic is exempt from the guard by design (src/core/db_safety.py), so
    the migrations job needs no escape hatch — and nothing else may grow one.

    Checked against the parsed workflow, not the raw text: ci.yml explains in
    a comment why the flag is absent, and matching raw text would make that
    comment fail the test it documents.
    """
    from src.core import db_safety

    flag = db_safety.ALLOW_PROD_ENV_VAR
    assert flag not in ci.get("env", {})
    for name, job in ci["jobs"].items():
        assert flag not in job.get("env", {}), name
        for step in steps(job):
            assert flag not in step.get("env", {}), name
            assert flag not in step.get("run", ""), name


@pytest.mark.parametrize("workflow", [CI, STALENESS, AUDIT], ids=["ci", "staleness", "audit"])
def test_every_workflow_pins_the_interpreter(workflow):
    """sysmon falls back silently below 3.12 and reports ~6 points low."""
    doc = load(workflow)
    for name, job in doc["jobs"].items():
        pinned = [
            step
            for step in steps(job)
            if "setup-uv" in step.get("uses", "") and step.get("with", {}).get("python-version")
        ]
        assert pinned, f"{workflow.name}:{name} does not pin python-version"


@pytest.mark.parametrize("workflow", [CI, STALENESS], ids=["ci", "staleness"])
def test_every_job_installs_from_the_lockfile(workflow):
    """`coverage` is pinned nowhere in pyproject but sysmon needs >= 7.10, so
    an unlocked resolve can change what the coverage gate measures.

    Walks parsed steps rather than grepping the file: raw text waves through
    `uv sync --no-dev`, misses a trailing `uv sync` with no newline after it,
    and cannot tell that *every* job installs this way.
    """
    for name, job in load(workflow)["jobs"].items():
        syncs = [
            shlex.split(step["run"])
            for step in steps(job)
            if step.get("run", "").startswith("uv sync")
        ]
        assert syncs, f"{workflow.name}:{name} installs nothing"
        for tokens in syncs:
            assert "--locked" in tokens, f"{workflow.name}:{name} runs {' '.join(tokens)}"


def test_staleness_check_can_actually_fire(staleness):
    """It has never run once: a pull_request-only trigger on a repo that
    commits to main (#27)."""
    assert "main" in triggers(staleness)["push"]["branches"]


def test_staleness_check_covers_hand_written_sdk_code(staleness):
    """clients/python/src/notifier_client/ holds 12 hand-written modules and
    ~14 unit test files. Under the original filter an SDK-only change got no
    CI at all — the generated/ paths are not the only ones that can break."""
    paths = triggers(staleness)["push"]["paths"]
    assert any(p.startswith("clients/python/") and "scripts" not in p for p in paths)


def test_staleness_check_fires_on_a_service_dependency_bump(staleness):
    """fastapi and pydantic shape /openapi.json as surely as src/api/ does.
    Filtered out, a bump that changes the schema passes its own PR and fails
    the next unrelated src/api push instead (#103)."""
    paths = triggers(staleness)["push"]["paths"]
    assert {"pyproject.toml", "uv.lock"} <= set(paths)


def test_staleness_check_filters_push_and_pull_request_identically(staleness):
    """The two lists are duplicated because the Actions parser does not expand
    YAML aliases. Nothing but this test keeps them in step, and a drifted
    filter means pushes and PRs gate on different paths."""
    on = triggers(staleness)
    assert on["push"]["paths"] == on["pull_request"]["paths"]


def test_staleness_check_takes_read_only_permissions(staleness):
    assert staleness["permissions"] == {"contents": "read"}


@pytest.mark.parametrize("workflow", [CI, STALENESS, AUDIT], ids=["ci", "staleness", "audit"])
def test_every_job_bounds_its_own_runtime(workflow):
    """GitHub's default is 360 minutes. A wedged `uv sync` or a postgres that
    never comes up would burn six hours before anyone noticed; these runs
    finish in under a minute."""
    for name, job in load(workflow)["jobs"].items():
        assert job.get("timeout-minutes"), f"{workflow.name}:{name} has no timeout"


@pytest.mark.parametrize("job_name", ["test", "migrations"], ids=["test", "migrations"])
def test_database_services_are_waited_for(ci, job_name):
    """Without a health check the job races container startup, and the failure
    surfaces as an intermittent red — the hardest kind to attribute."""
    assert "pg_isready" in postgres(ci["jobs"][job_name])["options"]


def test_test_job_checks_out_full_history_and_tags(ci):
    """`tests/ci/test_release_tags.py` needs tags and history to mean anything.

    actions/checkout defaults to `fetch-depth: 1`, which fetches no tags and no
    parent commit. Under that default the tag gate finds no tag, finds no
    `HEAD~1` to compare against, and reports green — a gate that has quietly
    stopped being one, with nothing in the log to notice. The test itself
    refuses a shallow checkout rather than passing vacuously; this asserts the
    workflow keeps handing it a checkout it can accept.
    """
    checkouts = [
        step
        for step in steps(ci["jobs"]["test"])
        if str(step.get("uses", "")).startswith("actions/checkout")
    ]
    assert checkouts, "the test job has no actions/checkout step"
    assert all(step.get("with", {}).get("fetch-depth") == 0 for step in checkouts), (
        "the test job must check out with fetch-depth: 0 — tests/ci/test_release_tags.py "
        "needs full history and tags to distinguish an untagged release from a shallow clone"
    )


def audit_directories(doc: dict) -> set[str]:
    """The tables the audit matrix covers, in `working-directory` form."""
    return set(doc["jobs"]["audit"]["strategy"]["matrix"]["directory"])


def audit_steps(doc: dict) -> list[list[str]]:
    """Every `uv audit` step in the audit job, split into shell words."""
    return [
        shlex.split(step["run"])
        for step in steps(doc["jobs"]["audit"])
        if step.get("run", "").startswith("uv audit")
    ]


def test_audit_workflow_exists():
    """Nothing else checks the lock against advisories. Dependabot's version
    updates cover direct dependencies only; starlette 1.0.0 sat in the lock
    with five open advisories, invisible to every gate (#103)."""
    assert AUDIT.is_file(), "no .github/workflows/audit.yml — the lock is never audited"


def test_audit_fires_on_a_schedule_as_well_as_on_change(audit):
    """Advisories publish independently of commits. A gate that only runs on
    push reports a new one on whichever unrelated commit lands next — or, on
    a quiet repo, never."""
    on = triggers(audit)
    assert "main" in on["push"]["branches"]
    assert "main" in on["pull_request"]["branches"]
    assert on["schedule"] and all(entry.get("cron") for entry in on["schedule"])
    assert "workflow_dispatch" in on


def test_audit_covers_every_dependency_table(audit):
    """Derived from TABLES, so a table added there without an audit fails
    here. The SDK's lock is what its own CI and tests install."""
    expected = {
        "." if path.parent == REPO_ROOT else path.parent.relative_to(REPO_ROOT).as_posix()
        for path in TABLES.values()
    }
    assert audit_directories(audit) == expected


def test_audit_runs_in_each_matrix_directory(audit):
    """A matrix whose step ignores `matrix.directory` audits the root twice."""
    runs = [step for step in steps(audit["jobs"]["audit"]) if "uv audit" in step.get("run", "")]
    assert runs and all(step.get("working-directory") == "${{ matrix.directory }}" for step in runs)


def test_one_table_failing_does_not_cancel_the_other(audit):
    """fail-fast would cancel the SDK's audit the moment the service's goes
    red, and the run would report one table's advisories instead of both."""
    assert audit["jobs"]["audit"]["strategy"]["fail-fast"] is False


def test_audit_reads_the_committed_lock(audit):
    """`--locked` audits what is deployed. Without it uv re-resolves first and
    can audit a lock nobody committed — a green run about the wrong versions."""
    commands = audit_steps(audit)
    assert commands, "the audit job never runs `uv audit`"
    assert all("--locked" in tokens for tokens in commands)


def test_audit_does_not_exclude_the_dev_group(audit):
    """Dev tools run on this VM and in CI. virtualenv (via pre-commit) carried
    eight advisories in the first audit (#103); excluding the group hides them."""
    excluding = {"--no-dev", "--no-default-groups", "--only-dev", "--only-group", "--no-group"}
    for tokens in audit_steps(audit):
        assert not excluding & set(tokens), " ".join(tokens)


def test_audit_takes_read_only_permissions(audit):
    assert audit["permissions"] == {"contents": "read"}


CANARY_STEP_PATTERN = "uv audit --script"


def canary_steps(doc: dict) -> list[dict]:
    """The canary job's `uv audit --script` steps."""
    return [
        step
        for step in steps(doc["jobs"].get("canary", {}))
        if CANARY_STEP_PATTERN in step.get("run", "")
    ]


def canary_script(doc: dict) -> Path:
    """The PEP 723 script the canary audits, as the workflow names it."""
    for step in canary_steps(doc):
        for line in step["run"].splitlines():
            words = shlex.split(line)
            if words[:3] == ["uv", "audit", "--script"]:
                return REPO_ROOT / words[3]
    raise AssertionError(f"no `{CANARY_STEP_PATTERN} <path>` line in the canary job")


def test_audit_has_a_canary_proving_it_can_still_fail(audit):
    """`uv audit` is a preview feature on an unpinned uv. A release that
    changed its exit status, or an OSV lookup failing quietly, would leave
    every run green — a gate that has stopped being one with nothing in the
    log to say so (#27, #50). The canary audits a pin with known advisories
    and must see them (CR 1, #103)."""
    assert canary_steps(audit), "no canary job running `uv audit --script`"


def test_canary_passes_only_on_exit_status_one(audit):
    """uv audit exits 1 on findings and 2 on a service or resolution error.
    A canary satisfied by any non-zero status would read an OSV outage as
    the gate working."""
    runs = "\n".join(step["run"] for step in canary_steps(audit))
    assert '"$rc" -eq 1' in runs


def test_canary_script_pins_a_version_with_known_advisories(audit):
    """An unpinned canary resolves to the latest release, which is exactly
    the version expected to be clean."""
    script = canary_script(audit)
    assert script.is_file(), f"{script} is missing"
    block = re.search(r"^# /// script\n(.*?)^# ///$", script.read_text(), re.S | re.M)
    assert block, f"{script.name} carries no PEP 723 metadata block"
    metadata = tomllib.loads(
        "\n".join(line.removeprefix("#").removeprefix(" ") for line in block[1].splitlines())
    )
    assert metadata["dependencies"] and all("==" in dep for dep in metadata["dependencies"])
