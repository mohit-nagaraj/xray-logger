"""End-to-end integration tests for X-Ray SDK and API.

These tests verify the complete data flow from SDK instrumentation
through API storage and query. Each test:
1. Uses the SDK to instrument code
2. Waits for data to flush to the API
3. Queries the API to verify data integrity
"""

import time

import pytest

from sdk import attach_candidates, attach_reasoning, step


class TestE2EBasicFlow:
    """Tests for basic SDK-to-API data flow."""

    @pytest.mark.asyncio
    async def test_run_created_with_correct_pipeline_name(
        self, xray_client, api_client
    ):
        """Verify run is created in API with correct pipeline name."""
        with xray_client.start_run(
            pipeline_name="test-pipeline",
            input_data={"query": "test"},
            metadata={"request_id": "e2e-001"},
        ):
            pass  # Empty run

        # Wait for flush
        time.sleep(0.5)

        response = await api_client.get(
            "/xray/runs", params={"pipeline": "test-pipeline"}
        )
        assert response.status_code == 200

        data = response.json()
        assert data["total"] >= 1
        assert data["runs"][0]["pipeline_name"] == "test-pipeline"

    @pytest.mark.asyncio
    async def test_run_status_transitions_to_success(self, xray_client, api_client):
        """Verify run status is 'success' after normal completion."""
        with xray_client.start_run(
            pipeline_name="status-test",
            metadata={"request_id": "e2e-002"},
        ) as run:
            run_id = run.id

        time.sleep(0.5)

        response = await api_client.get(f"/xray/runs/{run_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    @pytest.mark.asyncio
    async def test_run_status_transitions_to_error(self, xray_client, api_client):
        """Verify run status is 'error' when exception occurs."""
        run_id = None
        with pytest.raises(ValueError):
            with xray_client.start_run(
                pipeline_name="error-test",
                metadata={"request_id": "e2e-003"},
            ) as run:
                run_id = run.id
                raise ValueError("Intentional test error")

        time.sleep(0.5)

        response = await api_client.get(f"/xray/runs/{run_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "ValueError" in data["error_message"]

    @pytest.mark.asyncio
    async def test_run_metadata_captured(self, xray_client, api_client):
        """Verify run metadata (request_id, user_id, environment) is captured."""
        with xray_client.start_run(
            pipeline_name="metadata-test",
            metadata={
                "request_id": "req-12345",
                "user_id": "user-abc",
                "environment": "testing",
            },
        ) as run:
            run_id = run.id

        time.sleep(0.5)

        response = await api_client.get(f"/xray/runs/{run_id}")
        data = response.json()

        assert data["request_id"] == "req-12345"
        assert data["user_id"] == "user-abc"
        assert data["environment"] == "testing"


class TestE2EStepTracking:
    """Tests for step creation and tracking."""

    @pytest.mark.asyncio
    async def test_steps_linked_to_run(self, xray_client, api_client):
        """Verify steps are correctly linked to parent run."""

        @step(step_type="filter")
        def filter_items(items):
            return [i for i in items if i > 5]

        with xray_client.start_run(
            pipeline_name="step-link-test",
            metadata={"request_id": "e2e-004"},
        ) as run:
            run_id = run.id
            filter_items([1, 2, 6, 7, 8])

        time.sleep(0.5)

        response = await api_client.get(f"/xray/runs/{run_id}")
        assert response.status_code == 200
        data = response.json()

        assert len(data["steps"]) == 1
        assert data["steps"][0]["step_name"] == "filter_items"
        assert data["steps"][0]["step_type"] == "filter"
        assert data["steps"][0]["run_id"] == str(run_id)

    @pytest.mark.asyncio
    async def test_multiple_steps_ordered_correctly(self, xray_client, api_client):
        """Verify multiple steps maintain execution order."""

        @step(step_type="retrieval")
        def step_a(data):
            return data

        @step(step_type="filter")
        def step_b(data):
            return data

        @step(step_type="rank")
        def step_c(data):
            return data

        with xray_client.start_run(
            pipeline_name="order-test",
            metadata={"request_id": "e2e-005"},
        ) as run:
            run_id = run.id
            result = step_a([1, 2, 3])
            result = step_b(result)
            result = step_c(result)

        time.sleep(0.5)

        response = await api_client.get(f"/xray/runs/{run_id}")
        data = response.json()

        assert len(data["steps"]) == 3
        # Steps should be ordered by started_at (execution order)
        step_names = [s["step_name"] for s in data["steps"]]
        assert step_names == ["step_a", "step_b", "step_c"]

    @pytest.mark.asyncio
    async def test_step_index_increments(self, xray_client, api_client):
        """Verify step index increments for each step in a run."""

        @step(step_type="transform")
        def transform_data(data, suffix):
            return [f"{d}{suffix}" for d in data]

        with xray_client.start_run(
            pipeline_name="index-test",
        ) as run:
            run_id = run.id
            data = ["a", "b"]
            data = transform_data(data, "1")
            data = transform_data(data, "2")
            data = transform_data(data, "3")

        time.sleep(0.5)

        response = await api_client.get(f"/xray/runs/{run_id}")
        steps = response.json()["steps"]

        indices = [s["index"] for s in steps]
        assert indices == [0, 1, 2]


class TestE2EReasoningCapture:
    """Tests for reasoning and metadata capture."""

    @pytest.mark.asyncio
    async def test_attach_reasoning_captured(self, xray_client, api_client):
        """Verify attach_reasoning data is captured in API."""

        @step(step_type="filter")
        def filter_with_reasoning(items, threshold):
            filtered = [i for i in items if i > threshold]
            attach_reasoning(
                {
                    "threshold": threshold,
                    "input_count": len(items),
                    "output_count": len(filtered),
                    "filter_type": "greater_than",
                }
            )
            return filtered

        with xray_client.start_run(
            pipeline_name="reasoning-test",
            metadata={"request_id": "e2e-006"},
        ) as run:
            run_id = run.id
            filter_with_reasoning([1, 5, 10, 15], 7)

        time.sleep(0.5)

        response = await api_client.get(f"/xray/runs/{run_id}")
        data = response.json()

        step_data = data["steps"][0]
        assert step_data["reasoning"] is not None
        assert step_data["reasoning"]["threshold"] == 7
        assert step_data["reasoning"]["input_count"] == 4
        assert step_data["reasoning"]["output_count"] == 2
        assert step_data["reasoning"]["filter_type"] == "greater_than"

    @pytest.mark.asyncio
    async def test_attach_candidates_captured(self, xray_client, api_client):
        """Verify attach_candidates data is captured in API."""

        @step(step_type="rank")
        def rank_with_candidates(items):
            ranked = sorted(items, key=lambda x: x["score"], reverse=True)
            attach_candidates(ranked, phase="output")
            return ranked

        candidates = [
            {"id": "A", "score": 0.9},
            {"id": "B", "score": 0.7},
            {"id": "C", "score": 0.5},
        ]

        with xray_client.start_run(
            pipeline_name="candidates-test",
            metadata={"request_id": "e2e-007"},
        ) as run:
            run_id = run.id
            rank_with_candidates(candidates)

        time.sleep(0.5)

        response = await api_client.get(f"/xray/runs/{run_id}")
        data = response.json()

        step_data = data["steps"][0]
        assert step_data["reasoning"] is not None
        assert "output_candidates" in step_data["reasoning"]
        assert len(step_data["reasoning"]["output_candidates"]) == 3

    @pytest.mark.asyncio
    async def test_multiple_reasoning_calls_merged(self, xray_client, api_client):
        """Verify multiple attach_reasoning calls are merged."""

        @step(step_type="filter")
        def multi_reasoning_step(items):
            attach_reasoning({"phase1": "started"})
            filtered = [i for i in items if i > 0]
            attach_reasoning({"phase2": "filtered", "count": len(filtered)})
            return filtered

        with xray_client.start_run(
            pipeline_name="multi-reasoning-test",
        ) as run:
            run_id = run.id
            multi_reasoning_step([1, -2, 3])

        time.sleep(0.5)

        response = await api_client.get(f"/xray/runs/{run_id}")
        step_data = response.json()["steps"][0]

        # Both reasoning attachments should be present
        assert step_data["reasoning"]["phase1"] == "started"
        assert step_data["reasoning"]["phase2"] == "filtered"
        assert step_data["reasoning"]["count"] == 2


class TestE2ECountsAndRemovedRatio:
    """Tests for input/output counts and removed_ratio computation."""

    @pytest.mark.asyncio
    async def test_input_output_counts_captured(self, xray_client, api_client):
        """Verify input_count and output_count are captured."""

        @step(step_type="filter")
        def count_filter(items):
            return items[:5]  # Keep first 5

        with xray_client.start_run(
            pipeline_name="counts-test",
        ) as run:
            run_id = run.id
            count_filter([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

        time.sleep(0.5)

        response = await api_client.get(f"/xray/runs/{run_id}")
        step_data = response.json()["steps"][0]

        assert step_data["input_count"] == 10
        assert step_data["output_count"] == 5

    @pytest.mark.asyncio
    async def test_removed_ratio_computed_correctly(self, xray_client, api_client):
        """Verify removed_ratio is computed at query time."""

        @step(step_type="filter")
        def aggressive_filter(items):
            return items[:2]  # Keep only first 2

        with xray_client.start_run(
            pipeline_name="ratio-test",
        ) as run:
            run_id = run.id
            aggressive_filter([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

        time.sleep(0.5)

        response = await api_client.get(f"/xray/runs/{run_id}")
        step_data = response.json()["steps"][0]

        assert step_data["input_count"] == 10
        assert step_data["output_count"] == 2
        # removed_ratio = (10 - 2) / 10 = 0.8
        assert step_data["removed_ratio"] == 0.8

    @pytest.mark.asyncio
    async def test_removed_ratio_zero_when_no_removal(self, xray_client, api_client):
        """Verify removed_ratio is 0 when nothing is removed."""

        @step(step_type="transform")
        def identity(items):
            return items  # No filtering

        with xray_client.start_run(
            pipeline_name="no-removal-test",
        ) as run:
            run_id = run.id
            identity([1, 2, 3])

        time.sleep(0.5)

        response = await api_client.get(f"/xray/runs/{run_id}")
        step_data = response.json()["steps"][0]

        assert step_data["input_count"] == 3
        assert step_data["output_count"] == 3
        assert step_data["removed_ratio"] == 0.0


class TestE2ECompetitorPipeline:
    """Tests using the competitor pipeline example."""

    @pytest.mark.asyncio
    async def test_full_pipeline_execution(self, xray_client, api_client):
        """Verify complete competitor pipeline creates expected trace."""
        from examples.competitor_pipeline.pipeline import run_competitor_analysis

        with xray_client.start_run(
            pipeline_name="competitor-analysis",
            input_data={"query": "AI", "min_relevance": 0.5},
            metadata={"request_id": "e2e-pipeline-001", "user_id": "test-user"},
        ) as run:
            run_id = run.id
            result = run_competitor_analysis("AI", min_relevance=0.5)

        time.sleep(0.8)

        # Verify run
        response = await api_client.get(f"/xray/runs/{run_id}")
        assert response.status_code == 200
        data = response.json()

        assert data["pipeline_name"] == "competitor-analysis"
        assert data["status"] == "success"
        assert data["request_id"] == "e2e-pipeline-001"
        assert data["user_id"] == "test-user"

        # Verify steps (4 steps: retrieval, filter, rank, llm)
        assert len(data["steps"]) == 4

        step_types = [s["step_type"] for s in data["steps"]]
        assert "retrieval" in step_types
        assert "filter" in step_types
        assert "rank" in step_types
        assert "llm" in step_types

        # Verify step order matches pipeline flow
        step_names = [s["step_name"] for s in data["steps"]]
        assert step_names == [
            "retrieve_documents",
            "filter_by_relevance",
            "rank_by_importance",
            "generate_summary",
        ]

    @pytest.mark.asyncio
    async def test_pipeline_filter_reasoning_captured(self, xray_client, api_client):
        """Verify filter step reasoning is captured correctly."""
        from examples.competitor_pipeline.pipeline import run_competitor_analysis

        with xray_client.start_run(
            pipeline_name="competitor-analysis",
        ) as run:
            run_id = run.id
            run_competitor_analysis("AI", min_relevance=0.7)

        time.sleep(0.8)

        response = await api_client.get(f"/xray/runs/{run_id}")
        steps = response.json()["steps"]

        # Find filter step
        filter_step = next(s for s in steps if s["step_type"] == "filter")
        assert filter_step["reasoning"] is not None
        assert "threshold" in filter_step["reasoning"]
        assert "filter_type" in filter_step["reasoning"]

    @pytest.mark.asyncio
    async def test_pipeline_rank_candidates_captured(self, xray_client, api_client):
        """Verify rank step candidates are captured correctly."""
        from examples.competitor_pipeline.pipeline import run_competitor_analysis

        with xray_client.start_run(
            pipeline_name="competitor-analysis",
        ) as run:
            run_id = run.id
            run_competitor_analysis("AI analytics", min_relevance=0.5)

        time.sleep(0.8)

        response = await api_client.get(f"/xray/runs/{run_id}")
        steps = response.json()["steps"]

        # Find rank step
        rank_step = next(s for s in steps if s["step_type"] == "rank")
        assert rank_step["reasoning"] is not None
        assert "ranking_algorithm" in rank_step["reasoning"]
        assert "top_results" in rank_step["reasoning"]

    @pytest.mark.asyncio
    async def test_pipeline_with_no_matching_documents(self, xray_client, api_client):
        """Verify pipeline handles empty results gracefully."""
        from examples.competitor_pipeline.pipeline import run_competitor_analysis

        with xray_client.start_run(
            pipeline_name="competitor-analysis",
            input_data={"query": "nonexistent_xyz_query_12345"},
        ) as run:
            run_id = run.id
            result = run_competitor_analysis("nonexistent_xyz_query_12345")

        time.sleep(0.5)

        response = await api_client.get(f"/xray/runs/{run_id}")
        data = response.json()

        # Run should still succeed even with no results
        assert data["status"] == "success"
        # Only retrieval step executed (returns empty, pipeline exits early)
        assert len(data["steps"]) == 1
        assert data["steps"][0]["step_type"] == "retrieval"


class TestE2EQueryEndpoints:
    """Tests for query API endpoints."""

    @pytest.mark.asyncio
    async def test_list_runs_pagination(self, xray_client, api_client):
        """Verify list runs endpoint supports pagination."""
        # Create 5 runs
        for i in range(5):
            with xray_client.start_run(
                pipeline_name="pagination-test",
                metadata={"request_id": f"page-{i}"},
            ):
                pass

        time.sleep(0.5)

        # Get first 2
        response = await api_client.get(
            "/xray/runs", params={"pipeline": "pagination-test", "limit": 2, "offset": 0}
        )
        data = response.json()
        assert len(data["runs"]) == 2
        assert data["total"] >= 5

        # Get next 2
        response = await api_client.get(
            "/xray/runs", params={"pipeline": "pagination-test", "limit": 2, "offset": 2}
        )
        data = response.json()
        assert len(data["runs"]) == 2

    @pytest.mark.asyncio
    async def test_list_runs_filter_by_user_id(self, xray_client, api_client):
        """Verify list runs endpoint filters by user_id."""
        # Create runs with different user_ids
        for user in ["alice", "bob", "alice"]:
            with xray_client.start_run(
                pipeline_name="user-filter-test",
                metadata={"user_id": user},
            ):
                pass

        time.sleep(0.5)

        response = await api_client.get("/xray/runs", params={"user_id": "alice"})
        data = response.json()
        assert all(r["user_id"] == "alice" for r in data["runs"])
        assert data["total"] >= 2

    @pytest.mark.asyncio
    async def test_list_steps_filter_by_type(self, xray_client, api_client):
        """Verify list steps endpoint filters by step_type."""

        @step(step_type="filter")
        def filter_step(x):
            return x

        @step(step_type="rank")
        def rank_step(x):
            return x

        with xray_client.start_run(pipeline_name="step-type-test"):
            filter_step([1, 2, 3])
            rank_step([1, 2])

        time.sleep(0.5)

        response = await api_client.get("/xray/steps", params={"step_type": "filter"})
        data = response.json()
        assert all(s["step_type"] == "filter" for s in data["steps"])

    @pytest.mark.asyncio
    async def test_list_steps_filter_by_run_id(self, xray_client, api_client):
        """Verify list steps endpoint filters by run_id."""

        @step(step_type="transform")
        def transform(x):
            return x

        # Create two runs with steps
        with xray_client.start_run(pipeline_name="run-filter-test") as run1:
            run1_id = run1.id
            transform([1])

        with xray_client.start_run(pipeline_name="run-filter-test") as run2:
            run2_id = run2.id
            transform([2])
            transform([3])

        time.sleep(0.5)

        # Filter by run1
        response = await api_client.get("/xray/steps", params={"run_id": str(run1_id)})
        data = response.json()
        assert data["total"] == 1
        assert all(s["run_id"] == str(run1_id) for s in data["steps"])

        # Filter by run2
        response = await api_client.get("/xray/steps", params={"run_id": str(run2_id)})
        data = response.json()
        assert data["total"] == 2


class TestE2EFailOpenSemantics:
    """Tests for SDK fail-open behavior."""

    def test_pipeline_succeeds_without_api(self):
        """Verify pipeline execution succeeds even without API backend."""
        from sdk import XRayConfig, init_xray, shutdown_xray, step

        # Configure SDK with unreachable URL
        config = XRayConfig(
            base_url="http://127.0.0.1:59999",  # Non-existent port
            buffer_size=10,
            flush_interval=0.1,
        )
        client = init_xray(config)

        @step(step_type="filter")
        def my_filter(items):
            return [i for i in items if i > 5]

        try:
            with client.start_run(pipeline_name="fail-open-test"):
                result = my_filter([1, 3, 7, 9])

            # Pipeline should complete successfully
            assert result == [7, 9]
        finally:
            shutdown_xray(timeout=1.0)

    def test_exception_in_step_still_propagates(self):
        """Verify that SDK doesn't swallow application exceptions."""
        from sdk import XRayConfig, init_xray, shutdown_xray, step

        config = XRayConfig(
            base_url="http://127.0.0.1:59999",
            buffer_size=10,
            flush_interval=0.1,
        )
        client = init_xray(config)

        @step(step_type="transform")
        def failing_step(data):
            raise RuntimeError("Application error")

        try:
            with pytest.raises(RuntimeError, match="Application error"):
                with client.start_run(pipeline_name="error-propagation-test"):
                    failing_step([1, 2, 3])
        finally:
            shutdown_xray(timeout=1.0)
