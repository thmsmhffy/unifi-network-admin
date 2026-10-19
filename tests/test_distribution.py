from __future__ import annotations

import tarfile
from pathlib import Path
from zipfile import ZipFile

from build import ProjectBuilder

ROOT = Path(__file__).parents[1]


def test_wheel_contains_agent_skill_and_docs(tmp_path) -> None:
    builder = ProjectBuilder(ROOT)
    wheel = builder.build("wheel", str(tmp_path))

    with ZipFile(tmp_path / wheel) as archive:
        names = set(archive.namelist())

    assert any(
        name.endswith(
            "share/unifi-network-admin/skill/unifi-network-admin/SKILL.md"
        )
        for name in names
    )
    assert any(
        name.endswith("share/unifi-network-admin/docs/security.md")
        for name in names
    )

    assert any(
        name.endswith(
            "share/unifi-network-admin/skill/unifi-network-admin/agents/openai.yaml"
        )
        for name in names
    )
    assert any(
        name.endswith(
            "share/unifi-network-admin/skill/unifi-network-admin/references/safety.md"
        )
        for name in names
    )

    source = builder.build("sdist", str(tmp_path))
    with tarfile.open(tmp_path / source) as archive:
        source_names = set(archive.getnames())

    assert any(name.endswith("/skill/unifi-network-admin/SKILL.md") for name in source_names)
    assert any(name.endswith("/docs/security.md") for name in source_names)
