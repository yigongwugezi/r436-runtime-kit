from fastapi import APIRouter


router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/capabilities")
def runtime_capabilities() -> dict:
    from app.config import runtime_capabilities as get_runtime_capabilities
    return get_runtime_capabilities()


@router.get("/health/search")
def search_health() -> dict:
    """Expose aggregate diagnostics only; never include queries or identities."""
    from app.services.search_client import DuckDuckGoSearchClient, search_cache
    from app.services.section_resource_recommendations import SearchCascade

    return {"status": "ok", "cache": {**search_cache.stats(), **SearchCascade.stats()}, "providers": DuckDuckGoSearchClient.health_snapshot()}
