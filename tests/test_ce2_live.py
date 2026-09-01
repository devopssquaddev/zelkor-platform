"""Live CE-2 packager path. Skip unless ZELKOR_CE2_LIVE=1 (cluster + CLI image)."""
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("ZELKOR_CE2_LIVE", "") != "1",
    reason="ZELKOR_CE2_LIVE=1 required",
)


def test_ce2_init_deploy_run_body_graph_id_only():
    """See internal/dev/validate-ce2.sh: init → deploy → run with body graph_id only."""
    pytest.skip("exercised by internal/dev/validate-ce2.sh")
