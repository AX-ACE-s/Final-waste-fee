"""기능② 테스트 공용 픽스처. (기능③ 테스트는 각 파일 안에서 자체 픽스처를 쓴다)

con/rid : 공공데이터포털 미리보기 발췌본(4개 지자체 363행)으로 만든 작은 DB — 결과가 고정되어 테스트가 안정적
client  : 통합 Flask 앱 테스트 클라이언트(② 라우트가 위 DB를 보도록 연결)
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.spec_conftest_helpers import RAW  # noqa: E402


@pytest.fixture(scope="session")
def db_path(tmp_path_factory):
    from etl.build_db import build
    p = tmp_path_factory.mktemp("db") / "test.db"
    build(p, [RAW])
    return p


@pytest.fixture(scope="session")
def con(db_path):
    from spec_question.db import connect
    return connect(db_path)


@pytest.fixture(scope="session")
def rid(con):
    return {r["sigungu"]: r["id"] for r in con.execute("SELECT id, sigungu FROM region")}


@pytest.fixture()
def client(con):
    import app as flask_app
    from spec_question import routes
    routes.set_connection(con)
    yield flask_app.app.test_client()
    routes.set_connection(None)
