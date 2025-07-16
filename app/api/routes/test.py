from fastapi import APIRouter
from backend.Neo4jHandler import Neo4jHandler
from pathlib import Path
from fastapi.responses import FileResponse

router = APIRouter(tags=["test"], prefix="/test")

# Directory of exports.
EXPORT_DIR = Path(__file__).parent / "test"

# Endpoint for generating a report.
@router.get("/db-test")
async def test_database():
    handler = Neo4jHandler()
    try:
        result = handler.test_query()
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}