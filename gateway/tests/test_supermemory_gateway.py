"""Gateway tests: namespace isolation, request shaping, response mapping.

These cover the parts that carry security weight (a device must not be able
to reach another device's namespace) and the parts that cost money (payload
and limit clamping), without calling Supermemory.
"""

import pytest

import supermemory_gateway as gw


class TestNamespace:
    def test_derived_from_device_id(self):
        assert gw.namespace_for("device-abc123") == "guideai_device-abc123"

    def test_unsafe_characters_are_replaced(self):
        # A namespace is interpolated into the URL path; traversal and
        # separators must not survive. A run of unsafe characters collapses
        # to a single underscore.
        assert gw.namespace_for("../../other") == "guideai__other"

    def test_path_traversal_cannot_escape(self):
        assert "/" not in gw.namespace_for("a/b/c")
        assert ".." not in gw.namespace_for("../..")

    def test_length_is_capped(self):
        assert len(gw.namespace_for("x" * 500)) <= 100

    def test_empty_device_is_rejected(self):
        with pytest.raises(gw.SupermemoryError) as error:
            gw.namespace_for("  ")
        assert error.value.status == 400

    def test_two_devices_never_collide(self):
        assert gw.namespace_for("device-aaa") != gw.namespace_for("device-bbb")


class TestBuildDocument:
    def test_minimal_document(self):
        body = gw.build_document(content="A bin by the front door")
        assert body["content"] == "A bin by the front door"
        assert body["taskType"] == "memory"

    def test_blank_content_is_rejected(self):
        with pytest.raises(gw.SupermemoryError) as error:
            gw.build_document(content="   ")
        assert error.value.status == 400

    def test_oversized_fields_are_clamped(self):
        body = gw.build_document(
            content="x" * 99_000,
            document_id="y" * 900,
            supporting_context="z" * 9_000,
        )
        assert len(body["content"]) == gw.CONTENT_MAX
        assert len(body["id"]) == gw.DOCUMENT_ID_MAX
        assert len(body["supportingContext"]) == gw.SUPPORTING_CONTEXT_MAX

    def test_recall_critical_kinds_extract_immediately(self):
        # Measured: documents left to batch were still unextracted chunks
        # eight minutes later, so a hazard would not be recallable.
        assert gw.build_document(content="Wet floor", kind="hazard")["dreaming"] == "instant"
        assert gw.build_document(content="Maria asked", kind="conversation")["dreaming"] == "instant"

    def test_routine_scenery_is_allowed_to_batch(self):
        assert gw.build_document(content="A bench", kind="object")["dreaming"] == "dynamic"

    def test_instant_can_be_forced_either_way(self):
        assert gw.build_document(content="x", kind="object", instant=True)["dreaming"] == "instant"
        assert gw.build_document(content="x", kind="hazard", instant=False)["dreaming"] == "dynamic"

    def test_kind_is_recorded_as_filterable_metadata(self):
        body = gw.build_document(content="Wet floor", kind="hazard")
        assert body["metadata"]["kind"] == "hazard"

    def test_unsupported_metadata_values_are_dropped(self):
        body = gw.build_document(
            content="Hello",
            metadata={"ok": "yes", "n": 2, "flag": True, "bad": {"nested": 1}, "worse": [1, 2]},
        )
        assert set(body["metadata"]) == {"ok", "n", "flag"}


class TestBuildSearch:
    def test_graph_context_is_always_requested(self):
        body = gw.build_search(query="where is the lift")
        assert body["include"]["related"] is True
        assert body["searchMode"] == "hybrid"

    def test_weak_matches_are_excluded_by_default(self):
        # The documented default of 0.3 let an unrelated conversation through
        # at 0.49 on a live query. Spoken output gets no chance to skim.
        body = gw.build_search(query="roadworks")
        assert body["threshold"] == gw.DEFAULT_THRESHOLD
        assert gw.DEFAULT_THRESHOLD > 0.5

    def test_an_explicit_threshold_still_wins(self):
        assert gw.build_search(query="q", threshold=0.1)["threshold"] == 0.1

    def test_blank_query_is_rejected(self):
        with pytest.raises(gw.SupermemoryError) as error:
            gw.build_search(query=" ")
        assert error.value.status == 400

    def test_limit_is_clamped_to_the_documented_maximum(self):
        assert gw.build_search(query="q", limit=10_000)["limit"] == gw.SEARCH_LIMIT_MAX
        assert gw.build_search(query="q", limit=-5)["limit"] == 1
        # 0 reads as "unspecified", so the default applies rather than a
        # search that could never return anything.
        assert gw.build_search(query="q", limit=0)["limit"] == 8

    def test_single_kind_becomes_a_leaf_filter(self):
        body = gw.build_search(query="q", kinds=["hazard"])
        assert body["filter"] == {"field": "kind", "operator": "eq", "value": "hazard"}

    def test_several_kinds_become_an_or_filter(self):
        body = gw.build_search(query="q", kinds=["hazard", "place"])
        assert body["filter"]["operator"] == "or"
        assert len(body["filter"]["operands"]) == 2

    def test_no_kinds_means_no_filter(self):
        assert "filter" not in gw.build_search(query="q", kinds=[])


class TestNormalizeResults:
    def test_memory_and_chunk_results_both_carry_text(self):
        results = gw.normalize_results(
            {
                "results": [
                    {"id": "a", "memory": "A lift by the stairs", "similarity": 0.9},
                    {"id": "b", "chunk": "raw document text", "similarity": 0.5},
                ]
            }
        )
        assert [r["text"] for r in results] == ["A lift by the stairs", "raw document text"]

    def test_results_without_text_are_dropped(self):
        assert gw.normalize_results({"results": [{"id": "a", "similarity": 1.0}]}) == []

    def test_related_groups_map_onto_relation_kinds(self):
        results = gw.normalize_results(
            {
                "results": [
                    {
                        "id": "a",
                        "memory": "Roadworks on Oak Street",
                        "similarity": 0.8,
                        "metadata": {"kind": "hazard"},
                        "system": {"updatedAt": "2026-11-18T10:00:00Z"},
                        "included": {
                            "related": {
                                "parents": [{"id": "p", "memory": "Oak Street"}],
                                "siblings": [{"id": "s", "memory": "Crossing"}],
                                "children": [],
                            }
                        },
                    }
                ]
            }
        )
        hit = results[0]
        assert hit["kind"] == "hazard"
        assert hit["updatedAt"] == "2026-11-18T10:00:00Z"
        relations = {r["text"]: r["relation"] for r in hit["related"]}
        assert relations == {"Oak Street": "refers_to", "Crossing": "co_occurred"}

    def test_a_memory_replaces_the_chunk_it_came_from(self):
        # Hybrid search returns both; read aloud that is the same fact twice.
        results = gw.normalize_results(
            {
                "results": [
                    {"id": "c", "chunk": "The pedestrian crossing on Oak Street has an audible beeper.", "similarity": 0.70},
                    {"id": "m", "memory": "Pedestrian crossing on Oak Street has an audible beeper.", "similarity": 0.69},
                ]
            }
        )
        assert len(results) == 1
        assert results[0]["id"] == "m", "the extracted memory is the one kept"

    def test_distinct_facts_are_all_kept(self):
        results = gw.normalize_results(
            {
                "results": [
                    {"id": "a", "memory": "Roadworks on Oak Street", "similarity": 0.8},
                    {"id": "b", "memory": "The library lift is by the stairs", "similarity": 0.7},
                ]
            }
        )
        assert len(results) == 2

    def test_results_are_ordered_memories_first_then_by_similarity(self):
        results = gw.normalize_results(
            {
                "results": [
                    {"id": "chunk", "chunk": "Something entirely different", "similarity": 0.95},
                    {"id": "weak", "memory": "A weaker but extracted memory", "similarity": 0.60},
                    {"id": "strong", "memory": "A stronger extracted memory", "similarity": 0.80},
                ]
            }
        )
        assert [r["id"] for r in results] == ["strong", "weak", "chunk"]

    def test_internal_sorting_flag_never_leaks_to_the_client(self):
        results = gw.normalize_results({"results": [{"id": "a", "memory": "x y z", "similarity": 0.5}]})
        assert "_isMemory" not in results[0]

    def test_malformed_payloads_do_not_raise(self):
        assert gw.normalize_results({}) == []
        assert gw.normalize_results({"results": None}) == []
        assert gw.normalize_results({"results": ["not a dict"]}) == []


class TestConfiguration:
    def test_not_configured_without_a_key(self, monkeypatch):
        monkeypatch.delenv("SUPERMEMORY_API_KEY", raising=False)
        assert gw.configured() is False

    def test_missing_key_is_reported_as_unavailable_not_as_a_crash(self, monkeypatch):
        monkeypatch.delenv("SUPERMEMORY_API_KEY", raising=False)
        with pytest.raises(gw.SupermemoryError) as error:
            gw._headers()
        assert error.value.status == 503

    def test_base_url_defaults_and_strips_trailing_slash(self, monkeypatch):
        monkeypatch.delenv("SUPERMEMORY_BASE_URL", raising=False)
        assert gw.base_url() == gw.DEFAULT_BASE_URL
        monkeypatch.setenv("SUPERMEMORY_BASE_URL", "http://localhost:6767/")
        assert gw.base_url() == "http://localhost:6767"
