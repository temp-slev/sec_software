import pytest
from fastapi.testclient import TestClient

from src.main import app, items_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    items_db.clear()
    yield
    items_db.clear()


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello, QA!"}


@pytest.mark.parametrize(
    "item_data",
    [
        {"name": "Laptop", "price": 999.99},
        {"name": "Mouse", "price": 19.5},
        {"name": "Keyboard", "price": 49.0},
    ],
)
def test_create_item(item_data):
    response = client.post("/items/", json=item_data)
    assert response.status_code == 201
    assert response.json()["message"] == f"Item {item_data['name']} created"


def test_create_duplicate_item():
    item_data = {"name": "Laptop", "price": 999.99}
    client.post("/items/", json=item_data)
    response = client.post("/items/", json=item_data)
    assert response.status_code == 400
    assert response.json()["detail"] == "Item already exists"


def test_get_item():
    client.post("/items/", json={"name": "Laptop", "price": 999.99})
    response = client.get("/items/Laptop")
    assert response.status_code == 200
    assert response.json() == {"name": "Laptop", "price": 999.99}


def test_get_non_existent_item():
    response = client.get("/items/Nonexistent")
    assert response.status_code == 404
    assert response.json()["detail"] == "Item not found"


def test_get_all_items():
    client.post("/items/", json={"name": "Laptop", "price": 999.99})
    response = client.get("/items/")
    assert response.status_code == 200
    assert response.json() == [{"name": "Laptop", "price": 999.99}]


def test_delete_item():
    client.post("/items/", json={"name": "Laptop", "price": 999.99})
    response = client.delete("/items/Laptop")
    assert response.status_code == 200
    assert response.json()["message"] == "Item Laptop deleted"
    assert client.get("/items/Laptop").status_code == 404


def test_delete_non_existent_item():
    response = client.delete("/items/Nonexistent")
    assert response.status_code == 404
    assert response.json()["detail"] == "Item not found"
