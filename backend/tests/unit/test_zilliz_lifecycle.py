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

    def create_collection(self, collection_name=None, schema=None):
        self.created_collections.append((collection_name, schema))

    def list_indexes(self, name):
        return list(self.created_indexes)

    def create_index(self, collection_name=None, index_params=None, timeout=None):
        self.created_indexes.append(collection_name)

    def load_collection(self, name):
        self.loaded_collections.append(name)

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
    monkeypatch.setattr("pymilvus.MilvusClient", lambda **kw: fake)
    monkeypatch.setattr(
        "pymilvus.utility.load_state",
        lambda *a, **kw: "Unloaded",
    )

    store = ZillizVectorStore("uri", "token", "wf_docs", dimension=8)
    assert store._client is fake
    assert fake.created_collections and fake.created_collections[0][0] == "wf_docs"
    assert "wf_docs" in fake.created_indexes
    assert "wf_docs" in fake.loaded_collections


def test_existing_collection_skips_schema_but_ensures_index_and_load(monkeypatch):
    fake = _FakeMilvusClient(has_collection=True)
    monkeypatch.setattr("pymilvus.MilvusClient", lambda **kw: fake)

    store = ZillizVectorStore("uri", "token", "wf_docs", dimension=8)
    assert store._client is fake
    assert not fake.created_collections
    assert "wf_docs" in fake.created_indexes
    assert "wf_docs" in fake.loaded_collections
    assert store.collection_name == "wf_docs"