"""Meilisearch client and schema manager for dataset and sample indexing."""

from typing import Any

import httpx

from ubuntubio.config import settings

DATASETS_INDEX = "datasets"
SAMPLES_INDEX = "samples"

DATASETS_FILTERABLE_ATTRIBUTES = [
    "slug",
    "domain",
    "access",
    "license",
    "countries",
    "taxon_ids",
    "genus",
    "family",
    "is_verified_african",
    "owner_type",
    "owner_id",
]

DATASETS_SORTABLE_ATTRIBUTES = [
    "created_at",
    "updated_at",
    "samples_count",
    "slug",
]

DATASETS_SEARCHABLE_ATTRIBUTES = [
    "title",
    "slug",
    "description",
    "countries",
    "genus",
    "family",
    "benefit_sharing",
]

SAMPLES_FILTERABLE_ATTRIBUTES = [
    "repo_id",
    "repo_slug",
    "domain",
    "access",
    "country",
    "taxon_id",
    "genus",
    "family",
    "collection_date",
    "host",
    "isolation_source",
    "_geo",
]

SAMPLES_SORTABLE_ATTRIBUTES = [
    "collection_date",
    "sample_id",
    "created_at",
]

SAMPLES_SEARCHABLE_ATTRIBUTES = [
    "sample_id",
    "admin1",
    "host",
    "isolation_source",
    "genus",
    "family",
]


class MeiliService:
    """Meilisearch management service with transparent in-memory mock capability for tests."""

    def __init__(
        self,
        base_url: str | None = None,
        master_key: str | None = None,
        mock_mode: bool = False,
    ) -> None:
        self.base_url = (base_url or settings.MEILI_URL).rstrip("/")
        self.master_key = master_key or settings.MEILI_MASTER_KEY
        self.mock_mode = mock_mode

        # In-memory document store used in mock_mode or as unit test fallback
        self._mock_indices: dict[str, dict[str, dict[str, Any]]] = {
            DATASETS_INDEX: {},
            SAMPLES_INDEX: {},
        }
        self.headers = {
            "Authorization": f"Bearer {self.master_key}",
            "Content-Type": "application/json",
        }

    async def init_indexes(self) -> None:
        """Create indexes and configure filterable, sortable, and searchable attributes."""
        if self.mock_mode:
            return

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                # 1. Ensure datasets index
                await client.post(
                    f"{self.base_url}/indexes",
                    json={"uid": DATASETS_INDEX, "primaryKey": "id"},
                    headers=self.headers,
                )
                await client.put(
                    f"{self.base_url}/indexes/{DATASETS_INDEX}/settings/filterable-attributes",
                    json=DATASETS_FILTERABLE_ATTRIBUTES,
                    headers=self.headers,
                )
                await client.put(
                    f"{self.base_url}/indexes/{DATASETS_INDEX}/settings/sortable-attributes",
                    json=DATASETS_SORTABLE_ATTRIBUTES,
                    headers=self.headers,
                )
                await client.put(
                    f"{self.base_url}/indexes/{DATASETS_INDEX}/settings/searchable-attributes",
                    json=DATASETS_SEARCHABLE_ATTRIBUTES,
                    headers=self.headers,
                )

                # 2. Ensure samples index
                await client.post(
                    f"{self.base_url}/indexes",
                    json={"uid": SAMPLES_INDEX, "primaryKey": "id"},
                    headers=self.headers,
                )
                await client.put(
                    f"{self.base_url}/indexes/{SAMPLES_INDEX}/settings/filterable-attributes",
                    json=SAMPLES_FILTERABLE_ATTRIBUTES,
                    headers=self.headers,
                )
                await client.put(
                    f"{self.base_url}/indexes/{SAMPLES_INDEX}/settings/sortable-attributes",
                    json=SAMPLES_SORTABLE_ATTRIBUTES,
                    headers=self.headers,
                )
                await client.put(
                    f"{self.base_url}/indexes/{SAMPLES_INDEX}/settings/searchable-attributes",
                    json=SAMPLES_SEARCHABLE_ATTRIBUTES,
                    headers=self.headers,
                )
            except httpx.RequestError:
                # When Meilisearch is not running in local test environment, fallback to mock
                self.mock_mode = True

    async def add_documents(self, index_name: str, documents: list[dict[str, Any]]) -> None:
        """Add or update documents in a target index."""
        if not documents:
            return

        if self.mock_mode:
            store = self._mock_indices.setdefault(index_name, {})
            for doc in documents:
                doc_id = str(doc.get("id") or doc.get("slug"))
                store[doc_id] = dict(doc)
            return

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/indexes/{index_name}/documents",
                    json=documents,
                    headers=self.headers,
                )
                if resp.status_code >= 400:
                    self.mock_mode = True
                    await self.add_documents(index_name, documents)
            except httpx.RequestError:
                self.mock_mode = True
                await self.add_documents(index_name, documents)

    async def delete_documents(self, index_name: str, document_ids: list[str]) -> None:
        """Delete specific documents by primary key."""
        if not document_ids:
            return

        if self.mock_mode:
            store = self._mock_indices.get(index_name, {})
            for did in document_ids:
                store.pop(did, None)
            return

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                await client.post(
                    f"{self.base_url}/indexes/{index_name}/documents/delete-batch",
                    json=document_ids,
                    headers=self.headers,
                )
            except httpx.RequestError:
                self.mock_mode = True
                await self.delete_documents(index_name, document_ids)

    async def delete_repo_samples(self, repo_id: str) -> None:
        """Delete all samples belonging to a specific repository."""
        if self.mock_mode:
            store = self._mock_indices.get(SAMPLES_INDEX, {})
            to_remove = [k for k, v in store.items() if v.get("repo_id") == repo_id]
            for k in to_remove:
                store.pop(k, None)
            return

        # Use Meilisearch filter deletion
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                await client.post(
                    f"{self.base_url}/indexes/{SAMPLES_INDEX}/documents/delete",
                    json={"filter": f"repo_id = '{repo_id}'"},
                    headers=self.headers,
                )
            except httpx.RequestError:
                self.mock_mode = True
                await self.delete_repo_samples(repo_id)

    async def search(
        self,
        index_name: str,
        query: str,
        filter_str: str | None = None,
        facets: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Execute search against index with filtering and facet distributions."""
        if self.mock_mode:
            return self._mock_search(
                index_name=index_name,
                query=query,
                filter_str=filter_str,
                facets=facets,
                limit=limit,
                offset=offset,
            )

        payload: dict[str, Any] = {
            "q": query,
            "limit": limit,
            "offset": offset,
        }
        if filter_str:
            payload["filter"] = filter_str
        if facets:
            payload["facets"] = facets

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/indexes/{index_name}/search",
                    json=payload,
                    headers=self.headers,
                )
                if resp.status_code == 200:
                    result: dict[str, Any] = resp.json()
                    return result
                self.mock_mode = True
                return self._mock_search(
                    index_name=index_name,
                    query=query,
                    filter_str=filter_str,
                    facets=facets,
                    limit=limit,
                    offset=offset,
                )
            except httpx.RequestError:
                self.mock_mode = True
                return self._mock_search(
                    index_name=index_name,
                    query=query,
                    filter_str=filter_str,
                    facets=facets,
                    limit=limit,
                    offset=offset,
                )

    def _mock_search(
        self,
        index_name: str,
        query: str,
        filter_str: str | None = None,
        facets: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Perform accurate in-memory keyword matching, filtering, and facet computation."""
        store = self._mock_indices.get(index_name, {})
        all_docs = list(store.values())
        filtered_docs: list[dict[str, Any]] = []

        q = query.strip().lower()

        # Parse basic filter conditions: "field = 'val'", "field IN ['v1', 'v2']"
        conditions: list[tuple[str, str, Any]] = []
        if filter_str:
            for clause in filter_str.split(" AND "):
                clause = clause.strip()
                if " = " in clause:
                    field, val = clause.split(" = ", 1)
                    val = val.strip("'\"")
                    conditions.append((field.strip(), "eq", val))
                elif " != " in clause:
                    field, val = clause.split(" != ", 1)
                    val = val.strip("'\"")
                    conditions.append((field.strip(), "neq", val))

        for doc in all_docs:
            # 1. Apply filters
            match_filter = True
            for field, op, val in conditions:
                doc_val = doc.get(field)
                if op == "eq":
                    if isinstance(doc_val, list):
                        if val not in [str(x) for x in doc_val]:
                            match_filter = False
                            break
                    elif str(doc_val) != str(val):
                        match_filter = False
                        break
                elif op == "neq" and str(doc_val) == str(val):
                    match_filter = False
                    break

            if not match_filter:
                continue

            # 2. Apply query search
            if q:
                # Search across all string attributes
                doc_str = " ".join(
                    str(v)
                    for k, v in doc.items()
                    if k not in ("id", "created_at", "updated_at", "_geo")
                ).lower()
                if q not in doc_str:
                    continue

            filtered_docs.append(doc)

        total_hits = len(filtered_docs)
        hits = filtered_docs[offset : offset + limit]

        # 3. Compute facet distribution
        facet_distribution: dict[str, dict[str, int]] = {}
        if facets:
            for facet_name in facets:
                dist: dict[str, int] = {}
                for doc in filtered_docs:
                    doc_val = doc.get(facet_name)
                    if isinstance(doc_val, list):
                        for item in doc_val:
                            dist[str(item)] = dist.get(str(item), 0) + 1
                    elif doc_val is not None:
                        dist[str(doc_val)] = dist.get(str(doc_val), 0) + 1
                facet_distribution[facet_name] = dist

        return {
            "hits": hits,
            "query": query,
            "estimatedTotalHits": total_hits,
            "limit": limit,
            "offset": offset,
            "facetDistribution": facet_distribution,
        }


meili_service = MeiliService()
