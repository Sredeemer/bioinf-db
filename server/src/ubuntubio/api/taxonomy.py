"""NCBI Taxonomy suggestion and enrichment API endpoints powered by local taxdump."""

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status

from ubuntubio.indexer.taxonomy import taxonomy_service

router = APIRouter(prefix="/api/taxonomy", tags=["Taxonomy"])
v1_router = APIRouter(prefix="/api/v1/taxonomy", tags=["Taxonomy"])


@router.get("/suggest", response_model=dict[str, Any])
@v1_router.get("/suggest", response_model=dict[str, Any])
async def suggest_taxa(
    q: Annotated[str, Query(description="Organism name, common name, or NCBI taxon ID")] = "",
    limit: Annotated[int, Query(ge=1, le=50, description="Maximum suggestions to return")] = 10,
) -> dict[str, Any]:
    """Suggest organisms and NCBI taxonomy details using self-hosted taxdump index.

    Supports instant autocomplete for African pathogens, AMR organisms,
    vectors, and agricultural crops. Flags prohibited human genomic data (Taxon 9606).
    """
    suggestions = taxonomy_service.suggest(query=q, limit=limit)
    return {
        "query": q,
        "count": len(suggestions),
        "taxa": suggestions,
    }


@router.get("/{taxon_id}", response_model=dict[str, Any])
@v1_router.get("/{taxon_id}", response_model=dict[str, Any])
async def get_taxon_by_id(
    taxon_id: int,
) -> dict[str, Any]:
    """Retrieve verified taxonomy details and lineage for a specific NCBI Taxon ID."""
    info = taxonomy_service.enrich_taxon(taxon_id)
    if info.get("rank") == "unknown" and taxon_id not in taxonomy_service.taxa_cache:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Taxon ID {taxon_id} not found in local taxonomy database.",
        )
    return info


__all__ = ["router", "v1_router"]
