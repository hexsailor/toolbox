# Coding Standards Reference

This skill is based on the team's official coding guidelines document.

## Source Document
The complete coding guidelines are maintained in:
`Coding style _ Coding guidelines.docx.md`

## Key Areas Covered

### Python/Django
- Model conventions (timestamps, BigInt IDs, TimescaleDB)
- Comparison operators
- Architecture patterns (thin views, fat models)
- Data validation in serializers
- API design and error handling
- Async task routing
- Migration best practices
- Testing standards
- Function design (size, naming, type hints)
- Docstrings and comments
- Literals and constants
- Type hinting
- Code formatting with Black
- Views and ViewSet security

### JavaScript
- Code formatting with Prettier

### General
- Merge request guidelines
- Code optimization for critical paths

## Critical Security Pattern

**ALWAYS scope queries to the authenticated user:**

```python
# Prevents unauthorized data access
return self.request.user.all_user_boats.filter(id=user_boat_uuid)
```

## Performance-Critical Code Areas

When working on these areas, extra attention to optimization is required:
- Boat list
- Sensor list
- Dashboard lists
- Admin lists
- Data worker changes (all)
- Sensor worker changes (apply profile & composite sensors)

## Migration Strategy

1. Create schema migrations first
2. Apply schema migrations to database
3. Create separate data migration scripts
4. Provide clear deployment instructions
5. Allow for termination if data migration takes too long

This prevents long-running migrations from blocking deployments.
