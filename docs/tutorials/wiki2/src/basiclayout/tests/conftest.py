import alembic
import alembic.config
import alembic.command
import os
from pyramid.paster import get_appsettings
from pyramid.testing import DummyRequest, testConfig
import pytest
import transaction
from webob.cookies import Cookie
import webtest

from tutorial import main
from tutorial import models
from tutorial.models.meta import Base


def pytest_addoption(parser):
    parser.addoption('--ini', action='store', metavar='INI_FILE')

@pytest.fixture(scope='session')
def ini_file(request):
    # potentially grab this path from a pytest option
    return os.path.abspath(request.config.option.ini or 'testing.ini')

@pytest.fixture(scope='session')
def app_settings(ini_file):
    return get_appsettings(ini_file)

@pytest.fixture(scope='session')
def dbengine(app_settings, ini_file):
    engine = models.get_engine(app_settings)

    alembic_cfg = alembic.config.Config(ini_file)
    Base.metadata.drop_all(bind=engine)
    alembic.command.stamp(alembic_cfg, None, purge=True)

    # run migrations to initialize the database
    # depending on how we want to initialize the database from scratch
    # we could alternatively call:
    # Base.metadata.create_all(bind=engine)
    # alembic.command.stamp(alembic_cfg, "head")
    alembic.command.upgrade(alembic_cfg, "head")

    yield engine

    Base.metadata.drop_all(bind=engine)
    alembic.command.stamp(alembic_cfg, None, purge=True)

@pytest.fixture(scope='session')
def app(app_settings, dbengine):
    return main({}, dbengine=dbengine, **app_settings)

@pytest.fixture
def tm():
    tm = transaction.TransactionManager(explicit=True)
    tm.begin()
    tm.doom()

    yield tm

    tm.abort()

@pytest.fixture
def dbsession(app, tm):
    session_factory = app.registry['dbsession_factory']
    return models.get_tm_session(session_factory, tm)

@pytest.fixture
def testapp(app, tm, dbsession):
    # override request.dbsession and request.tm with our own
    # externally-controlled values that are shared across requests but aborted
    # at the end
    testapp = webtest.TestApp(app, extra_environ={
        'HTTP_HOST': 'example.com',
        'tm.active': True,
        'tm.manager': tm,
        'app.dbsession': dbsession,
    })

    return testapp

@pytest.fixture
def dummy_request(tm, dbsession):
    """
    A lightweight dummy request.

    This request is ultra-lightweight and should be used only when the
    request itself is not a large focus in the call-stack.

    It is way easier to mock and control side-effects using this object.

    - It does not have request extensions applied.
    - Threadlocals are not properly pushed.

    """
    request = DummyRequest()
    request.host = 'example.com'
    request.dbsession = dbsession
    request.tm = tm

    return request

@pytest.yield_fixture
def dummy_config(dummy_request):
    with testConfig(request=dummy_request) as config:
        yield config
