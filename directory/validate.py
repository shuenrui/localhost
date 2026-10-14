#!/usr/bin/env python3
"""Validate the directory dataset. Stdlib only.

Usage: python3 directory/validate.py [--strict]

Fails on: missing required fields, unknown cross-reference ids, measurements
without a source, values outside the enums, and duplicate ids. --strict also
fails on warnings (null fields that a complete entry would fill in).
"""

from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

QUANTS = {
    "bf16", "fp16", "fp8", "nvfp4", "mxfp4", "int8", "int4", "int4-hybrid",
    "awq", "gptq", "autoround", "gguf-q8", "gguf-q6", "gguf-q5", "gguf-q4",
    "gguf-q3", "gguf-q2", "mlx-8", "mlx-6", "mlx-4", "mlx-3", "mlx-2",
    "mixed", "other",
}

FORMATS = {
    "safetensors", "gguf", "mlx", "onnx", "gptq", "awq", "unknown",
}

SPEC_DECODE = {"none", "mtp", "eagle", "dspark", "dflash2", "ngram", "other"}

METRICS = {
    # speed
    "decode_code", "decode_essay", "decode_chat", "decode_agg",
    "decode_per_stream", "prefill_tok_s", "ttft_ms", "task_time_min",
    # quality
    "quality_index", "bench_code", "bench_toolcall", "bench_mmlu",
    "bench_gsm8k", "bench_humaneval", "bench_other",
    # footprint
    "memory_gb", "disk_gb",
}

UNITS = {"tok/s", "ms", "s", "min", "%", "GB", "score"}
STATS = {"mean", "median", "peak"}

PROVENANCE = {"box", "forum", "vendor"}
PROV_RANK = {"box": 3, "forum": 2, "vendor": 1, None: 0}

STATUS = {"measured", "reported", "claimed", "untested", "broken"}
PRACTICAL_STATUS = {"selected", "not_verified"}
PRACTICAL_QUANTS = {
    "bf16", "fp16", "fp8", "nvfp4", "mxfp4", "int8", "int4", "int4-hybrid",
    "awq", "gptq", "autoround", "gguf-q8", "gguf-q6", "gguf-q5", "gguf-q4",
    "mlx-8", "mlx-6", "mlx-4",
}

SOURCE_KINDS = {
    "repo", "model", "thread", "post", "video", "docs", "paper", "blog",
    "benchmark", "other",
}

URL_RE = re.compile(r"^https?://\S+$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EXPECTED_LANGUAGE_RE = re.compile(
    r"\b(expected|expects|expect|likely|should|would|may|might|presumed|assumed|risk)\b",
    re.IGNORECASE,
)
REPO_ROOT = os.path.dirname(HERE)

# ---------------------------------------------------------------------------
# schema_version 2 (docs/EVIDENCE-SCHEMA-2026-09-16.md). Every block below is
# optional and additive; legacy records remain valid without schema_version.
# A lone measurements[].id is identity metadata and does NOT trigger v2.
# ---------------------------------------------------------------------------
SCHEMA_VERSION = 2
SPEED_METRIC_PREFIXES = ("decode_", "prefill_", "ttft_", "task_time_")

EVIDENCE_LEVELS = {
    "c0_claim", "c1_configuration", "c2_observation", "c3_matched_ab",
    "c4_independent_reproduction",
}
CAUSAL_LEVELS_HIGH = {"c3_matched_ab", "c4_independent_reproduction"}
CONTRAST_KINDS = {"none", "claimed", "uncontrolled", "bundle", "single_variable"}
QUALITY_STATUSES = {"unchecked", "pass", "fail", "mixed", "recorded"}
QUALITY_STATUSES_REQUIRING_LINK = {"pass", "fail", "mixed", "recorded"}
METHOD_GRADES = {
    "server_telemetry", "benchmark_harness", "vendor_published_table",
    "author_report", "wall_clock_division", "crowd_report", "unspecified",
}
CONDITION_COMPLETENESS = {"full", "partial", "insufficient"}
BINARY_PROVENANCE_STATUSES = {"resolved", "unresolved", "not_applicable"}
CLAIM_KINDS = {
    "configuration", "mechanism", "observation", "performance_effect",
    "quality_effect", "fit_constraint", "failure_mode", "tradeoff",
    "reproducibility", "cost", "thermal", "interconnect", "other",
}
OUTCOME_CLAIM_KINDS = {
    "observation", "performance_effect", "quality_effect", "failure_mode",
}
CONFIGURATION_CLAIM_KINDS = {"configuration", "mechanism"}
COMPARISON_RESULTS = {"a_better", "b_better", "equivalent", "mixed", "inconclusive"}
CONTRADICTION_STATUSES = {
    "open", "resolved_by_source_priority", "resolved_by_measurement",
    "unresolved_conflict", "superseded",
}
OPEN_QUESTION_BLOCKS = {
    "fit_claim", "speed_claim", "quality_claim", "causal_claim",
    "exact_reproduction", "promotion_to_box", "technique_registry",
    "builder_input", "other",
}
MEMORY_COMPONENTS = {
    "weights", "kv_pool", "draft", "cache_table", "projector", "activation",
    "runtime_overhead", "other",
}
MEMORY_UNITS = {"GB", "GiB", "MB", "MiB"}
MEMORY_SCOPES = {"total", "per_unit"}
MEMORY_LOCATIONS = {"gpu", "unified", "host_ram", "ssd", "mixed"}
OFFLOAD_STRATEGIES = {
    "none", "layer_offload", "kv_offload", "pageable_ple", "mmap",
    "nfs_weight_share", "hybrid", "other",
}
INTERCONNECT_KINDS = {
    "none", "pcie", "nvlink", "roce", "infiniband", "thunderbolt", "usb",
    "network", "other",
}
INTERCONNECT_ROLES = {
    "tensor_parallel", "pipeline_parallel", "expert_parallel",
    "kv_replication", "weight_share", "other",
}
SERVING_WORKLOADS = {
    "chat", "code", "essay", "file_rewrite", "agent", "needle_haystack",
    "benchmark", "mixed", "other",
}
SERVING_BATCHING = {"static", "continuous", "chunked_prefill", "other"}
CEILING_EFFECTS = {
    "throughput_regression", "latency_regression", "oom", "crash",
    "quality_failure", "preemption", "other",
}
CORRECTNESS_KINDS = {
    "byte_clean", "manual_read", "needle_haystack", "accuracy_evaluator",
    "kl_divergence", "ppl", "top1_retention", "benchmark", "other",
}
CORRECTNESS_RESULTS = {"pass", "fail", "mixed", "recorded", "unknown"}
FAILURE_STAGES = {
    "download", "load", "prefill", "decode", "output", "serve", "crash",
    "oom", "other",
}
FAILURE_STATUSES = {"open", "fixed", "workaround", "intermittent"}
CAPABILITY_NAMES = {
    "vision", "video", "tools", "thinking", "long_context",
    "structured_output", "other",
}
CAPABILITY_STATUSES = {
    "works", "reported", "broken", "requires_extra_artifact",
    "not_supported", "not_tested", "unknown",
}
BACKENDS = {"cuda", "rocm", "metal", "vulkan", "cpu", "opencl", "other"}
REVISION_RESOLUTIONS = {
    "exact", "branch_on_anchor", "earliest_commit_after_anchor", "tag",
    "page_retrieval", "image_digest", "unresolved",
}
TECHNIQUE_CATEGORIES = {
    "speculative_decode", "memory_strategy", "quantization", "runtime_patch",
    "interconnect", "serving", "context_management", "other",
}
TECHNIQUE_STATUSES = {"proposed", "active", "deprecated"}

V2_SOURCE_KEYS = {"locator", "archive_path", "retrieved", "lineage_id", "quote"}
ALLOWED_SOURCE_KEYS = {"url", "kind", "note", "mirror_url"} | V2_SOURCE_KEYS

V2_VARIATION_KEYS = {"revision", "revision_date", "snapshot_url", "revision_note"}
ALLOWED_VARIATION_KEYS = {
    "checkpoint", "publisher", "quant", "quant_detail", "format", "size_gb",
    "url", "license", "downloads",
} | V2_VARIATION_KEYS

V2_ENGINE_KEYS = {
    "image_digest", "version", "backend", "fork_revision", "kernel_patches",
    "environment", "spec_decode_profile",
}
ALLOWED_ENGINE_KEYS = {
    "id", "config", "image", "requires_fork", "draft_model", "spec_decode",
    "flags", "bundled",
} | V2_ENGINE_KEYS

V2_RUN_KEYS = {"repo_revision"}

INSTALL_PLATFORMS = {"macos", "linux", "windows"}


def check_engine_install(rep, w, inst):
    """engines/<id>.install: how to install the engine, copied from its official docs.
    Optional. When present: a source URL and retrieval date for any method, methods with
    platforms and cmd/do steps. A `cmd` must be a literal command from the docs, never a
    template; anything with a placeholder is a `do` step."""
    if inst is None:
        return
    if not isinstance(inst, dict):
        rep.err(w, "install must be an object")
        return
    methods = inst.get("methods")
    if not isinstance(methods, list):
        rep.err(w, "install.methods must be a list")
        return
    if methods:
        check_url(rep, w, "install.source", inst.get("source"))
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(inst.get("retrieved") or "")):
            rep.err(w, "install.retrieved must be YYYY-MM-DD")
    for i, m in enumerate(methods):
        mw = f"{w}.install.methods[{i}]"
        plats = m.get("platforms") or []
        if not plats or not set(plats) <= INSTALL_PLATFORMS:
            rep.err(mw, f"platforms {plats!r} must be a non-empty subset of {sorted(INSTALL_PLATFORMS)}")
        if not m.get("label"):
            rep.err(mw, "missing label")
        steps = m.get("steps") or []
        if not steps:
            rep.err(mw, "no steps")
        for j, st in enumerate(steps):
            if st.get("kind") not in ("cmd", "do") or not (st.get("text") or "").strip():
                rep.err(f"{mw}.steps[{j}]", "step needs kind cmd|do and text")
            elif st["kind"] == "cmd" and re.search(r"[<{]\s*[\w-]+\s*[>}]|/path/to/", st["text"]):
                rep.err(f"{mw}.steps[{j}]", "cmd step contains a placeholder; make it a `do` step")
ALLOWED_RUN_KEYS = {
    "command", "repo", "repo_commit", "profile", "steps", "auto_bootable",
} | V2_RUN_KEYS

V2_REQUIREMENTS_KEYS = {"memory_profile", "offload"}
ALLOWED_REQUIREMENTS_KEYS = {
    "memory_gb", "disk_gb", "min_vram_gb", "notes",
} | V2_REQUIREMENTS_KEYS

V2_HARDWARE_REF_KEYS = {
    "variant_id", "variant_ambiguous", "variant_note", "variant_source",
    "variant_locator",
}
ALLOWED_HARDWARE_REF_KEYS = {"id", "count"} | V2_HARDWARE_REF_KEYS

V2_MEASUREMENT_KEYS = {"id", "conditions", "evidence"}
MEASUREMENT_ID_EXEMPT_KEYS = {"id"}
ALLOWED_MEASUREMENT_KEYS = {
    "metric", "value", "unit", "provenance", "date", "source", "method",
    "note", "concurrency", "n", "context", "stat", "range",
} | V2_MEASUREMENT_KEYS

ALLOWED_CAPABILITIES_KEYS = {
    "vision", "video", "tools", "thinking", "long_context", "max_context",
}

ALLOWED_REPO_REVISION_KEYS = {
    "commit", "branch", "tag", "anchor_date", "resolution", "ambiguous",
    "source", "locator", "retrieved", "note",
}
ALLOWED_FORK_REVISION_KEYS = {
    "repo", "branch", "commits", "anchor_date", "resolution", "ambiguous",
    "source", "locator", "retrieved", "note",
}
ALLOWED_KERNEL_PATCH_KEYS = {
    "id", "pr", "commit", "purpose", "source", "locator", "note",
}
ALLOWED_ENVIRONMENT_KEYS = {
    "os", "driver", "cuda", "rocm", "metal", "python", "packages", "source",
    "locator", "date", "note",
}
ALLOWED_SPEC_PROFILE_KEYS = {
    "method", "draft_checkpoint", "draft_revision", "draft_quant",
    "max_draft_tokens", "acceptance_rate_pct", "acceptance_basis",
    "decay_curve", "source", "locator", "date", "provenance", "note",
}
ALLOWED_DECAY_POINT_KEYS = {
    "context_tokens", "prompt_tokens", "completion_tokens",
    "acceptance_rate_pct", "decode_per_stream_tok_s", "prefill_tok_s",
    "source", "locator", "date", "note",
}
ALLOWED_MEMORY_PROFILE_KEYS = {
    "entries", "kv_dtype", "gpu_memory_utilization", "provenance", "date",
    "source", "locator", "note",
}
ALLOWED_MEMORY_ENTRY_KEYS = {
    "component", "value", "unit", "scope", "location", "pageable",
    "context_tokens", "kv_tokens", "source", "locator", "date", "provenance",
    "note",
}
ALLOWED_OFFLOAD_KEYS = {
    "strategy", "components", "intentional", "cold_start_effect", "source",
    "locator", "provenance", "date", "note",
}
ALLOWED_INTERCONNECT_KEYS = {
    "kind", "topology", "role", "bandwidth_gbs", "requires_same_fabric",
    "source", "locator", "date", "provenance", "note",
}
ALLOWED_SERVING_KEYS = {
    "workload", "batching", "scheduler", "prefix_cache", "session_affinity",
    "concurrency_ceiling", "ceiling_effect", "ceiling_reason", "source",
    "locator", "date", "provenance", "note",
}
ALLOWED_CORRECTNESS_KEYS = {
    "output_checked", "checks", "quality_measurement_ids",
    "known_output_failure", "note",
}
ALLOWED_CORRECTNESS_CHECK_KEYS = {
    "id", "kind", "result", "scope", "context_tokens", "measurement_ids",
    "source", "locator", "quote", "date", "lineage_id", "note",
}
ALLOWED_KNOWN_FAILURE_KEYS = {
    "id", "stage", "trigger", "effect", "status", "observed_date", "date",
    "lineage_id", "source", "locator", "quote", "resolution", "note",
    "measurement_ids",
}
ALLOWED_CAPABILITY_OBSERVATION_KEYS = {
    "capability", "status", "trigger", "scope", "source", "locator", "quote",
    "date", "lineage_id", "note", "measurement_ids",
}
ALLOWED_EVIDENCE_KEYS = {
    "rubric_version", "lineages", "claims", "comparisons", "contradictions",
    "open_questions", "re_review_triggers", "review",
}
ALLOWED_LINEAGE_KEYS = {
    "id", "actor", "publisher", "kind", "sources", "locator", "archive_path",
    "retrieved", "note",
}
ALLOWED_CLAIM_KEYS = {
    "id", "technique_id", "kind", "statement", "evidence_level",
    "contrast_kind", "lineage_id", "scope", "source", "locator", "quote",
    "status", "cause", "effect", "contradictions", "open_question_ids",
    "measurement_ids", "comparison_id", "independent_reproductions",
    "binary_provenance_status", "re_review_triggers", "note", "date",
    "provenance",
}
ALLOWED_COMPARISON_KEYS = {
    "id", "question", "variable", "candidate_variable", "a", "b", "result",
    "effect_metric", "effect_direction", "contrast_kind",
    "conditions_constant", "conditions_unstated", "evidence_level",
    "binary_provenance_status", "lineage_id", "independent_reproductions",
    "quality_status", "source", "locator", "quote", "promotion_gate",
    "re_review_triggers", "open_question_ids", "method_grade", "method_note",
    "note", "date", "provenance",
}
ALLOWED_COMPARISON_SIDE_KEYS = {"label", "measurement_id", "note", "source", "locator"}
ALLOWED_PROMOTION_GATE_KEYS = {
    "target_level", "target_contrast_kind", "required_facts", "status",
    "note",
}
ALLOWED_CONTRADICTION_KEYS = {
    "id", "statement", "resolution", "status", "sources", "lineage_ids",
    "measurement_ids", "comparison_ids", "note",
}
ALLOWED_OPEN_QUESTION_KEYS = {
    "id", "type", "question", "blocks", "owner", "status", "source",
    "locator", "related_measurement_ids", "related_comparison_ids", "answer",
    "answered_date", "note",
}
ALLOWED_REVIEW_KEYS = {"by", "date", "rubric_version", "notes"}
ALLOWED_MEASUREMENT_CONDITION_KEYS = {
    "context_tokens", "context_label", "prompt_tokens", "completion_tokens",
    "workload", "greedy", "thinking", "temperature", "warm", "client",
    "concurrency", "hardware_count", "hardware_variant_id", "backend",
    "spec_decode", "max_draft_tokens", "kv_dtype", "offload_strategy",
    "power_limit_pct", "clock_state", "eval_duration_s", "eval_count",
    "note",
}
ALLOWED_MEASUREMENT_EVIDENCE_KEYS = {
    "level", "contrast_id", "contrast_kind", "lineage_id", "method_grade",
    "method_note", "quality_status", "independent_reproductions",
    "corroborations", "quote", "note", "binary_provenance_status",
    "re_review_triggers", "open_question_ids", "dossier_cited",
}
ALLOWED_TECHNIQUE_KEYS = {
    "id", "name", "category", "canonical_description", "mechanism",
    "constraints", "tradeoffs", "re_review_triggers", "canonical_sources",
    "status", "updated", "note",
}
ALLOWED_TECHNIQUE_SOURCE_KEYS = {
    "url", "kind", "locator", "archive_path", "retrieved", "date", "note",
}
ALLOWED_GENERIC_SOURCE_OBJECT_KEYS = {
    "url", "kind", "locator", "archive_path", "retrieved", "date", "quote",
    "note",
}

URL_BEARING_KEYS = {"url", "source", "mirror_url", "sources", "canonical_sources"}

# device spec (data/device-schema.json): field shape per section. Numbers accept
# null ("vendor does not publish") but never strings; strings must be non-empty.
DEVICE_SECTIONS = {
    "identity": {
        "required": ("name", "chip", "manufacturer"),
        "strings": ("name", "chip", "manufacturer", "os", "form_factor", "sku"),
        "numbers": (),
    },
    "memory": {
        "required": ("total_gb", "type"),
        "strings": ("type", "note"),
        "numbers": ("total_gb", "usable_gb", "bandwidth_gbs", "interface_bits", "channels"),
        "bools": ("unified",),
    },
    "compute": {
        "required": (),
        "strings": ("cpu_cores", "note"),
        "numbers": ("fp32_tflops", "fp16_dense_tflops", "fp16_sparse_tflops",
                    "fp8_dense_tflops", "fp8_sparse_tflops", "fp4_sparse_pflops",
                    "tensor_ai_tops", "neural_engine_tops"),
    },
    "storage": {
        "required": (),
        "strings": ("type", "note"),
        "numbers": ("read_gbs", "capacity_gb"),
    },
    "thermal": {
        "required": (),
        "strings": ("cooling", "note"),
        "numbers": ("tdp_watts", "psu_watts"),
    },
}
DEVICE_TOP_KEYS = set(DEVICE_SECTIONS) | {"variants", "sources"}
DEVICE_VARIANT_KEYS = {"id", "name", "chip", "memory_configs", "bandwidth_gbs",
                       "fp32_tflops", "tensor_ai_tops", "neural_engine_tops",
                       "tdp_watts", "note"}

REQUIRED_SETUP = [
    "id", "title", "model", "variation", "engine", "hardware",
    "requirements", "run", "status", "sources",
]
REQUIRED_VARIATION = ["checkpoint", "publisher", "quant", "format", "url"]
REQUIRED_ENGINE = ["id", "config"]
REQUIRED_RUN = ["repo"]
RUN_STEP_KINDS = {"cmd", "do"}
RUN_STEP_FIELDS = {"kind", "text"}

V2_SETUP_KEYS = {
    "schema_version", "interconnect", "serving", "correctness",
    "known_failures", "capability_observations", "evidence",
}
ALLOWED_SETUP_KEYS = set(REQUIRED_SETUP) | {
    "slug_note", "capabilities", "measurements", "caveats",
    "provenance_tier", "updated", "builder", "device",
} | V2_SETUP_KEYS


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")


def load(rel: str):
    path = os.path.join(DATA, rel)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_dir(rel: str) -> dict:
    out = {}
    d = os.path.join(DATA, rel)
    if not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json") or name.startswith("_"):
            continue
        try:
            obj = load(os.path.join(rel, name))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{rel}/{name}: invalid JSON — {exc}") from exc
        out[name[:-5]] = obj
    return out


def check_id(rep: Report, where: str, value: str) -> None:
    if not isinstance(value, str) or not ID_RE.match(value):
        rep.err(where, f"id {value!r} must match {ID_RE.pattern}")


def check_url(rep: Report, where: str, field: str, value) -> None:
    if value is None:
        rep.warn(where, f"{field} is null")
        return
    if not isinstance(value, str) or not URL_RE.match(value):
        rep.err(where, f"{field} {value!r} is not an http(s) URL")


def hw_ref(ref):
    """A setup hardware reference is either an id string (count 1) or an object
    {"id": <id>, "count": <n>} for a multi-unit system. Returns (id, count)."""
    if isinstance(ref, str):
        return ref, 1
    if isinstance(ref, dict):
        return ref.get("id"), ref.get("count", 1)
    return None, None


def check_device(rep: Report, where: str, dev, hw=None) -> None:
    """Validate a device spec block (data/device-schema.json).

    `hw` is the enclosing hardware record, when the block sits in one; it
    enables the cross-checks that keep the block and the record's top-level
    numbers from drifting apart. `hw=None` for per-setup override blocks.
    """
    if not isinstance(dev, dict):
        rep.err(where, f"device must be an object, got {type(dev).__name__}")
        return
    unknown = set(dev) - DEVICE_TOP_KEYS
    if unknown:
        rep.err(where, f"device has unknown keys {sorted(unknown)}; allowed: {sorted(DEVICE_TOP_KEYS)}")

    for section, spec in DEVICE_SECTIONS.items():
        if section not in dev:
            if spec["required"]:
                rep.err(where, f"device.{section} missing (requires {list(spec['required'])})")
            continue
        sec = dev[section]
        if sec is None:
            continue
        if not isinstance(sec, dict):
            rep.err(where, f"device.{section} must be an object")
            continue
        sw = f"{where}.device.{section}"
        unknown = set(sec) - set(spec["strings"]) - set(spec["numbers"]) - set(spec.get("bools", ()))
        if unknown:
            rep.err(sw, f"unknown keys {sorted(unknown)}")
        num_fields, str_fields = set(spec["numbers"]), set(spec["strings"])
        bool_fields = set(spec.get("bools", ()))
        for f in spec["required"]:
            val = sec.get(f)
            if f in num_fields:
                if isinstance(val, bool) or not isinstance(val, (int, float)):
                    rep.err(sw, f"{f} must be a number, got {val!r}")
            elif not isinstance(val, str) or not val.strip():
                rep.err(sw, f"{f} must be a non-empty string, got {val!r}")
        for f in spec["strings"]:
            if f in sec and sec[f] is not None and (not isinstance(sec[f], str) or not sec[f].strip()):
                rep.err(sw, f"{f} must be a non-empty string or null, got {sec[f]!r}")
        for f in spec["numbers"]:
            val = sec.get(f)
            if val is None:
                continue
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                rep.err(sw, f"{f} must be a number or null, got {val!r}")
            elif val < 0:
                rep.err(sw, f"{f} must be >= 0, got {val!r}")
        for f in bool_fields:
            val = sec.get(f)
            if val is not None and not isinstance(val, bool):
                rep.err(sw, f"{f} must be a boolean or null, got {val!r}")

    mem = dev.get("memory") or {}
    if isinstance(mem.get("total_gb"), (int, float)) and not isinstance(mem["total_gb"], bool) \
            and mem["total_gb"] <= 0:
        rep.err(f"{where}.device.memory", f"total_gb must be positive, got {mem['total_gb']!r}")
    bw = mem.get("bandwidth_gbs")
    if isinstance(bw, (int, float)) and not isinstance(bw, bool) and bw <= 0:
        rep.err(f"{where}.device.memory", f"bandwidth_gbs must be positive, got {bw!r}")

    variants = dev.get("variants")
    if variants is not None:
        if not isinstance(variants, list):
            rep.err(f"{where}.device.variants", "must be a list")
        else:
            seen = set()
            for i, var in enumerate(variants):
                vw = f"{where}.device.variants[{i}]"
                if not isinstance(var, dict):
                    rep.err(vw, "must be an object")
                    continue
                unknown = set(var) - DEVICE_VARIANT_KEYS
                if unknown:
                    rep.err(vw, f"unknown keys {sorted(unknown)}")
                for f in ("id", "name", "chip"):
                    if not isinstance(var.get(f), str) or not var[f].strip():
                        rep.err(vw, f"{f} must be a non-empty string, got {var.get(f)!r}")
                if isinstance(var.get("id"), str) and var["id"] in seen:
                    rep.err(vw, f"duplicate variant id {var['id']!r}")
                seen.add(var.get("id"))
                vbw = var.get("bandwidth_gbs")
                if isinstance(vbw, bool) or not isinstance(vbw, (int, float)) or vbw <= 0:
                    rep.err(vw, f"bandwidth_gbs must be a positive number, got {vbw!r}")
                elif hw and isinstance(hw.get("bandwidth_range_gbs"), list) and len(hw["bandwidth_range_gbs"]) == 2:
                    lo, hi = hw["bandwidth_range_gbs"]
                    if not (lo <= vbw <= hi):
                        rep.err(vw, f"bandwidth {vbw} outside the class range [{lo}, {hi}]; "
                                    f"widen the range or move the SKU to another class")

    srcs = dev.get("sources")
    if not isinstance(srcs, list) or not srcs:
        rep.err(f"{where}.device.sources", "must be a non-empty list of {url, note}")
    else:
        for i, src in enumerate(srcs):
            if not isinstance(src, dict):
                rep.err(f"{where}.device.sources[{i}]", "must be an object with url and note")
                continue
            u = src.get("url")
            if not isinstance(u, str) or not URL_RE.match(u):
                rep.err(f"{where}.device.sources[{i}]", f"url {u!r} is not an http(s) URL")
            if not isinstance(src.get("note"), str) or not src["note"].strip():
                rep.err(f"{where}.device.sources[{i}]", "note must state which figures this source backs")

    if hw:
        if hw.get("vendor") == "Apple" and mem.get("unified") is not True:
            rep.warn(f"{where}.device.memory",
                     "Apple hardware should state memory.unified: true (CPU and GPU share one pool)")
        if not hw.get("bandwidth_range_gbs") and hw.get("bandwidth_gbs") is not None \
                and bw is not None and bw != hw["bandwidth_gbs"]:
            rep.err(f"{where}.device.memory",
                    f"bandwidth_gbs {bw} != hardware record's bandwidth_gbs {hw['bandwidth_gbs']} — "
                    f"an exact-SKU device block must match its record")


def check_keys(rep: Report, where: str, obj, allowed, required=(), label="object") -> bool:
    if not isinstance(obj, dict):
        rep.err(where, f"{label} must be an object, got {type(obj).__name__}")
        return False
    unknown = sorted(set(obj) - allowed)
    if unknown:
        rep.err(where, f"unknown {label} keys {unknown}; allowed: {sorted(allowed)}")
    for field in required:
        val = obj.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            rep.err(where, f"{label} requires {field}")
    return True


def check_nonempty_str(rep: Report, where: str, field: str, val, required=False) -> None:
    if val is None:
        if required:
            rep.err(where, f"{field} must be a non-empty string")
        return
    if not isinstance(val, str) or not val.strip():
        rep.err(where, f"{field} must be a non-empty string or null, got {val!r}")


def check_optional_url(rep: Report, where: str, field: str, val) -> None:
    if val is None:
        return
    if not isinstance(val, str) or not URL_RE.match(val):
        rep.err(where, f"{field} {val!r} is not an http(s) URL")


def check_source_value(rep: Report, where: str, field: str, val, required=False) -> None:
    if val is None:
        if required:
            rep.err(where, f"{field} is required")
        return
    if not isinstance(val, str) or not val.strip():
        rep.err(where, f"{field} must be a non-empty string or null, got {val!r}")
        return
    if val.startswith(("http://", "https://")) and not URL_RE.match(val):
        rep.err(where, f"{field} {val!r} is not a valid http(s) URL")


def check_archive_path(rep: Report, where: str, val) -> None:
    if val is None:
        return
    if not isinstance(val, str) or not val.strip():
        rep.err(where, f"archive_path must be a non-empty string or null, got {val!r}")
        return
    path = val if os.path.isabs(val) else os.path.join(REPO_ROOT, val)
    if not os.path.exists(path):
        rep.err(where, f"archive_path {val!r} does not exist")


def check_date_field(rep: Report, where: str, field: str, val, required=False) -> None:
    if val is None:
        if required:
            rep.err(where, f"{field} must be YYYY-MM-DD")
        return
    if not isinstance(val, str) or not DATE_RE.match(val):
        rep.err(where, f"{field} {val!r} must be YYYY-MM-DD")


def check_number(rep: Report, where: str, field: str, val, required=False,
                 positive=False, integer=False, minimum=None, maximum=None) -> None:
    if val is None:
        if required:
            rep.err(where, f"{field} must be a number")
        return
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        rep.err(where, f"{field} must be a number or null, got {val!r}")
        return
    if integer and not isinstance(val, int):
        rep.err(where, f"{field} must be an integer or null, got {val!r}")
        return
    if positive and val <= 0:
        rep.err(where, f"{field} must be positive, got {val!r}")
    if minimum is not None and val < minimum:
        rep.err(where, f"{field} must be >= {minimum}, got {val!r}")
    if maximum is not None and val > maximum:
        rep.err(where, f"{field} must be <= {maximum}, got {val!r}")


def check_bool(rep: Report, where: str, field: str, val) -> None:
    if val is not None and not isinstance(val, bool):
        rep.err(where, f"{field} must be a boolean or null, got {val!r}")


def check_enum(rep: Report, where: str, field: str, val, allowed, required=False) -> None:
    if val is None:
        if required:
            rep.err(where, f"{field} must be one of {sorted(allowed)}")
        return
    if val not in allowed:
        rep.err(where, f"{field} {val!r} must be one of {sorted(allowed)}")


def check_str_list(rep: Report, where: str, field: str, val, allow_empty=True) -> None:
    if val is None:
        return
    if not isinstance(val, list):
        rep.err(where, f"{field} must be a list or null, got {type(val).__name__}")
        return
    if not val and not allow_empty:
        rep.err(where, f"{field} must not be empty")
        return
    for i, item in enumerate(val):
        if not isinstance(item, str) or not item.strip():
            rep.err(where, f"{field}[{i}] must be a non-empty string, got {item!r}")


def check_id_list(rep: Report, where: str, field: str, val) -> None:
    if val is None:
        return
    if not isinstance(val, list):
        rep.err(where, f"{field} must be a list or null, got {type(val).__name__}")
        return
    for i, item in enumerate(val):
        if not isinstance(item, str) or not ID_RE.match(item):
            rep.err(where, f"{field}[{i}] {item!r} must match {ID_RE.pattern}")


def check_id_field(rep: Report, where: str, val, seen=None, required=True) -> None:
    if val is None:
        if required:
            rep.err(where, "id is required")
        return
    if not isinstance(val, str) or not ID_RE.match(val):
        rep.err(where, f"id {val!r} must match {ID_RE.pattern}")
        return
    if seen is not None:
        if val in seen:
            rep.err(where, f"duplicate id {val!r}")
        else:
            seen.add(val)


def add_ref(refs: list, where: str, kind: str, value) -> None:
    if value is None:
        return
    if isinstance(value, list):
        for item in value:
            add_ref(refs, where, kind, item)
        return
    refs.append((where, kind, value))


def resolve_refs(rep: Report, refs: list, ids_by_kind: dict, labels: dict) -> None:
    for where, kind, value in refs:
        ids = ids_by_kind.get(kind)
        if ids is None or value not in ids:
            rep.err(where, f"unknown {labels.get(kind, kind)} reference {value!r}")


def is_http_string(val) -> bool:
    return isinstance(val, str) and val.startswith(("http://", "https://"))


def _collect_urls_from_value(value, where: str, out: dict, key=None) -> None:
    if isinstance(value, str):
        if key in URL_BEARING_KEYS and is_http_string(value):
            out.setdefault(value, []).append(where)
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            _collect_urls_from_value(item, f"{where}[{i}]", out, key=key)
        return
    if isinstance(value, dict):
        for item_key, item in value.items():
            _collect_urls_from_value(item, f"{where}.{item_key}", out, key=item_key)


def collect_setup_v2_urls(setup: dict, sid: str) -> dict:
    """Nested schema-v2 source URLs that check_links.py must fetch."""
    out: dict[str, list[str]] = {}
    base = f"setups/{sid}"
    for key in ("variation", "engine", "run", "requirements", "interconnect",
                "serving", "correctness", "known_failures",
                "capability_observations", "evidence"):
        if key in setup:
            _collect_urls_from_value(setup[key], f"{base}.{key}", out)
    for i, m in enumerate(setup.get("measurements") or []):
        if isinstance(m, dict):
            for key in ("conditions", "evidence"):
                if key in m:
                    _collect_urls_from_value(m[key], f"{base}:measurements[{i}].{key}", out)
    return out


def collect_technique_urls(tid: str, technique: dict) -> dict:
    out: dict[str, list[str]] = {}
    _collect_urls_from_value(technique.get("canonical_sources"), f"techniques/{tid}.canonical_sources", out)
    return out


def is_speed_metric(metric) -> bool:
    return isinstance(metric, str) and metric.startswith(SPEED_METRIC_PREFIXES)


def derive_condition_completeness(measurement: dict):
    """Display-only derived axis. Never written back into data."""
    metric = measurement.get("metric")
    if not is_speed_metric(metric):
        return None
    conditions = measurement.get("conditions") or {}
    evidence = measurement.get("evidence") or {}
    method_grade = evidence.get("method_grade")
    signals = [
        bool(conditions.get("context_tokens") or conditions.get("context_label")
             or measurement.get("context")),
        conditions.get("workload") is not None,
        measurement.get("concurrency") is not None or conditions.get("concurrency") is not None,
        bool(measurement.get("method") or (method_grade and method_grade != "unspecified")),
        any(conditions.get(key) is not None for key in (
            "spec_decode", "offload_strategy", "kv_dtype", "hardware_count",
            "hardware_variant_id", "backend", "power_limit_pct", "clock_state",
            "greedy", "thinking", "temperature", "warm", "client",
        )),
    ]
    if all(signals):
        return "full"
    if any(signals):
        return "partial"
    return "insufficient"


def derive_comparison_completeness(comparison: dict):
    constant = comparison.get("conditions_constant") or []
    unstated = comparison.get("conditions_unstated") or []
    if constant and not unstated:
        return "full"
    if constant or unstated:
        return "partial"
    return "insufficient"


def derive_measurement_flags(measurement: dict) -> dict:
    """Build/UI-visible derived properties. Validator never stores them."""
    evidence = measurement.get("evidence") or {}
    method_grade = evidence.get("method_grade")
    wall_clock = method_grade == "wall_clock_division"
    speed = is_speed_metric(measurement.get("metric"))
    return {
        "condition_completeness": derive_condition_completeness(measurement),
        "method_grade": method_grade,
        "method_note_required": wall_clock,
        "headline_eligible": bool(speed and not wall_clock),
        "comparability_eligible": not wall_clock,
    }


def has_v2_fields(setup: dict) -> bool:
    if any(key in setup for key in V2_SETUP_KEYS):
        return True
    for key, v2_keys in (
        ("variation", V2_VARIATION_KEYS),
        ("engine", V2_ENGINE_KEYS),
        ("run", V2_RUN_KEYS),
        ("requirements", V2_REQUIREMENTS_KEYS),
    ):
        block = setup.get(key)
        if isinstance(block, dict) and (set(block) & v2_keys):
            return True
    for ref in setup.get("hardware") or []:
        if isinstance(ref, dict) and (set(ref) & V2_HARDWARE_REF_KEYS):
            return True
    for src in setup.get("sources") or []:
        if isinstance(src, dict) and (set(src) & V2_SOURCE_KEYS):
            return True
    for m in setup.get("measurements") or []:
        if isinstance(m, dict) and (set(m) & (V2_MEASUREMENT_KEYS - MEASUREMENT_ID_EXEMPT_KEYS)):
            return True
    return False


def check_generic_source_object(rep: Report, where: str, src, require_durable=True) -> None:
    if isinstance(src, str):
        check_source_value(rep, where, "source", src, required=True)
        return
    if not check_keys(rep, where, src, ALLOWED_GENERIC_SOURCE_OBJECT_KEYS, label="source"):
        return
    check_optional_url(rep, where, "url", src.get("url"))
    check_archive_path(rep, where, src.get("archive_path"))
    check_date_field(rep, where, "retrieved", src.get("retrieved"))
    check_date_field(rep, where, "date", src.get("date"))
    if src.get("kind") is not None:
        check_enum(rep, where, "kind", src.get("kind"), SOURCE_KINDS)
    if require_durable and not (src.get("url") or src.get("archive_path") or src.get("locator")):
        rep.err(where, "source requires url, archive_path, or locator")


def check_source_list(rep: Report, where: str, field: str, val, require_durable=True) -> None:
    if val is None:
        return
    if not isinstance(val, list):
        rep.err(where, f"{field} must be a list or null")
        return
    for i, item in enumerate(val):
        check_generic_source_object(rep, f"{where}.{field}[{i}]", item, require_durable=require_durable)


def check_revision_object(rep: Report, where: str, obj, allowed, require_repo=False) -> None:
    if obj is None:
        return
    if not check_keys(rep, where, obj, allowed, label="revision"):
        return
    check_nonempty_str(rep, where, "commit", obj.get("commit"))
    check_nonempty_str(rep, where, "branch", obj.get("branch"))
    check_nonempty_str(rep, where, "tag", obj.get("tag"))
    check_date_field(rep, where, "anchor_date", obj.get("anchor_date"))
    check_date_field(rep, where, "retrieved", obj.get("retrieved"))
    check_enum(rep, where, "resolution", obj.get("resolution"), REVISION_RESOLUTIONS)
    check_bool(rep, where, "ambiguous", obj.get("ambiguous"))
    check_source_value(rep, where, "source", obj.get("source"))
    check_nonempty_str(rep, where, "locator", obj.get("locator"))
    check_nonempty_str(rep, where, "note", obj.get("note"))
    if require_repo:
        check_source_value(rep, where, "repo", obj.get("repo"), required=True)
        check_optional_url(rep, where, "repo", obj.get("repo"))
    commits = obj.get("commits")
    if commits is not None:
        if not isinstance(commits, list) or not commits:
            rep.err(where, "commits must be a non-empty list or null")
        else:
            for i, commit in enumerate(commits):
                if not isinstance(commit, str) or not commit.strip():
                    rep.err(where, f"commits[{i}] must be a non-empty string")
    resolution = obj.get("resolution")
    ambiguous = obj.get("ambiguous")
    if resolution == "exact" and ambiguous is True:
        rep.err(where, "resolution 'exact' cannot be ambiguous")
    if resolution == "earliest_commit_after_anchor" and ambiguous is not True:
        rep.err(where, "resolution 'earliest_commit_after_anchor' requires ambiguous: true")


def check_technique(rep: Report, tid: str, technique: dict) -> None:
    w = f"techniques/{tid}"
    if technique.get("id", tid) != tid:
        rep.err(w, f"filename {tid} != id {technique.get('id')!r}")
    check_id_field(rep, w, tid)
    if not check_keys(rep, w, technique, ALLOWED_TECHNIQUE_KEYS,
                      required=("id", "name", "category", "canonical_description",
                                "canonical_sources", "status"),
                      label="technique packet"):
        return
    check_enum(rep, w, "category", technique.get("category"), TECHNIQUE_CATEGORIES, required=True)
    check_enum(rep, w, "status", technique.get("status"), TECHNIQUE_STATUSES, required=True)
    check_nonempty_str(rep, w, "mechanism", technique.get("mechanism"))
    check_str_list(rep, w, "constraints", technique.get("constraints"))
    check_str_list(rep, w, "tradeoffs", technique.get("tradeoffs"))
    check_str_list(rep, w, "re_review_triggers", technique.get("re_review_triggers"))
    check_date_field(rep, w, "updated", technique.get("updated"))
    sources = technique.get("canonical_sources")
    if not isinstance(sources, list) or not sources:
        rep.err(w, "canonical_sources must be a non-empty list")
        return
    for i, src in enumerate(sources):
        sw = f"{w}.canonical_sources[{i}]"
        if not check_keys(rep, sw, src, ALLOWED_TECHNIQUE_SOURCE_KEYS, label="technique source"):
            continue
        check_optional_url(rep, sw, "url", src.get("url"))
        check_archive_path(rep, sw, src.get("archive_path"))
        check_date_field(rep, sw, "retrieved", src.get("retrieved"))
        check_date_field(rep, sw, "date", src.get("date"))
        check_nonempty_str(rep, sw, "locator", src.get("locator"))
        check_nonempty_str(rep, sw, "note", src.get("note"))
        if src.get("kind") is not None:
            check_enum(rep, sw, "kind", src.get("kind"), SOURCE_KINDS)
        if not (src.get("url") or src.get("archive_path")):
            rep.err(sw, "technique source requires url or archive_path")


def check_setup_v2(rep: Report, sid: str, s: dict, techniques: dict,
                   hardware: dict, pub_ids: set, legacy_pin_warnings: bool = False) -> None:
    w = f"setups/{sid}"
    check_keys(rep, w, s, ALLOWED_SETUP_KEYS, label="setup")
    schema_version = s.get("schema_version")
    if schema_version is not None and schema_version != SCHEMA_VERSION:
        rep.err(w, f"schema_version {schema_version!r} must be {SCHEMA_VERSION} when present")
    if schema_version is None and has_v2_fields(s):
        rep.err(w, "record uses schema_version-2 fields; a lone measurements[].id is exempt, "
                   "but other v2 blocks require schema_version: 2")
    is_v2 = schema_version == SCHEMA_VERSION

    refs: list[tuple[str, str, str]] = []
    ids_by_kind = {
        "lineage": set(),
        "measurement": set(),
        "comparison": set(),
        "claim": set(),
        "contradiction": set(),
        "open_question": set(),
        "technique": set(techniques),
    }
    labels = {
        "lineage": "evidence.lineages[] id",
        "measurement": "measurements[].id",
        "comparison": "evidence.comparisons[] id",
        "claim": "evidence.claims[] id",
        "contradiction": "evidence.contradictions[] id",
        "open_question": "evidence.open_questions[] id",
        "technique": "technique registry id",
    }

    measurements = s.get("measurements") or []
    for i, m in enumerate(measurements):
        mw = f"{w} measurements[{i}]"
        if not isinstance(m, dict):
            rep.err(mw, f"measurement must be an object, got {type(m).__name__}")
            continue
        check_keys(rep, mw, m, ALLOWED_MEASUREMENT_KEYS, label="measurement")
        mid = m.get("id")
        if mid is not None:
            check_id_field(rep, mw, mid, seen=ids_by_kind["measurement"])
        elif is_v2:
            rep.err(mw, "schema_version-2 records require a stable measurement id")

    for i, src in enumerate(s.get("sources") or []):
        sw = f"{w} sources[{i}]"
        if not isinstance(src, dict):
            continue
        check_keys(rep, sw, src, ALLOWED_SOURCE_KEYS, label="source")
        check_archive_path(rep, sw, src.get("archive_path"))
        check_date_field(rep, sw, "retrieved", src.get("retrieved"))
        check_nonempty_str(rep, sw, "locator", src.get("locator"))
        check_nonempty_str(rep, sw, "quote", src.get("quote"))
        add_ref(refs, sw, "lineage", src.get("lineage_id"))

    v = s.get("variation") or {}
    if isinstance(v, dict):
        check_keys(rep, f"{w}.variation", v, ALLOWED_VARIATION_KEYS, label="variation")
        check_nonempty_str(rep, f"{w}.variation", "revision", v.get("revision"))
        check_date_field(rep, f"{w}.variation", "revision_date", v.get("revision_date"))
        check_optional_url(rep, f"{w}.variation", "snapshot_url", v.get("snapshot_url"))
        check_nonempty_str(rep, f"{w}.variation", "revision_note", v.get("revision_note"))

    e = s.get("engine") or {}
    runtime_pin = False
    exact_runtime_pin = False
    unresolved_binary_with_review = False
    if isinstance(e, dict):
        ew = f"{w}.engine"
        check_keys(rep, ew, e, ALLOWED_ENGINE_KEYS, label="engine")
        if "bundled" in e and not isinstance(e.get("bundled"), bool):
            rep.err(ew, "engine.bundled must be true or false")
        check_nonempty_str(rep, ew, "version", e.get("version"))
        check_nonempty_str(rep, ew, "image_digest", e.get("image_digest"))
        check_enum(rep, ew, "backend", e.get("backend"), BACKENDS)
        if e.get("version") or e.get("image_digest"):
            runtime_pin = True
        if e.get("image_digest"):
            exact_runtime_pin = True

        fork_revision = e.get("fork_revision")
        if fork_revision is not None:
            runtime_pin = True
            check_revision_object(rep, f"{ew}.fork_revision", fork_revision,
                                  ALLOWED_FORK_REVISION_KEYS, require_repo=True)
            if isinstance(fork_revision, dict) and fork_revision.get("resolution") in {"exact", "tag", "image_digest"}:
                exact_runtime_pin = True

        patches = e.get("kernel_patches")
        if patches is not None:
            if not isinstance(patches, list):
                rep.err(f"{ew}.kernel_patches", "must be a list or null")
            else:
                for i, patch in enumerate(patches):
                    pw = f"{ew}.kernel_patches[{i}]"
                    if not check_keys(rep, pw, patch, ALLOWED_KERNEL_PATCH_KEYS,
                                      required=("purpose", "source"), label="kernel patch"):
                        continue
                    check_nonempty_str(rep, pw, "id", patch.get("id"))
                    check_nonempty_str(rep, pw, "pr", patch.get("pr"))
                    check_nonempty_str(rep, pw, "commit", patch.get("commit"))
                    check_source_value(rep, pw, "source", patch.get("source"), required=True)
                    check_nonempty_str(rep, pw, "locator", patch.get("locator"))

        env = e.get("environment")
        if env is not None:
            envw = f"{ew}.environment"
            if check_keys(rep, envw, env, ALLOWED_ENVIRONMENT_KEYS, label="environment"):
                for field in ("os", "driver", "cuda", "rocm", "metal", "python", "source", "locator", "note"):
                    check_nonempty_str(rep, envw, field, env.get(field))
                check_date_field(rep, envw, "date", env.get("date"))
                packages = env.get("packages")
                if packages is not None:
                    if not isinstance(packages, dict):
                        rep.err(envw, "packages must be an object or null")
                    else:
                        for name, spec in packages.items():
                            if not isinstance(name, str) or not name.strip():
                                rep.err(envw, f"package name {name!r} must be a non-empty string")
                            if not isinstance(spec, str) or not spec.strip():
                                rep.err(envw, f"package {name!r} spec must be a non-empty string")

        profile = e.get("spec_decode_profile")
        if profile is not None:
            pw = f"{ew}.spec_decode_profile"
            if check_keys(rep, pw, profile, ALLOWED_SPEC_PROFILE_KEYS, label="spec_decode_profile"):
                method = profile.get("method")
                check_nonempty_str(rep, pw, "method", method)
                if method is not None and e.get("spec_decode") not in (None, method):
                    rep.err(pw, f"method {method!r} disagrees with engine.spec_decode {e.get('spec_decode')!r}")
                if e.get("spec_decode") in (None, "none") and method not in (None, "none"):
                    rep.err(pw, f"spec_decode_profile.method {method!r} requires engine.spec_decode")
                check_nonempty_str(rep, pw, "draft_checkpoint", profile.get("draft_checkpoint"))
                check_nonempty_str(rep, pw, "draft_revision", profile.get("draft_revision"))
                check_nonempty_str(rep, pw, "draft_quant", profile.get("draft_quant"))
                check_number(rep, pw, "max_draft_tokens", profile.get("max_draft_tokens"),
                             positive=True, integer=True)
                acceptance = profile.get("acceptance_rate_pct")
                check_number(rep, pw, "acceptance_rate_pct", acceptance, minimum=0, maximum=100)
                if acceptance is not None and not profile.get("source"):
                    rep.err(pw, "acceptance_rate_pct requires a source; it may not be inferred from speedup")
                check_nonempty_str(rep, pw, "acceptance_basis", profile.get("acceptance_basis"))
                check_source_value(rep, pw, "source", profile.get("source"))
                check_nonempty_str(rep, pw, "locator", profile.get("locator"))
                check_date_field(rep, pw, "date", profile.get("date"))
                if profile.get("provenance") is not None:
                    check_enum(rep, pw, "provenance", profile.get("provenance"), PROVENANCE)
                curve = profile.get("decay_curve")
                if curve is not None:
                    if not isinstance(curve, list):
                        rep.err(f"{pw}.decay_curve", "must be a list or null")
                    else:
                        for i, point in enumerate(curve):
                            dw = f"{pw}.decay_curve[{i}]"
                            if not check_keys(rep, dw, point, ALLOWED_DECAY_POINT_KEYS, label="decay point"):
                                continue
                            for field in ("context_tokens", "prompt_tokens", "completion_tokens"):
                                check_number(rep, dw, field, point.get(field), positive=True, integer=True)
                            check_number(rep, dw, "acceptance_rate_pct", point.get("acceptance_rate_pct"),
                                         minimum=0, maximum=100)
                            check_number(rep, dw, "decode_per_stream_tok_s", point.get("decode_per_stream_tok_s"),
                                         positive=True)
                            check_number(rep, dw, "prefill_tok_s", point.get("prefill_tok_s"), positive=True)
                            check_source_value(rep, dw, "source", point.get("source"))
                            check_nonempty_str(rep, dw, "locator", point.get("locator"))
                            check_date_field(rep, dw, "date", point.get("date"))
                            check_nonempty_str(rep, dw, "note", point.get("note"))

    run = s.get("run") or {}
    if isinstance(run, dict):
        rw = f"{w}.run"
        check_keys(rep, rw, run, ALLOWED_RUN_KEYS, label="run")
        repo_revision = run.get("repo_revision")
        if repo_revision is not None:
            runtime_pin = True
            check_revision_object(rep, f"{rw}.repo_revision", repo_revision, ALLOWED_REPO_REVISION_KEYS)
            if isinstance(repo_revision, dict):
                if repo_revision.get("resolution") in {"exact", "tag", "image_digest"}:
                    exact_runtime_pin = True
                commit = repo_revision.get("commit")
                legacy_commit = run.get("repo_commit")
                if commit and legacy_commit and not (
                    str(commit).startswith(str(legacy_commit))
                    or str(legacy_commit).startswith(str(commit))
                ):
                    rep.err(rw, f"run.repo_commit {legacy_commit!r} and repo_revision.commit {commit!r} disagree")

    req = s.get("requirements") or {}
    offload = None
    if isinstance(req, dict):
        reqw = f"{w}.requirements"
        check_keys(rep, reqw, req, ALLOWED_REQUIREMENTS_KEYS, label="requirements")
        profile = req.get("memory_profile")
        if profile is not None:
            pw = f"{reqw}.memory_profile"
            if check_keys(rep, pw, profile, ALLOWED_MEMORY_PROFILE_KEYS, label="memory_profile"):
                check_nonempty_str(rep, pw, "kv_dtype", profile.get("kv_dtype"))
                check_number(rep, pw, "gpu_memory_utilization", profile.get("gpu_memory_utilization"),
                             minimum=0, maximum=1)
                check_date_field(rep, pw, "date", profile.get("date"))
                check_source_value(rep, pw, "source", profile.get("source"))
                check_nonempty_str(rep, pw, "locator", profile.get("locator"))
                if profile.get("provenance") is not None:
                    check_enum(rep, pw, "provenance", profile.get("provenance"), PROVENANCE)
                entries = profile.get("entries")
                if not isinstance(entries, list) or not entries:
                    rep.err(pw, "entries must be a non-empty list")
                else:
                    for i, entry in enumerate(entries):
                        entryw = f"{pw}.entries[{i}]"
                        if not check_keys(rep, entryw, entry, ALLOWED_MEMORY_ENTRY_KEYS,
                                          required=("component", "value", "unit", "source"),
                                          label="memory entry"):
                            continue
                        check_enum(rep, entryw, "component", entry.get("component"), MEMORY_COMPONENTS, required=True)
                        check_number(rep, entryw, "value", entry.get("value"), required=True, positive=True)
                        check_enum(rep, entryw, "unit", entry.get("unit"), MEMORY_UNITS, required=True)
                        check_enum(rep, entryw, "scope", entry.get("scope"), MEMORY_SCOPES, required=True)
                        if entry.get("location") is not None:
                            check_enum(rep, entryw, "location", entry.get("location"), MEMORY_LOCATIONS)
                        check_bool(rep, entryw, "pageable", entry.get("pageable"))
                        for field in ("context_tokens", "kv_tokens"):
                            check_number(rep, entryw, field, entry.get(field), positive=True, integer=True)
                        check_source_value(rep, entryw, "source", entry.get("source"), required=True)
                        check_nonempty_str(rep, entryw, "locator", entry.get("locator"))
                        check_date_field(rep, entryw, "date", entry.get("date"))
                        if entry.get("provenance") is not None:
                            check_enum(rep, entryw, "provenance", entry.get("provenance"), PROVENANCE)

        offload = req.get("offload")
        if offload is not None:
            ow = f"{reqw}.offload"
            if check_keys(rep, ow, offload, ALLOWED_OFFLOAD_KEYS, required=("strategy", "source"),
                          label="offload"):
                strategy = offload.get("strategy")
                check_enum(rep, ow, "strategy", strategy, OFFLOAD_STRATEGIES, required=True)
                components = offload.get("components")
                if components is not None:
                    if not isinstance(components, list):
                        rep.err(ow, "components must be a list or null")
                    else:
                        for i, component in enumerate(components):
                            check_enum(rep, f"{ow}.components[{i}]", "component", component,
                                       MEMORY_COMPONENTS, required=True)
                check_bool(rep, ow, "intentional", offload.get("intentional"))
                cold = offload.get("cold_start_effect")
                check_nonempty_str(rep, ow, "cold_start_effect", cold)
                if isinstance(cold, str) and EXPECTED_LANGUAGE_RE.search(cold):
                    rep.err(ow, "cold_start_effect may record only an observed/measured outcome; "
                                "expected mechanisms belong in a c1 evidence.claims[] entry")
                if cold is not None and not offload.get("source"):
                    rep.err(ow, "cold_start_effect requires an explicit source")
                if strategy == "none":
                    if components:
                        rep.err(ow, "offload.strategy 'none' cannot list offloaded components")
                    if not offload.get("source"):
                        rep.err(ow, "offload.strategy 'none' requires an explicit source; "
                                    "absence of offload prose is not evidence")
                check_source_value(rep, ow, "source", offload.get("source"), required=True)
                check_nonempty_str(rep, ow, "locator", offload.get("locator"))
                check_date_field(rep, ow, "date", offload.get("date"))
                if offload.get("provenance") is not None:
                    check_enum(rep, ow, "provenance", offload.get("provenance"), PROVENANCE)

    interconnect = s.get("interconnect")
    if interconnect is not None:
        iw = f"{w}.interconnect"
        if check_keys(rep, iw, interconnect, ALLOWED_INTERCONNECT_KEYS, label="interconnect"):
            check_enum(rep, iw, "kind", interconnect.get("kind"), INTERCONNECT_KINDS)
            check_enum(rep, iw, "role", interconnect.get("role"), INTERCONNECT_ROLES)
            check_nonempty_str(rep, iw, "topology", interconnect.get("topology"))
            check_number(rep, iw, "bandwidth_gbs", interconnect.get("bandwidth_gbs"), positive=True)
            check_bool(rep, iw, "requires_same_fabric", interconnect.get("requires_same_fabric"))
            check_source_value(rep, iw, "source", interconnect.get("source"))
            check_nonempty_str(rep, iw, "locator", interconnect.get("locator"))
            check_date_field(rep, iw, "date", interconnect.get("date"))
            if interconnect.get("provenance") is not None:
                check_enum(rep, iw, "provenance", interconnect.get("provenance"), PROVENANCE)

    serving = s.get("serving")
    if serving is not None:
        sw = f"{w}.serving"
        if check_keys(rep, sw, serving, ALLOWED_SERVING_KEYS, label="serving"):
            check_enum(rep, sw, "workload", serving.get("workload"), SERVING_WORKLOADS)
            check_enum(rep, sw, "batching", serving.get("batching"), SERVING_BATCHING)
            check_nonempty_str(rep, sw, "scheduler", serving.get("scheduler"))
            check_bool(rep, sw, "prefix_cache", serving.get("prefix_cache"))
            check_bool(rep, sw, "session_affinity", serving.get("session_affinity"))
            check_number(rep, sw, "concurrency_ceiling", serving.get("concurrency_ceiling"),
                         positive=True, integer=True)
            check_enum(rep, sw, "ceiling_effect", serving.get("ceiling_effect"), CEILING_EFFECTS)
            check_nonempty_str(rep, sw, "ceiling_reason", serving.get("ceiling_reason"))
            check_source_value(rep, sw, "source", serving.get("source"))
            check_nonempty_str(rep, sw, "locator", serving.get("locator"))
            check_date_field(rep, sw, "date", serving.get("date"))
            if serving.get("provenance") is not None:
                check_enum(rep, sw, "provenance", serving.get("provenance"), PROVENANCE)

    correctness = s.get("correctness")
    quality_linked_ids = set()
    if correctness is not None:
        cw = f"{w}.correctness"
        if check_keys(rep, cw, correctness, ALLOWED_CORRECTNESS_KEYS, label="correctness"):
            check_bool(rep, cw, "output_checked", correctness.get("output_checked"))
            check_nonempty_str(rep, cw, "known_output_failure", correctness.get("known_output_failure"))
            check_id_list(rep, cw, "quality_measurement_ids", correctness.get("quality_measurement_ids"))
            add_ref(refs, cw, "measurement", correctness.get("quality_measurement_ids"))
            quality_linked_ids.update(correctness.get("quality_measurement_ids") or [])
            checks = correctness.get("checks")
            if checks is not None:
                if not isinstance(checks, list):
                    rep.err(f"{cw}.checks", "must be a list or null")
                else:
                    check_seen = set()
                    for i, chk in enumerate(checks):
                        chw = f"{cw}.checks[{i}]"
                        if not check_keys(rep, chw, chk, ALLOWED_CORRECTNESS_CHECK_KEYS,
                                          required=("kind", "result", "source"), label="correctness check"):
                            continue
                        check_id_field(rep, chw, chk.get("id"), seen=check_seen, required=False)
                        check_enum(rep, chw, "kind", chk.get("kind"), CORRECTNESS_KINDS, required=True)
                        check_enum(rep, chw, "result", chk.get("result"), CORRECTNESS_RESULTS, required=True)
                        check_nonempty_str(rep, chw, "scope", chk.get("scope"))
                        check_number(rep, chw, "context_tokens", chk.get("context_tokens"),
                                     positive=True, integer=True)
                        check_id_list(rep, chw, "measurement_ids", chk.get("measurement_ids"))
                        add_ref(refs, chw, "measurement", chk.get("measurement_ids"))
                        quality_linked_ids.update(chk.get("measurement_ids") or [])
                        check_source_value(rep, chw, "source", chk.get("source"), required=True)
                        check_nonempty_str(rep, chw, "locator", chk.get("locator"))
                        check_nonempty_str(rep, chw, "quote", chk.get("quote"))
                        check_date_field(rep, chw, "date", chk.get("date"))
                        add_ref(refs, chw, "lineage", chk.get("lineage_id"))

    failures = s.get("known_failures")
    if failures is not None:
        if not isinstance(failures, list):
            rep.err(f"{w}.known_failures", "must be a list or null")
        else:
            failure_seen = set()
            for i, failure in enumerate(failures):
                fw = f"{w}.known_failures[{i}]"
                if not check_keys(rep, fw, failure, ALLOWED_KNOWN_FAILURE_KEYS,
                                  required=("stage", "trigger", "effect", "status", "source"),
                                  label="known failure"):
                    continue
                check_id_field(rep, fw, failure.get("id"), seen=failure_seen, required=False)
                check_enum(rep, fw, "stage", failure.get("stage"), FAILURE_STAGES, required=True)
                check_enum(rep, fw, "status", failure.get("status"), FAILURE_STATUSES, required=True)
                check_date_field(rep, fw, "observed_date", failure.get("observed_date"))
                check_date_field(rep, fw, "date", failure.get("date"))
                check_source_value(rep, fw, "source", failure.get("source"), required=True)
                check_nonempty_str(rep, fw, "locator", failure.get("locator"))
                check_nonempty_str(rep, fw, "quote", failure.get("quote"))
                check_nonempty_str(rep, fw, "resolution", failure.get("resolution"))
                check_id_list(rep, fw, "measurement_ids", failure.get("measurement_ids"))
                add_ref(refs, fw, "measurement", failure.get("measurement_ids"))
                add_ref(refs, fw, "lineage", failure.get("lineage_id"))

    observations = s.get("capability_observations")
    if observations is not None:
        if not isinstance(observations, list):
            rep.err(f"{w}.capability_observations", "must be a list or null")
        else:
            for i, obs in enumerate(observations):
                ow = f"{w}.capability_observations[{i}]"
                if not check_keys(rep, ow, obs, ALLOWED_CAPABILITY_OBSERVATION_KEYS,
                                  required=("capability", "status"), label="capability observation"):
                    continue
                check_enum(rep, ow, "capability", obs.get("capability"), CAPABILITY_NAMES, required=True)
                status = obs.get("status")
                check_enum(rep, ow, "status", status, CAPABILITY_STATUSES, required=True)
                if status != "unknown" and not obs.get("source"):
                    rep.err(ow, "capability observation requires a source unless status is 'unknown'")
                check_nonempty_str(rep, ow, "trigger", obs.get("trigger"))
                check_nonempty_str(rep, ow, "scope", obs.get("scope"))
                check_source_value(rep, ow, "source", obs.get("source"))
                check_nonempty_str(rep, ow, "locator", obs.get("locator"))
                check_nonempty_str(rep, ow, "quote", obs.get("quote"))
                check_date_field(rep, ow, "date", obs.get("date"))
                check_id_list(rep, ow, "measurement_ids", obs.get("measurement_ids"))
                add_ref(refs, ow, "measurement", obs.get("measurement_ids"))
                add_ref(refs, ow, "lineage", obs.get("lineage_id"))

    evidence = s.get("evidence")
    comparisons = {}
    claims = {}
    open_questions = []
    comparison_ids = ids_by_kind["comparison"]
    if evidence is not None:
        evw = f"{w}.evidence"
        if check_keys(rep, evw, evidence, ALLOWED_EVIDENCE_KEYS, label="evidence"):
            check_nonempty_str(rep, evw, "rubric_version", evidence.get("rubric_version"))
            check_str_list(rep, evw, "re_review_triggers", evidence.get("re_review_triggers"))

            lineages = evidence.get("lineages")
            if lineages is not None:
                if not isinstance(lineages, list):
                    rep.err(f"{evw}.lineages", "must be a list or null")
                else:
                    for i, lineage in enumerate(lineages):
                        lw = f"{evw}.lineages[{i}]"
                        if not check_keys(rep, lw, lineage, ALLOWED_LINEAGE_KEYS,
                                          required=("id", "actor", "sources"), label="lineage"):
                            continue
                        check_id_field(rep, lw, lineage.get("id"), seen=ids_by_kind["lineage"])
                        publisher = lineage.get("publisher")
                        if publisher is not None and publisher not in pub_ids:
                            rep.err(lw, f"unknown publisher {publisher!r}")
                        check_nonempty_str(rep, lw, "kind", lineage.get("kind"))
                        check_archive_path(rep, lw, lineage.get("archive_path"))
                        check_date_field(rep, lw, "retrieved", lineage.get("retrieved"))
                        check_nonempty_str(rep, lw, "locator", lineage.get("locator"))
                        check_nonempty_str(rep, lw, "note", lineage.get("note"))
                        sources = lineage.get("sources")
                        if not isinstance(sources, list) or not sources:
                            rep.err(lw, "sources must be a non-empty list")
                        else:
                            for j, src in enumerate(sources):
                                check_generic_source_object(rep, f"{lw}.sources[{j}]", src)

            comps = evidence.get("comparisons")
            if comps is not None:
                if not isinstance(comps, list):
                    rep.err(f"{evw}.comparisons", "must be a list or null")
                else:
                    for i, cmp in enumerate(comps):
                        cw = f"{evw}.comparisons[{i}]"
                        if not check_keys(rep, cw, cmp, ALLOWED_COMPARISON_KEYS,
                                          required=("id", "question", "a", "b", "result",
                                                    "contrast_kind", "evidence_level",
                                                    "lineage_id", "source", "locator"),
                                          label="comparison"):
                            continue
                        cid = cmp.get("id")
                        check_id_field(rep, cw, cid, seen=comparison_ids)
                        if isinstance(cid, str):
                            comparisons[cid] = cmp
                        level = cmp.get("level") or cmp.get("evidence_level")
                        check_enum(rep, cw, "evidence_level", cmp.get("evidence_level"),
                                   EVIDENCE_LEVELS, required=True)
                        contrast = cmp.get("contrast_kind")
                        check_enum(rep, cw, "contrast_kind", contrast, CONTRAST_KINDS, required=True)
                        check_enum(rep, cw, "result", cmp.get("result"), COMPARISON_RESULTS, required=True)
                        if cmp.get("effect_metric") is not None:
                            check_enum(rep, cw, "effect_metric", cmp.get("effect_metric"), METRICS)
                        check_nonempty_str(rep, cw, "effect_direction", cmp.get("effect_direction"))
                        check_nonempty_str(rep, cw, "variable", cmp.get("variable"))
                        check_nonempty_str(rep, cw, "candidate_variable", cmp.get("candidate_variable"))
                        check_str_list(rep, cw, "conditions_constant", cmp.get("conditions_constant"))
                        check_str_list(rep, cw, "conditions_unstated", cmp.get("conditions_unstated"))
                        check_source_value(rep, cw, "source", cmp.get("source"), required=True)
                        check_nonempty_str(rep, cw, "locator", cmp.get("locator"), required=True)
                        check_nonempty_str(rep, cw, "quote", cmp.get("quote"))
                        check_date_field(rep, cw, "date", cmp.get("date"))
                        if cmp.get("provenance") is not None:
                            check_enum(rep, cw, "provenance", cmp.get("provenance"), PROVENANCE)
                        if cmp.get("method_grade") is not None:
                            check_enum(rep, cw, "method_grade", cmp.get("method_grade"), METHOD_GRADES)
                            if cmp.get("method_grade") == "wall_clock_division" and not cmp.get("method_note"):
                                rep.err(cw, "method_grade wall_clock_division requires method_note")
                        check_nonempty_str(rep, cw, "method_note", cmp.get("method_note"))
                        check_nonempty_str(rep, cw, "note", cmp.get("note"))
                        add_ref(refs, cw, "lineage", cmp.get("lineage_id"))
                        add_ref(refs, cw, "open_question", cmp.get("open_question_ids"))
                        check_str_list(rep, cw, "re_review_triggers", cmp.get("re_review_triggers"))

                        if "condition_completeness" in cmp:
                            rep.err(cw, "condition_completeness is derived only and must not be stored")

                        for side_name in ("a", "b"):
                            side = cmp.get(side_name)
                            sw = f"{cw}.{side_name}"
                            if not check_keys(rep, sw, side, ALLOWED_COMPARISON_SIDE_KEYS,
                                              required=("label", "measurement_id"), label="comparison side"):
                                continue
                            add_ref(refs, sw, "measurement", side.get("measurement_id"))

                        variable = cmp.get("variable")
                        candidate = cmp.get("candidate_variable")
                        constant = cmp.get("conditions_constant") or []
                        unstated = cmp.get("conditions_unstated") or []
                        binary_status = cmp.get("binary_provenance_status")
                        if binary_status is not None:
                            check_enum(rep, cw, "binary_provenance_status", binary_status,
                                       BINARY_PROVENANCE_STATUSES)
                        if contrast == "uncontrolled" and variable:
                            rep.err(cw, "uncontrolled contrasts may use candidate_variable, not a settled variable")
                        if contrast == "claimed" and variable:
                            rep.err(cw, "claimed contrasts may use candidate_variable, not a settled variable")
                        if contrast == "single_variable":
                            if not variable:
                                rep.err(cw, "single_variable requires variable")
                            if not constant:
                                rep.err(cw, "single_variable requires non-empty conditions_constant")
                        if not variable and not candidate and contrast in {"uncontrolled", "bundle", "single_variable", "claimed"}:
                            rep.err(cw, f"{contrast} comparison requires variable or candidate_variable")

                        derived_completeness = derive_comparison_completeness(cmp)
                        gate = cmp.get("promotion_gate")
                        if gate is not None:
                            gw = f"{cw}.promotion_gate"
                            if check_keys(rep, gw, gate, ALLOWED_PROMOTION_GATE_KEYS,
                                          required=("target_level", "target_contrast_kind",
                                                    "required_facts", "status"),
                                          label="promotion gate"):
                                check_enum(rep, gw, "target_level", gate.get("target_level"), EVIDENCE_LEVELS, required=True)
                                check_enum(rep, gw, "target_contrast_kind", gate.get("target_contrast_kind"),
                                           CONTRAST_KINDS, required=True)
                                check_str_list(rep, gw, "required_facts", gate.get("required_facts"), allow_empty=False)
                                check_nonempty_str(rep, gw, "status", gate.get("status"), required=True)
                                check_nonempty_str(rep, gw, "note", gate.get("note"))
                        elif contrast == "uncontrolled" and level == "c2_observation":
                            rep.warn(cw, "uncontrolled C2 comparison has no promotion_gate; add one when it could become C3")

                        reproductions = cmp.get("independent_reproductions")
                        reproduction_lineages = set()
                        if reproductions is not None:
                            if not isinstance(reproductions, list):
                                rep.err(cw, "independent_reproductions must be a list or null")
                            else:
                                for j, item in enumerate(reproductions):
                                    rw = f"{cw}.independent_reproductions[{j}]"
                                    if isinstance(item, str):
                                        reproduction_lineages.add(item)
                                        add_ref(refs, rw, "lineage", item)
                                    elif isinstance(item, dict):
                                        if not check_keys(rep, rw, item,
                                                          {"lineage_id", "measurement_id", "source",
                                                           "locator", "note", "date"},
                                                          required=("lineage_id",), label="reproduction"):
                                            continue
                                        reproduction_lineages.add(item.get("lineage_id"))
                                        add_ref(refs, rw, "lineage", item.get("lineage_id"))
                                        add_ref(refs, rw, "measurement", item.get("measurement_id"))
                                        check_source_value(rep, rw, "source", item.get("source"))
                                        check_nonempty_str(rep, rw, "locator", item.get("locator"))
                                        check_date_field(rep, rw, "date", item.get("date"))
                                        check_nonempty_str(rep, rw, "note", item.get("note"))
                                    else:
                                        rep.err(rw, "must be a lineage id string or object")
                        if cmp.get("lineage_id"):
                            reproduction_lineages.add(cmp.get("lineage_id"))

                        if level == "c3_matched_ab":
                            if contrast not in {"single_variable", "bundle"}:
                                rep.err(cw, "c3_matched_ab requires contrast_kind single_variable or bundle")
                            if binary_status is None:
                                rep.err(cw, "c3_matched_ab requires binary_provenance_status")
                            if not (cmp.get("quote") or cmp.get("source")):
                                rep.err(cw, "c3_matched_ab requires source and preferably quote/locator")
                            if binary_status == "unresolved":
                                if not cmp.get("re_review_triggers") and not cmp.get("open_question_ids"):
                                    rep.err(cw, "unresolved binary provenance requires re_review_triggers or open_question_ids")
                                if derived_completeness != "partial":
                                    rep.err(cw, "unresolved binary provenance requires derived partial condition completeness")
                                unresolved_binary_with_review = True
                        elif level == "c4_independent_reproduction":
                            if len(reproduction_lineages) < 2:
                                rep.err(cw, "c4_independent_reproduction requires at least two distinct lineages")
                            if binary_status is None:
                                rep.err(cw, "c4_independent_reproduction requires binary_provenance_status")
                        quality_status = cmp.get("quality_status")
                        if quality_status is not None:
                            check_enum(rep, cw, "quality_status", quality_status, QUALITY_STATUSES)
                            if quality_status in QUALITY_STATUSES_REQUIRING_LINK and not correctness:
                                rep.err(cw, f"quality_status {quality_status!r} requires linked correctness/quality evidence")

            claims = evidence.get("claims")
            if claims is not None:
                if not isinstance(claims, list):
                    rep.err(f"{evw}.claims", "must be a list or null")
                else:
                    for i, claim in enumerate(claims):
                        cw = f"{evw}.claims[{i}]"
                        if not check_keys(rep, cw, claim, ALLOWED_CLAIM_KEYS,
                                          required=("id", "technique_id", "kind", "statement",
                                                    "evidence_level", "lineage_id", "source",
                                                    "locator", "status"),
                                          label="claim"):
                            continue
                        check_id_field(rep, cw, claim.get("id"), seen=ids_by_kind["claim"])
                        technique_id = claim.get("technique_id")
                        check_id_field(rep, cw, technique_id, required=True)
                        add_ref(refs, cw, "technique", technique_id)
                        kind = claim.get("kind")
                        level = claim.get("evidence_level")
                        check_enum(rep, cw, "kind", kind, CLAIM_KINDS, required=True)
                        check_enum(rep, cw, "evidence_level", level, EVIDENCE_LEVELS, required=True)
                        check_enum(rep, cw, "contrast_kind", claim.get("contrast_kind"), CONTRAST_KINDS)
                        add_ref(refs, cw, "lineage", claim.get("lineage_id"))
                        add_ref(refs, cw, "measurement", claim.get("measurement_ids"))
                        add_ref(refs, cw, "comparison", claim.get("comparison_id"))
                        add_ref(refs, cw, "contradiction", claim.get("contradictions"))
                        add_ref(refs, cw, "open_question", claim.get("open_question_ids"))
                        check_id_list(rep, cw, "measurement_ids", claim.get("measurement_ids"))
                        check_str_list(rep, cw, "re_review_triggers", claim.get("re_review_triggers"))
                        check_source_value(rep, cw, "source", claim.get("source"), required=True)
                        check_nonempty_str(rep, cw, "locator", claim.get("locator"), required=True)
                        check_nonempty_str(rep, cw, "quote", claim.get("quote"))
                        check_nonempty_str(rep, cw, "status", claim.get("status"), required=True)
                        check_date_field(rep, cw, "date", claim.get("date"))
                        if claim.get("provenance") is not None:
                            check_enum(rep, cw, "provenance", claim.get("provenance"), PROVENANCE)
                        if claim.get("cause") is not None and not isinstance(claim.get("cause"), dict):
                            rep.err(cw, "cause must be an object or null")
                        if claim.get("effect") is not None and not isinstance(claim.get("effect"), dict):
                            rep.err(cw, "effect must be an object or null")
                        if claim.get("scope") is not None and not isinstance(claim.get("scope"), dict):
                            rep.err(cw, "scope must be an object or null")
                        binary_status = claim.get("binary_provenance_status")
                        if binary_status is not None:
                            check_enum(rep, cw, "binary_provenance_status", binary_status,
                                       BINARY_PROVENANCE_STATUSES)
                            if binary_status == "unresolved" and not (
                                claim.get("re_review_triggers") or claim.get("open_question_ids")
                            ):
                                rep.err(cw, "unresolved binary provenance requires re_review_triggers or open_question_ids")

                        has_support = bool(claim.get("quote") or claim.get("measurement_ids")
                                           or claim.get("comparison_id"))
                        if kind in OUTCOME_CLAIM_KINDS and not has_support:
                            rep.err(cw, f"{kind} claims require quote or linked measurement/comparison ids")
                        if kind in CONFIGURATION_CLAIM_KINDS and level in {"c0_claim", "c1_configuration"}:
                            if claim.get("measurement_ids") or claim.get("comparison_id"):
                                rep.err(cw, "c0/c1 configuration or mechanism claims may not attach an outcome measurement/comparison")
                        if level == "c3_matched_ab":
                            if not claim.get("comparison_id"):
                                rep.err(cw, "c3_matched_ab claim requires comparison_id")
                            if claim.get("contrast_kind") not in {"single_variable", "bundle"}:
                                rep.err(cw, "c3_matched_ab claim requires contrast_kind single_variable or bundle")
                        if level == "c4_independent_reproduction":
                            reproductions = claim.get("independent_reproductions") or []
                            lineages = set()
                            if claim.get("lineage_id"):
                                lineages.add(claim.get("lineage_id"))
                            if isinstance(reproductions, list):
                                for item in reproductions:
                                    if isinstance(item, str):
                                        lineages.add(item)
                                        add_ref(refs, cw, "lineage", item)
                                    elif isinstance(item, dict) and item.get("lineage_id"):
                                        lineages.add(item.get("lineage_id"))
                                        add_ref(refs, cw, "lineage", item.get("lineage_id"))
                            if len(lineages) < 2:
                                rep.err(cw, "c4_independent_reproduction claim requires at least two distinct lineages")
                        elif claim.get("independent_reproductions") is not None:
                            if not isinstance(claim.get("independent_reproductions"), list):
                                rep.err(cw, "independent_reproductions must be a list or null")

            contradictions = evidence.get("contradictions")
            if contradictions is not None:
                if not isinstance(contradictions, list):
                    rep.err(f"{evw}.contradictions", "must be a list or null")
                else:
                    for i, contradiction in enumerate(contradictions):
                        cw = f"{evw}.contradictions[{i}]"
                        if not check_keys(rep, cw, contradiction, ALLOWED_CONTRADICTION_KEYS,
                                          required=("id", "statement", "status"), label="contradiction"):
                            continue
                        check_id_field(rep, cw, contradiction.get("id"), seen=ids_by_kind["contradiction"])
                        check_enum(rep, cw, "status", contradiction.get("status"),
                                   CONTRADICTION_STATUSES, required=True)
                        check_nonempty_str(rep, cw, "resolution", contradiction.get("resolution"))
                        check_nonempty_str(rep, cw, "note", contradiction.get("note"))
                        check_source_list(rep, cw, "sources", contradiction.get("sources"))
                        check_id_list(rep, cw, "lineage_ids", contradiction.get("lineage_ids"))
                        check_id_list(rep, cw, "measurement_ids", contradiction.get("measurement_ids"))
                        check_id_list(rep, cw, "comparison_ids", contradiction.get("comparison_ids"))
                        add_ref(refs, cw, "lineage", contradiction.get("lineage_ids"))
                        add_ref(refs, cw, "measurement", contradiction.get("measurement_ids"))
                        add_ref(refs, cw, "comparison", contradiction.get("comparison_ids"))
                        if not (contradiction.get("sources") or contradiction.get("lineage_ids")):
                            rep.err(cw, "contradiction requires sources or lineage_ids")

            questions = evidence.get("open_questions")
            if questions is not None:
                if not isinstance(questions, list):
                    rep.err(f"{evw}.open_questions", "must be a list or null")
                else:
                    open_questions = questions
                    for i, question in enumerate(questions):
                        qw = f"{evw}.open_questions[{i}]"
                        if not check_keys(rep, qw, question, ALLOWED_OPEN_QUESTION_KEYS,
                                          required=("id", "question", "status", "source"),
                                          label="open question"):
                            continue
                        check_id_field(rep, qw, question.get("id"), seen=ids_by_kind["open_question"])
                        check_nonempty_str(rep, qw, "type", question.get("type"))
                        check_nonempty_str(rep, qw, "owner", question.get("owner"))
                        check_nonempty_str(rep, qw, "status", question.get("status"), required=True)
                        check_source_value(rep, qw, "source", question.get("source"), required=True)
                        check_nonempty_str(rep, qw, "locator", question.get("locator"))
                        check_nonempty_str(rep, qw, "answer", question.get("answer"))
                        check_date_field(rep, qw, "answered_date", question.get("answered_date"))
                        check_nonempty_str(rep, qw, "note", question.get("note"))
                        blocks = question.get("blocks")
                        if blocks is not None:
                            if not isinstance(blocks, list) or not blocks:
                                rep.err(qw, "blocks must be a non-empty list or null")
                            else:
                                for j, block in enumerate(blocks):
                                    check_enum(rep, f"{qw}.blocks[{j}]", "block", block,
                                               OPEN_QUESTION_BLOCKS, required=True)
                        check_id_list(rep, qw, "related_measurement_ids", question.get("related_measurement_ids"))
                        check_id_list(rep, qw, "related_comparison_ids", question.get("related_comparison_ids"))
                        add_ref(refs, qw, "measurement", question.get("related_measurement_ids"))
                        add_ref(refs, qw, "comparison", question.get("related_comparison_ids"))
                        if question.get("type") == "needs_builder_input":
                            for field in ("owner", "blocks", "status", "source"):
                                if not question.get(field):
                                    rep.err(qw, f"needs_builder_input open question requires {field}")

            review = evidence.get("review")
            if review is not None:
                rw = f"{evw}.review"
                if check_keys(rep, rw, review, ALLOWED_REVIEW_KEYS, label="review"):
                    check_nonempty_str(rep, rw, "by", review.get("by"))
                    check_date_field(rep, rw, "date", review.get("date"))
                    check_nonempty_str(rep, rw, "rubric_version", review.get("rubric_version"))
                    check_nonempty_str(rep, rw, "notes", review.get("notes"))

    for i, m in enumerate(measurements):
        if not isinstance(m, dict):
            continue
        mw = f"{w} measurements[{i}]"
        mid = m.get("id")
        if "condition_completeness" in m:
            rep.err(mw, "condition_completeness is derived only and must not be stored")
        conditions = m.get("conditions")
        if isinstance(conditions, dict) and "condition_completeness" in conditions:
            rep.err(f"{mw}.conditions", "condition_completeness is derived only and must not be stored")
        if conditions is not None:
            condw = f"{mw}.conditions"
            if check_keys(rep, condw, conditions, ALLOWED_MEASUREMENT_CONDITION_KEYS, label="conditions"):
                for field in ("context_tokens", "prompt_tokens", "completion_tokens",
                              "hardware_count", "max_draft_tokens", "eval_duration_s",
                              "eval_count"):
                    check_number(rep, condw, field, conditions.get(field), positive=True,
                                 integer=field not in {"eval_duration_s"})
                for field in ("context_label", "workload", "client", "hardware_variant_id",
                              "kv_dtype", "clock_state", "note"):
                    check_nonempty_str(rep, condw, field, conditions.get(field))
                for field in ("greedy", "thinking", "warm"):
                    check_bool(rep, condw, field, conditions.get(field))
                check_number(rep, condw, "temperature", conditions.get("temperature"), minimum=0)
                check_number(rep, condw, "power_limit_pct", conditions.get("power_limit_pct"),
                             minimum=0, maximum=100)
                check_number(rep, condw, "concurrency", conditions.get("concurrency"),
                             positive=True, integer=True)
                if conditions.get("workload") is not None:
                    check_enum(rep, condw, "workload", conditions.get("workload"), SERVING_WORKLOADS)
                if conditions.get("backend") is not None:
                    check_enum(rep, condw, "backend", conditions.get("backend"), BACKENDS)
                if conditions.get("spec_decode") is not None:
                    check_enum(rep, condw, "spec_decode", conditions.get("spec_decode"), SPEC_DECODE)
                    engine_spec = (s.get("engine") or {}).get("spec_decode")
                    if engine_spec is not None and conditions.get("spec_decode") != engine_spec:
                        rep.err(condw, f"spec_decode {conditions.get('spec_decode')!r} disagrees with engine.spec_decode {engine_spec!r}")
                if conditions.get("offload_strategy") is not None:
                    check_enum(rep, condw, "offload_strategy", conditions.get("offload_strategy"),
                               OFFLOAD_STRATEGIES)
                    if isinstance(offload, dict) and offload.get("strategy") is not None \
                            and conditions.get("offload_strategy") != offload.get("strategy"):
                        rep.err(condw, "offload_strategy disagrees with requirements.offload.strategy")
                if conditions.get("concurrency") is not None and m.get("concurrency") is not None \
                        and conditions.get("concurrency") != m.get("concurrency"):
                    rep.err(condw, "conditions.concurrency disagrees with top-level concurrency")
                if conditions.get("hardware_count") is not None:
                    total = 0
                    for ref in s.get("hardware") or []:
                        hid, count = hw_ref(ref)
                        if isinstance(count, int) and not isinstance(count, bool):
                            total += count
                    if total and conditions.get("hardware_count") != total:
                        rep.err(condw, f"hardware_count {conditions.get('hardware_count')} disagrees with hardware references ({total})")
                variant_id = conditions.get("hardware_variant_id")
                if variant_id is not None:
                    found = False
                    for ref in s.get("hardware") or []:
                        hid, _ = hw_ref(ref)
                        variants = ((hardware.get(hid) or {}).get("device") or {}).get("variants") or []
                        if any(isinstance(var, dict) and var.get("id") == variant_id for var in variants):
                            found = True
                            break
                    if not found:
                        rep.err(condw, f"hardware_variant_id {variant_id!r} is not a variant of this setup's hardware")

        mev = m.get("evidence")
        if mev is None:
            continue
        ew = f"{mw}.evidence"
        if not check_keys(rep, ew, mev, ALLOWED_MEASUREMENT_EVIDENCE_KEYS, label="measurement evidence"):
            continue
        if "condition_completeness" in mev:
            rep.err(ew, "condition_completeness is derived only and must not be stored")
        level = mev.get("level")
        check_enum(rep, ew, "level", level, EVIDENCE_LEVELS, required=True)
        check_enum(rep, ew, "contrast_kind", mev.get("contrast_kind"), CONTRAST_KINDS)
        check_enum(rep, ew, "method_grade", mev.get("method_grade"), METHOD_GRADES)
        check_enum(rep, ew, "quality_status", mev.get("quality_status"), QUALITY_STATUSES)
        check_enum(rep, ew, "binary_provenance_status", mev.get("binary_provenance_status"),
                   BINARY_PROVENANCE_STATUSES)
        check_nonempty_str(rep, ew, "contrast_id", mev.get("contrast_id"))
        check_nonempty_str(rep, ew, "method_note", mev.get("method_note"))
        check_nonempty_str(rep, ew, "quote", mev.get("quote"))
        check_nonempty_str(rep, ew, "note", mev.get("note"))
        check_bool(rep, ew, "dossier_cited", mev.get("dossier_cited"))
        check_number(rep, ew, "independent_reproductions", mev.get("independent_reproductions"),
                     integer=True, minimum=0)
        check_str_list(rep, ew, "re_review_triggers", mev.get("re_review_triggers"))
        add_ref(refs, ew, "lineage", mev.get("lineage_id"))
        add_ref(refs, ew, "comparison", mev.get("contrast_id"))
        add_ref(refs, ew, "open_question", mev.get("open_question_ids"))
        corroborations = mev.get("corroborations")
        if corroborations is not None:
            if not isinstance(corroborations, list):
                rep.err(ew, "corroborations must be a list or null")
            else:
                for j, item in enumerate(corroborations):
                    check_generic_source_object(rep, f"{ew}.corroborations[{j}]", item, require_durable=False)

        method_grade = mev.get("method_grade")
        if method_grade == "benchmark_harness" and not m.get("method"):
            rep.err(ew, "method_grade benchmark_harness requires measurement.method")
        if method_grade == "wall_clock_division":
            if not mev.get("method_note"):
                rep.err(ew, "method_grade wall_clock_division requires evidence.method_note")
            if not (m.get("note") or mev.get("note")):
                rep.err(ew, "method_grade wall_clock_division requires a preserved measurement/evidence note")

        quality_status = mev.get("quality_status")
        if quality_status in QUALITY_STATUSES_REQUIRING_LINK:
            metric = m.get("metric")
            linked = (
                (metric in {"quality_index", "bench_code", "bench_toolcall", "bench_mmlu",
                            "bench_gsm8k", "bench_humaneval", "bench_other"})
                or (mid and mid in quality_linked_ids)
                or bool(correctness and correctness.get("checks"))
            )
            if not linked:
                rep.err(ew, f"quality_status {quality_status!r} requires linked same-scope correctness/quality evidence")

        contrast_id = mev.get("contrast_id")
        comparison = comparisons.get(contrast_id) if isinstance(contrast_id, str) else None
        if level == "c2_observation":
            if not (m.get("source") or s.get("provenance_tier") == "box"):
                rep.err(ew, "c2_observation requires a measurement source or box provenance")
            if is_v2 and not method_grade:
                rep.err(ew, "c2_observation requires method_grade")
        if level == "c3_matched_ab":
            if not contrast_id:
                rep.err(ew, "c3_matched_ab requires contrast_id linking a comparison")
            elif comparison is None:
                pass  # resolution error is reported once by resolve_refs
            else:
                if comparison.get("evidence_level") != "c3_matched_ab":
                    rep.err(ew, "linked comparison must also be c3_matched_ab")
                if mev.get("contrast_kind") and comparison.get("contrast_kind") \
                        and mev.get("contrast_kind") != comparison.get("contrast_kind"):
                    rep.err(ew, "contrast_kind disagrees with linked comparison")
                if comparison.get("binary_provenance_status") == "unresolved" and not (
                    comparison.get("re_review_triggers") or comparison.get("open_question_ids")
                ):
                    rep.err(ew, "unresolved binary provenance requires re_review_triggers or open_question_ids")
        if level == "c4_independent_reproduction":
            if not contrast_id or comparison is None:
                rep.err(ew, "c4_independent_reproduction requires a linked comparison with distinct lineages")
            elif comparison.get("evidence_level") != "c4_independent_reproduction":
                rep.err(ew, "linked comparison must also be c4_independent_reproduction")

    resolve_refs(rep, refs, ids_by_kind, labels)

    if s.get("status") == "untested" and measurements:
        rep.err(w, "status 'untested' must not contain measurements")
    if s.get("status") == "broken" and not (s.get("known_failures") or s.get("caveats")):
        rep.warn(w, "status 'broken' should have known_failures[] or an explicit caveat")

    if is_v2:
        has_c3_plus = False
        for m in measurements:
            if isinstance(m, dict) and (m.get("evidence") or {}).get("level") in CAUSAL_LEVELS_HIGH:
                has_c3_plus = True
        for cmp in comparisons.values():
            if cmp.get("evidence_level") in CAUSAL_LEVELS_HIGH:
                has_c3_plus = True
        for claim in (evidence or {}).get("claims") or [] if isinstance(evidence, dict) else []:
            if isinstance(claim, dict) and claim.get("evidence_level") in CAUSAL_LEVELS_HIGH:
                has_c3_plus = True

        if e.get("requires_fork") and not e.get("fork_revision"):
            rep.err(w, "migrated fork-required lane requires engine.fork_revision")
        best = s.get("provenance_tier")
        if s.get("status") == "measured" or best == "box":
            if not runtime_pin:
                rep.err(w, "new box/measured schema_version-2 record requires an exact runtime/artifact pin")
            elif not exact_runtime_pin:
                rep.warn(w, "box/measured schema_version-2 record has a non-exact runtime/artifact pin")
        elif has_c3_plus:
            if not runtime_pin and not unresolved_binary_with_review:
                rep.err(w, "C3+ causal claim requires a load-bearing runtime/artifact pin or explicit unresolved binary provenance with re-review")
        elif not runtime_pin and best in {"forum", "vendor"}:
            rep.warn(w, "schema_version-2 forum/vendor record has no runtime/artifact pin; record an open question when the source does not state one")

        size_gb = (s.get("variation") or {}).get("size_gb")
        total_memory = 0
        for ref in s.get("hardware") or []:
            hid, count = hw_ref(ref)
            h = hardware.get(hid) or {}
            mem = h.get("memory_usable_gb") or h.get("memory_gb")
            if isinstance(mem, (int, float)) and isinstance(count, int) and not isinstance(count, bool):
                total_memory += mem * count
        if isinstance(size_gb, (int, float)) and not isinstance(size_gb, bool) and total_memory \
                and size_gb > total_memory:
            fit_question = any(
                isinstance(q, dict) and "fit_claim" in (q.get("blocks") or [])
                for q in open_questions
            )
            if not isinstance(offload, dict) and not fit_question:
                rep.err(w, "artifact exceeds recorded hardware memory; record source-backed offload "
                           "or an explicit fit_claim open question, never an inferred offload")
    elif legacy_pin_warnings:
        best = s.get("provenance_tier")
        if isinstance(e, dict) and e.get("requires_fork") and not e.get("fork_revision"):
            rep.warn(w, "unmigrated legacy fork-required lane has no engine.fork_revision")
        if not runtime_pin and (best in {"forum", "vendor", "box"} or s.get("status") == "measured"):
            rep.warn(w, "unmigrated legacy record has no runtime/artifact pin; warning only until migrated")


def main(data_dir: str | None = None, strict: bool | None = None,
         legacy_pin_warnings: bool | None = None) -> int:
    global DATA
    if data_dir is not None:
        DATA = os.path.abspath(data_dir)
    if strict is None:
        strict = "--strict" in sys.argv
    if legacy_pin_warnings is None:
        legacy_pin_warnings = "--legacy-pin-warnings" in sys.argv

    models = load_dir("models")
    hardware = load_dir("hardware")
    engines = load_dir("engines")
    setups = load_dir("setups")
    techniques = load_dir("techniques")
    publishers = load("publishers.json")
    pub_ids = set(publishers.get("publishers", {}))

    rep = Report()

    for mid, m in models.items():
        w = f"models/{mid}"
        if m.get("id", mid) != mid:
            rep.err(w, f"filename {mid} != id {m.get('id')!r}")
        check_id(rep, w, mid)
        for f in ("name", "family", "publisher"):
            if f not in m:
                rep.err(w, f"missing {f}")
        if m.get("publisher") not in pub_ids:
            rep.err(w, f"unknown publisher {m.get('publisher')!r}")
        check_url(rep, w, "url", m.get("url"))
        arch = m.get("architecture", {})
        # params_total_b may sit at top level or inside architecture; accept either.
        params = m.get("params_total_b", arch.get("params_total_b"))
        if not isinstance(params, (int, float)):
            rep.err(w, f"missing or non-numeric params_total_b (top level or architecture), got {params!r}")
        if arch.get("kind") not in ("dense", "moe", None):
            rep.err(w, f"architecture.kind {arch.get('kind')!r} not dense|moe")
        if arch.get("kind") == "moe" and not arch.get("params_active_b"):
            rep.warn(w, "MoE model without params_active_b")
        baseline = m.get("practical_baseline")
        if not isinstance(baseline, dict):
            rep.err(w, "practical_baseline must be an object")
        else:
            bstatus = baseline.get("status")
            if bstatus not in PRACTICAL_STATUS:
                rep.err(w, f"practical_baseline.status {bstatus!r} not in {sorted(PRACTICAL_STATUS)}")
            reviewed = baseline.get("reviewed")
            if not isinstance(reviewed, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", reviewed):
                rep.err(w, "practical_baseline.reviewed must be YYYY-MM-DD")
            target = baseline.get("setup")
            if bstatus == "not_verified":
                if target is not None:
                    rep.err(w, "not_verified practical baseline must set setup to null")
                if not isinstance(baseline.get("reason"), str) or not baseline["reason"].strip():
                    rep.err(w, "not_verified practical baseline requires a reason")
            elif bstatus == "selected":
                if not isinstance(baseline.get("rationale"), str) or not baseline["rationale"].strip():
                    rep.err(w, "selected practical baseline requires a rationale")
                setup = setups.get(target)
                if setup is None:
                    rep.err(w, f"practical_baseline.setup {target!r} is not a setup id")
                else:
                    if setup.get("model") != mid:
                        rep.err(w, f"practical baseline setup belongs to {setup.get('model')!r}, not {mid!r}")
                    quant = setup.get("variation", {}).get("quant")
                    if quant not in PRACTICAL_QUANTS:
                        rep.err(w, f"practical baseline quant {quant!r} is below the stable 4-bit-or-better policy")
                    if setup.get("status") not in {"measured", "reported"}:
                        rep.err(w, "practical baseline setup must be measured or reported")
                    run = setup.get("run", {})
                    if not run.get("command") and len(run.get("steps") or []) < 2:
                        rep.err(w, "practical baseline setup needs a command or at least two run steps")

    for hid, h in hardware.items():
        w = f"hardware/{hid}"
        if h.get("id", hid) != hid:
            rep.err(w, f"filename {hid} != id {h.get('id')!r}")
        check_id(rep, w, hid)
        for f in ("name", "memory_gb", "bandwidth_gbs"):
            if f not in h:
                rep.err(w, f"missing {f}")
        if not isinstance(h.get("memory_gb"), (int, float)):
            rep.err(w, f"memory_gb must be a number, got {h.get('memory_gb')!r}")
        if "device" in h:
            check_device(rep, w, h["device"], hw=h)
        else:
            rep.warn(w, "no device spec — readers cannot see the bandwidth/compute behind "
                        "this hardware's numbers (see data/device-schema.json)")

    for eid, e in engines.items():
        w = f"engines/{eid}"
        if e.get("id", eid) != eid:
            rep.err(w, f"filename {eid} != id {e.get('id')!r}")
        check_id(rep, w, eid)
        for f in ("name", "kind", "url"):
            if f not in e:
                rep.err(w, f"missing {f}")
        # A fork-category engine has no single canonical upstream, so a null url
        # is honest there; everywhere else it means a missing link.
        if e.get("kind") == "fork" and e.get("url") is None:
            pass
        else:
            check_url(rep, w, "url", e.get("url"))
        check_engine_install(rep, w, e.get("install"))

    for tid, technique in techniques.items():
        if not isinstance(technique, dict):
            rep.err(f"techniques/{tid}", f"technique packet must be an object, got {type(technique).__name__}")
            continue
        check_technique(rep, tid, technique)

    seen_titles: dict[str, str] = {}
    for sid, s in setups.items():
        w = f"setups/{sid}"
        if s.get("id", sid) != sid:
            rep.err(w, f"filename {sid} != id {s.get('id')!r}")
        check_id(rep, w, sid)

        for f in REQUIRED_SETUP:
            if f not in s:
                rep.err(w, f"missing required field {f!r}")

        if s.get("model") not in models:
            rep.err(w, f"unknown model id {s.get('model')!r}")

        if s.get("status") not in STATUS:
            rep.err(w, f"status {s.get('status')!r} not in {sorted(STATUS)}")

        # A near-duplicate setup is almost always a copy/paste mistake. The
        # hardware reference includes the unit count, so 1x and 2x of a class
        # are different identity.
        hwkey = sorted((hw_ref(x)[0], hw_ref(x)[1]) for x in (s.get("hardware") or []))
        key = json.dumps(
            [s.get("model"), s.get("variation", {}).get("checkpoint"),
             s.get("engine", {}).get("id"), s.get("engine", {}).get("config"),
             hwkey],
            sort_keys=True,
        )
        if key in seen_titles:
            rep.err(w, f"duplicate of setups/{seen_titles[key]} (same model+checkpoint+engine+config+hardware)")
        seen_titles[key] = sid

        v = s.get("variation", {})
        for f in REQUIRED_VARIATION:
            if f not in v or v[f] is None:
                rep.err(w, f"variation.{f} missing or null")
        if v.get("quant", "").lower() not in QUANTS:
            rep.err(w, f"variation.quant {v.get('quant')!r} not in enum")
        if v.get("format") not in FORMATS:
            rep.err(w, f"variation.format {v.get('format')!r} not in enum")
        if v.get("publisher") not in pub_ids:
            rep.err(w, f"variation.publisher {v.get('publisher')!r} unknown")
        if s.get("builder") and s["builder"] not in pub_ids:
            rep.err(w, f"builder {s.get('builder')!r} unknown publisher")
        check_url(rep, w, "variation.url", v.get("url"))
        if not isinstance(v.get("size_gb"), (int, float)):
            rep.err(w, f"variation.size_gb must be a number or null, got {v.get('size_gb')!r}")

        e = s.get("engine", {})
        for f in REQUIRED_ENGINE:
            if f not in e or e[f] is None:
                rep.err(w, f"engine.{f} missing or null")
        if e.get("id") not in engines:
            rep.err(w, f"engine.id {e.get('id')!r} unknown")
        if e.get("spec_decode", "none") not in SPEC_DECODE:
            rep.err(w, f"engine.spec_decode {e.get('spec_decode')!r} not in enum")

        hw = s.get("hardware")
        if not isinstance(hw, list) or not hw:
            rep.err(w, "hardware must be a non-empty list")
        else:
            seen_hw = set()
            for i, ref in enumerate(hw):
                rw = f"{w} hardware[{i}]"
                rid, cnt = hw_ref(ref)
                if not isinstance(rid, str) or not rid:
                    rep.err(rw, f"hardware reference must be an id string or {{id,count}}, got {ref!r}")
                    continue
                if rid not in hardware:
                    rep.err(rw, f"unknown hardware id {rid!r}")
                if isinstance(cnt, bool) or not isinstance(cnt, int) or cnt < 1:
                    rep.err(rw, f"count must be a positive integer, got {cnt!r}")
                if rid in seen_hw:
                    rep.err(rw, f"duplicate hardware id {rid!r} — use one entry with a count")
                seen_hw.add(rid)
        # Optional per-setup device override: a measurement-specific hardware
        # delta (e.g. an overclocked card). Same shape as the hardware block's
        # device spec, without the record cross-checks.
        if s.get("device") is not None:
            check_device(rep, f"{w} device", s["device"])

        req = s.get("requirements", {})
        for f in ("memory_gb", "disk_gb"):
            val = req.get(f)
            if val is not None and not isinstance(val, (int, float)):
                rep.err(w, f"requirements.{f} must be a number or null, got {val!r}")
        if req.get("memory_gb") is None:
            rep.warn(w, "requirements.memory_gb is null — cannot answer 'will it fit'")

        run = s.get("run", {})
        for f in REQUIRED_RUN:
            if f not in run or run[f] is None:
                rep.err(w, f"run.{f} missing or null")
        check_url(rep, w, "run.repo", run.get("repo"))
        rc = run.get("repo_commit")
        if rc is not None and (not isinstance(rc, str) or not rc.strip()):
            rep.err(w, "run.repo_commit must be a non-empty string (commit sha or tag)")
        if not run.get("command") and not run.get("steps"):
            rep.err(w, "run needs a command or steps — this is the 'how to run' directory")
        steps = run.get("steps")
        if steps is not None:
            if not isinstance(steps, list):
                rep.err(w, "run.steps must be a list")
            else:
                for i, step in enumerate(steps):
                    sw = f"{w} run.steps[{i}]"
                    if not isinstance(step, dict):
                        rep.err(sw, "must be an object with exactly 'kind' and 'text'")
                        continue
                    if set(step) != RUN_STEP_FIELDS:
                        rep.err(sw, "must contain exactly 'kind' and 'text'")
                    if step.get("kind") not in RUN_STEP_KINDS:
                        rep.err(sw, f"kind {step.get('kind')!r} not in {sorted(RUN_STEP_KINDS)}")
                    if not isinstance(step.get("text"), str) or not step["text"].strip():
                        rep.err(sw, "text must be a non-empty string")

        caps = s.get("capabilities", {})
        if caps.get("long_context") is not None and not isinstance(caps["long_context"], int):
            rep.err(w, "capabilities.long_context must be an int token count or null")

        best = None
        for i, m in enumerate(s.get("measurements", [])):
            mw = f"{w} measurements[{i}]"
            if m.get("metric") not in METRICS:
                rep.err(mw, f"metric {m.get('metric')!r} not in enum")
            if not isinstance(m.get("value"), (int, float)):
                rep.err(mw, f"value must be a number, got {m.get('value')!r}")
            concurrency = m.get("concurrency")
            if concurrency is not None and (
                isinstance(concurrency, bool)
                or not isinstance(concurrency, int)
                or concurrency <= 0
            ):
                rep.err(mw, f"concurrency must be a positive integer, got {concurrency!r}")
            if m.get("metric") == "decode_agg" and (
                not isinstance(concurrency, int)
                or isinstance(concurrency, bool)
                or concurrency <= 1
            ):
                rep.err(mw, "decode_agg requires concurrency > 1; use decode_per_stream for single-stream or cross-prompt summaries")
            if m.get("stat") is not None and m["stat"] not in STATS:
                rep.err(mw, f"stat {m.get('stat')!r} not in {sorted(STATS)}")
            if m.get("unit") not in UNITS:
                rep.err(mw, f"unit {m.get('unit')!r} not in enum")
            prov = m.get("provenance")
            if prov not in PROVENANCE:
                rep.err(mw, f"provenance {prov!r} not in {sorted(PROVENANCE)}")
                continue
            best = prov if PROV_RANK[prov] > PROV_RANK[best] else best
            if prov == "box":
                for f in ("date", "n", "method"):
                    if not m.get(f):
                        rep.err(mw, f"box measurement requires {f}")
            else:
                if not m.get("source"):
                    rep.err(mw, f"{prov} measurement requires a source URL")
            if m.get("source"):
                check_url(rep, mw, "source", m["source"])
            if m.get("date") and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(m["date"])):
                rep.err(mw, f"date {m['date']!r} must be YYYY-MM-DD")

        declared = s.get("provenance_tier")
        if declared and PROV_RANK.get(declared, 0) > PROV_RANK[best]:
            rep.err(w, f"provenance_tier {declared!r} overstates the best measurement tier {best!r}")
        if declared and declared != best and best is not None:
            rep.warn(w, f"provenance_tier {declared!r} != best measurement tier {best!r}")
        if s.get("measurements") and declared != best:
            rep.err(w, f"provenance_tier must equal best measurement tier ({best!r})")
        if not s.get("measurements") and declared not in (None, "vendor"):
            rep.err(w, "no measurements but provenance_tier claims evidence")

        srcs = s.get("sources", [])
        if not isinstance(srcs, list) or not srcs:
            rep.err(w, "sources must be a non-empty list")
        for i, src in enumerate(srcs):
            sw = f"{w} sources[{i}]"
            check_url(rep, sw, "url", src.get("url"))
            if src.get("mirror_url") is not None:
                check_url(rep, sw, "mirror_url", src.get("mirror_url"))
            if isinstance(src.get("url"), str) and "reddit.com" in src["url"] \
                    and not src.get("mirror_url"):
                rep.err(sw, "reddit.com source requires mirror_url (AGENTS law 10)")
            if src.get("kind") not in SOURCE_KINDS:
                rep.err(sw, f"kind {src.get('kind')!r} not in enum")

        if not s.get("updated"):
            rep.warn(w, "no updated date")

        check_setup_v2(rep, sid, s, techniques, hardware, pub_ids,
                       legacy_pin_warnings=legacy_pin_warnings)

    for m in models.values():
        used = any(s.get("model") == m["id"] for s in setups.values())
        if not used:
            rep.warn("models", f"{m['id']} has no setups — it will not appear in the directory")

    for line in rep.warnings:
        print(f"WARN  {line}")
    for line in rep.errors:
        print(f"ERROR {line}")

    print(
        f"\n{len(setups)} setups · {len(models)} models · {len(hardware)} hardware · "
        f"{len(engines)} engines · {len(pub_ids)} publishers · {len(techniques)} techniques"
    )
    print(f"{len(rep.errors)} errors, {len(rep.warnings)} warnings")

    if rep.errors or (strict and rep.warnings):
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
