from pathlib import Path

import pytest

from app.parser import parse_document

SAMPLE = """# Лимиты по карте

## Требования

* **Ф-1.** Клиент задаёт порог от 1 000 до 5 000 ₸.
* **Ф-2.** Система быстро отправляет push после покупки.

Сервис хранит сумму в тиынах
и порог в тенге.

## REST API

| Поле | Значение |
| :--- | :--- |
| **Description** | Сохранение порога |
| **REST type** | GET |
| **Request URL** | Dev: `/alerts/saveLimit` . Prod: — |

### Логика
1. Проверить сессию.
2. Заменить настройку.

```json
{"result":"ERROR","message":"Проверьте сумму"}
```
"""


@pytest.fixture
def sample_text():
    return SAMPLE


@pytest.fixture
def doc():
    return parse_document("sample.md", SAMPLE.encode())


@pytest.fixture
def organizer_doc():
    path = Path(__file__).parents[2] / "docs" / "requirements.md"
    if not path.exists():
        pytest.skip("выданный документ не входит в репозиторий")
    return parse_document("requirements.md", path.read_bytes())
