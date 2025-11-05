---
name: coding-standards
description: Use this skill when writing, reviewing, or refactoring Python/Django or JavaScript code. Enforces team coding standards including model conventions, API design, testing practices, function structure, and code formatting.
---

# Coding Standards Enforcer

## Purpose
Automatically apply and enforce team coding standards when writing or reviewing code. This skill ensures consistency across the codebase for Python/Django and JavaScript projects.

## When to Use
- Writing new Python/Django models, views, serializers, or API endpoints
- Creating or modifying JavaScript code
- Reviewing code for style compliance
- Refactoring existing code
- Creating tests
- Writing async tasks or migrations

## Instructions

### Python/Django Standards

#### 1. Models
- **ALWAYS include timestamp fields:**
  ```python
  created = models.DateTimeField(auto_now_add=True)
  modified = models.DateTimeField(auto_now=True)
  ```

- **Use BigInt IDs for scalable tables:**
  ```python
  id = models.BigAutoField(primary_key=True)
  ```
  Apply to any table that could exceed 2B records.

- **Use TimescaleDB for time-series data** when old data access becomes rare and deletion is needed.

- **Explicit field updates to prevent race conditions:**
  ```python
  # GOOD
  token.save(update_fields=["valid_until", "rejected_at"])

  # BAD
  token.save()  # Updates all fields
  ```

#### 2. Comparisons
- Use `is` or `is not` for None comparisons:
  ```python
  if value is None:  # GOOD
  if value == None:  # BAD
  ```

#### 3. Architecture Patterns
- **Thin views, fat models** - business logic belongs in models/helpers
- **Data validation in serializers** - not in views or models
- **Views** - only forward data to serializers, trigger logic functions, handle HTTP responses
- **Serializers** - convert data and store it, call business logic (don't contain it)
- **Models/helpers/interfaces** - contain business logic
- **tasks.py** - async entry functions handle exceptions and logging, call logic from other files

#### 4. Views and ViewSets
- **ALWAYS scope queries to request.user:**
  ```python
  # GOOD
  def get_queryset(self, user_boat_uuid: str = None):
      return self.request.user.all_user_boats.filter(id=user_boat_uuid)

  # BAD
  def get_queryset(self, user_boat_uuid: str = None):
      return UserBoat.objects.filter(id=user_boat_uuid)
  ```

#### 5. APIs
- **Document with OpenAPI schema** - all new/changed APIs
- **Error messages (4xx) must include `message` key** for mobile display
- Additional error fields are optional but `message` is required

#### 6. Async Tasks
- **MUST route all shared tasks in settings**

#### 7. Migrations
- **Avoid data migrations** - create scripts with clear deployment instructions instead
- **Separate schema from data migrations** - apply schema first, then data
- **No `bulk_update` in data migrations** unless explicitly approved

#### 8. Testing
- **Proper mock cleanup:**
  ```python
  # GOOD
  sub_patcher = patch("some.function.path")
  some_function_mock = sub_patcher.start()
  self.addCleanup(sub_patcher.stop())

  # BAD
  sub_patcher = patch("some.function.path").start()
  self.addCleanup(sub_patcher.stop())
  ```

- **Explicit sorting in sequence comparisons**
- **Use `django.test.TestCase`** not `unittest.TestCase`
- **No tests, no approve** (unless hotfix)

#### 9. Functions
- **Do only what the name suggests**
- **Max 20 statements** (~50-100 lines depending on statement size)
- **No double loops in one function**
- **Naming conventions:**
  - `is_/was_/has_` prefix for boolean returns
  - `get_` for value returns
  - `set_/create_/update_/upsert_/delete_` for write operations
  - No prefix for properties
- **Type hints required** for arguments and return values

#### 10. Docstrings and Comments
- Required for non-trivial functions
- **Avoid tautologies** - don't write `"""Returns a list of boats"""` for `get_boat_list()`
- **Test structure: GIVEN, WHEN, THEN, AND**
- **Remove useless comments** that provide no value
- **Document "why/purpose"** of classes, especially related flows/architecture

#### 11. Literals
- **No literals except bools** - create constants in `transl_strings`, `sentinel_system_settings`, or new dedicated files
- **Add translation markings** for strings that may reach frontend

#### 12. Type Hinting
- **Always use type hints** for inputs and outputs
- Use `Optional[]` when null is possible
- For collections: `List["CRMGroup"]` is sufficient (no need for deep dictionary typing)

#### 13. Code Formatting
- **Use Black** for Python formatting

#### 14. Settings
- **Add default values to settings.py** when adding new settings to prevent test breakage

#### 15. Commented Code
- **Avoid when possible**
- If necessary, explain why: `# todo @username DATE: reason for commented code`

### JavaScript Standards

#### Code Formatting
- **Use Prettier** for all JavaScript formatting (https://prettier.io/)

### Merge Request Standards
- **Single feature per MR**
- **Max 500 lines when possible**
- **No tests, no approve** (unless hotfix)

## Validation Checklist

When writing or reviewing code, verify:

- [ ] Models have `created` and `modified` timestamp fields
- [ ] Large tables use BigInt IDs
- [ ] None comparisons use `is`/`is not`
- [ ] Views are thin, business logic in models/helpers
- [ ] Data validation in serializers
- [ ] Views scope queries to `request.user`
- [ ] APIs documented with OpenAPI
- [ ] API errors include `message` key
- [ ] Async tasks routed in settings
- [ ] Migrations separated (schema vs data)
- [ ] Functions < 20 statements, proper naming, type hints
- [ ] No tautological docstrings
- [ ] Tests use GIVEN/WHEN/THEN structure
- [ ] No magic literals (use constants)
- [ ] Type hints on inputs and outputs
- [ ] Code formatted with Black (Python) or Prettier (JavaScript)
- [ ] Explicit `save(update_fields=[...])` when updating specific fields

## Examples

### Example 1: Model Creation
```python
# GOOD - Follows all standards
from django.db import models

class Boat(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def update_name(self, new_name: str) -> None:
        """Update boat name with explicit field saving to prevent race conditions."""
        self.name = new_name
        self.save(update_fields=["name", "modified"])
```

### Example 2: View Implementation
```python
# GOOD - Thin view, scoped to user
class BoatViewSet(viewsets.ModelViewSet):
    def get_queryset(self) -> QuerySet:
        return self.request.user.boats.all()

    def create(self, request):
        serializer = BoatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=201)
```

### Example 3: Test Structure
```python
def test_boat_creation(self):
    # GIVEN a user with no boats
    user = UserFactory()

    # WHEN creating a new boat
    boat = Boat.objects.create(name="Test Boat", owner=user)

    # THEN the boat is created with timestamps
    self.assertIsNotNone(boat.created)
    self.assertIsNotNone(boat.modified)
    # AND the boat belongs to the user
    self.assertEqual(boat.owner, user)
```

## Reference
See [reference.md](reference.md) for the complete coding guidelines document.
