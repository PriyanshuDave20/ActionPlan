"""Unit tests for ZillizVectorStore lifecycle (schema, index, load).

Uses a fake client so no Zilliz connection is made. Covers the regression:
a freshly created collection needs a vector index and a load before search.
"""

from app.rag.zilliz import ZillizVectorStore


class _FakeMilvusClient:
    def __init__(self, *, has_collection=False):
        self._has_collection = has_collection
        self.created_collections = []
        self.created_indexes = []
        self.loaded_collections = []
        self.searched = []

    def has_collection(self, name):
        return self._has_collection

    def list_databases(self):
        return ["default"]

    def create_collection(self, collection_name=None, schema=None):
        self.created_collections.append((collection_name, schema))

    def list_indexes(self, name):
        return list(self.created_indexes)

    def prepare_index_params(self):
        class Params:
            def add_index(self, **kwargs):
                self.kwargs = kwargs

        return Params()

    def create_index(self, collection_name=None, index_params=None, timeout=None):
        self.created_indexes.append(collection_name)

    def load_collection(self, name):
        self.loaded_collections.append(name)

    def get_load_state(self, name):
        return {"state": "Unloaded"}

    def insert(self, collection_name, data):
        return []

    def search(self, **kwargs):
        self.searched.append(kwargs)
        return []


class _FakeUtility:
    def __init__(self, state="Unloaded"):
        self._state = state

    def load_state(self, collection_name, using=None):
        return self._state


def test_new_collection_gets_index_and_load(monkeypatch):
    fake = _FakeMilvusClient()
    client_kwargs = {}

    def make_client(**kwargs):
        client_kwargs.update(kwargs)
        return fake

    monkeypatch.setattr("pymilvus.MilvusClient", make_client)
    store = ZillizVectorStore("uri", "token", "wf_docs", dimension=8)
    assert store._client is fake
    assert client_kwargs["db_name"] == "default"
    assert fake.created_collections and fake.created_collections[0][0] == "wf_docs"
    assert "wf_docs" in fake.created_indexes
    assert "wf_docs" in fake.loaded_collections


def test_existing_collection_skips_schema_but_ensures_index_and_load(monkeypatch):
    fake = _FakeMilvusClient(has_collection=True)
    client_kwargs = {}

    def make_client(**kwargs):
        client_kwargs.update(kwargs)
        return fake

    monkeypatch.setattr("pymilvus.MilvusClient", make_client)

    store = ZillizVectorStore(
        "uri", "token", "wf_docs", database_name="db_project", dimension=8
    )
    assert store._client is fake
    assert client_kwargs["db_name"] == "db_project"
    assert store.database_name == "db_project"
    assert not fake.created_collections
    assert "wf_docs" in fake.created_indexes
    assert "wf_docs" in fake.loaded_collections
    assert store.collection_name == "wf_docs"


def test_finds_existing_collection_in_named_database_before_creating(monkeypatch):
    clients = {}

    class DatabaseClient(_FakeMilvusClient):
        def __init__(self, db_name):
            super().__init__(has_collection=db_name == "db_project")
            self.db_name = db_name

        def list_databases(self):
            return ["default", "db_project"]

    def make_client(*, uri, token, db_name):
        clients[db_name] = DatabaseClient(db_name)
        return clients[db_name]

    monkeypatch.setattr("pymilvus.MilvusClient", make_client)
    store = ZillizVectorStore("uri", "token", "wf_docs", dimension=8)

    assert store.database_name == "db_project"
    assert store._client is clients["db_project"]
    assert not clients["db_project"].created_collections
    assert "wf_docs" in clients["db_project"].loaded_collections
