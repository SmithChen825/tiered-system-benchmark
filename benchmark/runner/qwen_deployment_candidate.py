from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:
    from .common import REPOSITORY_ROOT
except ImportError:  # Supports direct script execution.
    from common import REPOSITORY_ROOT  # type: ignore


SHA256_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")
COMMIT_PATTERN = re.compile(r"^[a-f0-9]{40}$")
EXPECTED_ARGUMENTS = [
    "--model",
    "/repository",
    "--served-model-name",
    "Qwen/Qwen2.5-Coder-7B-Instruct",
    "--host",
    "0.0.0.0",
    "--port",
    "8000",
    "--max-model-len",
    "32768",
    "--tensor-parallel-size",
    "1",
    "--data-parallel-size",
    "1",
    "--max-num-seqs",
    "1",
    "--gpu-memory-utilization",
    "0.90",
    "--enable-auto-tool-choice",
    "--tool-call-parser",
    "hermes",
]
EXPECTED_GATES = {
    "account_and_capacity",
    "immutable_container_pull",
    "exact_model_revision",
    "memory_and_context_smoke",
    "openai_tool_call_smoke",
    "cost_and_endpoint_evidence",
}
EXPECTED_SOURCES = {
    "https://huggingface.co/api/models/Qwen/Qwen2.5-Coder-7B-Instruct",
    "https://huggingface.co/docs/inference-endpoints/faq",
    "https://huggingface.co/docs/inference-endpoints/pricing",
    "https://huggingface.co/docs/inference-endpoints/guides/configuration",
    "https://huggingface.co/docs/inference-endpoints/en/guides/update_endpoint",
    "https://huggingface.co/docs/inference-endpoints/en/guides/foundations",
    "https://huggingface.co/docs/inference-endpoints/guides/autoscaling",
    "https://huggingface.co/docs/inference-endpoints/engines/custom_container",
    "https://huggingface.co/docs/inference-endpoints/engines/vllm",
    "https://github.com/vllm-project/vllm/releases/tag/v0.26.0",
    "https://docs.vllm.ai/en/v0.26.0/deployment/docker/",
    "https://docs.vllm.ai/en/v0.26.0/features/tool_calling/",
    "https://docs.vllm.ai/en/v0.26.0/cli/serve/",
}


def candidate_configuration_sha256(value: dict[str, Any]) -> str:
    payload = {
        key: item
        for key, item in value.items()
        if key != "candidate_configuration_sha256"
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_qwen_deployment_candidate(value: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    required_top = {
        "schema_version",
        "status",
        "candidate_id",
        "decided_on",
        "timezone",
        "review",
        "amendment",
        "authorization_state",
        "deployment",
        "decision_basis",
        "live_verification_gates",
        "promotion_rule",
        "official_sources",
        "candidate_configuration_sha256",
    }
    if set(value) != required_top:
        issues.append(f"top-level fields must equal {sorted(required_top)}")
        return issues
    if value["schema_version"] != "1.3.0":
        issues.append("schema_version must be 1.3.0")
    if value["status"] != "CANDIDATE":
        issues.append("status must remain CANDIDATE until every live gate passes")
    if value["candidate_id"] != "qwen-deployment-candidate-20260811-r4":
        issues.append("candidate_id does not match the reviewed candidate")
    if value["decided_on"] != "2026-08-11":
        issues.append("decided_on does not match the reviewed decision date")
    if value["timezone"] != "Australia/Sydney":
        issues.append("timezone must be Australia/Sydney")

    review = value["review"]
    expected_review = {
        "status": "AMENDED_AFTER_FAILED_LIVE_GATE",
        "recorded_at": "2026-08-11T18:05:48.3348072+10:00",
        "recorded_at_utc": "2026-08-11T08:05:48.3348072Z",
        "supersedes": "qwen-deployment-candidate-20260811-r3",
        "findings": [
            "The r2 Endpoint reached running and returned HTTP 200 from /health on gpu/nvidia-l4/x1.",
            "The first OpenAI-compatible text request returned HTTP 404 because vLLM served the default model name /repository while the frozen wrapper requested Qwen/Qwen2.5-Coder-7B-Instruct.",
            "vLLM 0.26.0 documents that --served-model-name fixes the API-visible model name independently of the local --model path.",
            "The r3 change adds only the exact served model name; model revision, image digest, hardware, region, context cap, parser, and scaling remain unchanged.",
            "The r3 web-console update entered Initializing and then Failed without producing any new container log after 2026-08-11T07:33:24.592Z.",
            "The r3 Endpoint was positively forced to Scaled to Zero; the account-visible snapshot showed four compute minutes and USD 0.05 while the conservative ledger estimate was USD 0.12.",
            "Hugging Face documents updates for running Endpoints and directs operators to create a new Endpoint after a failed state, so r4 requires a new Endpoint name and prohibits another in-place retry.",
        ],
    }
    if review != expected_review:
        issues.append("review does not match the recorded independent review")

    expected_authorization = {
        "endpoint_created": True,
        "api_credentials_used": True,
        "provider_cost_incurred": True,
        "authorizes_pilot_execution": False,
    }
    if value["authorization_state"] != expected_authorization:
        issues.append("authorization_state must record a credential-free candidate only")

    deployment = value["deployment"]
    if not isinstance(deployment, dict):
        return issues + ["deployment must be an object"]
    if deployment.get("provider") != "hugging_face_inference_endpoints_dedicated":
        issues.append("deployment.provider must be Hugging Face Dedicated Endpoints")
    if deployment.get("cloud") != "aws" or deployment.get("region") != "us-east-1":
        issues.append("deployment cloud/region must be aws/us-east-1")
    expected_endpoint_strategy = {
        "required_name": "tsb-api-pilot-2026-r4",
        "create_new_endpoint": True,
        "reuse_or_update_endpoint_names": ["tsb-api-pilot-2026"],
        "reuse_or_update_prohibited": True,
    }
    if deployment.get("endpoint_strategy") != expected_endpoint_strategy:
        issues.append("deployment.endpoint_strategy must require the reviewed new r4 Endpoint")

    model = deployment.get("model")
    expected_model = {
        "repository": "Qwen/Qwen2.5-Coder-7B-Instruct",
        "repository_commit": "c03e6d358207e414f1eca0bb1891e29f1db0e242",
        "weight_dtype": "bfloat16",
        "parameter_count": 7615616512,
    }
    if model != expected_model:
        issues.append("deployment.model does not match the reviewed immutable model")
    elif COMMIT_PATTERN.fullmatch(model["repository_commit"]) is None:
        issues.append("deployment.model.repository_commit must be a 40-character SHA")

    expected_hardware = {
        "accelerator": "gpu",
        "instance_type": "nvidia-l4",
        "instance_size": "x1",
        "accelerator_count": 1,
        "accelerator_memory_gb": 24,
        "public_listed_hourly_rate_usd": 0.8,
        "price_observed_on": "2026-08-09",
    }
    if deployment.get("hardware") != expected_hardware:
        issues.append("deployment.hardware must be one NVIDIA L4 with 24 GB")

    runtime = deployment.get("runtime")
    if not isinstance(runtime, dict):
        issues.append("deployment.runtime must be an object")
    else:
        expected_runtime_scalars = {
            "deployment_mode": "custom_container",
            "container_registry": "docker.io",
            "container_repository": "vllm/vllm-openai",
            "container_tag": "v0.26.0",
            "container_platform": "linux/amd64",
            "container_image_uri": "docker.io/vllm/vllm-openai@sha256:770fe65b2c73ee74a5c42165cf3433de4048cc2cd9c57a937ca4e35aba5aa87b",
            "vllm_version": "0.26.0",
            "container_port": 8000,
            "health_route": "/health",
            "model_mount_path": "/repository",
            "served_model_name": "Qwen/Qwen2.5-Coder-7B-Instruct",
            "tool_call_parser": "hermes",
            "automatic_tool_choice": True,
            "max_model_length_tokens": 32768,
            "tensor_parallel_size": 1,
            "data_parallel_size": 1,
            "max_num_sequences": 1,
            "gpu_memory_utilization": 0.9,
        }
        for key, expected in expected_runtime_scalars.items():
            if runtime.get(key) != expected:
                issues.append(f"deployment.runtime.{key} must equal {expected!r}")
        if runtime.get("verified_image_entrypoint") != ["vllm", "serve"]:
            issues.append("deployment.runtime.verified_image_entrypoint must be vllm serve")
        if runtime.get("container_arguments") != EXPECTED_ARGUMENTS:
            issues.append("deployment.runtime.container_arguments do not match the reviewed order")
        for field in ("container_index_digest", "container_platform_digest"):
            digest = runtime.get(field)
            if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
                issues.append(f"deployment.runtime.{field} must be a sha256 digest")
        if runtime.get("container_index_digest") != (
            "sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52"
        ):
            issues.append("container_index_digest does not match v0.26.0")
        if runtime.get("container_platform_digest") != (
            "sha256:770fe65b2c73ee74a5c42165cf3433de4048cc2cd9c57a937ca4e35aba5aa87b"
        ):
            issues.append("container_platform_digest does not match linux/amd64 v0.26.0")

    expected_scaling = {
        "minimum_replicas": 0,
        "maximum_replicas": 1,
        "scale_to_zero_timeout_minutes": 15,
        "prewarm_before_timed_run": True,
        "timed_run_must_start_after_ready": True,
    }
    if deployment.get("scaling") != expected_scaling:
        issues.append("deployment.scaling does not match the reviewed cost-control rule")
    expected_network = {
        "endpoint_type": "authenticated",
        "tls_required": True,
        "openai_compatible_route": "/v1/chat/completions",
    }
    if deployment.get("network") != expected_network:
        issues.append("deployment.network does not match the authenticated API boundary")

    basis = value["decision_basis"]
    if not isinstance(basis, list) or len(basis) < 5 or not all(
        isinstance(item, str) and item.strip() for item in basis
    ):
        issues.append("decision_basis must contain at least five non-empty statements")

    gates = value["live_verification_gates"]
    if not isinstance(gates, list):
        issues.append("live_verification_gates must be a list")
    else:
        gate_map = {
            item.get("gate"): item for item in gates if isinstance(item, dict)
        }
        if set(gate_map) != EXPECTED_GATES or len(gates) != len(EXPECTED_GATES):
            issues.append("live_verification_gates must contain the six reviewed gates")
        for gate_name, gate in gate_map.items():
            if gate.get("status") != "PENDING":
                issues.append(f"live gate {gate_name} must remain PENDING in the candidate")
            if gate.get("requires_credentials_or_billing") is not True:
                issues.append(f"live gate {gate_name} must be credential/billing-gated")
            acceptance = gate.get("acceptance")
            if not isinstance(acceptance, str) or not acceptance.strip():
                issues.append(f"live gate {gate_name} must define acceptance evidence")

    expected_promotion = {
        "target_status": "FROZEN",
        "all_live_verification_gates_must_pass": True,
        "failed_or_unavailable_candidate_requires_amendment": True,
        "silent_fallback_prohibited": True,
        "retry_requires_new_paid_authorization": True,
    }
    if value["promotion_rule"] != expected_promotion:
        issues.append("promotion_rule must remain fail closed")

    amendment = value["amendment"]
    expected_evidence = {
        "artifacts/paid-pilot-20260811/qwen-live-smoke-001.json":
            "93a6d8b9a5f57ecde114eea54ee1d472ec7a8b44c722434896f68d7fa1317342",
        "artifacts/paid-pilot-20260811/qwen-live-smoke-001-provider-log.png":
            "9ff9020ebd56871741299cd9be3fc329ac0c044be173daf052ea3f4f9646847c",
        "artifacts/paid-pilot-20260811/qwen-endpoint-scale-to-zero-001.json":
            "719873dffdf761784abe2bd496f8ec1b62db4a57a6a14f94ac67991b3221d017",
        "artifacts/paid-pilot-20260811-r3/tsb-api-pilot-2026-full-log-after-r3-failure.txt":
            "01bd8e2010d0f8d962a7fa58500c245ffffbd86c5afc4b91f16d956534c5b0ac",
        "artifacts/paid-pilot-20260811-r3/qwen-endpoint-scale-to-zero-r3-001.png":
            "32f2f52f0f80c934d892d333851eab2c55018ca2f6d3dd5233bdcad8995b928f",
        "artifacts/paid-pilot-20260811-r3/qwen-overview-post-r3-failure-001.png":
            "7cf7dc207321fa09f387ae68fd8642fbd29a8bd2e98b8ec95517a325cbaffa73",
        "artifacts/paid-pilot-20260811-r3/paid-stage-ledger.json":
            "b4331e85df0c256732b405557af8159f741f16e68f1ef922121493e2b2dab4a4",
    }
    if not isinstance(amendment, dict):
        issues.append("amendment must be an object")
    else:
        if amendment.get("amendment_id") != "QWEN-AMEND-20260811-02":
            issues.append("amendment_id does not match the reviewed amendment")
        if amendment.get("status") != "RECORDED_RETRY_NOT_AUTHORIZED":
            issues.append("amendment must not authorize a paid retry")
        if amendment.get("retry_requires_new_user_authorization") is not True:
            issues.append("amendment must require new user authorization")
        if amendment.get("silent_retry_or_in_place_unmetered_update_prohibited") is not True:
            issues.append("amendment must prohibit silent or unmetered updates")
        evidence = amendment.get("failure_evidence")
        evidence_map = {
            item.get("path"): item.get("sha256")
            for item in evidence or []
            if isinstance(item, dict)
        }
        if evidence_map != expected_evidence or len(evidence or []) != len(expected_evidence):
            issues.append("amendment failure evidence bindings do not match")
        else:
            for relative, digest in expected_evidence.items():
                path = REPOSITORY_ROOT / relative
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    issues.append(f"amendment evidence hash mismatch: {relative}")
    sources = value["official_sources"]
    if not isinstance(sources, list) or set(sources) != EXPECTED_SOURCES:
        issues.append("official_sources must contain the reviewed primary references")

    expected_hash = candidate_configuration_sha256(value)
    if value["candidate_configuration_sha256"] != expected_hash:
        issues.append("candidate_configuration_sha256 does not match canonical content")
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the Qwen deployment candidate")
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=REPOSITORY_ROOT / "benchmark" / "config" / "qwen_deployment.candidate.json",
    )
    arguments = parser.parse_args()
    value = json.loads(arguments.path.read_text(encoding="utf-8"))
    issues = validate_qwen_deployment_candidate(value)
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}")
        raise SystemExit(1)
    print(f"valid={arguments.path.resolve()}")
    print(f"candidate_configuration_sha256={candidate_configuration_sha256(value)}")


if __name__ == "__main__":
    main()
