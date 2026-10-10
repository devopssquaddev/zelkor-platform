from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session")
def kubeconfig() -> str:
    return os.environ.get("KUBECONFIG", "")


@pytest.fixture(scope="session")
def kubecontext() -> str:
    return os.environ.get("KUBECONTEXT", "k3s")
